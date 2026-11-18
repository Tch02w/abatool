using System.Diagnostics;
using System.Net;
using System.Reflection;
using System.Text.Json;
using System.Text.Json.Nodes;
using AbaqusTools.WinUI.Services;

if (args.Contains("--wait-child"))
{
    await Task.Delay(Timeout.Infinite);
    return 0;
}

try
{
    if (args.Length == 3 && args[0] == "--archive-recovery-api")
    {
        var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(args[1]),
            new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        await using var host = new ControlPlaneHost();
        SetField(host, "_descriptor", descriptor);
        SetField(host, "_descriptorPath", args[1]);
        await ArchivePresentationChecks.RunApi(host, args[2]);
        return 0;
    }
    if (args.Length is 3 or 4 && args[0] == "--execution-options-api")
    {
        var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(args[1]),
            new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        await using var host = new ControlPlaneHost();
        SetField(host, "_descriptor", descriptor);
        SetField(host, "_descriptorPath", args[1]);
        await ExecutionOptionChecks.RunApi(host, args[2], args.Length == 4 && args[3] == "unsupported");
        return 0;
    }
    if (args.Length == 2 && args[0] is "--notifications-api" or "--archive-notifications-api")
    {
        var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(args[1]),
            new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
        await using var host = new ControlPlaneHost();
        SetField(host, "_descriptor", descriptor);
        SetField(host, "_descriptorPath", args[1]);
        var inbox = await host.GetJobNotificationsAsync();
        var archive = args[0] == "--archive-notifications-api";
        if (inbox.UnreadCount != 1 || inbox.Items[0].Status != (archive ? "succeeded" : "cancelled")
            || (archive && !inbox.Items[0].IsArchive))
            throw new Exception("Expected the previous owned attempt's durable cancellation notice");
        var acknowledged = await host.AcknowledgeJobNotificationsAsync([inbox.Items[0].Id]);
        if (acknowledged.UnreadCount != 0 || (await host.GetJobNotificationsAsync()).UnreadCount != 0)
            throw new Exception("Acknowledged execution reappeared after refresh");
        Console.WriteLine("Production notification client: persisted inbox, acknowledgement, no replay passed.");
        return 0;
    }
    if (args.Length == 3 && args[0] == "--close-api")
    {
        await CheckCloseApi(args[1], args[2]);
        return 0;
    }
    if (args.Length == 4 && args[0] is "--batch-api" or "--batch-recover-api")
    {
        await CheckBatchApi(args[1], args[2], args[3], recover: args[0] == "--batch-recover-api");
        return 0;
    }
    if ((args.Length == 3 || (args.Length == 5 && args[3] == "--odb")
        || (args.Length == 4 && args[3] == "--execution-options")) && args[0] == "--launch-bundle")
    {
        Environment.SetEnvironmentVariable("ABAQUS_TOOLS_ROOT", Path.GetFullPath(args[1]));
        Environment.SetEnvironmentVariable("ABAQUS_TOOLS_PYTHON", null);
        Environment.SetEnvironmentVariable("PYTHONPATH", null);
        Environment.SetEnvironmentVariable("PYTHONHOME", null);
        Environment.SetEnvironmentVariable("ABAQUS_SUBMITTER_DATA_DIR", Path.Combine(Path.GetFullPath(args[2]), "submitter"));
        Environment.SetEnvironmentVariable("ABAQUS_POSTPROCESSOR_DATA_DIR", Path.Combine(Path.GetFullPath(args[2]), "postprocessor"));
        await using var host = new ControlPlaneHost();
        var descriptorPath = Path.Combine(Path.GetFullPath(args[2]), "control-plane.json");
        SetField(host, "_descriptorPath", descriptorPath);
        SetField(host, "_launchLockPath", descriptorPath + ".lock");
        var ready = await host.EnsureReadyAsync();
        using var child = Process.GetProcessById(ready.Pid);
        var expected = Path.Combine(Path.GetFullPath(args[1]), "control-plane", ControlPlaneLaunch.BundleExecutable);
        if (!string.Equals(child.MainModule?.FileName, expected, StringComparison.OrdinalIgnoreCase))
            throw new Exception("Host launched an unexpected control-plane executable");
        await host.GetLocalResourceAsync();
        await host.GetLocalQueueRuntimeAsync();
        if (args.Length == 4)
        {
            var fixture = Path.Combine(Path.GetFullPath(args[2]), "client_case.inp");
            await File.WriteAllTextAsync(fixture, "*Heading\nSubmission parameter fixture; no solver.\n");
            await ExecutionOptionChecks.RunApi(host, fixture);
        }
        if (args.Length == 5)
        {
            var source = Path.GetFullPath(args[4]);
            var copy = Path.Combine(Path.GetFullPath(args[2]), Path.GetFileName(source));
            File.Copy(source, copy, overwrite: false);
            byte[] before;
            using (var input = File.OpenRead(copy)) before = System.Security.Cryptography.SHA256.HashData(input);
            var snapshot = await host.StartOdbCompatibilityCheckAsync(Path.GetDirectoryName(copy)!, [copy], true, Guid.NewGuid());
            Console.WriteLine($"Packaged Abaqus compatibility operation: {snapshot.OperationId}");
            snapshot = await host.PollOperationUntilTerminalAsync(snapshot);
            byte[] after;
            using (var input = File.OpenRead(copy)) after = System.Security.Cryptography.SHA256.HashData(input);
            var unchanged = before.SequenceEqual(after);
            await File.WriteAllTextAsync(Path.Combine(Path.GetFullPath(args[2]), "abaqus-verification.json"),
                JsonSerializer.Serialize(new { snapshot, sourceUnchanged = unchanged, sha256 = Convert.ToHexString(after) }));
            if (!snapshot.IsSuccessful || snapshot.Results.Count != 1 || snapshot.Results[0].Status != "valid" || !unchanged)
                throw new Exception("Packaged read-only Abaqus check failed; inspect abaqus-verification.json");
            Console.WriteLine("Packaged Abaqus worker read-only ODB check passed; SHA256 unchanged.");
        }
        await host.DisposeAsync();
        if (!child.WaitForExit(10000)) throw new Exception("Owned idle bundle did not stop");
        Console.WriteLine("Bundled host startup, resource/queue APIs, and safe shutdown passed.");
        return 0;
    }
    if (args.Length == 6 && args[0] == "--results-api")
    {
        await CheckResultsApi(args[1], args[2], args[3], args[4], args[5]);
        return 0;
    }
    if (args.Length == 4 && args[0] == "--region-api")
    {
        await CheckRegionApi(args[1], args[2], args[3]);
        return 0;
    }
    if (args.Length == 4 && args[0] == "--upgrade-api")
    {
        await CheckUpgradeApi(args[1], args[2], args[3]);
        return 0;
    }
    await Check("idle reservation", """{"schemaVersion":1,"scope":"all-workers-v1","safeToStop":true,"operations":[]}""", true);
    await Check("active background job", """{"schemaVersion":1,"scope":"all-workers-v1","safeToStop":false,"operations":[{"kind":"local.job"}]}""", false);
    await Check("contradictory response", """{"schemaVersion":1,"scope":"all-workers-v1","safeToStop":true,"operations":[{}]}""", false);
    await Check("old ODB-only response", """{"schemaVersion":1,"safeToStop":true,"operations":[]}""", false);
    await Check("invalid scope", """{"schemaVersion":1,"scope":{},"safeToStop":true,"operations":[]}""", false);
    await Check("malformed response", "not json", false);
    await Check("unknown schema", """{"schemaVersion":2,"safeToStop":true,"operations":[]}""", false);
    await Check("missing endpoint", "{}", false, HttpStatusCode.NotFound);
    await Check("connection lost", "", false, disconnect: true);
    await Check("reconnect failure", "", false, connectionCleanup: true);
    await Check("background detach preserves owned backend and active tasks", "", false, detach: true);
    await ShutdownClientChecks.RunAsync();
    CheckUpgradeContracts();
    CheckMergeRecoveryContracts();
    CheckBatchContracts();
    ControlPlaneLaunchChecks.Run();
    WorkbenchSessionChecks.Run();
    MemoryPresentationChecks.Run();
    ArchivePresentationChecks.Run();
    RemoteRecoveryChecks.Run();
    RemoteServerSnapshotChecks.Run();
    JobNotificationChecks.Run();
    ExecutionOptionChecks.Run();
    Console.WriteLine("11 host process lifecycle checks passed.");
    return 0;
}
catch (Exception error)
{
    Console.Error.WriteLine(error);
    return 1;
}

