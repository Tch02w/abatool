using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class RestartChainSnapshot
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("nodes")]
    public IReadOnlyList<RestartChainNode> Nodes { get; init; } = [];

    [JsonPropertyName("graphNodes")]
    public IReadOnlyList<RestartChainNode> GraphNodes { get; init; } = [];

    [JsonPropertyName("graphNodeCount")]
    public int GraphNodeCount { get; init; }

    [JsonPropertyName("nodeCount")]
    public int NodeCount { get; init; }

    [JsonPropertyName("chainCount")]
    public int ChainCount { get; init; }

    [JsonPropertyName("checks")]
    public RestartChainChecks Checks { get; init; } = new();

    [JsonPropertyName("hasIssues")]
    public bool HasIssues { get; init; }
}

public sealed class RestartChainChecks
{
    [JsonPropertyName("cycleCount")]
    public int CycleCount { get; init; }

    [JsonPropertyName("missingParentCount")]
    public int MissingParentCount { get; init; }

    [JsonPropertyName("incompatiblePathCount")]
    public int IncompatiblePathCount { get; init; }

    [JsonPropertyName("upstreamInvalidCount")]
    public int UpstreamInvalidCount { get; init; }

    [JsonPropertyName("validCount")]
    public int ValidCount { get; init; }
}

public sealed class RestartChainNode
{
    [JsonPropertyName("itemId")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("jobId")]
    public string JobId { get; init; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; init; } = string.Empty;

    [JsonPropertyName("parentJobId")]
    public string ParentJobId { get; init; } = string.Empty;

    [JsonPropertyName("parentJobName")]
    public string ParentJobName { get; init; } = string.Empty;

    [JsonPropertyName("stage")]
    public int Stage { get; init; }

    [JsonPropertyName("jobStatus")]
    public string JobStatus { get; init; } = string.Empty;

    [JsonPropertyName("validationStatus")]
    public string ValidationStatus { get; init; } = string.Empty;

    [JsonPropertyName("validationMessage")]
    public string ValidationMessage { get; init; } = string.Empty;

    [JsonPropertyName("inpPath")]
    public string InpPath { get; init; } = string.Empty;

    [JsonPropertyName("oldjobPath")]
    public string OldjobPath { get; init; } = string.Empty;

    [JsonPropertyName("outputOdb")]
    public string OutputOdb { get; init; } = string.Empty;

    [JsonPropertyName("isRestart")]
    public bool IsRestart { get; init; }

    [JsonIgnore]
    public string StageDisplay => Stage <= 0 ? "—" : Stage.ToString();

    [JsonIgnore]
    public string ArrowDisplay => "→";

    [JsonIgnore]
    public string ValidationStatusDisplay => ValidationStatus switch
    {
        "valid" => "有效",
        "cycle" => "循环依赖",
        "missing_parent" => "缺少父作业",
        "incompatible_path" => "路径不兼容",
        "upstream_invalid" => "上游依赖异常",
        _ => ValidationStatus,
    };

    [JsonIgnore]
    public string PathDisplay => string.IsNullOrWhiteSpace(OldjobPath)
        ? InpPath
        : OldjobPath;
}
