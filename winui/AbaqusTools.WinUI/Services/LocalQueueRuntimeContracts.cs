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
}

public sealed class LocalQueueRuntimeSnapshot
{
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

    [JsonPropertyName("logs")]
    public IReadOnlyList<string> Logs { get; init; } = [];
}
