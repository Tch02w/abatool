using System.Text.Json;
using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

internal sealed class OdbPostprocessScanCreateRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("clientRequestId")]
    public required string ClientRequestId { get; init; }

    [JsonPropertyName("root")]
    public required string Root { get; init; }

    [JsonPropertyName("paths")]
    public required IReadOnlyList<string> Paths { get; init; }

    [JsonPropertyName("parallelWorkers")]
    public int ParallelWorkers { get; init; }

    [JsonPropertyName("forceRescan")]
    public bool ForceRescan { get; init; }
}

public sealed record OdbPostprocessRunCreateRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = Guid.NewGuid().ToString("D");

    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;

    [JsonPropertyName("parallelWorkers")]
    public int ParallelWorkers { get; init; } = 2;

    [JsonPropertyName("forceRescan")]
    public bool ForceRescan { get; init; }

    [JsonPropertyName("fullTimehistoryFreebody")]
    public bool FullTimehistoryFreebody { get; init; }

    [JsonPropertyName("rebarMethod")]
    public string RebarMethod { get; init; } = "element_cut";

    [JsonPropertyName("expectedLongitudinalRebarCount")]
    public int ExpectedLongitudinalRebarCount { get; init; }

    [JsonPropertyName("imageSizeUnit")]
    public string ImageSizeUnit { get; init; } = "px";

    [JsonPropertyName("imageWidth")]
    public int ImageWidth { get; init; } = 1500;

    [JsonPropertyName("imageHeight")]
    public int ImageHeight { get; init; } = 1000;

    [JsonPropertyName("exportWhiteBackgroundPng")]
    public bool ExportWhiteBackgroundPng { get; init; } = true;

    [JsonPropertyName("exportTransparentBackgroundPng")]
    public bool ExportTransparentBackgroundPng { get; init; } = true;

    [JsonPropertyName("animationFps")]
    public int AnimationFps { get; init; } = 25;

    [JsonPropertyName("animationDurationSeconds")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public double? AnimationDurationSeconds { get; init; }

    [JsonPropertyName("rebarCutToleranceMm")]
    public double RebarCutToleranceMm { get; init; } = 0.0001;

    [JsonPropertyName("jobs")]
    public IReadOnlyList<OdbPostprocessJobDraft> Jobs { get; init; } = [];

    [JsonPropertyName("groups")]
    public IReadOnlyList<OdbPostprocessGroupDraft> Groups { get; init; } = [];
}

public sealed class OdbPostprocessJobDraft
{
    [JsonPropertyName("path")]
    public string Path { get; set; } = string.Empty;

    [JsonPropertyName("startStep")]
    public string StartStep { get; set; } = string.Empty;

    [JsonPropertyName("endStep")]
    public string EndStep { get; set; } = string.Empty;

    [JsonPropertyName("frameMode")]
    public string FrameMode { get; set; } = "auto";

    [JsonPropertyName("manualSequenceExpression")]
    public string ManualSequenceExpression { get; set; } = string.Empty;

    [JsonPropertyName("loadDirection")]
    public string LoadDirection { get; set; } = string.Empty;

    [JsonPropertyName("loadSet")]
    public string LoadSet { get; set; } = string.Empty;

    [JsonPropertyName("pileType")]
    public string PileType { get; set; } = "RC";

    [JsonPropertyName("pileDisplaySet")]
    public string PileDisplaySet { get; set; } = string.Empty;

    [JsonPropertyName("pileConcreteSet")]
    public string PileConcreteSet { get; set; } = string.Empty;

    [JsonPropertyName("pileSteelSet")]
    public string PileSteelSet { get; set; } = string.Empty;

    [JsonPropertyName("soilSet")]
    public string SoilSet { get; set; } = string.Empty;

    [JsonPropertyName("rebarSet")]
    public string RebarSet { get; set; } = string.Empty;

    [JsonPropertyName("reinforcementMode")]
    public string ReinforcementMode { get; set; } = "required";

    [JsonPropertyName("longitudinalMaterial")]
    public string LongitudinalMaterial { get; set; } = "HRB400";

    [JsonPropertyName("rebarDiameterMm")]
    public double RebarDiameterMm { get; set; } = 32;

    [JsonPropertyName("prefractureSequenceIndex")]
    public int PrefractureSequenceIndex { get; set; } = -1;

    public OdbPostprocessJobDraft Clone() => (OdbPostprocessJobDraft)MemberwiseClone();
}

public sealed record OdbPostprocessGroupDraft
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("members")]
    public IReadOnlyList<string> Members { get; init; } = [];

    [JsonPropertyName("standalone")]
    public bool Standalone { get; init; }

    [JsonPropertyName("legendOverrides")]
    public IReadOnlyDictionary<string, OdbLegendOverride> LegendOverrides { get; init; }
        = new Dictionary<string, OdbLegendOverride>();
}

public sealed class OdbLegendOverride
{
    [JsonPropertyName("mode")]
    public string Mode { get; init; } = "manual";

    [JsonPropertyName("min")]
    public double Minimum { get; init; }

    [JsonPropertyName("max")]
    public double Maximum { get; init; }
}

