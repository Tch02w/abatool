using System.Text.Json;
using AbaqusTools.WinUI.Services;

internal static class ArchivePresentationChecks
{
    internal static void Run()
    {
        var legacy = JsonSerializer.Deserialize<JobQueueItem>("{\"message\":\"计算已完成\"}")!;
        if (legacy.HasPublishedArchive || legacy.ArchiveRecoveryAvailable || legacy.ArchiveDetailsDisplay != ""
            || legacy.ResultMessageDisplay != "计算已完成") throw new Exception("Legacy archive defaults changed");
        foreach (var status in new[] { "已归档", "已归档，清理未完成", "归档失败", "归档需核对", "归档待恢复", "归档记录异常", "" })
        {
            var item = new JobQueueItem { ArchiveStatus = status, ArchiveDestination = "archive",
                ArchiveError = status == "归档失败" ? "copy failed" : "", Message = "计算已完成" };
            var published = status is "已归档" or "已归档，清理未完成";
            if (item.HasPublishedArchive != published) throw new Exception("Partial archive selected as output");
            if (status != "" && !item.ResultMessageDisplay.Contains(status)) throw new Exception("Archive outcome hidden");
            if (status == "归档失败" && !item.ArchiveDetailsDisplay.Contains("copy failed"))
                throw new Exception("Archive failure reason hidden");
        }
        var restored = JsonSerializer.Deserialize<JobQueueItem>("{\"archiveRecoveryAvailable\":true}")!;
        if (!restored.ArchiveRecoveryAvailable) throw new Exception("Archive retry availability lost");
        foreach (var operation in new[] { new LocalJobRuntimeOperation { ArchiveOnly = true },
            new LocalJobRuntimeOperation { Phase = "archive_cancelling" } })
            if (!operation.IsArchiving) throw new Exception("Archive cancellation routed to solver controls");
        Console.WriteLine("11 archive presentation, recovery and legacy compatibility checks passed.");
    }

    internal static async Task RunApi(ControlPlaneHost host, string itemId)
    {
        var before = (await host.GetLocalQueueRuntimeAsync()).Queue.QueueItems.Single(x => x.ItemId == itemId);
        if (!before.ArchiveRecoveryAvailable) throw new Exception("Recovery unavailable before client request");
        using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(45));
        var busyRetries = 0;
        while (true)
        {
            try
            {
                await host.RetryLocalArchiveAsync(itemId, timeout.Token);
                break;
            }
            catch (ControlPlaneException error) when (error.Code == "LOCAL_ARCHIVE_BUSY")
            {
                // A previous fixture's final callback may still own its slot.
                // This 409 explicitly means no new operation was accepted.
                var current = (await host.GetLocalQueueRuntimeAsync(timeout.Token)).Queue.QueueItems.Single(x => x.ItemId == itemId);
                if (current.AttemptId != before.AttemptId || !current.ArchiveRecoveryAvailable)
                    throw new Exception("Archive state changed while awaiting its slot");
                busyRetries++;
                await Task.Delay(100, timeout.Token);
            }
        }
        while (true)
        {
            timeout.Token.ThrowIfCancellationRequested();
            var state = await host.GetLocalQueueRuntimeAsync(timeout.Token);
            var row = state.Queue.QueueItems.Single(x => x.ItemId == itemId);
            if (row.AttemptId != before.AttemptId) throw new Exception("Recovery created another solve attempt");
            if (row.ArchiveStatus == "已归档")
            {
                if (row.ArchiveRecoveryAvailable || !row.HasPublishedArchive)
                    throw new Exception("Completed archive state inconsistent");
                Console.WriteLine($"Production archive client recovered original attempt and published output; busy retries: {busyRetries}.");
                return;
            }
            if (row.ArchiveRecoveryAvailable) throw new Exception("Archive recovery failed: " + row.ArchiveDetailsDisplay);
            await Task.Delay(100, timeout.Token);
        }
    }
}
