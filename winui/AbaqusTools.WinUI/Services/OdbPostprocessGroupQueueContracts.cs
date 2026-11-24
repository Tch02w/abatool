using System.Text.Json.Serialization;

namespace AbaqusTools.WinUI.Services;

public enum PostprocessGroupQueueAction { Append, UpdatePending, SkipPending, CancelCurrent, ClearPending, Stop, Resume, AcknowledgeInterrupted }

public sealed class OdbPostprocessGroupQueueList
{
    public int SchemaVersion { get; init; }
    [JsonRequired] public IReadOnlyList<OdbPostprocessGroupQueueSnapshot> Operations { get; init; } = [];
}

internal sealed class OdbPostprocessGroupQueueChange
{
    public int SchemaVersion { get; init; }
    [JsonRequired] public OdbPostprocessGroupQueueSnapshot? Operation { get; init; }
}

public sealed class OdbPostprocessGroupQueueItem
{
    public string GroupId { get; init; } = "";
    public string GroupKey { get; init; } = "";
    public string Name { get; init; } = "";
    public IReadOnlyList<string> Members { get; init; } = [];
    public bool Standalone { get; init; }
    public string Status { get; init; } = "";
    public string? ChildOperationId { get; init; }
    public string Message { get; init; } = "";
    public OdbPostprocessRunCreateRequest? Run { get; init; }
    [JsonRequired] public OdbPostprocessResult Result { get; init; } = new();
}

public sealed class OdbPostprocessGroupQueueSnapshot
{
    public int SchemaVersion { get; init; }
    public string OperationId { get; init; } = "";
    public string Kind { get; init; } = "";
    public string ClientRequestId { get; init; } = "";
    public string Root { get; init; } = "";
    public string Status { get; init; } = "";
    public long Version { get; init; }
    public string Phase { get; init; } = "";
    public string CurrentGroupId { get; init; } = "";
    public IReadOnlyList<OdbPostprocessGroupQueueItem> Groups { get; init; } = [];
    [JsonRequired] public OdbPostprocessResult Result { get; init; } = new();
    public DateTimeOffset CreatedAt { get; init; }
    public DateTimeOffset UpdatedAt { get; init; }
    [JsonIgnore] public bool IsActive => Status is "queued" or "running" or "cancelling";
    [JsonIgnore] public bool IsTerminal => Status is "succeeded" or "partial" or "failed" or "cancelled";
    [JsonIgnore] public bool CanResume => Status == "suspended";

    internal void Validate(string? expectedId = null)
    {
        if (SchemaVersion != 1 || Kind != "odb.postprocess.group-queue" || string.IsNullOrWhiteSpace(OperationId)
            || (expectedId is not null && expectedId != OperationId) || string.IsNullOrWhiteSpace(ClientRequestId)
            || string.IsNullOrWhiteSpace(Root) || Version < 1 || !(IsActive || IsTerminal || CanResume)
            || Groups is null || Groups.Count == 0 || Result is null || CurrentGroupId is null)
            throw new ControlPlaneException("控制面返回了无效的分组提取队列。");

        var ids = new HashSet<string>(StringComparer.Ordinal);
        var outputs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var roots = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var group in Groups)
        {
            if (group is null || string.IsNullOrWhiteSpace(group.GroupId) || !ids.Add(group.GroupId)
                || string.IsNullOrWhiteSpace(group.GroupKey) || group.Members is null || group.Members.Count == 0
                || group.Members.Any(string.IsNullOrWhiteSpace)
                || group.Status is not ("queued" or "running" or "cancelling" or "interrupted" or "succeeded" or "failed" or "cancelled" or "skipped"))
                throw new ControlPlaneException("分组提取队列包含无效或重复的组条目。");
            if (group.Status is "queued" or "running" or "cancelling" or "interrupted")
            {
                if (group.Run is not { Groups.Count: 1 } run
                    || !string.Equals(run.Root, Root, StringComparison.OrdinalIgnoreCase)
                    || run.ClientRequestId != "pgq:" + group.GroupId
                    || run.Groups[0]?.Members is not { } members || !members.SequenceEqual(group.Members, StringComparer.OrdinalIgnoreCase))
                    throw new ControlPlaneException("分组执行草稿与当前队列条目不匹配。");
            }
            if (group.Result is null) throw new ControlPlaneException("分组缺少已发布结果回执。");
            ValidateResult(group.Result);
            outputs.UnionWith(group.Result.Outputs);
            roots.UnionWith(group.Result.ResultRoots);
        }
        if (CurrentGroupId.Length > 0 && !ids.Contains(CurrentGroupId))
            throw new ControlPlaneException("分组提取队列的当前组不存在。");
        ValidateResult(Result);
        if (outputs.Count != Result.OutputCount || !outputs.SetEquals(Result.Outputs)
            || !roots.SetEquals(Result.ResultRoots))
            throw new ControlPlaneException("分组队列的汇总与各组已发布回执不一致。");
    }

    private static void ValidateResult(OdbPostprocessResult result)
    {
        if (result.Outputs is null || result.ResultRoots is null || result.OutputCount != result.Outputs.Count
            || result.Outputs.Any(string.IsNullOrWhiteSpace) || result.ResultRoots.Any(string.IsNullOrWhiteSpace)
            || (result.OutputCount == 0) != (result.ResultRoots.Count == 0))
            throw new ControlPlaneException("分组提取的已发布结果回执不完整。");
    }
}
