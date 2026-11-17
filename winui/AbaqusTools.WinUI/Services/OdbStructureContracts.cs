using System.Text.Json;
using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class OdbStructureCatalog
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }
    [JsonPropertyName("regions")]
    public IReadOnlyList<OdbRegionDescriptor> Regions { get; init; } = [];
    [JsonPropertyName("steps")]
    public IReadOnlyList<OdbStepDescriptor> Steps { get; init; } = [];
    [JsonPropertyName("sections")]
    public IReadOnlyList<JsonElement> Sections { get; init; } = [];
    [JsonPropertyName("sectionAssignments")]
    public IReadOnlyList<JsonElement> SectionAssignments { get; init; } = [];
}

public sealed class OdbRegionDescriptor
{
    [JsonPropertyName("id")]
    public string Id { get; init; } = string.Empty;
    [JsonPropertyName("scope")]
    public string Scope { get; init; } = string.Empty;
    [JsonPropertyName("instance")]
    public string Instance { get; init; } = string.Empty;
    [JsonPropertyName("kind")]
    public string Kind { get; init; } = string.Empty;
    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;
    [JsonPropertyName("nodeCount")]
    public int NodeCount { get; init; }
    [JsonPropertyName("elementCount")]
    public int ElementCount { get; init; }
    [JsonPropertyName("elementTypes")]
    public IReadOnlyDictionary<string, int> ElementTypes { get; init; } = new Dictionary<string, int>();

    public string DisplayName => $"{(Scope == "assembly" ? "装配" : Instance)} / {Name} [{Kind switch { "instance" => "整个实例", "element_set" => "单元集", _ => "节点集" }}]";
}

public sealed class OdbStepDescriptor
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;
    [JsonPropertyName("frames")]
    public IReadOnlyList<OdbFrameDescriptor> Frames { get; init; } = [];
}

public sealed class OdbFrameDescriptor
{
    [JsonPropertyName("index")]
    public int Index { get; init; }
    [JsonPropertyName("value")]
    public double Value { get; init; }
    [JsonPropertyName("fields")]
    public IReadOnlyList<OdbFieldDescriptor> Fields { get; init; } = [];
    public string DisplayName => $"帧 {Index} · 步内时间/帧值 {Value:G8}";
}

public sealed class OdbFieldDescriptor
{
    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;
    [JsonPropertyName("components")]
    public IReadOnlyList<string> Components { get; init; } = [];
    [JsonPropertyName("positions")]
    public IReadOnlyList<string> Positions { get; init; } = [];
}

public sealed class OdbRegionExtractionRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;
    [JsonPropertyName("clientRequestId")]
    public string ClientRequestId { get; init; } = Guid.NewGuid().ToString("D");
    [JsonPropertyName("root")]
    public string Root { get; init; } = string.Empty;
    [JsonPropertyName("path")]
    public string Path { get; init; } = string.Empty;
    [JsonPropertyName("region")]
    public Dictionary<string, string> Region { get; init; } = [];
    [JsonPropertyName("method")]
    public string Method { get; init; } = string.Empty;
    [JsonPropertyName("frames")]
    public IReadOnlyList<OdbRegionFrameSelection> Frames { get; init; } = [];
    [JsonPropertyName("acknowledgeReferenceArea")]
    public bool AcknowledgeReferenceArea { get; init; }
    [JsonPropertyName("referenceAreaOverride")]
    public double? ReferenceAreaOverride { get; init; }
    [JsonPropertyName("section")]
    public OdbRegionSectionDefinition? Section { get; init; }
}

public sealed class OdbRegionSectionDefinition
{
    [JsonPropertyName("origin")]
    public IReadOnlyList<double> Origin { get; init; } = [];
    [JsonPropertyName("normal")]
    public IReadOnlyList<double> Normal { get; init; } = [];
    [JsonPropertyName("offsets")]
    public IReadOnlyList<double> Offsets { get; init; } = [];
    [JsonPropertyName("momentReference")]
    public string MomentReference { get; init; } = "centroid";
    [JsonPropertyName("momentPoint")]
    public IReadOnlyList<double>? MomentPoint { get; init; }
}

public sealed class OdbRegionFrameSelection
{
    [JsonPropertyName("step")]
    public string Step { get; init; } = string.Empty;
    [JsonPropertyName("index")]
    public int Index { get; init; }
}
