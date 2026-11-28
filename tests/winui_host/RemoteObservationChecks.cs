using System.Net;
using System.Reflection;
using System.Text.Json;
using AbaqusTools.WinUI.Services;

static class RemoteObservationChecks
{
    public static async Task RunJobOutputAsync(ControlPlaneHost host, string id, string localFile, bool original)
    {
        var job = await host.GetRemoteJobAsync(id);
        var servers = await host.GetRemoteServersAsync();
        var selected = servers.Profiles.Single(p => p.ProfileName == servers.Connection.ProfileName);
        await host.BrowseRemoteDirectoryAsync(job.WorkDirectory, expectedProfile: selected);
        var other = new RemoteServerProfile
        {
            ProfileName = selected.ProfileName, Host = selected.Host, Username = selected.Username,
            Port = selected.Port == 22 ? 2222 : 22, HostFingerprint = selected.HostFingerprint,
            ComputeRoot = selected.ComputeRoot, AllowedRoots = selected.AllowedRoots, AbaqusCommand = selected.AbaqusCommand,
        };
        try
        {
            await host.BrowseRemoteDirectoryAsync(job.WorkDirectory, expectedProfile: other);
            throw new Exception("Resource browser accepted the wrong port");
        }
        catch (ControlPlaneException error) when (error.Code == "REMOTE_CONNECTION_CHANGED") { }
        try
        {
            await host.StartRemoteTransferAsync("download", job.Files["sta"], localFile, true, expectedProfile: other);
            throw new Exception("Resource transfer accepted the wrong port");
        }
        catch (ControlPlaneException error) when (error.Code == "REMOTE_CONNECTION_CHANGED") { }
        try
        {
            await host.BrowseRemoteDirectoryAsync(job.WorkDirectory, sourceOperationId: job.OperationId);
            if (!original) throw new Exception("The job browser listed the alternate server");
        }
        catch (ControlPlaneException error) when (!original && error.Code == "REMOTE_CONNECTION_CHANGED") { }
        var transfer = await host.StartRemoteTransferAsync("download", job.Files["sta"], localFile,
            overwrite: true, sourceOperationId: job.OperationId);
        var result = await host.PollRemoteTransferUntilTerminalAsync(transfer.OperationId);
        if (result.Request.SourceOperationId != id || result.Status != (original ? "succeeded" : "failed"))
            throw new Exception("Unexpected output transfer identity or outcome");
        Console.WriteLine("Remote job output binding verified");
    }

    public static async Task RunApiAsync(string descriptorPath, string operationId)
    {
        var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(descriptorPath),
            new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        var host = new ControlPlaneHost();
        Field("_descriptor").SetValue(host, descriptor);
        Field("_descriptorPath").SetValue(host, descriptorPath);
        try
        {
            var active = await host.GetActiveRemoteTransfersAsync();
            if (active.Operations.Count(item => item.OperationId == operationId) != 1)
                throw new Exception("Active transfer not recovered");
            var observations = 0;
            using var cancel = new CancellationTokenSource(TimeSpan.FromMilliseconds(500));
            try
            {
                await host.PollRemoteTransferUntilTerminalAsync(operationId, _ => observations++, cancel.Token);
                throw new Exception("Held transfer unexpectedly ended");
            }
            catch (OperationCanceledException) when (cancel.IsCancellationRequested) { }
            var stillRunning = await host.GetRemoteTransferAsync(operationId);
            if (observations == 0 || stillRunning.Status != "running")
                throw new Exception("Cancelling observation changed or lost the transfer");
            Console.WriteLine("Live HTTP observation cancellation preserved the original running transfer");
        }
        finally { await host.DetachForCloseAsync(); }
    }

