using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

internal sealed class LocalJobDraftPreviewRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("inpFile")]
    public string InpFile { get; init; } = string.Empty;

    [JsonPropertyName("jobName")]
    public string JobName { get; init; } = string.Empty;

    [JsonPropertyName("gpuCount")] public int? GpuCount { get; init; }
    [JsonPropertyName("explicitPrecision")] public string ExplicitPrecision { get; init; } = "default";
    [JsonPropertyName("outputPrecision")] public string OutputPrecision { get; init; } = "default";

    [JsonPropertyName("cpus")]
    public int Cpus { get; init; }

    [JsonPropertyName("memoryValue")]
    public string MemoryValue { get; init; } = string.Empty;

    [JsonPropertyName("memoryUnit")]
    public string MemoryUnit { get; init; } = "%";

    [JsonPropertyName("oldjobPath")]
    public string OldjobPath { get; init; } = string.Empty;

    [JsonPropertyName("fortranPath")]
    public string FortranPath { get; init; } = string.Empty;

    [JsonPropertyName("interactive")]
    public bool Interactive { get; init; }

    [JsonPropertyName("datacheck")]
    public bool Datacheck { get; init; }

    [JsonPropertyName("notify")]
    public bool Notify { get; init; } = true;

    [JsonPropertyName("abaqusCommand")]
    public string AbaqusCommand { get; init; } = "abaqus";

    [JsonPropertyName("priority")]
    public int Priority { get; init; }

    [JsonPropertyName("maxParallel")]
    public int MaxParallel { get; init; } = 1;

    [JsonPropertyName("useSsdCalculation")]
    public bool UseSsdCalculation { get; init; }

    [JsonPropertyName("calculationRootDir")]
    public string CalculationRootDir { get; init; } = string.Empty;

    [JsonPropertyName("archiveDir")]
    public string ArchiveDir { get; init; } = string.Empty;
}

public sealed class LocalJobDraftPreviewResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("valid")]
    public bool Valid { get; init; }

    [JsonPropertyName("validationMessage")]
    public string ValidationMessage { get; init; } = string.Empty;

    [JsonPropertyName("effectiveJobName")]
    public string EffectiveJobName { get; init; } = string.Empty;

    [JsonPropertyName("oldjobName")]
    public string OldjobName { get; init; } = string.Empty;

    [JsonPropertyName("hasRestartInput")]
    public bool HasRestartInput { get; init; }

    [JsonPropertyName("command")]
    public string Command { get; init; } = string.Empty;

    [JsonPropertyName("workDirectory")]
    public string WorkDirectory { get; init; } = string.Empty;

    [JsonPropertyName("archivePath")]
    public string ArchivePath { get; init; } = string.Empty;
}
