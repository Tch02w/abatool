using System.Net.Http.Headers;

namespace AbaqusTools.WinUI.Services;

public sealed partial class ControlPlaneHost
{
    private readonly HashSet<string> _activeResultBatchIds = new(StringComparer.Ordinal);

    private async Task<T> SendBatchRequestAsync<T>(HttpMethod method, string path, object? body, CancellationToken cancellationToken)
    {
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(30));
        var descriptor = await EnsureReadyAsync(timeout.Token);
        return await SendJsonRequestAsync<T>(descriptor, method, path, body, "完整结果批量任务", timeout.Token);
    }

    private OdbResultBatchSnapshot TrackBatch(OdbResultBatchSnapshot snapshot, string? expectedId = null)
    {
        snapshot.Validate(expectedId);
        if (snapshot.CurrentOperation is { } child) ValidateOdbMergeSnapshot(child);
        lock (_operationGate)
        {
            if (snapshot.IsActive) _activeResultBatchIds.Add(snapshot.OperationId);
            else _activeResultBatchIds.Remove(snapshot.OperationId);
        }
        return snapshot;
    }

    public async Task<OdbResultBatchSnapshot> StartOdbResultBatchAsync(object source, OdbResultBatchOptions options,
        Guid clientRequestId, CancellationToken cancellationToken = default)
    {
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        await _operationCreationGate.WaitAsync(lifetime.Token);
        try
        {
            lock (_operationGate)
                if (!_acceptNewOperations) throw new OperationCanceledException("应用正在关闭，无法开始批量合并。");
            var snapshot = await SendBatchRequestAsync<OdbResultBatchSnapshot>(HttpMethod.Post, "/api/v1/odb-result-batches",
                new { schemaVersion = 1, clientRequestId = clientRequestId.ToString("D"), source, options }, lifetime.Token);
            if (snapshot.ClientRequestId != clientRequestId.ToString("D"))
                throw new ControlPlaneException("批量请求标识不一致。");
            return TrackBatch(snapshot);
        }
        finally { _operationCreationGate.Release(); }
    }

    public async Task<OdbResultBatchListResponse> ListOdbResultBatchesAsync(CancellationToken cancellationToken = default)
    {
        var response = await SendBatchRequestAsync<OdbResultBatchListResponse>(HttpMethod.Get, "/api/v1/odb-result-batches", null, cancellationToken);
        if (response.SchemaVersion != 1 || response.Operations is null)
            throw new ControlPlaneException("完整结果任务列表无效。");
        foreach (var item in response.Operations) TrackBatch(item);
        return response;
    }

    public async Task<OdbResultBatchSnapshot> GetOdbResultBatchAsync(string operationId, CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        return TrackBatch(await SendBatchRequestAsync<OdbResultBatchSnapshot>(HttpMethod.Get,
            $"/api/v1/odb-result-batches/{Uri.EscapeDataString(operationId)}", null, cancellationToken), operationId);
    }

    public async Task<OdbResultBatchSnapshot> CancelOdbResultBatchAsync(string operationId, CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        return TrackBatch(await SendBatchRequestAsync<OdbResultBatchSnapshot>(HttpMethod.Post,
            $"/api/v1/odb-result-batches/{Uri.EscapeDataString(operationId)}/cancel", null, cancellationToken), operationId);
    }

    public async Task<OdbResultBatchSnapshot> ResumeOdbResultBatchAsync(string operationId, CancellationToken cancellationToken = default)
    {
        operationId = ValidateOperationId(operationId);
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken, _shutdownSource.Token);
        await _operationCreationGate.WaitAsync(lifetime.Token);
        try
        {
            lock (_operationGate)
                if (!_acceptNewOperations) throw new OperationCanceledException("应用正在关闭，无法继续批量任务。");
            return TrackBatch(await SendBatchRequestAsync<OdbResultBatchSnapshot>(HttpMethod.Post,
                $"/api/v1/odb-result-batches/{Uri.EscapeDataString(operationId)}/resume", null, lifetime.Token), operationId);
        }
        finally { _operationCreationGate.Release(); }
    }

    private async Task BestEffortCancelBatchAsync(ControlPlaneDescriptor descriptor, string operationId, CancellationToken cancellationToken)
    {
        try
        {
            using var request = new HttpRequestMessage(HttpMethod.Post,
                BuildEndpoint(descriptor, $"/api/v1/odb-result-batches/{Uri.EscapeDataString(operationId)}/cancel"));
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", descriptor.Token);
            using var response = await _httpClient.SendAsync(request, cancellationToken);
        }
        catch (Exception exception) when (exception is HttpRequestException or IOException or OperationCanceledException or ObjectDisposedException)
        {
            System.Diagnostics.Debug.WriteLine($"Batch cancellation was not confirmed: {exception.Message}");
        }
    }
}
