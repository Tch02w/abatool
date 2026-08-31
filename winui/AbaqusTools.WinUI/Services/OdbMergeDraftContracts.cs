using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

internal sealed class OdbMergeDraftPreviewRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("originalOdb")]
    public string OriginalOdb { get; init; } = string.Empty;

    [JsonPropertyName("restartOdb")]
    public string RestartOdb { get; init; } = string.Empty;

    [JsonPropertyName("outputOdb")]
    public string OutputOdb { get; init; } = string.Empty;

    [JsonPropertyName("includeHistory")]
    public bool IncludeHistory { get; init; } = true;

    [JsonPropertyName("compressResult")]
    public bool CompressResult { get; init; }

    [JsonPropertyName("copyOriginal")]
    public bool CopyOriginal { get; init; }

    [JsonPropertyName("conflictPolicy")]
    public string ConflictPolicy { get; init; } = "auto_number";
}

public sealed class OdbMergeDraftPreviewResponse
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("valid")]
    public bool Valid { get; init; }

    [JsonPropertyName("validationMessage")]
    public string ValidationMessage { get; init; } = string.Empty;

    [JsonPropertyName("validationLevel")]
    public string ValidationLevel { get; init; } = string.Empty;

    [JsonPropertyName("invalidField")]
    public string InvalidField { get; init; } = string.Empty;

    [JsonPropertyName("normalizedOutputOdb")]
    public string NormalizedOutputOdb { get; init; } = string.Empty;

    [JsonPropertyName("originalBackup")]
    public string OriginalBackup { get; init; } = string.Empty;

    [JsonPropertyName("restartBackup")]
    public string RestartBackup { get; init; } = string.Empty;

    [JsonPropertyName("command")]
    public string Command { get; init; } = string.Empty;

    [JsonPropertyName("autoNumbered")]
    public bool AutoNumbered { get; init; }

    [JsonPropertyName("willOverwrite")]
    public bool WillOverwrite { get; init; }

    [JsonPropertyName("sourceTotalBytes")]
    public long SourceTotalBytes { get; init; }

    [JsonPropertyName("executionSteps")]
    public IReadOnlyList<string> ExecutionSteps { get; init; } = [];
}
