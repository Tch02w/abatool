using System.Net;
using System.Reflection;
using AbaqusTools.WinUI.Services;

static class ShutdownClientChecks
{
    public static async Task RunAsync()
    {
        await CheckCreationDrainAsync();
        foreach (var recoverable in new[] { true, false })
        {
            var host = new ControlPlaneHost();
            var handler = new LostCommitHandler(recoverable);
            ((HttpClient)Field("_httpClient").GetValue(host)!).Dispose();
            Field("_httpClient").SetValue(host, new HttpClient(handler));
            Field("_closeRequestId").SetValue(host, "close-test");
            Field("_closeDescriptor").SetValue(host, new ControlPlaneDescriptor
            {
                SchemaVersion = 1, ApiVersion = "v1", InstanceId = "pinned-instance", Pid = 1,
                Host = "127.0.0.1", Port = 12345, BaseUrl = "http://127.0.0.1:12345", Token = "close-test-token",
            });
            try
            {
                try
                {
                    var state = await host.CommitCloseAsync("background");
                    if (!recoverable || state.Mode != "background" || state.StopBackend)
                        throw new Exception("Unconfirmed close accepted");
                }
                catch (ControlPlaneException error) when (!recoverable && error.Code == "CONTROL_PLANE_DISCONNECTED") { }
                if (handler.Calls != 2) throw new Exception("Commit replayed or backend reconnected");
            }
            finally { await host.DetachForCloseAsync(); }
        }
        Console.WriteLine("2 pinned-instance lost close acknowledgement checks passed.");
    }

    private static async Task CheckCreationDrainAsync()
    {
        var host = new ControlPlaneHost();
        ((HttpClient)Field("_httpClient").GetValue(host)!).Dispose();
        var handler = new PreparedHandler();
        Field("_httpClient").SetValue(host, new HttpClient(handler));
        var gate = (SemaphoreSlim)Field("_operationCreationGate").GetValue(host)!;
        await gate.WaitAsync();
        var requestId = Guid.NewGuid();
        handler.RequestId = requestId.ToString();
        var preparing = host.PrepareCloseAsync(requestId);
        if (preparing.IsCompleted || handler.Calls != 0) throw new Exception("Close raced an active task creation");
        Field("_descriptor").SetValue(host, new ControlPlaneDescriptor
        {
            SchemaVersion = 1, ApiVersion = "v1", InstanceId = "started-during-create", Pid = Environment.ProcessId,
            Host = "127.0.0.1", Port = 12345, BaseUrl = "http://127.0.0.1:12345", Token = "close-test-token",
        });
        gate.Release();
        try
        {
            var state = await preparing;
            if (state.SafeToStop || state.Operations.Count != 1 || handler.Calls != 2)
                throw new Exception("Newly started backend was treated as absent during close");
        }
        finally { await host.DetachForCloseAsync(); }
        Console.WriteLine("1 close-during-creation race check passed.");
    }

    private sealed class PreparedHandler : HttpMessageHandler
    {
        public int Calls { get; private set; }
        public string RequestId { get; set; } = "";
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Calls++;
            var body = request.RequestUri?.AbsolutePath switch
            {
                "/healthz" => """{"schemaVersion":1,"apiVersion":"v1","status":"ok","instanceId":"started-during-create","capabilities":["jobQueue.scanExternalJobs","odb.resultGraph"]}""",
                "/api/v1/shutdown-requests" => $$"""{"schemaVersion":1,"kind":"controlPlane.shutdown","requestId":"{{RequestId}}","state":"prepared","safeToStop":false,"pendingRequests":0,"stopBackend":false,"operations":[{"kind":"postprocess","name":"active"}]}""",
                _ => throw new Exception("Unexpected prepare request"),
            };
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(body) });
        }
    }

    private static FieldInfo Field(string name) => typeof(ControlPlaneHost).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!;

    private sealed class LostCommitHandler(bool recoverable) : HttpMessageHandler
    {
        public int Calls { get; private set; }
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            Calls++;
            if (request.Headers.Authorization?.ToString() != "Bearer close-test-token" || request.RequestUri?.Port != 12345)
                throw new Exception("Close left its prepared instance");
            if (Calls == 1 && request.Method == HttpMethod.Post && request.RequestUri.AbsolutePath == "/api/v1/shutdown-requests/close-test/commit")
                throw new HttpRequestException("Commit response lost after acceptance");
            if (Calls != 2 || request.Method != HttpMethod.Get || request.RequestUri.AbsolutePath != "/api/v1/shutdown-requests/close-test")
                throw new Exception("Unexpected close retry or new-backend request");
            if (!recoverable) throw new HttpRequestException("Receipt unreachable");
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(
                """{"schemaVersion":1,"kind":"controlPlane.shutdown","requestId":"close-test","state":"committed","mode":"background","safeToStop":false,"pendingRequests":0,"stopBackend":false,"operations":[{"kind":"postprocess","name":"active"}]}""") });
        }
    }
}