    public static async Task RunAsync()
    {
        var handler = new ObservationHandler();
        await using var host = CreateHost(handler);
        var gate = (SemaphoreSlim)Field("_connectionGate").GetValue(host)!;
        await gate.WaitAsync();
        Task[] reads = [host.GetRemoteServersAsync(), host.GetActiveRemoteTransfersAsync(), host.GetRemoteTransferAsync("transfer-1")];
        try
        {
            await Task.Delay(TimeSpan.FromSeconds(10.4));
            if (reads.Any(task => task.IsCompleted))
                throw new Exception("State-read deadline expired while only waiting for backend readiness");
        }
        finally { gate.Release(); }
        await Task.WhenAll(reads);
        if (handler.Reads != 3 || handler.Writes != 0) throw new Exception("Readiness wait duplicated a request");
        Console.WriteLine("PASS three status reads wait for readiness without consuming their response budget");

        handler.DelayReads = true;
        try
        {
            await host.GetActiveRemoteTransfersAsync();
            throw new Exception("Expected state read timeout");
        }
        catch (ControlPlaneException error) when (error.Code == "REMOTE_STATE_TIMEOUT" && error.Retryable) { }
        Console.WriteLine("PASS state timeout is distinct from caller cancellation");
        using (var cancelled = new CancellationTokenSource(TimeSpan.FromMilliseconds(40)))
        {
            try
            {
                await host.GetRemoteTransferAsync("transfer-1", cancelled.Token);
                throw new Exception("Expected caller cancellation");
            }
            catch (OperationCanceledException) when (cancelled.IsCancellationRequested) { }
        }
        Console.WriteLine("PASS caller cancellation remains cancellation and sends no write");
        if (handler.Writes != 0) throw new Exception("Observation sent a transfer mutation");
        handler.DelayReads = false;
        await host.GetRemoteTransferAsync("transfer-1");
        await host.DetachForCloseAsync();
        Console.WriteLine("6 remote observation checks passed");
    }

    private static ControlPlaneHost CreateHost(HttpMessageHandler handler)
    {
        var host = new ControlPlaneHost();
        ((HttpClient)Field("_httpClient").GetValue(host)!).Dispose();
        Field("_httpClient").SetValue(host, new HttpClient(handler) { Timeout = Timeout.InfiniteTimeSpan });
        Field("_descriptor").SetValue(host, new ControlPlaneDescriptor
        {
            SchemaVersion = 1, ApiVersion = "v1", InstanceId = "observation-test", Pid = Environment.ProcessId,
            Host = "127.0.0.1", Port = 12345, BaseUrl = "http://127.0.0.1:12345", Token = "test-only",
        });
        return host;
    }

    private static FieldInfo Field(string name) => typeof(ControlPlaneHost).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!;

    private sealed class ObservationHandler : HttpMessageHandler
    {
        public int Reads;
        public int Writes;
        public bool DelayReads;

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
        {
            if (request.Method != HttpMethod.Get) { Interlocked.Increment(ref Writes); throw new Exception("Unexpected write"); }
            var path = request.RequestUri!.AbsolutePath;
            if (path == "/healthz") return Json("""{"schemaVersion":1,"apiVersion":"v1","status":"ok","instanceId":"observation-test","capabilities":["jobQueue.scanExternalJobs","odb.resultGraph"]}""");
            Interlocked.Increment(ref Reads);
            if (DelayReads) await Task.Delay(Timeout.Infinite, token);
            return path switch
            {
                "/api/v1/remote-servers" => Json("""{"schemaVersion":1,"profiles":[],"connection":{"status":"disconnected"}}"""),
                "/api/v1/remote-transfers" => Json("""{"schemaVersion":1,"operations":[]}"""),
                "/api/v1/remote-transfers/transfer-1" => Json("""{"schemaVersion":1,"kind":"remote.transfer","operationId":"transfer-1","status":"running","progress":{"percent":10,"completedBytes":1,"totalBytes":10},"request":{"direction":"download"}}"""),
                _ => throw new Exception("Unexpected observation path " + path),
            };
        }

        private static HttpResponseMessage Json(string body) => new(HttpStatusCode.OK) { Content = new StringContent(body) };
    }
}
