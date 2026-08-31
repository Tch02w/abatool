using System.Text.Json;
using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public enum ControlPlaneState
{
    Disconnected,
    Connecting,
    Starting,
    Ready,
    Error,
}

public sealed class ControlPlaneStateChangedEventArgs(
    ControlPlaneState state,
    string message,
    Exception? exception = null) : EventArgs
{
    public ControlPlaneState State { get; } = state;

    public string Message { get; } = message;

    public Exception? Exception { get; } = exception;
}

public sealed class ControlPlaneDescriptor
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("apiVersion")]
    public string ApiVersion { get; init; } = string.Empty;

    [JsonPropertyName("instanceId")]
    public string InstanceId { get; init; } = string.Empty;

    [JsonPropertyName("pid")]
    public int Pid { get; init; }

    [JsonPropertyName("host")]
    public string Host { get; init; } = string.Empty;

    [JsonPropertyName("port")]
    public int Port { get; init; }

    [JsonPropertyName("baseUrl")]
    public string BaseUrl { get; init; } = string.Empty;

    [JsonPropertyName("token")]
    public string Token { get; init; } = string.Empty;

    [JsonPropertyName("startedAt")]
    public DateTimeOffset StartedAt { get; init; }

    [JsonPropertyName("launchToken")]
    public string LaunchToken { get; init; } = string.Empty;
}

internal sealed class HealthResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("apiVersion")]
    public string ApiVersion { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("instanceId")]
    public string InstanceId { get; init; } = string.Empty;
}

internal sealed class OdbDiscoveryRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("root")]
    public required string Root { get; init; }

    [JsonPropertyName("recursive")]
    public bool Recursive { get; init; } = true;
}

internal sealed class OdbCompatibilityCheckRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("clientRequestId")]
    public required string ClientRequestId { get; init; }

    [JsonPropertyName("root")]
    public required string Root { get; init; }

    [JsonPropertyName("paths")]
    public required IReadOnlyList<string> Paths { get; init; }

    [JsonPropertyName("forceRescan")]
    public bool ForceRescan { get; init; }
}

public sealed class OdbDiscoveryResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("discoveryId")]
    public string DiscoveryId { get; init; } = string.Empty;

    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;

    [JsonPropertyName("recursive")]
    public bool Recursive { get; init; }

    [JsonPropertyName("odbs")]
    public IReadOnlyList<OdbDiscoveryItem> Odbs { get; init; } = [];

    [JsonPropertyName("count")]
    public int Count { get; init; }

    [JsonPropertyName("warnings")]
    public IReadOnlyList<string> Warnings { get; init; } = [];

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }
}

public sealed class OdbDiscoveryItem
{
    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("relativePath")]
    public string RelativePath { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("sizeBytes")]
    public long SizeBytes { get; init; }

    [JsonPropertyName("modifiedAt")]
    public DateTimeOffset ModifiedAt { get; init; }

    [JsonIgnore]
    public string SizeDisplay => FormatFileSize(SizeBytes);

    [JsonIgnore]
    public string ModifiedDisplay => ModifiedAt == DateTimeOffset.MinValue
        ? "不可用"
        : ModifiedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss");

    private static string FormatFileSize(long bytes)
    {
        string[] units = ["B", "KB", "MB", "GB", "TB"];
        double value = Math.Max(0, bytes);
        var unit = 0;
        while (value >= 1024 && unit < units.Length - 1)
        {
            value /= 1024;
            unit++;
        }

        return unit == 0 ? $"{value:0} {units[unit]}" : $"{value:0.##} {units[unit]}";
    }
}

public sealed class OdbCompatibilityOperationSnapshot
{
    private static readonly IReadOnlySet<string> TerminalStatuses =
        new HashSet<string>(StringComparer.Ordinal)
        {
            "succeeded",
            "cancelled",
            "failed",
        };

    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("operationId")]
    public string OperationId { get; init; } = string.Empty;

    [JsonPropertyName("attemptId")]
    public string AttemptId { get; init; } = string.Empty;

    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("createdAt")]
    public DateTimeOffset CreatedAt { get; init; }

    [JsonPropertyName("updatedAt")]
    public DateTimeOffset UpdatedAt { get; init; }

    [JsonPropertyName("version")]
    public long Version { get; init; }

    [JsonPropertyName("progress")]
    public OdbCompatibilityProgress Progress { get; init; } = new();

    [JsonPropertyName("request")]
    public OdbCompatibilityOperationRequest? Request { get; init; }

    [JsonPropertyName("results")]
    public IReadOnlyList<OdbCompatibilityResult> Results { get; init; } = [];

    [JsonPropertyName("error")]
    public OdbCompatibilityOperationError? Error { get; init; }

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }

    [JsonIgnore]
    public bool IsTerminal => TerminalStatuses.Contains(Status);

    [JsonIgnore]
    public bool IsSuccessful => string.Equals(Status, "succeeded", StringComparison.Ordinal);
}

public sealed class OdbCompatibilityOperationRequest
{
    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;

    [JsonPropertyName("paths")]
    public IReadOnlyList<string> Paths { get; init; } = [];

    [JsonPropertyName("forceRescan")]
    public bool ForceRescan { get; init; }
}

public sealed class OdbOperationListResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("operations")]
    public IReadOnlyList<OdbCompatibilityOperationSnapshot> Operations { get; init; } = [];

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }
}

public sealed class OdbCompatibilityProgress
{
    [JsonPropertyName("completed")]
    public int Completed { get; init; }

    [JsonPropertyName("total")]
    public int Total { get; init; }

    [JsonPropertyName("currentItem")]
    public string? CurrentItem { get; init; }
}

public sealed class OdbCompatibilityResult
{
    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("sizeBytes")]
    public long SizeBytes { get; init; }

    [JsonPropertyName("stepCount")]
    public int? StepCount { get; init; }
}

public sealed class OdbCompatibilityOperationError
{
    [JsonPropertyName("code")]
    public string Code { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("retryable")]
    public bool Retryable { get; init; }

    [JsonPropertyName("traceId")]
    public string TraceId { get; init; } = string.Empty;

    [JsonPropertyName("details")]
    public JsonElement Details { get; init; }
}

internal sealed class ErrorEnvelope
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("error")]
    public ControlPlaneError? Error { get; init; }
}

internal sealed class ControlPlaneError
{
    [JsonPropertyName("code")]
    public string Code { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;

    [JsonPropertyName("retryable")]
    public bool Retryable { get; init; }

    [JsonPropertyName("traceId")]
    public string TraceId { get; init; } = string.Empty;

    [JsonPropertyName("details")]
    public JsonElement Details { get; init; }
}

public sealed class ControlPlaneException : Exception
{
    public ControlPlaneException(
        string message,
        string? code = null,
        string? traceId = null,
        bool retryable = false,
        Exception? innerException = null)
        : base(message, innerException)
    {
        Code = code;
        TraceId = traceId;
        Retryable = retryable;
    }

    public string? Code { get; }

    public string? TraceId { get; }

    public bool Retryable { get; }

    public string ToDisplayMessage()
    {
        var suffix = string.IsNullOrWhiteSpace(TraceId) ? string.Empty : $"（跟踪 ID：{TraceId}）";
        return $"{Message}{suffix}";
    }
}
