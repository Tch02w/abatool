using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class LocalResourceSnapshot
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("capturedAt")]
    public DateTimeOffset CapturedAt { get; init; }

    [JsonPropertyName("resourceId")]
    public string ResourceId { get; init; } = string.Empty;

    [JsonPropertyName("name")]
    public string Name { get; init; } = string.Empty;

    [JsonPropertyName("status")]
    public string Status { get; init; } = string.Empty;

    [JsonPropertyName("logicalCpus")]
    public int LogicalCpus { get; init; }

    [JsonPropertyName("busyCpus")]
    public int BusyCpus { get; init; }

    [JsonPropertyName("cpuPercent")]
    public double CpuPercent { get; init; }

    [JsonPropertyName("memoryUsedBytes")]
    public long MemoryUsedBytes { get; init; }

    [JsonPropertyName("memoryTotalBytes")]
    public long MemoryTotalBytes { get; init; }

    [JsonPropertyName("memoryPercent")]
    public double MemoryPercent { get; init; }

    [JsonPropertyName("runningJobs")]
    public int RunningJobs { get; init; }

    [JsonPropertyName("waitingJobs")]
    public int WaitingJobs { get; init; }

    [JsonPropertyName("totalJobs")]
    public int TotalJobs { get; init; }

    [JsonPropertyName("activeJobs")]
    public IReadOnlyList<string> ActiveJobs { get; init; } = [];

    [JsonPropertyName("abaqusCommand")]
    public string AbaqusCommand { get; init; } = string.Empty;

    [JsonPropertyName("abaqusRelease")]
    public string AbaqusRelease { get; init; } = string.Empty;

    [JsonPropertyName("abaqusAvailable")]
    public bool AbaqusAvailable { get; init; }

    [JsonIgnore]
    public string CpuDisplay => $"{BusyCpus} / {LogicalCpus} 线程（{CpuPercent:0.#}%）";

    [JsonIgnore]
    public string MemoryDisplay =>
        $"{MemoryUsedBytes / 1073741824d:0.0} / {MemoryTotalBytes / 1073741824d:0.0} GB（{MemoryPercent:0.#}%）";

    [JsonIgnore]
    public string AbaqusDisplay => AbaqusAvailable
        ? string.IsNullOrWhiteSpace(AbaqusRelease)
            ? $"{AbaqusCommand} · 可用"
            : $"Abaqus {AbaqusRelease} · 可用"
        : $"{AbaqusCommand} · 未发现";
}
