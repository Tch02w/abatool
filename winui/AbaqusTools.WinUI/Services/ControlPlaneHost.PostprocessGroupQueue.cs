namespace AbaqusTools.WinUI.Services;

public sealed partial class ControlPlaneHost
{
    private const string GroupQueueEndpoint = "/api/v1/odb-postprocess-group-queues";
    private readonly HashSet<string> _activePostprocessGroupQueues = new(StringComparer.Ordinal);

    public Task<OdbPostprocessGroupQueueSnapshot> StartPostprocessGroupQueueAsync(
        OdbPostprocessRunCreateRequest run, CancellationToken cancellationToken = default) =>
        SubmitGroupQueueAsync(GroupQueueEndpoint, run, null, run.ClientRequestId, cancellationToken);

    public async Task<OdbPostprocessGroupQueueList> ListPostprocessGroupQueuesAsync(
        bool activeOnly = false, CancellationToken cancellationToken = default)
    {
        var list = await SendGroupQueueAsync<OdbPostprocessGroupQueueList>(HttpMethod.Get,
            GroupQueueEndpoint + (activeOnly ? "?activeOnly=true" : ""), null, cancellationToken);
        if (list.SchemaVersion != 1 || list.Operations is null) throw new ControlPlaneException("分组提取队列列表无效。");
        foreach (var queue in list.Operations) TrackGroupQueue(queue, null);
        return list;
    }

    public async Task<OdbPostprocessGroupQueueSnapshot> GetPostprocessGroupQueueAsync(
        string operationId, CancellationToken cancellationToken = default)
    {
        var snapshot = await SendGroupQueueAsync<OdbPostprocessGroupQueueSnapshot>(HttpMethod.Get,
            GroupQueuePath(operationId), null, cancellationToken);
        return TrackGroupQueue(snapshot, operationId);
    }

    public async Task<OdbPostprocessGroupQueueSnapshot?> GetPostprocessGroupQueueIfChangedAsync(
        string operationId, long knownVersion, CancellationToken cancellationToken = default)
    {
        ArgumentOutOfRangeException.ThrowIfNegative(knownVersion);
        var version = knownVersion.ToString(System.Globalization.CultureInfo.InvariantCulture);
        var change = await SendGroupQueueAsync<OdbPostprocessGroupQueueChange>(HttpMethod.Get,
            GroupQueuePath(operationId) + "?afterVersion=" + version, null, cancellationToken);
        if (change.SchemaVersion != 1 || change.Operation?.Version == knownVersion)
            throw new ControlPlaneException("分组队列版本查询响应无效。");
        return change.Operation is { } queue ? TrackGroupQueue(queue, operationId) : null;
    }

    public Task<OdbPostprocessGroupQueueSnapshot> ChangePostprocessGroupQueueAsync(
        string operationId, PostprocessGroupQueueAction action, Guid clientRequestId, long expectedVersion,
        OdbPostprocessRunCreateRequest? run = null, string? expectedGroupId = null, CancellationToken cancellationToken = default)
    {
        if (clientRequestId == Guid.Empty || expectedVersion < 1)
            throw new ArgumentException("请选择已读取的队列版本，并使用有效的动作请求编号。");
        var needsRun = action is PostprocessGroupQueueAction.Append or PostprocessGroupQueueAction.UpdatePending;
        var needsGroup = action is PostprocessGroupQueueAction.CancelCurrent or PostprocessGroupQueueAction.SkipPending
            or PostprocessGroupQueueAction.AcknowledgeInterrupted;
        if (needsRun != (run is not null) || needsGroup != (expectedGroupId is not null)
            || (needsGroup && string.IsNullOrWhiteSpace(expectedGroupId)))
            throw new ArgumentException("分组队列动作的提取参数或目标组不匹配。");
        var suffix = action switch
        {
            PostprocessGroupQueueAction.Append => "append",
            PostprocessGroupQueueAction.UpdatePending => "update-pending",
            PostprocessGroupQueueAction.SkipPending => "skip-pending",
            PostprocessGroupQueueAction.CancelCurrent => "cancel-current",
            PostprocessGroupQueueAction.ClearPending => "clear-pending",
            PostprocessGroupQueueAction.Stop => "stop",
            PostprocessGroupQueueAction.Resume => "resume",
            PostprocessGroupQueueAction.AcknowledgeInterrupted => "acknowledge-interrupted",
            _ => throw new ArgumentOutOfRangeException(nameof(action))
        };
        var body = new Dictionary<string, object> {
            ["schemaVersion"] = 1, ["clientRequestId"] = clientRequestId.ToString("D"), ["expectedVersion"] = expectedVersion
        };
        if (run is not null) body.Add("run", run);
        if (expectedGroupId is not null) body.Add("expectedGroupId", expectedGroupId);
        return SubmitGroupQueueAsync(GroupQueuePath(operationId) + "/" + suffix, body, operationId, null, cancellationToken);
    }

