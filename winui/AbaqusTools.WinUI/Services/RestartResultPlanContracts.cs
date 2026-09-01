using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

internal sealed class RestartResultPlanRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("itemId")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("outputDirectory")]
    public string OutputDirectory { get; init; } = string.Empty;
}

public sealed class RestartResultPlan
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("planKind")]
    public string PlanKind { get; init; } = string.Empty;

    [JsonPropertyName("targetItemId")]
    public string TargetItemId { get; init; } = string.Empty;

    [JsonPropertyName("targetJobId")]
    public string TargetJobId { get; init; } = string.Empty;

    [JsonPropertyName("targetJobName")]
    public string TargetJobName { get; init; } = string.Empty;

    [JsonPropertyName("valid")]
    public bool Valid { get; init; }

    [JsonPropertyName("issues")]
    public IReadOnlyList<string> Issues { get; init; } = [];

    [JsonPropertyName("ancestry")]
    public IReadOnlyList<RestartResultAncestryItem> Ancestry { get; init; } = [];

    [JsonPropertyName("steps")]
    public IReadOnlyList<RestartResultStep> Steps { get; init; } = [];

    [JsonPropertyName("finalOutputOdb")]
    public string FinalOutputOdb { get; init; } = string.Empty;
}

public sealed class RestartResultAncestryItem
{
    [JsonPropertyName("itemId")]
    public string ItemId { get; init; } = string.Empty;

    [JsonPropertyName("jobId")]
    public string JobId { get; init; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; init; } = string.Empty;

    [JsonPropertyName("runMode")]
    public string RunMode { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("outputOdb")]
    public string OutputOdb { get; init; } = string.Empty;

    [JsonIgnore]
    public string Display => $"{JobName} · {Status}";
}

public sealed class RestartResultStep
{
    [JsonPropertyName("index")]
    public int Index { get; init; }

    [JsonPropertyName("jobId")]
    public string JobId { get; init; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; init; } = string.Empty;

    [JsonPropertyName("originalOdb")]
    public string OriginalOdb { get; init; } = string.Empty;

    [JsonPropertyName("restartOdb")]
    public string RestartOdb { get; init; } = string.Empty;

    [JsonPropertyName("outputOdb")]
    public string OutputOdb { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonIgnore]
    public string Title => $"步骤 {Index} · 生成 {JobName} 的完整结果";

    [JsonIgnore]
    public string Detail => $"{OriginalOdb}\n+ {RestartOdb}\n→ {OutputOdb}";
}