static void SetField(ControlPlaneHost host, string name, object value) =>
    typeof(ControlPlaneHost).GetField(name, BindingFlags.Instance | BindingFlags.NonPublic)!.SetValue(host, value);

static async Task CheckCloseApi(string descriptorPath, string mode)
{
    var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(descriptorPath),
        new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
    var host = new ControlPlaneHost();
    SetField(host, "_descriptor", descriptor);
    SetField(host, "_descriptorPath", descriptorPath);
    try
    {
        await host.GetActiveRemoteTransfersAsync();
        var prepared = await host.PrepareCloseAsync(Guid.NewGuid());
        if (prepared.State != "prepared" || prepared.PendingRequests != 0) throw new Exception("Unexpected close preparation");
        if (mode == "abort")
        {
            await host.AbortCloseAsync();
            if (!(bool)typeof(ControlPlaneHost).GetField("_acceptNewOperations", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(host)!)
                throw new Exception("Cancelling close did not restore client admission");
            await host.GetLocalQueueRuntimeAsync();
        }
        else
        {
            if (mode == "stop")
            {
                await host.StopForCloseAsync();
                using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                while (!(await host.GetCloseStateAsync(timeout.Token)).SafeToStop) await Task.Delay(50, timeout.Token);
            }
            var committed = await host.CommitCloseAsync(mode);
            if (committed.State != "committed" || committed.Mode != mode || committed.StopBackend != (mode != "background"))
                throw new Exception("Incorrect close acknowledgement");
        }
        Console.WriteLine("Production C# close API passed: " + mode);
    }
    finally { await host.DetachForCloseAsync(); }
}

static async Task CheckBatchApi(string descriptorPath, string fixturePath, string reportPath, bool recover)
{
    var json = new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true };
    var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(descriptorPath), json)!;
    var fixture = JsonNode.Parse(await File.ReadAllTextAsync(fixturePath))!;
    var sources = fixture["sources"]!.AsArray().Select(n => n!.GetValue<string>()).ToArray();
    if (sources.Length != 3 || sources.Any(p => !File.Exists(p))) throw new Exception("Expected three existing fixture ODBs");
    var directory = fixture["outputDirectory"]!.GetValue<string>();
    var requestId = Guid.Parse(fixture["clientRequestId"]!.GetValue<string>());
    await using var host = new ControlPlaneHost();
    SetField(host, "_descriptor", descriptor);
    SetField(host, "_descriptorPath", descriptorPath);
    var graph = await host.GetOdbResultGraphAsync();
    string[] targets = ["branch0", "branch1"];
    if (!recover)
    {
        if (graph.Revision != 0 || graph.Nodes.Count != 0) throw new Exception("Use an isolated empty result graph");
        graph = await host.SaveOdbResultGraphAsync(0, directory,
            [new() { NodeId = "base", Name = Path.GetFileNameWithoutExtension(sources[0]), OdbPath = sources[0] },
             new() { NodeId = targets[0], Name = Path.GetFileNameWithoutExtension(sources[1]), ParentNodeId = "base", OdbPath = sources[1] },
             new() { NodeId = targets[1], Name = Path.GetFileNameWithoutExtension(sources[2]), ParentNodeId = "base", OdbPath = sources[2] }]);
        var plans = await host.PreviewOdbResultGraphPlansAsync(targets);
        if (!plans.Valid || plans.Plans.Count != 2 || plans.Plans.Any(p => p.Steps.Count != 1 || p.Steps[0].OriginalOdb != sources[0]))
            throw new Exception("Branch preview does not match the real ancestry");
    }
    if (graph.Revision != 1 || graph.Nodes.Count != 3) throw new Exception("Persisted graph was not restored");
    var source = new { kind = "graph", revision = graph.Revision, targetNodeIds = targets };
    var options = new OdbResultBatchOptions { IncludeHistory = true, CompressResult = true, CopyOriginal = false };
    var snapshot = await host.StartOdbResultBatchAsync(source, options, requestId);
    var repeat = await host.StartOdbResultBatchAsync(source, options, requestId);
    if (repeat.OperationId != snapshot.OperationId) throw new Exception("Batch creation was not idempotent");
    var statePath = Path.Combine(Path.GetDirectoryName(reportPath)!, "current-batch.json");
    string? previous = null;
    while (true)
    {
        var display = $"{snapshot.Status} {snapshot.CompletedSteps}/{snapshot.TotalSteps} {snapshot.Phase} "
            + $"{snapshot.CurrentOperation?.Progress.Percent}% {snapshot.CurrentOperation?.Progress.Phase}";
        if (display != previous)
        {
            previous = display;
            Console.WriteLine(display);
            await File.WriteAllTextAsync(statePath, JsonSerializer.Serialize(snapshot, json));
        }
        if (!snapshot.IsActive) break;
        await Task.Delay(500);
        snapshot = await host.GetOdbResultBatchAsync(snapshot.OperationId);
    }
    await File.WriteAllTextAsync(reportPath, JsonSerializer.Serialize(snapshot, json));
    if (snapshot.Status != "succeeded" || snapshot.Results.Count != 2 || snapshot.CompletedSteps != 2 || snapshot.TotalSteps != 2)
        throw new Exception("Real batch did not complete both independent targets; inspect the saved report");
    var history = await host.ListOdbResultBatchesAsync();
    if (history.Operations.Count != 1 || history.Operations[0].OperationId != snapshot.OperationId)
        throw new Exception("Batch history is inconsistent");
    var merges = await host.ListOdbMergeOperationsAsync();
    if (merges.Operations.Count != 2 || merges.Operations.Any(m => !m.IsSuccessful || m.Result?.ValidationReport is null
            || m.Request?.OriginalOdb != sources[0] || m.Request.IncludeHistory != true))
        throw new Exception("Completed branches lost source identity or content-validation receipts");
    await File.WriteAllTextAsync(Path.ChangeExtension(reportPath, ".merges.json"), JsonSerializer.Serialize(merges, json));
    Console.WriteLine(recover ? "Production C# client restored the completed batch without new merges." : "Production C# client completed the two-target batch.");
}

