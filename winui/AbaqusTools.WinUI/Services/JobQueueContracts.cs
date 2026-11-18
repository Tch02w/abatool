using System.Text.Json.Serialization;
using System.Text.Json;

namespace AbaqusTools.WinUI.Services;

public sealed class JobQueueSnapshot
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("capturedAt")]
    public DateTimeOffset CapturedAt { get; init; }

    [JsonPropertyName("candidates")]
    public IReadOnlyList<JobQueueItem> Candidates { get; init; } = [];

    [JsonPropertyName("queueItems")]
    public IReadOnlyList<JobQueueItem> QueueItems { get; init; } = [];

    [JsonPropertyName("candidateCount")]
    public int CandidateCount { get; init; }

    [JsonPropertyName("selectedCandidateCount")]
    public int SelectedCandidateCount { get; init; }

    [JsonPropertyName("invalidCandidateCount")]
    public int InvalidCandidateCount { get; init; }

    [JsonPropertyName("queueCount")]
    public int QueueCount { get; init; }

    [JsonPropertyName("statusCounts")]
    public IReadOnlyDictionary<string, int> StatusCounts { get; init; } =
        new Dictionary<string, int>(StringComparer.Ordinal);
}

public sealed class JobQueueItem
{
    [JsonPropertyName("attemptId")]
    public string AttemptId { get; init; } = string.Empty;
    [JsonPropertyName("index")]
    public int Index { get; init; }

    [JsonPropertyName("itemId")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("jobId")]
    public string JobId { get; init; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; init; } = string.Empty;

    [JsonPropertyName("inpPath")]
    public string InpPath { get; init; } = string.Empty;

    [JsonPropertyName("source")]
    public string Source { get; init; } = string.Empty;

    [JsonPropertyName("selected")]
    public bool Selected { get; init; }

    [JsonPropertyName("valid")]
    public bool Valid { get; init; }

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("runMode")]
    public string RunMode { get; init; } = string.Empty;

    [JsonPropertyName("jobType")]
    public string JobType { get; init; } = string.Empty;

    [JsonPropertyName("oldjobName")]
    public string OldjobName { get; init; } = string.Empty;

    [JsonPropertyName("oldjobPath")]
    public string OldjobPath { get; init; } = string.Empty;

    [JsonPropertyName("fortranPath")]
    public string FortranPath { get; init; } = string.Empty;

    [JsonPropertyName("gpuCount")] public int? GpuCount { get; init; }
    [JsonPropertyName("explicitPrecision")] public string ExplicitPrecision { get; init; } = "default";
    [JsonPropertyName("outputPrecision")] public string OutputPrecision { get; init; } = "default";

    [JsonPropertyName("cores")]
    public int Cores { get; init; }

    [JsonPropertyName("memory")]
    public string Memory { get; init; } = string.Empty;

    [JsonPropertyName("runtimeMemoryBytes")]
    public long RuntimeMemoryBytes { get; init; }

    [JsonPropertyName("memoryObservationStatus")]
    public string MemoryObservationStatus { get; init; } = string.Empty;

    [JsonPropertyName("memoryPeakBytes")]
    public long MemoryPeakBytes { get; init; }

    [JsonPropertyName("memoryEstimatedBytes")]
    public long MemoryEstimatedBytes { get; init; }

    [JsonPropertyName("memorySampleCount")]
    public int MemorySampleCount { get; init; }

    [JsonPropertyName("memoryEstimateSource")]
    public string MemoryEstimateSource { get; init; } = string.Empty;

    [JsonPropertyName("priority")]
    public int Priority { get; init; }

    [JsonPropertyName("held")]
    public bool Held { get; init; }

    [JsonPropertyName("schedulerState")]
    public string SchedulerState { get; init; } = string.Empty;

    [JsonPropertyName("pendingReason")]
    public string PendingReason { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("effectiveWorkDir")]
    public string EffectiveWorkDir { get; init; } = string.Empty;

    [JsonPropertyName("archiveDestination")]
    public string ArchiveDestination { get; init; } = string.Empty;

    [JsonPropertyName("archiveStatus")]
    public string ArchiveStatus { get; init; } = string.Empty;

    [JsonPropertyName("archiveError")]
    public string ArchiveError { get; init; } = string.Empty;

    [JsonIgnore]
    public bool HasPublishedArchive => !string.IsNullOrWhiteSpace(ArchiveDestination)
        && ArchiveStatus is "已归档" or "已归档，清理未完成";

    [JsonIgnore]
    public string ArchiveDetailsDisplay => string.IsNullOrWhiteSpace(ArchiveStatus) ? string.Empty
        : $"归档：{ArchiveStatus}"
          + (HasPublishedArchive ? $"\n目录：{ArchiveDestination}" : "\n请核对计算目录和归档提示；未发布目录不能作为完整归档")
          + (string.IsNullOrWhiteSpace(ArchiveError) ? string.Empty : $"\n说明：{ArchiveError}");

    [JsonIgnore]
    public string ResultMessageDisplay => string.IsNullOrWhiteSpace(ArchiveStatus)
        || Message.Contains(ArchiveStatus, StringComparison.Ordinal) ? Message : $"{Message} · {ArchiveStatus}";

    [JsonPropertyName("elapsed")]
    public string Elapsed { get; init; } = string.Empty;

    [JsonPropertyName("isExternal")]
    public bool IsExternal { get; init; }

    [JsonPropertyName("dependencyJobIds")]
    public IReadOnlyList<string> DependencyJobIds { get; init; } = [];

    [JsonIgnore]
    public string SelectedDisplay => Selected ? "✓" : string.Empty;

    [JsonIgnore]
    public string FortranName => string.IsNullOrWhiteSpace(FortranPath)
        ? string.Empty
        : Path.GetFileName(FortranPath);

    [JsonIgnore]
    public string CoresDisplay => Cores <= 0 ? string.Empty : Cores.ToString();

    [JsonIgnore]
    public string PriorityDisplay => Priority > 0 ? $"+{Priority}" : Priority.ToString();

    [JsonIgnore]
    public string SchedulingDisplay => Held ? "已暂停" : "可调度";

    [JsonIgnore]
    public string RuntimeMemoryDisplay => MemoryObservationStatus switch
    {
        "unavailable" => "暂不可读",
        "stale" => "待更新",
        "waiting" => "采集中",
        "ended" => "已结束",
        _ => FormatMemory(RuntimeMemoryBytes),
    };

    [JsonIgnore]
    public string MemoryDetailsDisplay => $"当前：{RuntimeMemoryDisplay} · 观测峰值：{FormatMemory(MemoryPeakBytes)}"
        + (MemoryEstimatedBytes > 0 ? $"\n调度参考：{FormatMemory(MemoryEstimatedBytes)}（{MemoryEstimateSource switch
        {
            "history" => "同模型历史",
            "reference" => "本次运行的其他作业参考",
            "observed" => "已观测峰值含安全余量",
            _ => "预估",
        }}）" : "\n尚无内存估计，仍受并行数与 CPU 限制");

    private static string FormatMemory(long bytes) => bytes switch
    {
        <= 0 => "未统计",
        >= 1073741824 => $"{bytes / 1073741824d:0.0} GB",
        _ => $"{bytes / 1048576d:0} MB",
    };
}

