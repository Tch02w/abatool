using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

internal sealed class ResultScopesRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("root")]
    public required string Root { get; init; }

    [JsonPropertyName("includeInternal")]
    public bool IncludeInternal { get; init; }
}

public sealed class ResultScopesResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;

    [JsonPropertyName("nodes")]
    public IReadOnlyList<ResultScopeNode> Nodes { get; init; } = [];

    [JsonPropertyName("count")]
    public int Count { get; init; }

    [JsonPropertyName("warnings")]
    public IReadOnlyList<string> Warnings { get; init; } = [];
}

public sealed class ResultScopeNode
{
    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;

    [JsonPropertyName("parentPath")]
    public string ParentPath { get; init; } = string.Empty;

    [JsonPropertyName("timeDirectory")]
    public string TimeDirectory { get; init; } = string.Empty;

    [JsonPropertyName("indexState")]
    public string IndexState { get; init; } = string.Empty;

    [JsonIgnore]
    public bool CanBuildMissingIndexes => Kind is "root" or "group";

    [JsonIgnore]
    public bool CanRefreshIndex => Kind is "batch" or "odb" && !string.IsNullOrWhiteSpace(TimeDirectory);

    [JsonIgnore]
    public string KindDisplay => Kind switch
    {
        "root" => "结果根目录",
        "group" => "对比组目录",
        "batch" => "提取批次目录",
        "odb" => "模型结果目录",
        "shared_root" => "公共数据目录",
        "shared_odb" => "模型公共数据目录",
        "shared_asset" => "公共数据版本目录",
        _ => "结果目录",
    };

    [JsonIgnore]
    public string IndexStateDisplay => IndexState switch
    {
        "available" => "已索引",
        "missing" => "未索引",
        _ => string.Empty,
    };

    public override string ToString() => string.IsNullOrWhiteSpace(IndexStateDisplay)
        ? Name
        : $"{Name}  ·  {IndexStateDisplay}";
}

public sealed record ResultDirectPageAnchor(
    [property: JsonPropertyName("name")] string Name,
    [property: JsonPropertyName("isDirectory")] bool IsDirectory,
    [property: JsonPropertyName("direction")] string Direction,
    [property: JsonPropertyName("sortAnchor"), JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)] string? SortAnchor = null);