    private static string GroupQueuePath(string operationId)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(operationId);
        return GroupQueueEndpoint + "/" + Uri.EscapeDataString(operationId);
    }

    private async Task<T> SendGroupQueueAsync<T>(HttpMethod method, string path, object? body, CancellationToken token)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token, _shutdownSource.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(timeout.Token);
        return await SendJsonRequestAsync<T>(descriptor, method, path, body, "分组提取队列", timeout.Token);
    }

    private async Task<OdbPostprocessGroupQueueSnapshot> SubmitGroupQueueAsync(
        string path, object body, string? expectedId, string? expectedRequestId, CancellationToken token)
    {
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(token, _shutdownSource.Token);
        await _operationCreationGate.WaitAsync(lifetime.Token);
        try
        {
            lock (_operationGate)
                if (!_acceptNewOperations) throw new OperationCanceledException("应用正在关闭，分组队列操作已停止。");
            var snapshot = await SendGroupQueueAsync<OdbPostprocessGroupQueueSnapshot>(HttpMethod.Post, path, body, lifetime.Token);
            if (expectedRequestId is not null && expectedRequestId != snapshot.ClientRequestId)
                throw new ControlPlaneException("分组提取请求标识不一致。");
            return TrackGroupQueue(snapshot, expectedId);
        }
        finally { _operationCreationGate.Release(); }
    }

    private OdbPostprocessGroupQueueSnapshot TrackGroupQueue(OdbPostprocessGroupQueueSnapshot snapshot, string? expectedId)
    {
        snapshot.Validate(expectedId);
        lock (_operationGate)
        {
            if (snapshot.IsActive) _activePostprocessGroupQueues.Add(snapshot.OperationId);
            else _activePostprocessGroupQueues.Remove(snapshot.OperationId);
        }
        return snapshot;
    }

    private async Task BestEffortStopGroupQueueAsync(ControlPlaneDescriptor descriptor, string operationId, CancellationToken token)
    {
        if (_preserveBackground) return;
        var path = GroupQueuePath(operationId);
        try
        {
            var current = await SendJsonRequestAsync<OdbPostprocessGroupQueueSnapshot>(
                descriptor, HttpMethod.Get, path, null, "分组队列停止前状态", token);
            current.Validate(operationId);
            if (!current.IsActive) return;
            await SendJsonRequestAsync<OdbPostprocessGroupQueueSnapshot>(descriptor, HttpMethod.Post, path + "/stop",
                new { schemaVersion = 1, clientRequestId = Guid.NewGuid().ToString("D"), expectedVersion = current.Version },
                "停止分组队列", token);
        }
        catch (Exception error) when (error is ControlPlaneException or IOException or OperationCanceledException or ObjectDisposedException)
        {
            // The backend's shutdown reservation still protects work whose stop could not be confirmed.
            System.Diagnostics.Debug.WriteLine($"分组队列停止尚未确认：{error.Message}");
        }
    }
}
