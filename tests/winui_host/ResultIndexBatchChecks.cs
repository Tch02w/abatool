using AbaqusTools.WinUI.Services;

internal static class ResultIndexBatchChecks
{
    internal static async Task RunAsync(ControlPlaneHost host, string root)
    {
        foreach (var kind in new[] {"root", "group", "batch", "odb", "shared_root", "shared_odb", "shared_asset"})
        {
            var scope = new ResultScopeNode { Kind = kind, TimeDirectory = root };
            if (scope.CanBuildMissingIndexes != (kind is "root" or "group") || scope.CanRefreshIndex != (kind is "batch" or "odb"))
                throw new Exception("Wrong index action for " + kind);
        }
        using var deadline = new CancellationTokenSource(TimeSpan.FromSeconds(20));
        async Task<ResultIndexBatchSnapshot> Finish(ResultIndexBatchSnapshot snapshot)
        {
            while (!snapshot.IsTerminal)
            {
                await Task.Delay(40, deadline.Token);
                snapshot = await host.GetResultIndexBatchAsync(snapshot.BatchId, deadline.Token);
            }
            return snapshot;
        }

        var request = Guid.NewGuid();
        var hold = Path.Combine(root, "Hold");
        var running = await host.StartResultIndexBatchAsync(root, hold, request, deadline.Token);
        var members = await host.ListResultIndexOperationsAsync(activeOnly: true, deadline.Token);
        if (members.Operations.Count != 2 || !members.Operations.All(child => child.BatchId == running.BatchId))
            throw new Exception("Cannot recover the batch through its active members");
        var cancelled = await Finish(await host.CancelResultIndexBatchAsync(running.BatchId, deadline.Token));
        if (cancelled.Status != "cancelled" || cancelled.Cancelled != 2 || cancelled.Processed != 2)
            throw new Exception("Cancelling did not cover both queued and active directories");
        var repeated = await host.StartResultIndexBatchAsync(root, hold, request, deadline.Token);
        if (repeated.BatchId != cancelled.BatchId || repeated.Status != "cancelled")
            throw new Exception("Retrying the same request created another batch");

        var complete = Path.Combine(root, "Complete");
        var first = await Finish(await host.StartResultIndexBatchAsync(root, complete, Guid.NewGuid(), deadline.Token));
        var second = await Finish(await host.StartResultIndexBatchAsync(root, complete, Guid.NewGuid(), deadline.Token));
        if (first.Status != "succeeded" || first.Succeeded != 1 || second.Skipped != 1 || second.Succeeded != 0)
            throw new Exception("The completed directory was not skipped by the second request");
    }
}
