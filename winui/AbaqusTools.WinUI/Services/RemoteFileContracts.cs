using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class RemoteDirectoryListing
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("profileName")]
    public string ProfileName { get; init; } = string.Empty;

    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("parentPath")]
    public string ParentPath { get; init; } = string.Empty;

    [JsonPropertyName("entries")]
    public IReadOnlyList<RemoteDirectoryEntry> Entries { get; init; } = [];
}

public sealed class RemoteDirectoryEntry
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;

    [JsonPropertyName("sizeBytes")]
    public long SizeBytes { get; init; }

    [JsonPropertyName("modifiedAt")]
    public DateTimeOffset? ModifiedAt { get; init; }

    [JsonIgnore]
    public bool IsDirectory => string.Equals(Kind, "directory", StringComparison.Ordinal);

    [JsonIgnore]
    public string KindDisplay => IsDirectory ? "文件夹" : "文件";

    [JsonIgnore]
    public string SizeDisplay => IsDirectory ? "—" : FormatBytes(SizeBytes);

    private static string FormatBytes(long value) => value switch
    {
        >= 1L << 30 => $"{value / (double)(1L << 30):0.0} GB",
        >= 1L << 20 => $"{value / (double)(1L << 20):0.0} MB",
        >= 1L << 10 => $"{value / (double)(1L << 10):0.0} KB",
        _ => $"{value} B",
    };

    public override string ToString() =>
        $"{(IsDirectory ? "📁" : "📄")}  {Name}    {SizeDisplay}";
}

public sealed class RemoteDirectoryListingRequest
{
    [JsonPropertyName("expectedProfile"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RemoteServerProfile? ExpectedProfile { get; init; }

    [JsonPropertyName("sourceOperationId"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SourceOperationId { get; init; }

    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;
}

public sealed class RemoteTransferRequest
{
    [JsonPropertyName("expectedProfile"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RemoteServerProfile? ExpectedProfile { get; init; }

    [JsonPropertyName("sourceOperationId"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SourceOperationId { get; init; }

    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("direction")]
    public string Direction { get; init; } = string.Empty;

    [JsonPropertyName("source")]
    public string Source { get; init; } = string.Empty;

    [JsonPropertyName("destination")]
    public string Destination { get; init; } = string.Empty;

    [JsonPropertyName("overwrite")]
    public bool Overwrite { get; init; }
}

public sealed class RemoteTransferOperationSnapshot
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
    public RemoteTransferOperationRequest Request { get; init; } = new();

    [JsonPropertyName("progress")]
    public RemoteTransferProgress Progress { get; init; } = new();

    [JsonPropertyName("result")]
    public RemoteTransferResult? Result { get; init; }

    [JsonPropertyName("error")]
    public RemoteTransferError? Error { get; init; }

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }

    [JsonIgnore]
    public bool IsTerminal => Status is "succeeded" or "failed" or "cancelled";
}

public sealed class RemoteTransferListSnapshot
{
    public int SchemaVersion { get; init; }
    public List<RemoteTransferOperationSnapshot> Operations { get; init; } = [];
}

public sealed class RemoteTransferOperationRequest
{
    [JsonPropertyName("sourceOperationId")]
    public string? SourceOperationId { get; init; }

    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("direction")]
    public string Direction { get; init; } = string.Empty;

    [JsonPropertyName("source")]
    public string Source { get; init; } = string.Empty;

    [JsonPropertyName("destination")]
    public string Destination { get; init; } = string.Empty;

    [JsonPropertyName("overwrite")]
    public bool Overwrite { get; init; }
}

public sealed class RemoteTransferProgress
{
    [JsonPropertyName("completedBytes")]
    public long CompletedBytes { get; init; }

    [JsonPropertyName("totalBytes")]
    public long TotalBytes { get; init; }

    [JsonPropertyName("percent")]
    public int Percent { get; init; }
}

public sealed class RemoteTransferResult
{
    [JsonPropertyName("profileName")]
    public string ProfileName { get; init; } = string.Empty;

    [JsonPropertyName("direction")]
    public string Direction { get; init; } = string.Empty;

    [JsonPropertyName("source")]
    public string Source { get; init; } = string.Empty;

    [JsonPropertyName("destination")]
    public string Destination { get; init; } = string.Empty;

    [JsonPropertyName("sizeBytes")]
    public long SizeBytes { get; init; }
}

public sealed class RemoteTransferError
{
    [JsonPropertyName("code")]
    public string Code { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;
}
