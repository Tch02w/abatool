namespace AbaqusTools.WinUI.Services;

public sealed partial class ControlPlaneHost
{
    private const string ResultIndexBatchEndpoint = "/api/v1/result-index-batches";
    private readonly HashSet<string> _activeResultIndexBatches = new(StringComparer.Ordinal);

    public async Task<ResultIndexBatchSnapshot> StartResultIndexBatchAsync(
        string root, string scopeDirectory, Guid clientRequestId, CancellationToken cancellationToken = default)
    {
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        await _operationCreationGate.WaitAsync(lifetime.Token);
        try
        {
            lock (_operationGate)
                if (!_acceptNewOperations) throw new OperationCanceledException("应用正在关闭，无法开始补建索引。");
            return await SendIndexBatchAsync(HttpMethod.Post, null,
                new { schemaVersion = 1, clientRequestId, root, scopeDirectory }, lifetime.Token);
        }
        finally { _operationCreationGate.Release(); }
    }

    public Task<ResultIndexBatchSnapshot> GetResultIndexBatchAsync(string batchId, CancellationToken cancellationToken = default) =>
        SendIndexBatchAsync(HttpMethod.Get, ValidateOperationId(batchId), null, cancellationToken);

    public Task<ResultIndexBatchSnapshot> CancelResultIndexBatchAsync(string batchId, CancellationToken cancellationToken = default) =>
        SendIndexBatchAsync(HttpMethod.Post, ValidateOperationId(batchId), null, cancellationToken);

    private async Task<ResultIndexBatchSnapshot> SendIndexBatchAsync(HttpMethod method, string? id, object? body, CancellationToken token)
    {
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(token, _shutdownSource.Token);
        lifetime.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(lifetime.Token);
        var path = ResultIndexBatchEndpoint;
        if (id is not null)
            path += "/" + Uri.EscapeDataString(id) + (method == HttpMethod.Post ? "/cancel" : "");
        var snapshot = await SendJsonRequestAsync<ResultIndexBatchSnapshot>(
            descriptor, method, path, body, "补建结果索引", lifetime.Token);
        snapshot.Validate(id);
        lock (_operationGate)
        {
            if (snapshot.IsTerminal) _activeResultIndexBatches.Remove(snapshot.BatchId);
            else _activeResultIndexBatches.Add(snapshot.BatchId);
        }
        return snapshot;
    }

    private async Task BestEffortCancelIndexBatchAsync(ControlPlaneDescriptor descriptor, string id, CancellationToken token)
    {
        if (_preserveBackground) return;
        try
        {
            await SendJsonRequestAsync<ResultIndexBatchSnapshot>(descriptor, HttpMethod.Post,
                ResultIndexBatchEndpoint + "/" + Uri.EscapeDataString(id) + "/cancel", null, "取消补建索引", token);
        }
        catch (Exception error) when (error is ControlPlaneException or IOException or OperationCanceledException or ObjectDisposedException)
        {
            System.Diagnostics.Debug.WriteLine($"补建结果索引取消尚未确认：{error.Message}");
        }
    }
}