internal sealed class ResultRecordsRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("root")]
    public required string Root { get; init; }

    [JsonPropertyName("scope")]
    public required string Scope { get; init; }

    [JsonPropertyName("timeDirectory")]
    public string TimeDirectory { get; init; } = string.Empty;

    [JsonPropertyName("directDirectory")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? DirectDirectory { get; init; }

    [JsonPropertyName("directAnchor")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public ResultDirectPageAnchor? DirectAnchor { get; init; }

    [JsonPropertyName("sortBy")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? SortBy { get; init; }

    [JsonPropertyName("sortDescending")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingDefault)]
    public bool SortDescending { get; init; }

    [JsonPropertyName("section")]
    public string Section { get; init; } = "all";

    [JsonPropertyName("query")]
    public string Query { get; init; } = string.Empty;

    [JsonPropertyName("useCase")]
    public string UseCase { get; init; } = string.Empty;

    [JsonPropertyName("includeInternal")]
    public bool IncludeInternal { get; init; }

    [JsonPropertyName("offset")]
    public int Offset { get; init; }

    [JsonPropertyName("limit")]
    public int Limit { get; init; } = 500;
}

public sealed class ResultRecordsResponse
{
    [JsonPropertyName("sortBy")]
    public string SortBy { get; init; } = "default";

    [JsonPropertyName("sortDescending")]
    public bool SortDescending { get; init; }

    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;

    [JsonPropertyName("scope")]
    public string Scope { get; init; } = string.Empty;

    [JsonPropertyName("source")]
    public string Source { get; init; } = string.Empty;

    [JsonPropertyName("directDirectory")]
    public string? DirectDirectory { get; init; }

    [JsonPropertyName("records")]
    public IReadOnlyList<ResultRecordItem> Records { get; init; } = [];

    [JsonPropertyName("totalCount")]
    public int TotalCount { get; init; }

    [JsonPropertyName("filteredCount")]
    public int FilteredCount { get; init; }

    [JsonPropertyName("offset")]
    public int Offset { get; init; }

    [JsonPropertyName("limit")]
    public int Limit { get; init; }

    [JsonPropertyName("hasMore")]
    public bool HasMore { get; init; }

    [JsonPropertyName("useCases")]
    public IReadOnlyList<string> UseCases { get; init; } = [];

    [JsonPropertyName("sectionCounts")]
    public IReadOnlyDictionary<string, int> SectionCounts { get; init; } =
        new Dictionary<string, int>();

    [JsonPropertyName("indexMetadata")]
    public IReadOnlyDictionary<string, string> IndexMetadata { get; init; } =
        new Dictionary<string, string>();

    public ResultDirectPageAnchor? PageAnchor(bool before)
    {
        if (Source != "direct" || Records.Count == 0) return null;
        var edge = before ? Records[0] : Records[^1];
        return new(edge.Name, edge.IsDirectory, before ? "before" : "after", edge.SortAnchor);
    }
}

public sealed class ResultRecordItem
{
    [JsonPropertyName("sortAnchor")]
    public string? SortAnchor { get; init; }

    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("relativePath")]
    public string RelativePath { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("suffix")]
    public string Suffix { get; init; } = string.Empty;

    [JsonPropertyName("useCase")]
    public string UseCase { get; init; } = string.Empty;

    [JsonPropertyName("description")]
    public string Description { get; init; } = string.Empty;

    [JsonPropertyName("recommended")]
    public bool Recommended { get; init; }

    [JsonPropertyName("section")]
    public string Section { get; init; } = string.Empty;

    [JsonPropertyName("sizeBytes")]
    public long SizeBytes { get; init; }

    [JsonPropertyName("modifiedAt")]
    public DateTimeOffset? ModifiedAt { get; init; }

    [JsonPropertyName("error")]
    public string Error { get; init; } = string.Empty;

    [JsonPropertyName("internal")]
    public bool Internal { get; init; }

    [JsonPropertyName("isDirectory")]
    public bool IsDirectory { get; init; }

    [JsonIgnore]
    public string RecommendedDisplay => Recommended ? "★" : string.Empty;

    [JsonIgnore]
    public string SizeDisplay => IsDirectory ? string.Empty : FormatFileSize(SizeBytes);

    [JsonIgnore]
    public string ModifiedDisplay => ModifiedAt?.ToLocalTime().ToString("yyyy-MM-dd HH:mm") ?? "";

    private static string FormatFileSize(long bytes)
    {
        if (bytes < 0)
        {
            return "不可用";
        }

        string[] units = ["B", "KB", "MB", "GB", "TB"];
        double value = bytes;
        var unit = 0;
        while (value >= 1024 && unit < units.Length - 1)
        {
            value /= 1024;
            unit++;
        }

        return unit == 0 ? $"{value:0} {units[unit]}" : $"{value:0.0} {units[unit]}";
    }
}

internal sealed class ResultPreviewRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("root")]
    public required string Root { get; init; }

    [JsonPropertyName("path")]
    public required string Path { get; init; }

    [JsonPropertyName("maxRows")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public int? MaxRows { get; init; }
}

public sealed class ResultPreviewResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("sizeBytes")]
    public long SizeBytes { get; init; }

    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;

    [JsonPropertyName("headers")]
    public IReadOnlyList<string> Headers { get; init; } = [];

    [JsonPropertyName("rows")]
    public IReadOnlyList<IReadOnlyList<string>> Rows { get; init; } = [];

    [JsonPropertyName("text")]
    public string Text { get; init; } = string.Empty;

    [JsonPropertyName("truncated")]
    public bool Truncated { get; init; }

    [JsonPropertyName("mediaPath")]
    public string MediaPath { get; init; } = string.Empty;

    [JsonPropertyName("message")]
    public string Message { get; init; } = string.Empty;
}

