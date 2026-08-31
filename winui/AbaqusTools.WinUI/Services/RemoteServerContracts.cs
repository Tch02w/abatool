using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public sealed class RemoteServersSnapshot
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; }

    [JsonPropertyName("profiles")]
    public IReadOnlyList<RemoteServerProfile> Profiles { get; init; } = [];

    [JsonPropertyName("profilesError")]
    public string ProfilesError { get; init; } = string.Empty;

    [JsonPropertyName("connection")]
    public RemoteServerConnection Connection { get; init; } = new();

    [JsonPropertyName("eventCursor")]
    public long EventCursor { get; init; }
}

public sealed class RemoteServerProfile
{
    [JsonPropertyName("profileName")]
    public string ProfileName { get; init; } = string.Empty;

    [JsonPropertyName("host")]
    public string Host { get; init; } = string.Empty;

    [JsonPropertyName("username")]
    public string Username { get; init; } = string.Empty;

    [JsonPropertyName("authentication")]
    public string Authentication { get; init; } = "用户名/密码";

    [JsonPropertyName("hostFingerprint")]
    public string HostFingerprint { get; init; } = string.Empty;

    [JsonPropertyName("abaqusCommand")]
    public string AbaqusCommand { get; init; } = "abaqus.bat";

    [JsonPropertyName("computeRoot")]
    public string ComputeRoot { get; init; } = string.Empty;

    [JsonPropertyName("allowedRoots")]
    public IReadOnlyList<string> AllowedRoots { get; init; } = [];

    [JsonPropertyName("port")]
    public int Port { get; init; } = 22;

    [JsonPropertyName("privateKeyPath")]
    public string PrivateKeyPath { get; init; } = string.Empty;
}

public sealed class RemoteServerCredentials
{
    [JsonPropertyName("password")]
    public string Password { get; init; } = string.Empty;

    [JsonPropertyName("privateKeyPassphrase")]
    public string PrivateKeyPassphrase { get; init; } = string.Empty;
}

public sealed class RemoteServerCommandRequest
{
    [JsonPropertyName("schemaVersion")]
    public int SchemaVersion { get; init; } = 1;

    [JsonPropertyName("action")]
    public string Action { get; init; } = string.Empty;

    [JsonPropertyName("profile")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RemoteServerProfile? Profile { get; init; }

    [JsonPropertyName("profileName")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ProfileName { get; init; }

    [JsonPropertyName("credentials")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public RemoteServerCredentials? Credentials { get; init; }

    [JsonPropertyName("confirmFingerprint")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public string? ConfirmFingerprint { get; init; }

    [JsonPropertyName("saveProfile")]
    [JsonIgnore(Condition = JsonIgnoreCondition.WhenWritingNull)]
    public bool? SaveProfile { get; init; }
}

public sealed class RemoteServerConnection
{
    [JsonPropertyName("status")]
    public string Status { get; init; } = "disconnected";

    [JsonPropertyName("profileName")]
    public string ProfileName { get; init; } = string.Empty;

    [JsonPropertyName("pendingFingerprint")]
    public string PendingFingerprint { get; init; } = string.Empty;

    [JsonPropertyName("lastError")]
    public string LastError { get; init; } = string.Empty;

    [JsonPropertyName("resource")]
    public RemoteResourceSnapshot? Resource { get; init; }
}

public sealed class RemoteResourceSnapshot
{
    [JsonPropertyName("profile_name")]
    public string ProfileName { get; init; } = string.Empty;

    [JsonPropertyName("host")]
    public string Host { get; init; } = string.Empty;

    [JsonPropertyName("connected")]
    public bool Connected { get; init; }

    [JsonPropertyName("computer_name")]
    public string ComputerName { get; init; } = string.Empty;

    [JsonPropertyName("cpu_used")]
    public int CpuUsed { get; init; }

    [JsonPropertyName("cpu_total")]
    public int CpuTotal { get; init; }

    [JsonPropertyName("cpu_percent")]
    public double CpuPercent { get; init; }

    [JsonPropertyName("memory_used_gb")]
    public double MemoryUsedGb { get; init; }

    [JsonPropertyName("memory_total_gb")]
    public double MemoryTotalGb { get; init; }

    [JsonPropertyName("running_jobs")]
    public int RunningJobs { get; init; }

    [JsonPropertyName("waiting_jobs")]
    public int WaitingJobs { get; init; }

    [JsonPropertyName("active_jobs")]
    public IReadOnlyList<string> ActiveJobs { get; init; } = [];

    [JsonPropertyName("compute_root")]
    public string ComputeRoot { get; init; } = string.Empty;

    [JsonPropertyName("compute_root_exists")]
    public bool ComputeRootExists { get; init; }

    [JsonPropertyName("allowed_roots")]
    public IReadOnlyList<string> AllowedRoots { get; init; } = [];

    [JsonPropertyName("abaqus_command")]
    public string AbaqusCommand { get; init; } = string.Empty;

    [JsonPropertyName("abaqus_command_available")]
    public bool AbaqusCommandAvailable { get; init; }

    [JsonPropertyName("host_fingerprint")]
    public string HostFingerprint { get; init; } = string.Empty;

    [JsonPropertyName("updated_at")]
    public DateTimeOffset UpdatedAt { get; init; }

    [JsonIgnore]
    public string CpuDisplay => $"{CpuUsed} / {CpuTotal} 线程（{CpuPercent:0.#}%）";

    [JsonIgnore]
    public string MemoryDisplay => $"{MemoryUsedGb:0.0} / {MemoryTotalGb:0.0} GB";
}
