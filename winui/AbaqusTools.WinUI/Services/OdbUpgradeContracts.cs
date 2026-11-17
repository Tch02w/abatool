using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class OdbUpgradePreview
{
    public int SchemaVersion { get; init; }
    public string Root { get; init; } = string.Empty;
    public string TargetRelease { get; init; } = string.Empty;
    public IReadOnlyList<OdbUpgradeEntry> Entries { get; init; } = [];
    public bool RequiresCompatibilityCheck { get; init; }
    public bool RequiresConfirmation { get; init; }
    public string SourcePolicy { get; init; } = string.Empty;
    public string CancellationPolicy { get; init; } = string.Empty;
}

public sealed class OdbUpgradeEntry
{
    public string SourcePath { get; init; } = string.Empty;
    public string UpgradedPath { get; init; } = string.Empty;
    public string BackupPath { get; init; } = string.Empty;
    public string TemporaryPath { get; init; } = string.Empty;
    public long SourceSizeBytes { get; init; }
    public long SourceMtimeNs { get; init; }
}

public sealed class OdbUpgradeResult
{
    [JsonPropertyName("source_path")]
    public string SourcePath { get; init; } = string.Empty;
    [JsonPropertyName("upgraded_path")]
    public string UpgradedPath { get; init; } = string.Empty;
    [JsonPropertyName("backup_path")]
    public string BackupPath { get; init; } = string.Empty;
    public string Status { get; init; } = string.Empty;
    public string Message { get; init; } = string.Empty;
    [JsonPropertyName("cache_warning")]
    public string CacheWarning { get; init; } = string.Empty;
}

public sealed class OdbUpgradeOperationSnapshot
{
    public int SchemaVersion { get; init; }
    public string OperationId { get; init; } = string.Empty;
    public string ClientRequestId { get; init; } = string.Empty;
    public string Kind { get; init; } = string.Empty;
    public string Status { get; init; } = string.Empty;
    public long Version { get; init; }
    public OdbUpgradePreview Preview { get; init; } = new();
    public IReadOnlyList<OdbUpgradeResult> Results { get; init; } = [];
    public IReadOnlyList<string> Logs { get; init; } = [];
    public OdbUpgradeProgress Progress { get; init; } = new();
    public OdbCompatibilityOperationError? Error { get; init; }
    public string PersistenceWarning { get; init; } = string.Empty;
    [JsonIgnore]
    public bool IsTerminal => Status is "succeeded" or "failed" or "cancelled";
}

public sealed class OdbUpgradeProgress
{
    public int Completed { get; init; }
    public int Total { get; init; }
    public string CurrentFile { get; init; } = string.Empty;
}

public sealed class OdbUpgradeOperationListResponse
{
    public int SchemaVersion { get; init; }
    public IReadOnlyList<OdbUpgradeOperationSnapshot> Operations { get; init; } = [];
}

internal static class OdbUpgradeContractValidation
{
    public static void Validate(OdbUpgradePreview preview)
    {
        if (preview.SchemaVersion != 1 || !Path.IsPathFullyQualified(preview.Root)
            || string.IsNullOrWhiteSpace(preview.TargetRelease)
            || !preview.RequiresCompatibilityCheck || !preview.RequiresConfirmation
            || preview.SourcePolicy != "backup-original-before-validated-replacement"
            || preview.CancellationPolicy != "finish-active-file-then-stop"
            || preview.Entries is not { Count: > 0 })
            throw new ControlPlaneException("控制面返回了无效的升级预览。");
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var entry in preview.Entries)
        {
            if (entry is null || !Path.IsPathFullyQualified(entry.SourcePath)
                || !Path.IsPathFullyQualified(entry.UpgradedPath)
                || !Path.IsPathFullyQualified(entry.BackupPath)
                || !Path.IsPathFullyQualified(entry.TemporaryPath)
                || !string.Equals(entry.SourcePath, entry.UpgradedPath, StringComparison.OrdinalIgnoreCase)
                || entry.SourceSizeBytes <= 0 || entry.SourceMtimeNs <= 0
                || !paths.Add(Path.GetFullPath(entry.SourcePath))
                || !paths.Add(Path.GetFullPath(entry.BackupPath))
                || !paths.Add(Path.GetFullPath(entry.TemporaryPath)))
                throw new ControlPlaneException("升级预览的源文件、备份或临时路径无效或相互冲突。");
        }
    }

    public static void Validate(OdbUpgradeOperationSnapshot snapshot, string? expectedId = null)
    {
        if (snapshot.SchemaVersion != 1 || snapshot.Kind != "odb.upgrade"
            || string.IsNullOrWhiteSpace(snapshot.OperationId) || snapshot.Version < 1
            || (expectedId is not null && snapshot.OperationId != expectedId)
            || snapshot.Status is not ("queued" or "running" or "cancelling" or "succeeded" or "failed" or "cancelled")
            || snapshot.Results is null || snapshot.Logs is null || snapshot.Preview is null || snapshot.Progress is null)
            throw new ControlPlaneException("控制面返回了无效的升级任务状态。");
        Validate(snapshot.Preview);
        if (snapshot.Progress.Total != snapshot.Preview.Entries.Count || snapshot.Progress.Completed < 0
            || snapshot.Progress.Completed > snapshot.Progress.Total)
            throw new ControlPlaneException("升级进度与任务文件数不一致。");
        var expected = snapshot.Preview.Entries.Select(entry => Path.GetFullPath(entry.SourcePath))
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var returned = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var result in snapshot.Results)
        {
            if (result is null || !Path.IsPathFullyQualified(result.SourcePath)
                || !expected.Contains(Path.GetFullPath(result.SourcePath))
                || !returned.Add(Path.GetFullPath(result.SourcePath)))
                throw new ControlPlaneException("升级任务返回了不属于本计划或重复的文件结果。");
        }
        if (snapshot.Status == "succeeded" && (returned.Count != expected.Count
            || snapshot.Results.Any(result => result.Status != "upgraded")))
            throw new ControlPlaneException("升级任务缺少成功的逐文件回执。");
    }
}
