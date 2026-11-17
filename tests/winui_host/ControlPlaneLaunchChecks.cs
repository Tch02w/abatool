using AbaqusTools.WinUI.Services;

internal static class ControlPlaneLaunchChecks
{
    internal static void Run()
    {
        var root = Path.GetFullPath(Path.Combine("GPTWork", "launch-resolution-" + Guid.NewGuid().ToString("N")));
        Directory.CreateDirectory(Path.Combine(root, "modules", "control_plane"));
        File.WriteAllText(Path.Combine(root, "pyproject.toml"), "");
        File.WriteAllText(Path.Combine(root, "modules", "control_plane", "__main__.py"), "");
        Directory.CreateDirectory(Path.Combine(root, ".venv", "Scripts"));
        var python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        File.WriteAllText(python, "");
        var baseDirectory = Path.Combine(root, "build", "中文 路径");
        Directory.CreateDirectory(baseDirectory);
        var source = ControlPlaneLaunch.Resolve(baseDirectory, null, null);
        Require(!source.Bundled && source.Root == root && source.Executable == python, "Source ancestor resolution");
        var bundle = Path.Combine(baseDirectory, "control-plane");
        Directory.CreateDirectory(bundle);
        var executable = Path.Combine(bundle, ControlPlaneLaunch.BundleExecutable);
        Reject(() => ControlPlaneLaunch.Resolve(baseDirectory, null, null));
        File.WriteAllText(executable, "");
        var release = ControlPlaneLaunch.Resolve(baseDirectory, null, null);
        Require(release.Bundled && release.Executable == executable && release.Root == baseDirectory, "Bundle must win over ancestor source");
        Require(ControlPlaneLaunch.Resolve(root, baseDirectory, null).Bundled, "Explicit bundle root");
        Require(ControlPlaneLaunch.Resolve(baseDirectory, root, null) == source, "Explicit source root");
        Require(ControlPlaneLaunch.Resolve(root, root, ".venv/Scripts/python.exe") == source, "Relative Python override");
        Require(ControlPlaneLaunch.Resolve(root, root, '"' + python + '"') == source, "Quoted Python override");
        Require(ControlPlaneLaunch.Resolve(root, root, "python.exe").Executable == "python.exe", "PATH override");
        Reject(() => ControlPlaneLaunch.Resolve(root, bundle, null));
        Reject(() => ControlPlaneLaunch.Resolve(baseDirectory, null, python));
        Reject(() => ControlPlaneLaunch.Resolve(root, root, Path.Combine(root, "missing.exe")));
        Console.WriteLine("11 control-plane launch resolution checks passed.");
    }

    private static void Require(bool condition, string message)
    {
        if (!condition) throw new Exception(message);
    }

    private static void Reject(Action action)
    {
        try { action(); }
        catch (ControlPlaneException) { return; }
        throw new Exception("Invalid launch configuration was accepted");
    }
}
