namespace AbaqusTools.WinUI.Services;

public sealed class ShutdownWorkItem
{
    public string OperationId { get; init; } = "";
    public string Kind { get; init; } = "";
    public string Name { get; init; } = "";
    public string Status { get; init; } = "";

    public string DisplayName => Kind switch
    {
        "local.queue" => "本机队列调度",
        "local.job" => "本机作业" + (string.IsNullOrWhiteSpace(Name) || Name == Kind ? "" : " · " + Name),
        "remote.job" => "远端作业" + (string.IsNullOrWhiteSpace(Name) || Name == Kind ? "" : " · " + Name),
        "remote.transfer" => "远端文件传输",
        "result.index" => "结果索引",
        "odb.postprocess.group-queue" => "分组提取队列" + (string.IsNullOrWhiteSpace(Name) || Name == Kind ? "" : " · " + Name),
        _ when Kind.StartsWith("odb.postprocess", StringComparison.Ordinal) => "ODB 后处理",
        _ when Kind.StartsWith("odb.compatibility", StringComparison.Ordinal) => "ODB 兼容性检查",
        _ when Kind.StartsWith("odb.upgrade", StringComparison.Ordinal) => "ODB 升级",
        _ when Kind.StartsWith("odb.merge", StringComparison.Ordinal) => "ODB 合并",
        _ when Kind.StartsWith("odb.result", StringComparison.Ordinal) => "完整结果批量生成",
        _ => "后台工作",
    };
}

public sealed class ShutdownSnapshot
{
    public int SchemaVersion { get; init; }
    public string Kind { get; init; } = "";
    public string RequestId { get; init; } = "";
    public string State { get; init; } = "";
    public bool SafeToStop { get; init; }
    public int PendingRequests { get; init; }
    public bool StopBackend { get; init; }
    public string? Mode { get; init; }
    public List<ShutdownWorkItem> Operations { get; init; } = [];

    public void Validate(string expectedId)
    {
        if (SchemaVersion != 1 || Kind != "controlPlane.shutdown" || RequestId != expectedId
            || State is not ("prepared" or "stopping" or "committed" or "aborted")
            || PendingRequests < 0 || Operations is null
            || (SafeToStop && (PendingRequests != 0 || Operations.Count != 0))
            || (StopBackend && (State != "committed" || !SafeToStop || Mode is not ("idle" or "stop")))
            || (State == "committed" && (Mode is not ("idle" or "stop" or "background")
                || (Mode != "background" && !StopBackend))))
            throw new InvalidDataException("后台关闭回执无效，已保留后台。");
    }
}
