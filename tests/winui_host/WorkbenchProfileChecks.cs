using AbaqusTools.WinUI.Services;

internal static class WorkbenchProfileChecks
{
    public static void Run(string directory)
    {
        var root = Path.GetFullPath(directory);
        if (!root.StartsWith("G:\\", StringComparison.OrdinalIgnoreCase)) throw new Exception("Use G: GPTWork");
        var checks = 0;
        void Check(bool value) { if (!value) throw new Exception("Profile check failed: " + checks); checks++; }
        var normal = WorkbenchProfile.Resolve(null, root, root);
        Check(!normal.IsCustom && normal.StateDirectory == Path.Combine(root, "AbaqusTools"));
        Check(normal.SingleInstanceKey == "AbaqusTools.WinUI.Primary");
        Check(WorkbenchProfile.Resolve(" ", root, root) == normal);
        Check(WorkbenchProfile.Resolve(null, "", root) == normal);
        var first = WorkbenchProfile.Resolve(Path.Combine(root, "配置 A"), root, root);
        var same = WorkbenchProfile.Resolve(Path.Combine(root, "配置 A", ".") + "\\", root, root);
        var second = WorkbenchProfile.Resolve(Path.Combine(root, "配置 B"), root, root);
        Check(first == same && first.IsCustom);
        Check(first.SingleInstanceKey == same.SingleInstanceKey);
        Check(first.SingleInstanceKey == WorkbenchProfile.Resolve(first.StateDirectory.ToUpperInvariant(), root, root).SingleInstanceKey);
        Check(first.SingleInstanceKey != second.SingleInstanceKey && first.SingleInstanceKey != normal.SingleInstanceKey);
        foreach (var invalid in new[] { "relative", "G:relative", "\\relative", normal.StateDirectory })
        {
            try { WorkbenchProfile.Resolve(invalid, root, root); throw new Exception("Invalid profile accepted"); }
            catch (ArgumentException) { checks++; }
        }
        var previousSubmitter = Environment.GetEnvironmentVariable("ABAQUS_SUBMITTER_DATA_DIR");
        var previousPost = Environment.GetEnvironmentVariable("ABAQUS_POSTPROCESSOR_DATA_DIR");
        try
        {
            Environment.SetEnvironmentVariable("ABAQUS_SUBMITTER_DATA_DIR", "prior-submitter");
            Environment.SetEnvironmentVariable("ABAQUS_POSTPROCESSOR_DATA_DIR", "prior-post");
            normal.ConfigureBackendEnvironment();
            Check(Environment.GetEnvironmentVariable("ABAQUS_SUBMITTER_DATA_DIR") == "prior-submitter"
                && Environment.GetEnvironmentVariable("ABAQUS_POSTPROCESSOR_DATA_DIR") == "prior-post");
            first.ConfigureBackendEnvironment();
            Check(Environment.GetEnvironmentVariable("ABAQUS_SUBMITTER_DATA_DIR") == Path.Combine(first.StateDirectory, "submitter")
                && Environment.GetEnvironmentVariable("ABAQUS_POSTPROCESSOR_DATA_DIR") == Path.Combine(first.StateDirectory, "postprocessor"));
        }
        finally
        {
            Environment.SetEnvironmentVariable("ABAQUS_SUBMITTER_DATA_DIR", previousSubmitter);
            Environment.SetEnvironmentVariable("ABAQUS_POSTPROCESSOR_DATA_DIR", previousPost);
        }
        Console.WriteLine($"{checks} profile isolation checks passed");
    }
}
