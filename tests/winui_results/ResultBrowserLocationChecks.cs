using AbaqusTools.WinUI.Services;

internal static class ResultBrowserLocationChecks
{
    public static async Task RunAsync()
    {
        var work = Path.Combine(Path.GetTempPath(), "result-location-" + Guid.NewGuid().ToString("N"));
        var first = Path.Combine(work, "显示目录");
        var second = Path.Combine(work, "待读取目录");
        var destination = Path.Combine(work, "export");
        Directory.CreateDirectory(first);
        Directory.CreateDirectory(second);
        Directory.CreateDirectory(destination);
        var source = Path.Combine(first, "curve.csv");
        var other = Path.Combine(second, "curve.csv");
        await File.WriteAllTextAsync(source, "time,force\n0,123\n");
        await File.WriteAllTextAsync(other, "time,force\n0,999\n");
        var count = 0;
        void Check(bool condition, string reason)
        {
            if (!condition) throw new InvalidOperationException(reason);
            count++;
        }
        try
        {
            var location = new ResultBrowserLocation { DraftRoot = first + Path.DirectorySeparatorChar };
            location.Apply(location.BeginRead(), first);
            Check(location.RequireLoadedRoot() == first && location.DraftRoot == first && !location.HasPendingRoot,
                "The first accepted directory should normalize the editor and become the source");
            location.DraftRoot = second;
            Check(location.HasPendingRoot && location.RequireLoadedRoot() == first,
                "An unsubmitted directory must not retarget visible results");
            Check(ResultFileRecycle.ValidatePath(location.RequireLoadedRoot(), source) == source,
                "Recycle validation must still accept the visible source (without recycling in this test)");
            var outcome = await ResultFileExport.CopyAsync(location.RequireLoadedRoot(), destination,
                [new ResultExportFile(source, "curve.csv")], null, CancellationToken.None);
            Check(outcome.Succeeded && await File.ReadAllTextAsync(Path.Combine(destination, "curve.csv"))
                == await File.ReadAllTextAsync(source), "Export must copy the visible source, not the draft directory's same-name file");
            var indexRefresh = location.BeginRead(location.RequireLoadedRoot());
            location.ClearLoadedRoot();
            location.Apply(indexRefresh, first);
            Check(location.RequireLoadedRoot() == first && location.DraftRoot == second && location.HasPendingRoot,
                "Refreshing after indexing must preserve the pending directory and the indexed source");
            location.DraftRoot = first.ToUpperInvariant() + Path.DirectorySeparatorChar;
            Check(!location.HasPendingRoot, "Equivalent Windows paths must not show a false pending hint");
            location.DraftRoot = "bad\0path";
            Check(location.HasPendingRoot && location.RequireLoadedRoot() == first,
                "Incomplete or invalid editor text must not break the loaded context");
            location.DraftRoot = second;
            var manualRead = location.BeginRead();
            location.ClearLoadedRoot();
            location.Apply(manualRead, second);
            Check(!location.HasPendingRoot && location.RequireLoadedRoot() == second,
                "Only an accepted manual read should switch the source to the new directory");
            var delayedRead = location.BeginRead();
            location.DraftRoot = first;
            location.Apply(delayedRead, second);
            Check(location.DraftRoot == first && location.RequireLoadedRoot() == second && location.HasPendingRoot,
                "A delayed response must not overwrite a newer editor draft");
            location.ClearLoadedRoot();
            var rejected = false;
            try { location.RequireLoadedRoot(); }
            catch (InvalidOperationException) { rejected = true; }
            Check(rejected && location.DraftRoot == first,
                "Failed or cleared discovery must not silently fall back to editor text for file actions");
            Check(await File.ReadAllTextAsync(other) == "time,force\n0,999\n"
                && await File.ReadAllTextAsync(source) == "time,force\n0,123\n", "Both result sources must remain unchanged");
            var scope = Path.Combine(first, "分组", "批次", "模型");
            var current = new ResultDirectLocation(first, scope, scope);
            var nested = current.Child(Path.Combine(scope, "data"))!;
            var nestedFile = Path.Combine(nested.DirectoryPath, "原始值.csv");
            Directory.CreateDirectory(nested.DirectoryPath);
            await File.WriteAllTextAsync(nestedFile, "force\n123\n");
            Check(current.AtScope && current.Parent() is null && nested.Parent() == current,
                "Moving up stops at the selected model");
            Check(nested.Child(other) is null && !nested.Matches(second, scope), "A stale selection cannot retarget the cursor");
            var state = new Dictionary<string, string>();
            nested.Capture(state);
            Check(ResultDirectLocation.Restore(state) == nested, "Direct scope and nested directory survive session restore");

            var cold = new ResultBrowserLocation { DraftRoot = second, DirectBookmark = ResultDirectLocation.Restore(state) };
            ResultDirectLocation? Checkpoint()
            {
                var fields = new Dictionary<string, string> { ["RootTextBox"] = cold.DraftRoot };
                cold.DirectBookmark?.Capture(fields);
                return ResultDirectLocation.Restore(fields);
            }
            Check(Checkpoint() == nested && cold.VisibleDirect(scope) is null,
                "Waiting for the initial index check preserves the last direct folder without enabling file actions");
            var restoring = cold.BeginRead(first, scope);
            cold.ClearLoadedRoot();
            Check(Checkpoint() == nested && cold.DraftRoot == second && cold.VisibleDirect(scope) is null,
                "A checkpoint during scope discovery preserves both the bookmark and the unsubmitted root");
            cold.Apply(restoring, first);
            cold.RetainMatchingBookmark(first, scope);
            Check(cold.VisibleDirect(scope) == nested && cold.VisibleDirect(first) is null && cold.DraftRoot == second,
                "The saved directory is actionable only in the matching displayed scope");
            var newerRead = cold.BeginRead(second, scope);
            Check(Checkpoint() is null, "A user read of another root retires the saved direct location immediately");
            cold.DirectBookmark = nested;
            cold.RetainMatchingBookmark(first, first);
            Check(Checkpoint() is null, "Falling back to the root when a model disappeared clears its bookmark");
            cold.Apply(newerRead, second);
            Check(cold.VisibleDirect(scope) is null, "A superseded location cannot become actionable in another root");
            state["DirectDirectory"] = second;
            Check(ResultDirectLocation.Restore(state) is null, "Restore rejects an unrelated directory");
            var candidate = new ResultExportFile(nestedFile, Path.GetRelativePath(scope, nestedFile));
            var exported = await ResultFileExport.CopyAsync(first, destination, [candidate], null, CancellationToken.None, nested.ValidateFile);
            Check(exported.Succeeded && await File.ReadAllTextAsync(Path.Combine(destination, "data", "原始值.csv")) == "force\n123\n",
                "Direct export preserves the selected model's relative layout and real content");
            await File.WriteAllTextAsync(Path.Combine(scope, "_postprocess_incomplete.json"), "{}");
            var unpublished = await ResultFileExport.CopyAsync(first, destination, [candidate], null, CancellationToken.None, nested.ValidateFile);
            Check(!unpublished.Succeeded && unpublished.Completed.Count == 0 && unpublished.Remaining.Count == 1,
                "A formerly visible direct result must not publish a copy after the scope becomes incomplete");
            Console.WriteLine($"{count} result directory context and actual export checks passed");
        }
        finally { Directory.Delete(work, recursive: true); }
    }
}