static void CheckBatchContracts()
{
    var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
    var value = JsonNode.Parse("""
        {"schemaVersion":1,"kind":"odb.result_batch","operationId":"batch-id","clientRequestId":"request-id",
         "status":"suspended","phase":"等待继续","totalSteps":2,"completedSteps":1,"options":{},
         "plans":[{"valid":true,"steps":[{},{}]}],"results":[]}
        """)!;
    var paused = value.Deserialize<OdbResultBatchSnapshot>(options)!;
    paused.Validate("batch-id");
    if (!paused.CanResume || paused.IsActive) throw new Exception("Suspended batch must offer explicit resume");
    value["status"] = "running";
    var running = value.Deserialize<OdbResultBatchSnapshot>(options)!;
    running.Validate();
    if (!running.IsActive || running.CanResume) throw new Exception("Running batch cannot resume twice");
    foreach (var field in new[] { "status", "completedSteps", "schemaVersion" })
    {
        var invalid = value.DeepClone();
        if (field == "status") invalid[field] = "succeeded"; // One stage and result still missing.
        else invalid[field] = 99;
        try { invalid.Deserialize<OdbResultBatchSnapshot>(options)!.Validate(); }
        catch (ControlPlaneException) { continue; }
        throw new Exception($"Invalid batch {field} was accepted");
    }
    try { paused.Validate("other-id"); }
    catch (ControlPlaneException) { Console.WriteLine("6 batch recovery contract checks passed."); return; }
    throw new Exception("Mismatched batch identity was accepted");
}

