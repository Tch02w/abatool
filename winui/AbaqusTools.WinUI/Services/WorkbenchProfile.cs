using System.Security.Cryptography;
using System.Text;

namespace AbaqusTools.WinUI.Services;

/// <summary>Process-local profile. Default paths and the existing primary instance stay compatible.</summary>
public sealed record WorkbenchProfile(string StateDirectory, bool IsCustom)
{
    public const string EnvironmentVariable = "ABAQUS_TOOLS_PROFILE_DIR";
    public static WorkbenchProfile Current { get; } = Resolve(
        Environment.GetEnvironmentVariable(EnvironmentVariable),
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), Path.GetTempPath());

    public string SingleInstanceKey => !IsCustom ? "AbaqusTools.WinUI.Primary"
        : "AbaqusTools.WinUI.Profile." + Convert.ToHexString(SHA256.HashData(
            Encoding.UTF8.GetBytes(StateDirectory.TrimEnd('\\', '/').ToUpperInvariant())));

    public static WorkbenchProfile Resolve(string? configured, string localAppData, string temporaryDirectory)
    {
        var normal = Path.GetFullPath(Path.Combine(
            string.IsNullOrWhiteSpace(localAppData) ? temporaryDirectory : localAppData, "AbaqusTools"));
        if (string.IsNullOrWhiteSpace(configured)) return new(normal, false);
        if (!Path.IsPathFullyQualified(configured))
            throw new ArgumentException("独立工作目录必须是完整的绝对路径：" + EnvironmentVariable);
        var directory = Path.TrimEndingDirectorySeparator(Path.GetFullPath(configured));
        if (string.Equals(directory, Path.TrimEndingDirectorySeparator(normal), StringComparison.OrdinalIgnoreCase))
            throw new ArgumentException("独立工作目录不能使用日常配置目录。");
        return new(directory, true);
    }

    public void ConfigureBackendEnvironment()
    {
        if (!IsCustom) return;
        // The native descriptor, Python queues/config and all recovery drafts must share one profile.
        Environment.SetEnvironmentVariable("ABAQUS_SUBMITTER_DATA_DIR", Path.Combine(StateDirectory, "submitter"));
        Environment.SetEnvironmentVariable("ABAQUS_POSTPROCESSOR_DATA_DIR", Path.Combine(StateDirectory, "postprocessor"));
    }
}