internal sealed class ResultIndexBuildRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("clientRequestId")]
    public required string ClientRequestId { get; init; }

    [JsonPropertyName("root")]
    public required string Root { get; init; }

    [JsonPropertyName("timeDirectory")]
    public required string TimeDirectory { get; init; }
}

public sealed class ResultIndexOperationSnapshot
{
    private static readonly IReadOnlySet<string> TerminalStatuses =
        new HashSet<string>(StringComparer.Ordinal) { "succeeded", "cancelled", "failed" };

    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("operationId")]
    public string OperationId { get; init; } = string.Empty;

    [JsonPropertyName("batchId")]
    public string? BatchId { get; init; }

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
    public ResultIndexOperationRequest Request { get; init; } = new();

    [JsonPropertyName("progress")]
    public ResultIndexProgress Progress { get; init; } = new();

    [JsonPropertyName("metadata")]
    public IReadOnlyDictionary<string, string> Metadata { get; init; } =
        new Dictionary<string, string>();

    [JsonPropertyName("error")]
    public OdbCompatibilityOperationError? Error { get; init; }

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }

    [JsonIgnore]
    public bool IsTerminal => TerminalStatuses.Contains(Status);
}

public sealed class ResultIndexOperationRequest
{
    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;

    [JsonPropertyName("timeDirectory")]
    public string TimeDirectory { get; init; } = string.Empty;
}

public sealed class ResultIndexProgress
{
    [JsonPropertyName("processed")]
    public int Processed { get; init; }

    [JsonPropertyName("currentItem")]
    public string CurrentItem { get; init; } = string.Empty;
}

public sealed class ResultIndexOperationListResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("operations")]
    public IReadOnlyList<ResultIndexOperationSnapshot> Operations { get; init; } = [];

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }
}

public sealed class ResultIndexBatchSnapshot
{
    public int SchemaVersion { get; init; }
    public string BatchId { get; init; } = string.Empty;
    public string Root { get; init; } = string.Empty;
    public string ScopeDirectory { get; init; } = string.Empty;
    public string Status { get; init; } = string.Empty;
    public int Total { get; init; }
    public int Succeeded { get; init; }
    public int Skipped { get; init; }
    public int Failed { get; init; }
    public int Cancelled { get; init; }
    public int Waiting { get; init; }
    public int Active { get; init; }
    public int Processed { get; init; }
    public string CurrentDirectory { get; init; } = string.Empty;
    public IReadOnlyList<ResultIndexBatchFailure> Failures { get; init; } = [];

    [JsonIgnore]
    public bool IsTerminal => Status is "succeeded" or "failed" or "cancelled";

    internal void Validate(string? expectedId)
    {
        if (SchemaVersion != 1 || string.IsNullOrWhiteSpace(BatchId)
            || (expectedId is not null && BatchId != expectedId)
            || string.IsNullOrWhiteSpace(Root) || string.IsNullOrWhiteSpace(ScopeDirectory)
            || (!IsTerminal && Status is not ("queued" or "running" or "cancelling"))
            || Total < 0 || Succeeded < 0 || Skipped < 0 || Failed < 0 || Cancelled < 0 || Active < 0 || Waiting < 0
            || Processed != (long)Succeeded + Skipped + Failed + Cancelled || Total != (long)Processed + Waiting + Active
            || (IsTerminal && Total != Processed) || Failures is null || Failures.Count > Failed)
            throw new InvalidDataException("补建索引任务返回了无效的进度。");
    }
}

public sealed class ResultIndexBatchFailure
{
    public string TimeDirectory { get; init; } = string.Empty;
    public string Message { get; init; } = string.Empty;
}