static void CheckMergeRecoveryContracts()
{
    var interrupted = JsonSerializer.Deserialize<OdbMergeOperationSnapshot>("""
        {"status":"failed","error":{"code":"ODB_MERGE_INTERRUPTED","message":"原任务待核对"},
         "progress":{"percent":60,"phase":"旧进度"}}
        """)!;
    if (!interrupted.IsInterrupted || !interrupted.IsTerminal || interrupted.IsSuccessful
        || interrupted.CompletionMessage != "原任务待核对")
        throw new Exception("Interrupted merge must preserve uncertainty and its recovery guidance");
    var success = JsonSerializer.Deserialize<OdbMergeOperationSnapshot>("""
        {"status":"succeeded","progress":{"percent":100,"phase":"4 个分析步无结果帧，请核对计算状态"},
         "result":{"outputOdb":"full_joined.odb","validationReport":"validation.json"}}
        """)!;
    if (!success.CompletionMessage.Contains("4 个分析步") || success.Result?.ValidationReport != "validation.json")
        throw new Exception("Completion must retain partial-result guidance and receipt path");
    var unsaved = JsonSerializer.Deserialize<OdbMergeOperationSnapshot>("""
        {"status":"succeeded","persistenceWarning":"记录未保存","progress":{"percent":100,"phase":"已完成"}}
        """)!;
    if (!unsaved.IsSuccessful || unsaved.CompletionMessage != "记录未保存")
        throw new Exception("Committed result remains successful while persistence warning takes priority");
    Console.WriteLine("3 merge recovery presentation checks passed.");
}

