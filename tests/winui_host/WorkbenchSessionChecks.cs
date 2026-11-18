using AbaqusTools.WinUI.Services;

static class WorkbenchSessionChecks
{
    public static void Run()
    {
        var directory = Path.Combine(Path.GetTempPath(), "abatool-session-test-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, "中文 草稿.json");
        try
        {
            var store = new WorkbenchSessionStore(path);
            var state = store.Load();
            if (!state.ExplorerVisible) throw new Exception("New profiles must show the explorer");
            File.WriteAllText(path, "{\"SchemaVersion\":1,\"LastRoute\":\"new-job\"}");
            if (!new WorkbenchSessionStore(path).Load().ExplorerVisible)
                throw new Exception("Old profiles must keep the explorer visible");
            state.ExplorerVisible = false;
            state.LastRoute = "odb-merge";
            state.Pages["new-job"] = new() { ["InputPathTextBox"] = @"G:\中文 目录\未完成.inp", ["CpuNumberBox"] = "1+" };
            state.Window = new() { X = -1200, Width = 1400, Height = 900, Maximized = false };
            store.Save(state);
            var restored = new WorkbenchSessionStore(path).Load();
            if (restored.LastRoute != "odb-merge" || restored.Pages["new-job"]["CpuNumberBox"] != "1+"
                || restored.Window.X != -1200 || restored.Window.Maximized || restored.ExplorerVisible)
                throw new Exception("Raw draft, explorer visibility or window state lost");
            restored.ExplorerVisible = true;
            new WorkbenchSessionStore(path).Save(restored);
            if (!new WorkbenchSessionStore(path).Load().ExplorerVisible)
                throw new Exception("Showing the explorer was not persisted");
            if (Directory.GetFiles(directory, "*.tmp").Length != 0) throw new Exception("Atomic save left scratch files");
            var before = File.ReadAllBytes(path);
            state.SchemaVersion = 2;
            Reject(() => store.Save(state));
            if (!before.SequenceEqual(File.ReadAllBytes(path))) throw new Exception("Invalid save overwrote prior session");
            File.WriteAllText(path, "broken json");
            var damaged = new WorkbenchSessionStore(path);
            Reject(() => damaged.Load());
            Reject(() => damaged.Save(new()));
            if (File.ReadAllText(path) != "broken json") throw new Exception("Unreadable session was overwritten");
            File.WriteAllText(path, "{\"SchemaVersion\":99}");
            Reject(() => new WorkbenchSessionStore(path).Load());
            var blockedDirectory = Path.Combine(directory, "not-a-directory");
            File.WriteAllText(blockedDirectory, "keep");
            Reject(() => new WorkbenchSessionStore(Path.Combine(blockedDirectory, "session.json")).Save(new()));
            if (File.ReadAllText(blockedDirectory) != "keep") throw new Exception("Failed save changed blocker");
            Console.WriteLine("9 workbench session persistence checks passed.");
        }
        finally { Directory.Delete(directory, recursive: true); }
    }

    private static void Reject(Action action)
    {
        try { action(); }
        catch (Exception error) when (error is IOException or InvalidDataException or System.Text.Json.JsonException or UnauthorizedAccessException) { return; }
        throw new Exception("Invalid session operation was accepted");
    }
}
