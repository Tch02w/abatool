using System.Text.Json;
using AbaqusTools.WinUI.Services;

internal static class ExecutionOptionChecks
{
    public static void Run()
    {
        var old = JsonSerializer.Deserialize<JobQueueItem>("{}");
        if (old?.GpuCount is not null || old?.ExplicitPrecision != "default" || old.OutputPrecision != "default")
            throw new Exception("Old queues must retain environment defaults");
        var defaults = new ExecutionOptionsValues();
        if (!defaults.IsValid || defaults.HasOverrides) throw new Exception("Defaults unexpectedly override Abaqus");
        if (!new ExecutionOptionsValues { GpuCount = 0 }.HasOverrides) throw new Exception("Zero must explicitly disable GPU");
        foreach (var invalid in new[] { new ExecutionOptionsValues { GpuCount = -1 },
            new ExecutionOptionsValues { GpuCount = 1025 }, new ExecutionOptionsValues { ExplicitPrecision = "double" },
            new ExecutionOptionsValues { OutputPrecision = "both" } })
            if (invalid.IsValid) throw new Exception("Invalid execution setting accepted");
        var absent = JsonSerializer.SerializeToElement(new JobQueueCommandRequest { Action = "updateQueueItem" });
        if (absent.TryGetProperty("gpuCount", out _)) throw new Exception("Unrelated queue edit resets GPU");
        var reset = JsonSerializer.SerializeToElement(new JobQueueCommandRequest {
            GpuCount = JsonSerializer.SerializeToElement<int?>(null), ExplicitPrecision = "default", OutputPrecision = "default" });
        if (reset.GetProperty("gpuCount").ValueKind != JsonValueKind.Null) throw new Exception("Explicit GPU reset omitted");
        var raw = new ExecutionOptionsDraft { OverrideGpu = true, GpuText = "1.", ExplicitPrecision = "constraint", OutputPrecision = "full" };
        if (ExecutionOptionsDraft.Parse(JsonSerializer.Serialize(raw)).GpuText != "1.") throw new Exception("Unfinished draft was rounded");
        try { ExecutionOptionsDraft.Parse("{\"ExplicitPrecision\":\"invalid\"}"); throw new Exception("Invalid draft accepted"); }
        catch (InvalidDataException) { }
        Console.WriteLine("11 GPU/precision contract and draft checks passed.");
    }

    public static async Task RunApi(ControlPlaneHost host, string input, bool expectUnsupported = false)
    {
        var values = new ExecutionOptionsValues { GpuCount = 2, ExplicitPrecision = "both", OutputPrecision = "full" };
        Task<LocalJobDraftPreviewResponse> Preview() => host.PreviewLocalJobDraftAsync(input, "client_case", 1, "2", "GB", "", "",
            false, false, false, "abaqus.bat", 0, 1, false, "", "", executionOptions: values);
        if (expectUnsupported)
        {
            try { await Preview(); throw new Exception("Older backend must not receive unsupported options"); }
            catch (ControlPlaneException error) when (error.Code == "EXECUTION_OPTIONS_UNSUPPORTED") { }
            Console.WriteLine("Older backend preserved; no job submission attempted.");
            return;
        }
        var preview = await Preview();
        if (!preview.Valid || !preview.Command.Contains("gpus=2 double=both output_precision=full"))
            throw new Exception("Production preview lost execution overrides");
        var queued = await host.EnqueueLocalJobDraftAsync(input, "client_case", 1, "2", "GB", "", "",
            false, false, false, "abaqus.bat", 0, 1, false, "", "", executionOptions: values);
        var item = queued.Snapshot.QueueItems.Single();
        if (item.GpuCount != 2 || item.ExplicitPrecision != "both" || item.OutputPrecision != "full")
            throw new Exception("Production enqueue lost execution overrides");
        await host.UpdateJobQueueItemAsync(item.ItemId, false, item.JobName, 1, "2GB", 0, "", "");
        if ((await host.GetJobQueuesAsync()).QueueItems.Single().GpuCount != 2)
            throw new Exception("Older client edit overwrote GPU");
        await host.UpdateJobQueueItemAsync(item.ItemId, false, item.JobName, 1, "2GB", 0, "", "",
            executionOptions: new ExecutionOptionsValues());
        var reset = (await host.GetJobQueuesAsync()).QueueItems.Single();
        if (reset.GpuCount is not null || reset.ExplicitPrecision != "default" || reset.OutputPrecision != "default")
            throw new Exception("Production reset did not return to environment defaults");
        Console.WriteLine("Production GPU/precision client: preview, enqueue, preserve and explicit reset passed; no solver started.");
    }
}
