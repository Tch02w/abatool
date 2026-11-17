using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

internal sealed class OdbMergeOperationCreateRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("originalOdb")]
    public string OriginalOdb { get; init; } = string.Empty;

    [JsonPropertyName("restartOdb")]
    public string RestartOdb { get; init; } = string.Empty;

    [JsonPropertyName("outputOdb")]
    public string OutputOdb { get; init; } = string.Empty;

    [JsonPropertyName("includeHistory")]
    public bool IncludeHistory { get; init; }

    [JsonPropertyName("compressResult")]
    public bool CompressResult { get; init; }

    [JsonPropertyName("copyOriginal")]
    public bool CopyOriginal { get; init; }

    [JsonPropertyName("conflictPolicy")]
    public string ConflictPolicy { get; init; } = "auto_number";
}

public sealed class OdbMergeOperationSnapshot
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

    [JsonPropertyName("request")]
    public OdbMergeOperationRequest? Request { get; init; }

    [JsonPropertyName("progress")]
    public OdbMergeOperationProgress Progress { get; init; } = new();

    [JsonPropertyName("logs")]
    public IReadOnlyList<string> Logs { get; init; } = [];

    [JsonPropertyName("result")]
    public OdbMergeOperationResult? Result { get; init; }

    [JsonPropertyName("error")]
    public OdbCompatibilityOperationError? Error { get; init; }

    [JsonPropertyName("persistenceWarning")]
    public string? PersistenceWarning { get; init; }

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }

    [JsonIgnore]
    public bool IsTerminal => TerminalStatuses.Contains(Status);

    [JsonIgnore]
    public bool IsSuccessful => string.Equals(Status, "succeeded", StringComparison.Ordinal);

    [JsonIgnore]
    public bool IsInterrupted => string.Equals(Error?.Code, "ODB_MERGE_INTERRUPTED", StringComparison.Ordinal);

    [JsonIgnore]
    public string CompletionMessage => !string.IsNullOrWhiteSpace(PersistenceWarning)
        ? PersistenceWarning
        : Error?.Message ?? (string.IsNullOrWhiteSpace(Progress.Phase)
            ? (IsSuccessful ? "ODB 合并与只读验证完成。" : "ODB 合并未成功完成。") : Progress.Phase);
}

public sealed class OdbMergeOperationRequest
{
    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("originalOdb")]
    public string OriginalOdb { get; init; } = string.Empty;

    [JsonPropertyName("restartOdb")]
    public string RestartOdb { get; init; } = string.Empty;

    [JsonPropertyName("outputOdb")]
    public string OutputOdb { get; init; } = string.Empty;

    [JsonPropertyName("includeHistory")]
    public bool IncludeHistory { get; init; }

    [JsonPropertyName("compressResult")]
    public bool CompressResult { get; init; }

    [JsonPropertyName("copyOriginal")]
    public bool CopyOriginal { get; init; }

    [JsonPropertyName("conflictPolicy")]
    public string ConflictPolicy { get; init; } = string.Empty;
}

public sealed class OdbMergeOperationProgress
{
    [JsonPropertyName("percent")]
    public int Percent { get; init; }

    [JsonPropertyName("phase")]
    public string Phase { get; init; } = string.Empty;
}

public sealed class OdbMergeOperationResult
{
    [JsonPropertyName("validationReport")]
    public string? ValidationReport { get; init; }
    [JsonPropertyName("outputOdb")]
    public string OutputOdb { get; init; } = string.Empty;

    [JsonPropertyName("originalBackup")]
    public string OriginalBackup { get; init; } = string.Empty;

    [JsonPropertyName("restartBackup")]
    public string RestartBackup { get; init; } = string.Empty;

    [JsonPropertyName("command")]
    public string Command { get; init; } = string.Empty;
}

public sealed class OdbMergeOperationListResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("operations")]
    public IReadOnlyList<OdbMergeOperationSnapshot> Operations { get; init; } = [];

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }
}
