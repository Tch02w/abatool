namespace AbaqusTools.WinUI.Services;

public sealed partial class ControlPlaneHost
{
    private ControlPlaneDescriptor? _closeDescriptor;
    private string? _closeRequestId;
    private bool _localClose;
    private bool _preserveBackground;

    private ShutdownSnapshot LocalCloseState(string state, string? mode = null) => new()
    {
        SchemaVersion = 1, Kind = "controlPlane.shutdown", RequestId = _closeRequestId!,
        State = state, SafeToStop = true, Mode = mode,
        StopBackend = state == "committed" && mode != "background",
    };

    public async Task<ShutdownSnapshot> PrepareCloseAsync(Guid requestId, CancellationToken token = default)
    {
        _closeRequestId = requestId.ToString();
        // Drain creation before closing admission, so an in-flight creation is
        // not mistaken for an unsolicited operation to cancel before the user decides.
        await _operationCreationGate.WaitAsync(token);
        try { lock (_operationGate) _acceptNewOperations = false; }
        finally { _operationCreationGate.Release(); }
        try
        {
            // A creation that was just drained may have started the backend.
            // Decide this only after draining, and include an ongoing connection
            // or published descriptor from another window.
            _localClose = _descriptor is null && _ownedProcess is null
                && _connectionGate.CurrentCount != 0 && !File.Exists(_descriptorPath);
            if (!_localClose) _closeDescriptor = await EnsureReadyAsync(token);
            return _localClose ? LocalCloseState("prepared")
                : await SendCloseAsync(HttpMethod.Post, "/api/v1/shutdown-requests",
                    new { schemaVersion = 1, clientRequestId = _closeRequestId }, token);
        }
        catch
        {
            try { await AbortCloseAsync(CancellationToken.None); } catch { /* Lease expires if unreachable. */ }
            lock (_operationGate) _acceptNewOperations = true;
            throw;
        }
    }

    private async Task<ShutdownSnapshot> SendCloseAsync(HttpMethod method, string path, object? body, CancellationToken token)
    {
        var descriptor = _closeDescriptor ?? throw new InvalidOperationException("没有已准备的关闭连接。");
        using var timeout = CancellationTokenSource.CreateLinkedTokenSource(token, _shutdownSource.Token);
        timeout.CancelAfter(TimeSpan.FromSeconds(10));
        // Pin all close commands to the prepared instance. Never start/reconnect
        // another backend in response to a lost commit acknowledgement.
        var value = await SendJsonRequestAsync<ShutdownSnapshot>(descriptor, method, path, body, "关闭工作台", timeout.Token);
        value.Validate(_closeRequestId!);
        return value;
    }

    public Task<ShutdownSnapshot> GetCloseStateAsync(CancellationToken token = default) => _localClose
        ? Task.FromResult(LocalCloseState("prepared"))
        : SendCloseAsync(HttpMethod.Get, $"/api/v1/shutdown-requests/{_closeRequestId}", null, token);

    public Task<ShutdownSnapshot> StopForCloseAsync(CancellationToken token = default) => _localClose
        ? Task.FromResult(LocalCloseState("stopping"))
        : SendCloseAsync(HttpMethod.Post, $"/api/v1/shutdown-requests/{_closeRequestId}/stop", new { schemaVersion = 1 }, token);

    public async Task AbortCloseAsync(CancellationToken token = default)
    {
        try
        {
            if (!_localClose && _closeDescriptor is not null && _closeRequestId is not null)
                await SendCloseAsync(HttpMethod.Post, $"/api/v1/shutdown-requests/{_closeRequestId}/abort", new { schemaVersion = 1 }, token);
        }
        finally { lock (_operationGate) _acceptNewOperations = true; }
    }

    public async Task<ShutdownSnapshot> CommitCloseAsync(string mode, CancellationToken token = default)
    {
        if (mode is not ("idle" or "background" or "stop")) throw new ArgumentException("关闭方式无效。", nameof(mode));
        if (_localClose) return LocalCloseState("committed", mode);
        try
        {
            return await SendCloseAsync(HttpMethod.Post, $"/api/v1/shutdown-requests/{_closeRequestId}/commit",
                new { schemaVersion = 1, mode }, token);
        }
        catch (Exception error) when (error is HttpRequestException or IOException or OperationCanceledException
            or ControlPlaneException { Code: "CONTROL_PLANE_DISCONNECTED" })
        {
            // The same instance may already have accepted the decision. Do not
            // replay stop commands, and never infer permission to kill a PID.
            try
            {
                var state = await GetCloseStateAsync(CancellationToken.None);
                if (state.State == "committed" && state.Mode == mode) return state;
            }
            catch (Exception readError) when (readError is HttpRequestException or IOException or OperationCanceledException
                or ControlPlaneException { Code: "CONTROL_PLANE_DISCONNECTED" }) { }
            throw;
        }
    }

    public ValueTask DetachForCloseAsync()
    {
        lock (_disposeGate)
        {
            _preserveBackground = true;
            _disposeTask ??= DisposeCoreAsync(preserveBackground: true);
            return new ValueTask(_disposeTask);
        }
    }
}
