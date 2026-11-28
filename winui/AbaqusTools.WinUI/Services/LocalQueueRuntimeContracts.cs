using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

internal sealed class LocalQueueControlRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;

    [JsonPropertyName("maxParallel")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MaxParallel { get; init; }

    [JsonPropertyName("existingResultPolicy")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ExistingResultPolicy { get; init; }

    [JsonPropertyName("itemIds")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public IReadOnlyList<string>? ItemIds { get; init; }

    [JsonPropertyName("confirmationId")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ConfirmationId { get; init; }
}

public sealed class QueueTerminationTarget
{
    public required string ItemId { get; init; }
    public required string AttemptId { get; init; }
    public required string JobName { get; init; }
    public required string InpPath { get; init; }
    public bool ArchiveOnly { get; init; }
}

public sealed class QueueTerminationPreview
{
    public required int SchemaVersion { get; init; }
    public required string ConfirmationId { get; init; }
    public required bool SchedulingActive { get; init; }
    public required IReadOnlyList<QueueTerminationTarget> Pending { get; init; }
    public required IReadOnlyList<QueueTerminationTarget> Running { get; init; }
    public required int UntouchedCount { get; init; }

    public void Validate()
    {
        var ids = new HashSet<string>(StringComparer.Ordinal);
        if (SchemaVersion != 1 || string.IsNullOrWhiteSpace(ConfirmationId) || UntouchedCount < 0
            || Pending is null || Running is null || Pending.Concat(Running).Any(target =>
                target is null || string.IsNullOrWhiteSpace(target.ItemId) || string.IsNullOrWhiteSpace(target.JobName)
                || target.InpPath is null || !ids.Add(target.ItemId)) || Running.Any(target => string.IsNullOrWhiteSpace(target.AttemptId)))
            throw new ControlPlaneException("无法核对整队终止的作业范围，请重新读取队列。");
    }

    public bool HasWork => SchedulingActive || Pending.Count > 0 || Running.Count > 0;

    public string Describe()
    {
        var lines = new List<string>();
        if (SchedulingActive) lines.Add("将停止后续调度。");
        static string PathKey(QueueTerminationTarget item) => item.InpPath.Trim().Replace('/', '\\');
        var repeatedNames = Pending.Concat(Running).GroupBy(item => item.JobName, StringComparer.OrdinalIgnoreCase)
            .Where(group => group.Count() > 1).ToDictionary(group => group.Key,
                group => group.ToLookup(PathKey, StringComparer.OrdinalIgnoreCase), StringComparer.OrdinalIgnoreCase);
        string TargetLabel(QueueTerminationTarget item)
        {
            if (!repeatedNames.TryGetValue(item.JobName, out var paths)) return item.JobName;
            if (string.IsNullOrWhiteSpace(item.InpPath)) return $"{item.JobName} · 输入路径不可用 · 作业标识 {item.ItemId}";
            var label = $"{item.JobName} · {item.InpPath}";
            return paths[PathKey(item)].Count() > 1 ? $"{label} · 作业标识 {item.ItemId}" : label;
        }
        void AddGroup(string label, IEnumerable<QueueTerminationTarget> targets)
        {
            var names = targets.Select(TargetLabel).ToArray();
            if (names.Length > 0) lines.Add($"{label}（{names.Length}）{Environment.NewLine}{string.Join(Environment.NewLine, names)}");
        }
        AddGroup("取消待运行或等待前置的作业", Pending);
        AddGroup("请求终止运行中的作业", Running.Where(item => !item.ArchiveOnly));
        AddGroup("请求取消正在进行的归档", Running.Where(item => item.ArchiveOnly));
        if (UntouchedCount > 0) lines.Add($"其余 {UntouchedCount} 个正式作业保持原状态。");
        return string.Join(Environment.NewLine + Environment.NewLine, lines);
    }
}

public sealed class QueueTerminationReceipt
{
    public required int SchemaVersion { get; init; }
    public required string ConfirmationId { get; init; }
    public required string Status { get; init; }
    public required int PendingCancelled { get; init; }
    public required int TerminationRequested { get; init; }
    public required int UntouchedCount { get; init; }
}

public sealed class LocalQueueRuntimeSnapshot
{
    [JsonPropertyName("refreshPending")]
    public bool RefreshPending { get; init; }

    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("active")]
    public bool Active { get; init; }

    [JsonPropertyName("stopRequested")]
    public bool StopRequested { get; init; }

    [JsonPropertyName("schedulerMessage")]
    public string SchedulerMessage { get; init; } = string.Empty;

    [JsonPropertyName("maxParallel")]
    public int MaxParallel { get; init; }

    [JsonPropertyName("existingResultPolicy")]
    public string ExistingResultPolicy { get; init; } = string.Empty;

    [JsonPropertyName("startedAt")]
    public DateTimeOffset? StartedAt { get; init; }

    [JsonPropertyName("activeItemIds")]
    public IReadOnlyList<string> ActiveItemIds { get; init; } = [];

    [JsonPropertyName("operations")]
    public IReadOnlyList<LocalJobRuntimeOperation> Operations { get; init; } = [];

    [JsonPropertyName("queue")]
    public JobQueueSnapshot Queue { get; init; } = new();
}

public sealed class LocalJobRuntimeOperation
{
    [JsonPropertyName("attemptId")]
    public string AttemptId { get; init; } = string.Empty;
    [JsonPropertyName("itemId")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("phase")]
    public string Phase { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("detail")]
    public string Detail { get; init; } = string.Empty;

    [JsonPropertyName("progress")]
    public int Progress { get; init; }

    [JsonPropertyName("startedAt")]
    public DateTimeOffset StartedAt { get; init; }

    [JsonPropertyName("finishedAt")]
    public DateTimeOffset? FinishedAt { get; init; }

    [JsonPropertyName("active")]
    public bool Active { get; init; }

    [JsonPropertyName("paused")]
    public bool Paused { get; init; }

    [JsonPropertyName("archiveOnly")]
    public bool ArchiveOnly { get; init; }

    [JsonIgnore]
    public bool IsArchiving => ArchiveOnly || Phase is "archiving" or "archive_cancelling";

    [JsonPropertyName("logs")]
    public IReadOnlyList<string> Logs { get; init; } = [];
}
