using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class JobNotification
{
    [JsonPropertyName("id")] public string Id { get; init; } = "";
    [JsonPropertyName("source")] public string Source { get; init; } = "";
    [JsonPropertyName("executionId")] public string ExecutionId { get; init; } = "";
    [JsonPropertyName("jobId")] public string JobId { get; init; } = "";
    [JsonPropertyName("jobName")] public string JobName { get; init; } = "";
    [JsonPropertyName("status")] public string Status { get; init; } = "";
    [JsonPropertyName("message")] public string Message { get; init; } = "";
    [JsonPropertyName("workDirectory")] public string WorkDirectory { get; init; } = "";
    [JsonPropertyName("observedAt")] public DateTimeOffset ObservedAt { get; init; }
    [JsonPropertyName("read")] public bool Read { get; init; }
    [JsonIgnore] public string Heading => $"{(Source == "remote" ? "远端" : "本机")} · {JobName} · {StatusLabel}";
    [JsonIgnore] public string StatusLabel => Status switch
    {
        "succeeded" => "已完成", "failed" => "失败", "cancelled" => "已取消", _ => "状态未知",
    };
    [JsonIgnore] public string RecordedTime => $"记录于 {ObservedAt.ToLocalTime():MM-dd HH:mm:ss}";
    [JsonIgnore] public string JobKey => $"{Source}:{JobId}";
}

public sealed class JobNotificationSnapshot
{
    [JsonPropertyName("schemaVersion")] public int SchemaVersion { get; init; }
    [JsonPropertyName("unreadCount")] public int UnreadCount { get; init; }
    [JsonPropertyName("items")] public IReadOnlyList<JobNotification> Items { get; init; } = [];
    [JsonPropertyName("persistenceWarning")] public string? PersistenceWarning { get; init; }

    public bool IsValid => SchemaVersion == 1 && Items is not null && UnreadCount >= Items.Count && Items.Count <= 50
        && (UnreadCount == 0 || Items.Count > 0)
        && Items.All(item => item is not null && item.Id is { Length: 64 } && item.Id.All(Uri.IsHexDigit) && !item.Read
            && item.Source is "local" or "remote" && item.Status is "succeeded" or "failed" or "cancelled"
            && !string.IsNullOrWhiteSpace(item.ExecutionId) && !string.IsNullOrWhiteSpace(item.JobId)
            && !string.IsNullOrWhiteSpace(item.JobName) && item.ObservedAt != default)
        && Items.Select(item => item.Id).Distinct().Count() == Items.Count;
}

public sealed class JobNotificationPresentation
{
    private readonly HashSet<string> _observed = new(StringComparer.Ordinal);
    public JobNotificationSnapshot Current { get; private set; } = new() { SchemaVersion = 1 };

    public bool Apply(JobNotificationSnapshot snapshot)
    {
        if (!snapshot.IsValid) throw new InvalidDataException("作业提醒响应无效");
        var newItems = false;
        foreach (var item in snapshot.Items) newItems |= _observed.Add(item.Id);
        Current = snapshot;
        return newItems;
    }
}