internal sealed class JobQueueCommandRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;

    [JsonPropertyName("paths")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public IReadOnlyList<string>? Paths { get; init; }

    [JsonPropertyName("source")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Source { get; init; }

    [JsonPropertyName("root")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Root { get; init; }

    [JsonPropertyName("recursive")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? Recursive { get; init; }

    [JsonPropertyName("skipRestartNames")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? SkipRestartNames { get; init; }

    [JsonPropertyName("skipExistingResults")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? SkipExistingResults { get; init; }

    [JsonPropertyName("itemIds")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public IReadOnlyList<string>? ItemIds { get; init; }

    [JsonPropertyName("itemId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ItemId { get; init; }

    [JsonPropertyName("selected")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? Selected { get; init; }

    [JsonPropertyName("held")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? Held { get; init; }

    [JsonPropertyName("direction")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Direction { get; init; }

    [JsonPropertyName("jobName")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? JobName { get; init; }

    [JsonPropertyName("cores")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Cores { get; init; }

    [JsonPropertyName("gpuCount"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public JsonElement? GpuCount { get; init; }
    [JsonPropertyName("explicitPrecision"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ExplicitPrecision { get; init; }
    [JsonPropertyName("outputPrecision"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? OutputPrecision { get; init; }

    [JsonPropertyName("memory")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? Memory { get; init; }

    [JsonPropertyName("priority")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? Priority { get; init; }

    [JsonPropertyName("oldjobPath")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? OldjobPath { get; init; }

    [JsonPropertyName("fortranPath")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? FortranPath { get; init; }

    [JsonPropertyName("calculationRootDir")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? CalculationRootDir { get; init; }

    [JsonPropertyName("archiveDir")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ArchiveDir { get; init; }

    [JsonPropertyName("draft")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public LocalJobDraftPreviewRequest? Draft { get; init; }
}

public sealed class JobQueueCommandResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;

    [JsonPropertyName("changed")]
    public int Changed { get; init; }

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("stats")]
    public JsonElement Stats { get; init; }

    [JsonPropertyName("snapshot")]
    public JobQueueSnapshot Snapshot { get; init; } = new();
}
