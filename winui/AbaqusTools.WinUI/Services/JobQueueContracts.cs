using System.Text.Json.Serialization;
using System.Text.Json;
using System.ComponentModel;
using System.Reflection;

namespace AbaqusTools.WinUI.Services;

public sealed class JobQueueSnapshot
{
    [JsonPropertyName("externalScanActive")]
    public bool ExternalScanActive { get; init; }

    [JsonPropertyName("externalManualScanActive")]
    public bool ExternalManualScanActive { get; init; }

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

    public bool HasSameExplorerContent(JobQueueSnapshot other) =>
        CandidateCount == other.CandidateCount && QueueCount == other.QueueCount
        && Candidates.Select(item => (item.ItemId, item.JobName, item.InpPath, item.Message, item.Valid, item.Selected))
            .SequenceEqual(other.Candidates.Select(item => (item.ItemId, item.JobName, item.InpPath, item.Message, item.Valid, item.Selected)))
        && QueueItems.Select(item => (item.ItemId, item.JobName, item.InpPath, item.Status))
            .SequenceEqual(other.QueueItems.Select(item => (item.ItemId, item.JobName, item.InpPath, item.Status)));
}

public sealed class JobQueueItem : INotifyPropertyChanged
{
    private static readonly PropertyInfo[] SnapshotProperties = typeof(JobQueueItem).GetProperties()
        .Where(property => property.GetCustomAttribute<JsonPropertyNameAttribute>() is not null).ToArray();
    public event PropertyChangedEventHandler? PropertyChanged;

    public void UpdateFrom(JobQueueItem snapshot)
    {
        if (ItemId != snapshot.ItemId) throw new ArgumentException("Queue row identity must not change.");
        var changed = new HashSet<string>(StringComparer.Ordinal);
        foreach (var property in SnapshotProperties)
        {
            var before = property.GetValue(this);
            var after = property.GetValue(snapshot);
            if (Equals(before, after) || (before is IReadOnlyList<string> left
                && after is IReadOnlyList<string> right && left.SequenceEqual(right))) continue;
            property.SetValue(this, after);
            changed.Add(property.Name);
        }
        // Notify only changed fields and the displays that depend on them.
        void Derived(string name, params string[] inputs)
        {
            if (inputs.Any(changed.Contains)) changed.Add(name);
        }
        Derived(nameof(SelectedDisplay), nameof(Selected));
        Derived(nameof(FortranName), nameof(FortranPath));
        Derived(nameof(CoresDisplay), nameof(Cores));
        Derived(nameof(PriorityDisplay), nameof(Priority));
        Derived(nameof(SchedulingDisplay), nameof(Held));
        Derived(nameof(HasPublishedArchive), nameof(ArchiveDestination), nameof(ArchiveStatus));
        Derived(nameof(ArchiveDetailsDisplay), nameof(ArchiveStatus), nameof(HasPublishedArchive), nameof(ArchiveError), nameof(ArchiveDestination));
        Derived(nameof(ResultMessageDisplay), nameof(Message), nameof(ArchiveStatus));
        Derived(nameof(RuntimeMemoryDisplay), nameof(MemoryObservationStatus), nameof(RuntimeMemoryBytes));
        Derived(nameof(MemoryDetailsDisplay), nameof(RuntimeMemoryDisplay), nameof(MemoryPeakBytes), nameof(MemoryEstimatedBytes), nameof(MemoryEstimateSource));
        foreach (var property in changed) PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(property));
    }

    [JsonPropertyName("attemptId")]
    public string AttemptId { get; set; } = string.Empty;
    [JsonPropertyName("index")]
    public int Index { get; set; }

    [JsonPropertyName("itemId")]
    public string ItemId { get; set; } = string.Empty;

    [JsonPropertyName("jobId")]
    public string JobId { get; set; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; set; } = string.Empty;

    [JsonPropertyName("inpPath")]
    public string InpPath { get; set; } = string.Empty;

    [JsonPropertyName("source")]
    public string Source { get; set; } = string.Empty;

    [JsonPropertyName("selected")]
    public bool Selected { get; set; }

    [JsonPropertyName("valid")]
    public bool Valid { get; set; }

    [JsonPropertyName("message")]
    public string Message { get; set; } = string.Empty;

    [JsonPropertyName("runMode")]
    public string RunMode { get; set; } = string.Empty;

    [JsonPropertyName("jobType")]
    public string JobType { get; set; } = string.Empty;

    [JsonPropertyName("oldjobName")]
    public string OldjobName { get; set; } = string.Empty;

    [JsonPropertyName("oldjobPath")]
    public string OldjobPath { get; set; } = string.Empty;

    [JsonPropertyName("fortranPath")]
    public string FortranPath { get; set; } = string.Empty;

    [JsonPropertyName("gpuCount")] public int? GpuCount { get; set; }
    [JsonPropertyName("explicitPrecision")] public string ExplicitPrecision { get; set; } = "default";
    [JsonPropertyName("outputPrecision")] public string OutputPrecision { get; set; } = "default";

    [JsonPropertyName("cores")]
    public int Cores { get; set; }

    [JsonPropertyName("memory")]
    public string Memory { get; set; } = string.Empty;

    [JsonPropertyName("runtimeMemoryBytes")]
    public long RuntimeMemoryBytes { get; set; }

    [JsonPropertyName("memoryObservationStatus")]
    public string MemoryObservationStatus { get; set; } = string.Empty;

    [JsonPropertyName("memoryPeakBytes")]
    public long MemoryPeakBytes { get; set; }

    [JsonPropertyName("memoryEstimatedBytes")]
    public long MemoryEstimatedBytes { get; set; }

    [JsonPropertyName("memorySampleCount")]
    public int MemorySampleCount { get; set; }

    [JsonPropertyName("memoryEstimateSource")]
    public string MemoryEstimateSource { get; set; } = string.Empty;

    [JsonPropertyName("priority")]
    public int Priority { get; set; }

    [JsonPropertyName("held")]
    public bool Held { get; set; }

    [JsonPropertyName("schedulerState")]
    public string SchedulerState { get; set; } = string.Empty;

    [JsonPropertyName("pendingReason")]
    public string PendingReason { get; set; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; set; } = string.Empty;

    [JsonPropertyName("effectiveWorkDir")]
    public string EffectiveWorkDir { get; set; } = string.Empty;

    [JsonPropertyName("calculationRootDir")]
    public string CalculationRootDir { get; set; } = string.Empty;

    [JsonPropertyName("archiveDir")]
    public string ArchiveDir { get; set; } = string.Empty;

    [JsonPropertyName("archiveAfterComplete")]
    public bool ArchiveAfterComplete { get; set; }

    [JsonPropertyName("cleanupAfterArchive")]
    public bool CleanupAfterArchive { get; set; }

    [JsonPropertyName("archiveDestination")]
    public string ArchiveDestination { get; set; } = string.Empty;

    [JsonPropertyName("archiveStatus")]
    public string ArchiveStatus { get; set; } = string.Empty;

    [JsonPropertyName("archiveError")]
    public string ArchiveError { get; set; } = string.Empty;

    [JsonPropertyName("archiveRecoveryAvailable")]
    public bool ArchiveRecoveryAvailable { get; set; }

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
    public string Elapsed { get; set; } = string.Empty;

    [JsonPropertyName("isExternal")]
    public bool IsExternal { get; set; }

    [JsonPropertyName("dependencyJobIds")]
    public IReadOnlyList<string> DependencyJobIds { get; set; } = [];

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

    [JsonPropertyName("cleanupAfterArchive")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? CleanupAfterArchive { get; init; }

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
