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
            VerifyLegacySettings(directory);
            Console.WriteLine("9 workbench session persistence checks passed.");
        }
        finally { Directory.Delete(directory, recursive: true); }
    }

    private static void VerifyLegacySettings(string directory)
    {
        var path = Path.Combine(directory, "config.json");
        File.WriteAllText(path, """
            {"workbench":{"cpus":0,"priority":-10,"max_parallel":4,"memory_value":"17","memory_unit":"GB",
             "notify":false,"archive_dir":"","merge_name_source":"custom","merge_conflict_strategy":"confirm",
             "merge_compress_result":true,"password":"must-not-import"},
             "remote_server":{"host":"must-not-import"},"qt_archive_dir":"obsolete","qt_ssd_work_dir":"SSD"}
            """);
        var bytes = File.ReadAllBytes(path);
        var state = new WorkbenchSessionState();
        LegacyWorkbenchSettings.ImportMissingPages(state, path);
        var job = state.Pages["new-job"];
        var merge = state.Pages["odb-merge"];
        if (job.Count != 8 || job["CpuNumberBox"] != "0" || job["PriorityComboBox"] != "2"
            || job["MaxParallelNumberBox"] != "4" || job["MemoryValueTextBox"] != "17" || job["MemoryUnitComboBox"] != "2"
            || job["NotifyCheckBox"] != "false" || job["ArchiveRootTextBox"] != "" || job["CalculationRootTextBox"] != "SSD"
            || merge.Count != 3 || merge["ResultNamingComboBox"] != "2" || merge["ConflictPolicyComboBox"] != "1"
            || merge["CompressResultCheckBox"] != "true")
            throw new Exception("Incorrect mapping of PySide controls");
        state.Pages["new-job"].Clear();
        state.Pages.Remove("odb-merge");
        LegacyWorkbenchSettings.ImportMissingPages(state, path);
        if (state.Pages["new-job"].Count != 0 || state.Pages["odb-merge"].Count != 3 || !bytes.SequenceEqual(File.ReadAllBytes(path)))
            throw new Exception("Import changed a cleared native page or the PySide settings");
        var profile = new WorkbenchProfile(directory, IsCustom: true);
        if (profile.LegacySubmitterConfigPath() != Path.Combine(directory, "submitter", "config.json"))
            throw new Exception("Independent profile can read another profile's settings");
    }

    private static void Reject(Action action)
    {
        try { action(); }
        catch (Exception error) when (error is IOException or InvalidDataException or System.Text.Json.JsonException or UnauthorizedAccessException) { return; }
        throw new Exception("Invalid session operation was accepted");
    }
}