static void CheckUpgradeContracts()
{
    var root = Path.GetFullPath(Path.GetTempPath());
    var source = Path.Combine(root, "model.odb");
    var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
    var preview = new OdbUpgradePreview
    {
        SchemaVersion = 1, Root = root, TargetRelease = "2025",
        RequiresCompatibilityCheck = true, RequiresConfirmation = true,
        SourcePolicy = "backup-original-before-validated-replacement",
        CancellationPolicy = "finish-active-file-then-stop",
        Entries = [new OdbUpgradeEntry { SourcePath = source, UpgradedPath = source,
            BackupPath = Path.Combine(root, "model-old.odb"), TemporaryPath = Path.Combine(root, "model-upgrading.odb"),
            SourceSizeBytes = 123, SourceMtimeNs = 1_798_000_000_123_456_789L }],
    };
    var snapshot = new OdbUpgradeOperationSnapshot
    {
        SchemaVersion = 1, Kind = "odb.upgrade", OperationId = "test-operation", Status = "succeeded", Version = 3,
        Preview = preview, Results = [new OdbUpgradeResult { SourcePath = source, Status = "upgraded" }],
        Progress = new OdbUpgradeProgress { Completed = 1, Total = 1 },
    };
    var json = JsonSerializer.SerializeToNode(snapshot, options)!;
    var roundtrip = json.Deserialize<OdbUpgradeOperationSnapshot>(options)!;
    OdbUpgradeContractValidation.Validate(roundtrip, "test-operation");
    if (roundtrip.Preview.Entries[0].SourceMtimeNs != preview.Entries[0].SourceMtimeNs)
        throw new Exception("Native client rounded nanosecond fingerprint");
    Action<JsonNode>[] corruptions = [
        node => node["preview"]!["requiresConfirmation"] = false,
        node => node["preview"]!["entries"]![0]!["backupPath"] = source,
        node => node["preview"]!["entries"] = new JsonArray(),
        node => node["status"] = "unknown",
        node => node["results"] = new JsonArray(),
        node => node["results"]![0]!["source_path"] = Path.Combine(root, "unexpected.odb"),
        node => node["progress"]!["completed"] = 2,
        node => node["progress"] = null,
    ];
    foreach (var corrupt in corruptions)
    {
        var changed = json.DeepClone();
        corrupt(changed);
        try { OdbUpgradeContractValidation.Validate(changed.Deserialize<OdbUpgradeOperationSnapshot>(options)!); }
        catch (ControlPlaneException) { continue; }
        throw new Exception("Unsafe upgrade response was accepted");
    }
    Console.WriteLine("9 upgrade contract checks passed.");
}

static async Task CheckUpgradeApi(string descriptorPath, string root, string source)
{
    var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(descriptorPath),
        new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
    await using var host = new ControlPlaneHost();
    SetField(host, "_descriptor", descriptor);
    SetField(host, "_descriptorPath", descriptorPath);
    var preview = await host.PreviewOdbUpgradeAsync(root, [source]);
    if (preview.Entries.Count != 1 || preview.Entries[0].SourcePath != source)
        throw new Exception("Native preview paths differ from server paths");
    var key = Guid.NewGuid();
    var initial = await host.StartOdbUpgradeAsync(preview, key);
    var again = await host.StartOdbUpgradeAsync(preview, key);
    if (again.OperationId != initial.OperationId) throw new Exception("Native client duplicated an upgrade");
    var active = await host.ListOdbUpgradeOperationsAsync(activeOnly: true);
    if (active.Operations.Count != 1) throw new Exception("Active upgrade recovery failed");
    var snapshot = await host.GetOdbUpgradeOperationAsync(initial.OperationId);
    await host.CancelOdbUpgradeOperationAsync(snapshot.OperationId);
    var final = await host.PollOdbUpgradeUntilTerminalAsync(snapshot);
    if (final.Status != "cancelled" || final.Results.Count != 1
        || final.Results[0].SourcePath != source || final.Results[0].BackupPath != preview.Entries[0].BackupPath
        || final.Progress.Completed != 1 || final.Results[0].Status != "upgraded")
        throw new Exception("Native client lost the safely completed file receipt");
    var history = await host.ListOdbUpgradeOperationsAsync();
    if (history.Operations.Single().OperationId != final.OperationId)
        throw new Exception("Native upgrade history failed");
    Console.WriteLine("Native HTTP upgrade workflow passed (simulated file upgrader).");
}

