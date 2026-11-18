using System.Text.Json;
using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class ExecutionOptionsValues
{
    [JsonPropertyName("gpuCount")] public int? GpuCount { get; init; }
    [JsonPropertyName("explicitPrecision")] public string ExplicitPrecision { get; init; } = "default";
    [JsonPropertyName("outputPrecision")] public string OutputPrecision { get; init; } = "default";
    [JsonIgnore] public bool IsValid => (GpuCount is null || GpuCount is >= 0 and <= 1024)
        && ExplicitPrecision is "default" or "off" or "explicit" or "both" or "constraint"
        && OutputPrecision is "default" or "single" or "full";
    [JsonIgnore] public bool HasOverrides => GpuCount is not null || ExplicitPrecision != "default" || OutputPrecision != "default";
}

public sealed class ExecutionOptionsDraft
{
    public bool OverrideGpu { get; init; }
    public string GpuText { get; init; } = "0";
    public string ExplicitPrecision { get; init; } = "default";
    public string OutputPrecision { get; init; } = "default";
    public static ExecutionOptionsDraft Parse(string value)
    {
        var draft = JsonSerializer.Deserialize<ExecutionOptionsDraft>(value);
        if (draft is null || draft.GpuText is null || !new ExecutionOptionsValues
            { ExplicitPrecision = draft.ExplicitPrecision, OutputPrecision = draft.OutputPrecision }.IsValid)
            throw new InvalidDataException("GPU 与精度草稿无效");
        return draft;
    }
}