public sealed class OdbPostprocessOperationSnapshot
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
    public OdbPostprocessOperationRequestSummary Request { get; init; } = new();

    [JsonPropertyName("progress")]
    public OdbPostprocessProgress Progress { get; init; } = new();

    [JsonPropertyName("logs")]
    public IReadOnlyList<string> Logs { get; init; } = [];

    [JsonPropertyName("result")]
    public OdbPostprocessResult? Result { get; init; }

    [JsonPropertyName("error")]
    public OdbCompatibilityOperationError? Error { get; init; }

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }

    [JsonIgnore]
    public bool IsTerminal => TerminalStatuses.Contains(Status);
}

public sealed class OdbPostprocessOperationRequestSummary
{
    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = string.Empty;

    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;

    [JsonPropertyName("paths")]
    public IReadOnlyList<string> Paths { get; init; } = [];

    [JsonPropertyName("jobCount")]
    public int JobCount { get; init; }

    [JsonPropertyName("groupCount")]
    public int GroupCount { get; init; }

    [JsonPropertyName("parallelWorkers")]
    public int ParallelWorkers { get; init; }

    [JsonPropertyName("forceRescan")]
    public bool ForceRescan { get; init; }

    [JsonPropertyName("batchId")]
    public string BatchId { get; init; } = string.Empty;
}

public sealed class OdbPostprocessProgress
{
    [JsonPropertyName("percent")]
    public int Percent { get; init; }

    [JsonPropertyName("phase")]
    public string Phase { get; init; } = string.Empty;
}

public sealed class OdbPostprocessResult
{
    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;

    [JsonPropertyName("count")]
    public int Count { get; init; }

    [JsonPropertyName("cacheHits")]
    public int CacheHits { get; init; }

    [JsonPropertyName("parallelWorkers")]
    public int ParallelWorkers { get; init; }

    [JsonPropertyName("items")]
    public IReadOnlyList<OdbPostprocessScanItem> Items { get; init; } = [];

    [JsonPropertyName("batchId")]
    public string BatchId { get; init; } = string.Empty;

    [JsonPropertyName("resultRoots")]
    public IReadOnlyList<string> ResultRoots { get; init; } = [];

    [JsonPropertyName("outputCount")]
    public int OutputCount { get; init; }

    [JsonPropertyName("outputs")]
    public IReadOnlyList<string> Outputs { get; init; } = [];

    [JsonPropertyName("groups")]
    public IReadOnlyList<OdbPostprocessGroupResult> Groups { get; init; } = [];
}

public sealed class OdbPostprocessScanItem
{
    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("error")]
    public string Error { get; init; } = string.Empty;

    [JsonPropertyName("steps")]
    public IReadOnlyList<string> Steps { get; init; } = [];

    [JsonPropertyName("assemblyNodeSets")]
    public IReadOnlyList<string> AssemblyNodeSets { get; init; } = [];

    [JsonPropertyName("assemblyElementSets")]
    public IReadOnlyList<string> AssemblyElementSets { get; init; } = [];

    [JsonPropertyName("fieldOutputs")]
    public IReadOnlyList<string> FieldOutputs { get; init; } = [];

    [JsonPropertyName("historyOutputDetails")]
    public IReadOnlyList<JsonElement> HistoryOutputDetails { get; init; } = [];

    [JsonPropertyName("setDetails")]
    public JsonElement SetDetails { get; init; }

    [JsonPropertyName("structureCatalog")]
    public OdbStructureCatalog StructureCatalog { get; init; } = new();

    [JsonPropertyName("contentFingerprint")]
    public string ContentFingerprint { get; init; } = string.Empty;

    [JsonPropertyName("suggested")]
    public OdbPostprocessJobDraft Suggested { get; init; } = new();

    [JsonPropertyName("nameMetadata")]
    public OdbPostprocessNameMetadata NameMetadata { get; init; } = new();
}

public sealed class OdbPostprocessNameMetadata
{
    [JsonPropertyName("sampleId")]
    public string SampleId { get; init; } = string.Empty;

    [JsonPropertyName("family")]
    public string Family { get; init; } = string.Empty;

    [JsonPropertyName("scheme")]
    public string Scheme { get; init; } = string.Empty;

    [JsonPropertyName("reinforced")]
    public bool Reinforced { get; init; }

    [JsonPropertyName("condition")]
    public string Condition { get; init; } = string.Empty;

    [JsonPropertyName("parameterTags")]
    public IReadOnlyList<string> ParameterTags { get; init; } = [];

    [JsonPropertyName("isOld")]
    public bool IsOld { get; init; }

    [JsonPropertyName("upDisplacementMm")]
    public double? UpDisplacementMm { get; init; }

    [JsonPropertyName("lateralDisplacementMm")]
    public double? LateralDisplacementMm { get; init; }

    [JsonPropertyName("rebarDiameterMm")]
    public double? RebarDiameterMm { get; init; }
}

public sealed class OdbPostprocessGroupResult
{
    [JsonPropertyName("groupId")]
    public string GroupId { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("outputCount")]
    public int OutputCount { get; init; }

    [JsonPropertyName("outputs")]
    public IReadOnlyList<string> Outputs { get; init; } = [];
}

public sealed class OdbPostprocessOperationListResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("operations")]
    public IReadOnlyList<OdbPostprocessOperationSnapshot> Operations { get; init; } = [];

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }
}