static async Task CheckResultsApi(string descriptorPath, string root, string batch, string csvPath, string xlsxPath)
{
    var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(descriptorPath),
        new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
    await using var host = new ControlPlaneHost();
    SetField(host, "_descriptor", descriptor);
    SetField(host, "_descriptorPath", descriptorPath);
    Task<ResultRecordsResponse> Page(int offset, string query = "") =>
        host.GetResultRecordsAsync(root, batch, batch, "all", query, "", false, offset: offset);
    var first = await Page(0);
    if (!first.HasMore || first.Records.Count != 500) throw new Exception("Expected a full first page with more results");
    var second = await Page(first.Records.Count);
    var back = await Page(0);
    var firstPaths = first.Records.Select(r => r.Path).ToArray();
    if (second.Records.Count == 0 || second.HasMore || second.FilteredCount != first.FilteredCount ||
        second.Offset + second.Records.Count != first.FilteredCount ||
        firstPaths.Intersect(second.Records.Select(r => r.Path), StringComparer.OrdinalIgnoreCase).Any() ||
        !back.Records.Select(r => r.Path).SequenceEqual(firstPaths))
        throw new Exception("Page offsets, order or records changed between reads");
    var last = second.Records[^1];
    var filtered = await Page(0, last.Name);
    if (!filtered.Records.Any(r => r.Path == last.Path)) throw new Exception("Filtered page lost selected file");
    var csv = await host.GetResultPreviewAsync(root, csvPath);
    var limited = await host.GetResultPreviewAsync(root, csvPath, 2);
    var xlsx = await host.GetResultPreviewAsync(root, xlsxPath);
    if (new[] { csv, limited, xlsx }.Any(p => p.Kind != "table")) throw new Exception("Table preview missing");
    Console.WriteLine(JsonSerializer.Serialize(new
    {
        firstPage = first.Records.Count, secondPage = second.Records.Count, total = first.FilteredCount,
        filtered = filtered.FilteredCount, csv, limited, xlsx,
    }));
}

static async Task CheckRegionApi(string descriptorPath, string root, string source)
{
    var descriptor = JsonSerializer.Deserialize<ControlPlaneDescriptor>(await File.ReadAllTextAsync(descriptorPath),
        new JsonSerializerOptions(JsonSerializerDefaults.Web))!;
    await using var host = new ControlPlaneHost();
    SetField(host, "_descriptor", descriptor);
    SetField(host, "_descriptorPath", descriptorPath);
    var request = new OdbRegionExtractionRequest
    {
        Root = root, Path = source, Method = "truss_reference_area", AcknowledgeReferenceArea = true,
        ReferenceAreaOverride = null,
        Region = new() { ["scope"] = "instance", ["instance"] = "钢筋-1", ["kind"] = "instance", ["name"] = "钢筋-1" },
        Frames = [new() { Step = "Load", Index = 1 }],
    };
    var initial = await host.StartOdbRegionExtractionAsync(request);
    var again = await host.StartOdbRegionExtractionAsync(request);
    if (initial.OperationId != again.OperationId) throw new Exception("Region request duplicated");
    var final = await host.PollOdbPostprocessUntilTerminalAsync(initial);
    if (final.Kind != "odb.postprocess.region" || final.Status != "succeeded" || final.Result?.OutputCount != 1)
        throw new Exception("Native region extraction result invalid: " + final.Error?.Message);
    var solid = await host.StartOdbRegionExtractionAsync(new OdbRegionExtractionRequest
    {
        Root = root, Path = source, Method = "solid_section",
        Region = new() { ["scope"] = "assembly", ["instance"] = "", ["kind"] = "element_set", ["name"] = "混凝土" },
        Frames = [new() { Step = "Load", Index = 1 }],
        Section = new() { Origin = [0, 0, 0], Normal = [0, 0, 2], Offsets = [10, 20],
            MomentReference = "point", MomentPoint = [1, 2, 3] },
    });
    var solidFinal = await host.PollOdbPostprocessUntilTerminalAsync(solid);
    if (solidFinal.Status != "succeeded") throw new Exception("Native solid DTO failed: " + solidFinal.Error?.Message);
    Console.WriteLine("Native HTTP region extraction workflow passed (simulated worker).");
}

