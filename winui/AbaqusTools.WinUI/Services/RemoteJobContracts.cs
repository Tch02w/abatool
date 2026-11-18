using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class RemoteJobRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; init; } = string.Empty;

    [JsonPropertyName("inputMode")]
    public string InputMode { get; init; } = string.Empty;

    [JsonPropertyName("inputPath")]
    public string InputPath { get; init; } = string.Empty;

    [JsonPropertyName("oldjobPath")]
    public string OldjobPath { get; init; } = string.Empty;

    [JsonPropertyName("fortranPath")]
    public string FortranPath { get; init; } = string.Empty;

    [JsonPropertyName("cpus")]
    public int Cpus { get; init; }

    [JsonPropertyName("memory")]
    public string Memory { get; init; } = string.Empty;

    [JsonPropertyName("datacheck")]
    public bool Datacheck { get; init; }

    [JsonPropertyName("notify")]
    public bool Notify { get; init; } = true;
}

public sealed class RemoteJobPreview
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("valid")]
    public bool Valid { get; init; }

    [JsonPropertyName("profileName")]
    public string ProfileName { get; init; } = string.Empty;

    [JsonPropertyName("inputMode")]
    public string InputMode { get; init; } = string.Empty;

    [JsonPropertyName("computeRoot")]
    public string ComputeRoot { get; init; } = string.Empty;

    [JsonPropertyName("command")]
    public string Command { get; init; } = string.Empty;
}

public sealed class RemoteJobOperationSnapshot
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("operationId")]
    public string OperationId { get; init; } = string.Empty;

    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("updatedAt")]
    public DateTimeOffset UpdatedAt { get; init; }

    [JsonPropertyName("version")]
    public int Version { get; init; }

    [JsonPropertyName("request")]
    public RemoteJobOperationRequest Request { get; init; } = new();

    [JsonPropertyName("phase")]
    public string Phase { get; init; } = string.Empty;

    [JsonPropertyName("percent")]
    public int Percent { get; init; }

    [JsonPropertyName("workDirectory")]
    public string WorkDirectory { get; init; } = string.Empty;

    [JsonPropertyName("processId")]
    public int ProcessId { get; init; }

    [JsonPropertyName("paused")]
    public bool Paused { get; init; }

    [JsonPropertyName("logs")]
    public IReadOnlyList<string> Logs { get; init; } = [];

    [JsonPropertyName("files")]
    public IReadOnlyDictionary<string, string> Files { get; init; } =
        new Dictionary<string, string>(StringComparer.Ordinal);

    [JsonPropertyName("error")]
    public RemoteJobError? Error { get; init; }

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }

    [JsonPropertyName("trackingState")]
    public string TrackingState { get; init; } = string.Empty;

    [JsonPropertyName("persistenceWarning")]
    public string? PersistenceWarning { get; init; }

    [JsonIgnore]
    public bool CanPauseResume => !IsTerminal && Status == "running"
        && TrackingState is "" or "tracking";

    [JsonIgnore]
    public string StatusDisplay => !IsTerminal && TrackingState is "reconnecting" or "submission_unknown" or "unverified"
        ? TrackingState switch
        {
            "reconnecting" => "等待重连核对", "submission_unknown" => "提交状态待核对", _ => "等待状态核对",
        }
        : Status switch
        {
            "queued" => "等待远端执行", "starting" => "正在准备", "running" => "远端运行中",
            "cancelling" => "正在终止", "succeeded" => "已完成", "cancelled" => "已取消",
            "failed" => "失败", _ => "未知",
        };

    [JsonIgnore]
    public bool IsTerminal => Status is "succeeded" or "failed" or "cancelled";
}

public sealed class RemoteJobOperationRequest
{
    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; init; } = string.Empty;

    [JsonPropertyName("inputMode")]
    public string InputMode { get; init; } = string.Empty;

    [JsonPropertyName("inputPath")]
    public string InputPath { get; init; } = string.Empty;

    [JsonPropertyName("cpus")]
    public int Cpus { get; init; }

    [JsonPropertyName("memory")]
    public string Memory { get; init; } = string.Empty;

    [JsonPropertyName("datacheck")]
    public bool Datacheck { get; init; }
}

public sealed class RemoteJobError
{
    [JsonPropertyName("code")]
    public string Code { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;
}

public sealed class RemoteJobListResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("operations")]
    public IReadOnlyList<RemoteJobOperationSnapshot> Operations { get; init; } = [];

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }
}

public sealed class RemoteJobControlRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;
}
