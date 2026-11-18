using AbaqusTools.WinUI.Services;

internal static class NewJobDraftResetChecks
{
    public static async Task RunAsync(string directory)
    {
        Directory.CreateDirectory(directory);
        var checks = 0;
        void Check(bool condition, string label)
        {
            if (!condition) throw new Exception(label);
            checks++;
        }
        WorkbenchSessionState Draft() => new()
        {
            LastRoute = "result-browser", ExplorerVisible = false, Window = new() { X = 42, Width = 1400 },
            Pages = new()
            {
                ["new-job"] = new()
                {
                    ["JobNameTextBox"] = "example", ["InputPathTextBox"] = @"G:\inputs\case.inp",
                    ["OldjobPathTextBox"] = @"G:\results\parent.odb", ["FortranPathTextBox"] = " material.for ",
                    ["ExecutionLocationComboBox"] = "2", ["CpuNumberBox"] = "12",
                    ["MemoryValueTextBox"] = " 90.", ["UseSsdCheckBox"] = "true",
                    ["ExecutionOptionsPanel"] = "raw GPU draft", ["ArchiveRootTextBox"] = @"G:\archive",
                },
                ["odb-merge"] = new() { ["OriginalOdbTextBox"] = @"G:\merge\original.odb" },
            },
        };
        var source = Draft();
        var sourceStore = new WorkbenchSessionStore(Path.Combine(directory, "session.json"));
        await sourceStore.SaveAsync(source);
        var originalBytes = File.ReadAllBytes(Path.Combine(directory, "session.json"));
        var reset = new NewJobDraftReset();
        var published = false;
        var confirmationCount = 0;
        Task<bool> Confirm() { confirmationCount++; return Task.FromResult(true); }
        var cancelled = await reset.RunAsync(() => source, () => Task.FromResult(false),
            _ => throw new Exception("Cancelled reset wrote data"), _ => published = true, () => true);
        Check(cancelled == NewJobResetResult.Cancelled && !published && !reset.IsBusy, "Cancellation must not publish");
        Check(originalBytes.SequenceEqual(File.ReadAllBytes(Path.Combine(directory, "session.json")))
            && source.Pages["new-job"]["JobNameTextBox"] == "example", "Cancellation changed disk or inputs");

        var busy = await reset.RunAsync(() => throw new Exception("Busy capture"), Confirm,
            sourceStore.SaveAsync, _ => published = true, () => false);
        Check(busy == NewJobResetResult.Busy && confirmationCount == 0, "Busy action opened confirmation");
        var canReset = true;
        var stopping = await reset.RunAsync(() => source, () => { canReset = false; return Confirm(); },
            _ => throw new Exception("Shutdown reset wrote data"), _ => published = true, () => canReset);
        Check(stopping == NewJobResetResult.Busy && !published, "Shutdown during confirmation was ignored");

        var gate = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var saving = reset.RunAsync(() => source, Confirm, async next =>
        {
            await gate.Task;
            await sourceStore.SaveAsync(next);
        }, next => { source = next; published = true; }, () => true);
        Check(reset.IsBusy && reset.PendingSave is not null && !published
            && source.Pages["new-job"]["InputPathTextBox"].Length > 0, "Inputs cleared before save finished");
        var repeated = await reset.RunAsync(() => throw new Exception("Reentrant capture"), Confirm,
            sourceStore.SaveAsync, _ => throw new Exception("Reentrant publication"), () => true);
        Check(repeated == NewJobResetResult.Busy, "Duplicate reset was accepted");
        gate.SetResult();
        Check(await saving == NewJobResetResult.Completed && published && !reset.IsBusy && reset.PendingSave is null,
            "Successful reset did not finish cleanly");
        var loaded = new WorkbenchSessionStore(Path.Combine(directory, "session.json")).Load();
        Check(!NewJobDraftReset.HasTaskInputs(loaded) && loaded.Pages["new-job"]["ExecutionLocationComboBox"] == "0",
            "Task inputs survived successful reset");
        Check(loaded.Pages["new-job"]["CpuNumberBox"] == "12" && loaded.Pages["new-job"]["MemoryValueTextBox"] == " 90."
            && loaded.Pages["new-job"]["ExecutionOptionsPanel"] == "raw GPU draft"
            && loaded.Pages["new-job"]["UseSsdCheckBox"] == "true"
            && loaded.Pages["new-job"]["ArchiveRootTextBox"] == @"G:\archive", "Resource draft was changed");
        Check(loaded.Pages["odb-merge"]["OriginalOdbTextBox"] == @"G:\merge\original.odb"
            && loaded.Window.X == 42 && loaded.Window.Width == 1400 && loaded.LastRoute == "new-job"
            && !loaded.ExplorerVisible,
            "Independent page/window or route lost");

        source = Draft();
        published = false;
        var blocked = Path.Combine(directory, "blocked");
        File.WriteAllText(blocked, "preserve");
        try
        {
            await reset.RunAsync(() => source, Confirm,
                new WorkbenchSessionStore(Path.Combine(blocked, "session.json")).SaveAsync,
                _ => published = true, () => true);
            throw new Exception("Write failure accepted");
        }
        catch (IOException) { }
        Check(!published && !reset.IsBusy && reset.PendingSave is null && NewJobDraftReset.HasTaskInputs(source)
            && File.ReadAllText(blocked) == "preserve", "Failed write lost original draft");

        var corruptPath = Path.Combine(directory, "corrupt.json");
        File.WriteAllText(corruptPath, "corrupt");
        var corrupt = new WorkbenchSessionStore(corruptPath);
        try { corrupt.Load(); throw new Exception("Corrupt load accepted"); }
        catch (System.Text.Json.JsonException) { }
        try { await reset.RunAsync(() => source, Confirm, corrupt.SaveAsync, _ => published = true, () => true);
            throw new Exception("Corrupt overwrite accepted"); }
        catch (IOException) { }
        Check(!published && !reset.IsBusy && File.ReadAllText(corruptPath) == "corrupt", "Unreadable draft overwritten");

        var empty = new WorkbenchSessionState();
        await reset.RunAsync(() => empty, () => throw new Exception("Empty draft prompted"),
            sourceStore.SaveAsync, next => empty = next, () => true);
        Check(empty.Pages["new-job"].Count == 5 && !NewJobDraftReset.HasTaskInputs(empty), "Unvisited page reset failed");
        empty.Pages["new-job"]["JobNameTextBox"] = "name-only";
        Check(NewJobDraftReset.HasTaskInputs(empty), "Name-only draft would be discarded without confirmation");
        var copy = NewJobDraftReset.CreateReset(source);
        copy.Pages["odb-merge"]["OriginalOdbTextBox"] = "changed";
        copy.Window.Width = 1;
        Check(source.Pages["odb-merge"]["OriginalOdbTextBox"] != "changed" && source.Window.Width == 1400,
            "Reset snapshot shares mutable state");
        await sourceStore.SaveAsync(source);
        await reset.RunAsync(() => source, Confirm, sourceStore.SaveAsync, next => source = next, () => true);
        Check(!NewJobDraftReset.HasTaskInputs(new WorkbenchSessionStore(Path.Combine(directory, "session.json")).Load()),
            "Retry after failure did not persist");
        Console.WriteLine($"{checks} new-job reset checks passed; no native UI or solver started.");
    }
}
