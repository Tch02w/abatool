namespace AbaqusTools.WinUI.Services;

internal sealed record ControlPlaneLaunch(string Root, string Executable, bool Bundled)
{
    internal const string BundleExecutable = "AbaqusTools.ControlPlane.exe";

    internal static ControlPlaneLaunch Resolve(string baseDirectory, string? configuredRoot, string? configuredPython)
    {
        configuredRoot = configuredRoot?.Trim().Trim('"');
        configuredPython = configuredPython?.Trim().Trim('"');
        if (!string.IsNullOrWhiteSpace(configuredRoot))
            return AtRoot(Path.GetFullPath(configuredRoot), configuredPython);

        var directory = new DirectoryInfo(Path.GetFullPath(baseDirectory));
        // A shipped bundle must not accidentally use an ancestor checkout's Python.
        if (Directory.Exists(Path.Combine(directory.FullName, "control-plane"))
            || File.Exists(Path.Combine(directory.FullName, "release-manifest.json")))
            return AtRoot(directory.FullName, configuredPython);
        while (directory is not null)
        {
            if (IsSourceRoot(directory.FullName))
                return AtRoot(directory.FullName, configuredPython);
            directory = directory.Parent;
        }
        throw new ControlPlaneException("未找到随应用发布的控制面或项目根目录。请完整解压应用；开发环境可设置 ABAQUS_TOOLS_ROOT。");
    }

    private static ControlPlaneLaunch AtRoot(string root, string? python)
    {
        if (string.IsNullOrWhiteSpace(python) && File.Exists(BundlePath(root)))
            return new(root, BundlePath(root), true);
        if (!IsSourceRoot(root))
            throw new ControlPlaneException($"不是有效的源码目录，或控制面发布文件缺失：{root}。指定 ABAQUS_TOOLS_PYTHON 时需同时提供源码目录。");
        if (string.IsNullOrWhiteSpace(python))
            python = Path.Combine(root, ".venv", "Scripts", "python.exe");
        else if (!Path.IsPathFullyQualified(python)
            && (python.Contains(Path.DirectorySeparatorChar) || python.Contains(Path.AltDirectorySeparatorChar)))
            python = Path.GetFullPath(python, root);
        if (Path.IsPathFullyQualified(python) && !File.Exists(python))
            throw new ControlPlaneException($"未找到控制面 Python：{python}。开发环境需创建项目 .venv 或设置 ABAQUS_TOOLS_PYTHON。");
        return new(root, python, false);
    }

    private static string BundlePath(string root) => Path.Combine(root, "control-plane", BundleExecutable);

    private static bool IsSourceRoot(string path) =>
        File.Exists(Path.Combine(path, "pyproject.toml"))
        && File.Exists(Path.Combine(path, "modules", "control_plane", "__main__.py"));
}
