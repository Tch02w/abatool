using System.Text.Json;
using System.Text.Json.Nodes;
using AbaqusTools.WinUI.Services;

internal static class PostprocessGroupQueueChecks
{
    internal static async Task RunAsync(ControlPlaneHost host, string fixture)
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        OdbPostprocessRunCreateRequest Read(string name) =>
            JsonSerializer.Deserialize<OdbPostprocessRunCreateRequest>(
                File.ReadAllText(Path.Combine(fixture, name + ".json")), options)!;
        var first = Read("initial");
        var created = await host.StartPostprocessGroupQueueAsync(first);
        var id = created.OperationId;
        var replay = await host.StartPostprocessGroupQueueAsync(first);
        Check(replay.OperationId == id, "Replaying creation must reuse the queue.");
        var queue = await WaitForAsync(host, id, q => q.Groups[0].ChildOperationId?.Length > 0);
        RejectInconsistentSnapshots(queue);
        Check((await host.ListPostprocessGroupQueuesAsync(activeOnly: true)).Operations.Any(op => op.OperationId == id),
            "Active list must include this queue.");

        var appendId = Guid.NewGuid();
        var beforeAppend = queue.Version;
        Check(await host.GetPostprocessGroupQueueIfChangedAsync(id, beforeAppend) is null,
            "Polling an unchanged queue must not return group drafts.");
        var append = Read("append");
        queue = await host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.Append,
            appendId, beforeAppend, run: append);
        var stable = queue.Groups.Select(g => g.GroupId).ToArray();
        var changed = await host.GetPostprocessGroupQueueIfChangedAsync(id, beforeAppend);
        Check(changed?.Version == queue.Version && changed.Groups.Count == 3 && changed.Groups[2].Run is not null,
            "After an append the conditional query must return the new waiting draft.");
        var again = await host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.Append,
            appendId, beforeAppend, run: append);
        Check(stable.Length == 3 && again.Groups.Select(g => g.GroupId).SequenceEqual(stable),
            "Action retry must not append C twice.");

        await ConflictAsync(() => host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.ClearPending,
            Guid.NewGuid(), beforeAppend));
        await ConflictAsync(() => host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.CancelCurrent,
            Guid.NewGuid(), queue.Version, expectedGroupId: stable[1]));
        await ConflictAsync(() => host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.AcknowledgeInterrupted,
            Guid.NewGuid(), queue.Version, expectedGroupId: stable[0]));

        queue = await host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.UpdatePending,
            Guid.NewGuid(), queue.Version, run: Read("edited"));
        var updated = queue.Groups.Single(g => g.Name == "B");
        Check(updated.GroupId == stable[1] && updated.Run?.AnimationFps == 37, "Waiting-group identity or edit lost.");
        queue = await host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.SkipPending,
            Guid.NewGuid(), queue.Version, expectedGroupId: stable[2]);
        Check(queue.Groups[2].Status == "skipped", "Skipping C must not cancel A or B.");
        await host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.CancelCurrent,
            Guid.NewGuid(), queue.Version, expectedGroupId: stable[0]);
        queue = await WaitForAsync(host, id, q => q.IsTerminal);
        Check(queue.Status == "partial" && queue.Groups.Select(g => g.Status).SequenceEqual(new[] { "cancelled", "succeeded", "skipped" }),
            "Terminal statuses do not match the executed groups.");
        Check(queue.Result.OutputCount == 1 && queue.Result.Outputs.SequenceEqual(queue.Groups[1].Result!.Outputs)
            && queue.Result.Outputs.All(Directory.Exists), "Published B results must survive A cancellation.");
        Check(!(await host.ListPostprocessGroupQueuesAsync(activeOnly: true)).Operations.Any(q => q.OperationId == id),
            "Finished queue must leave the active list.");
        Check((await host.ListPostprocessGroupQueuesAsync()).Operations.Any(q => q.OperationId == id),
            "Finished queue must remain available for recovery.");
        await ConflictAsync(() => host.ChangePostprocessGroupQueueAsync(id, PostprocessGroupQueueAction.Resume,
            Guid.NewGuid(), queue.Version));

        var stopped = await host.StartPostprocessGroupQueueAsync(Read("second"));
        stopped = await WaitForAsync(host, stopped.OperationId, q => q.Groups[0].ChildOperationId?.Length > 0);
        stopped = await host.ChangePostprocessGroupQueueAsync(stopped.OperationId, PostprocessGroupQueueAction.ClearPending,
            Guid.NewGuid(), stopped.Version);
        Check(stopped.Groups[1].Status == "cancelled", "Clearing pending groups must preserve the running group.");
        await host.ChangePostprocessGroupQueueAsync(stopped.OperationId, PostprocessGroupQueueAction.Stop,
            Guid.NewGuid(), stopped.Version);
        stopped = await WaitForAsync(host, stopped.OperationId, q => q.IsTerminal);
        Check(stopped.Status == "cancelled" && stopped.Result.OutputCount == 0, "Stop must not publish results.");
        await VerifyHistoryAsync(host);
        Console.WriteLine("Postprocess FIFO production client and HTTP queue checks passed.");
    }

    internal static async Task VerifyHistoryAsync(ControlPlaneHost host)
    {
        var history = await host.ListPostprocessGroupQueuesAsync();
        var partial = history.Operations.Single(q => q.ClientRequestId == "initial");
        var cancelled = history.Operations.Single(q => q.ClientRequestId == "second");
        var receipt = await host.GetPostprocessGroupQueueAsync(partial.OperationId);
        Check((await host.ListPostprocessGroupQueuesAsync(activeOnly: true)).Operations.Count == 0
            && receipt.Status == "partial" && cancelled.Status == "cancelled" && receipt.Result.OutputCount == 1
            && receipt.Result.Outputs.SequenceEqual(partial.Result.Outputs) && receipt.Result.Outputs.All(Directory.Exists)
            && receipt.Groups.Single(g => g.Name == "B").Result!.Outputs.SequenceEqual(receipt.Result.Outputs),
            "Group queue history did not preserve its successful output and cancelled sibling states.");
        Console.WriteLine("Group queue history: partial and cancelled states, published B receipt and empty active list verified.");
    }

    private static async Task<OdbPostprocessGroupQueueSnapshot> WaitForAsync(ControlPlaneHost host,
        string id, Func<OdbPostprocessGroupQueueSnapshot, bool> ready)
    {
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
        while (true)
        {
            var current = await host.GetPostprocessGroupQueueAsync(id, timeout.Token);
            if (ready(current)) return current;
            await Task.Delay(30, timeout.Token);
        }
    }

    private static async Task ConflictAsync(Func<Task<OdbPostprocessGroupQueueSnapshot>> command)
    {
        try { await command(); }
        catch (ControlPlaneException e) when (e.Code == "POSTPROCESS_QUEUE_CONFLICT" && e.StatusCode == 409) { return; }
        throw new InvalidOperationException("Expected an explicit queue state conflict.");
    }

    private static void RejectInconsistentSnapshots(OdbPostprocessGroupQueueSnapshot queue)
    {
        var options = new JsonSerializerOptions(JsonSerializerDefaults.Web);
        void MustReject(Action<JsonNode> change)
        {
            var raw = JsonSerializer.SerializeToNode(queue, options)!;
            change(raw);
            var edited = raw.Deserialize<OdbPostprocessGroupQueueSnapshot>(options)!;
            try { edited.Validate(queue.OperationId); }
            catch (ControlPlaneException) { return; }
            throw new InvalidOperationException("An inconsistent group queue snapshot was accepted.");
        }
        MustReject(raw => raw["groups"]![1]!["run"] = null);
        MustReject(raw => raw["groups"]![1]!["run"]!["clientRequestId"] = "another-attempt");
        MustReject(raw => raw["groups"]![1]!["run"]!["groups"]![0]!["members"]![0] = "different-member.odb");
        MustReject(raw => raw["result"]!["outputCount"] = 1);
    }

    private static void Check(bool condition, string error)
    {
        if (!condition) throw new InvalidOperationException(error);
    }
}