static async Task Check(string label, string body, bool shouldExit,
    HttpStatusCode status = HttpStatusCode.OK, bool disconnect = false, bool connectionCleanup = false, bool detach = false)
{
    var directory = Path.Combine(Path.GetTempPath(), "abatool-host-test-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(directory);
    var descriptorPath = Path.Combine(directory, "control-plane.json");
    using var child = Process.Start(new ProcessStartInfo("dotnet")
    {
        ArgumentList = { Assembly.GetExecutingAssembly().Location, "--wait-child" },
        UseShellExecute = false,
        CreateNoWindow = true,
    }) ?? throw new Exception("Unable to create test child");
    var handler = new ShutdownResponseHandler(body, status, disconnect);
    var host = new ControlPlaneHost();
    var originalClient = (HttpClient)typeof(ControlPlaneHost)
        .GetField("_httpClient", BindingFlags.Instance | BindingFlags.NonPublic)!.GetValue(host)!;
    originalClient.Dispose();
    SetField(host, "_httpClient", new HttpClient(handler));
    SetField(host, "_descriptorPath", descriptorPath);
    SetField(host, "_ownedProcess", Process.GetProcessById(child.Id));
    SetField(host, "_ownedInstanceId", "owned-test-instance");
    SetField(host, "_descriptor", new ControlPlaneDescriptor
    {
        SchemaVersion = 1, ApiVersion = "v1", InstanceId = "owned-test-instance", Pid = child.Id,
        Host = "127.0.0.1", Port = 12345, BaseUrl = "http://127.0.0.1:12345", Token = "test-token",
    });
    await File.WriteAllTextAsync(descriptorPath,
        $$"""{"schemaVersion":1,"instanceId":"owned-test-instance","pid":{{child.Id}}}""");
    try
    {
        if (connectionCleanup)
        {
            typeof(ControlPlaneHost).GetMethod("StopOwnedProcess", BindingFlags.Instance | BindingFlags.NonPublic)!
                .Invoke(host, [false]);
        }
        if (detach)
        {
            foreach (var field in new[] { "_activeOperationIds", "_activeResultIndexOperationIds", "_activeOdbMergeOperationIds",
                         "_activePostprocessOperationIds", "_activeResultBatchIds" })
                ((HashSet<string>)typeof(ControlPlaneHost).GetField(field, BindingFlags.Instance | BindingFlags.NonPublic)!
                    .GetValue(host)!).Add("tracked-active-operation");
            await Task.WhenAll(host.DetachForCloseAsync().AsTask(), host.DetachForCloseAsync().AsTask());
        }
        else await Task.WhenAll(host.DisposeAsync().AsTask(), host.DisposeAsync().AsTask());
        if (shouldExit)
        {
            using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(5));
            await child.WaitForExitAsync(deadline.Token);
        }
        if (child.HasExited != shouldExit)
            throw new Exception($"{label}: wrong child lifetime");
        if (File.Exists(descriptorPath) == shouldExit)
            throw new Exception($"{label}: descriptor should follow backend lifetime");
        if (handler.Calls != (connectionCleanup || detach ? 0 : 1))
            throw new Exception($"{label}: duplicate or missing shutdown reservation");
        Console.WriteLine($"PASS {label}");
    }
    finally
    {
        // Only terminate the helper created by this test, never a real backend.
        if (!child.HasExited) child.Kill(entireProcessTree: true);
        await child.WaitForExitAsync();
        await host.DisposeAsync();
        File.Delete(descriptorPath);
        Directory.Delete(directory);
    }
}

sealed class ShutdownResponseHandler(string body, HttpStatusCode status, bool disconnect) : HttpMessageHandler
{
    public int Calls { get; private set; }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken token)
    {
        Calls++;
        if (request.Method != HttpMethod.Post
            || request.RequestUri?.AbsolutePath != "/api/v1/odb-upgrade-shutdown-check"
            || request.Headers.Authorization?.ToString() != "Bearer test-token")
            throw new Exception("Unexpected shutdown request");
        if (disconnect) throw new HttpRequestException("Simulated lost connection");
        return Task.FromResult(new HttpResponseMessage(status) { Content = new StringContent(body) });
    }
}
