using AbaqusTools.WinUI.Services;

internal static class QueueDirectoryChecks
{
    public static async Task RunApi(ControlPlaneHost host, string directory)
    {
        var source = Path.Combine(directory, "source");
        var inputs = new[] { Path.Combine(source, "A.inp"), Path.Combine(source, "B.inp") };
        var added = await host.AddJobQueueCandidatesAsync(inputs, false, false);
        var rows = added.Snapshot.Candidates;
        var ids = rows.Select(item => item.ItemId).ToArray();
        var root = Path.Combine(directory, "ssd");
        var archive = Path.Combine(directory, "archive");
        var settings = await host.SetCandidateDirectoriesAsync(ids, root, archive);
        if (settings.Changed != 2 || settings.Snapshot.Candidates.Any(item =>
            item.CalculationRootDir != root || item.ArchiveDir != archive || !item.ArchiveAfterComplete ||
            item.CleanupAfterArchive || item.ArchiveDestination != "" || item.EffectiveWorkDir != Path.Combine(root, item.JobName)))
            throw new Exception("Batch directory edit lost fields or enabled cleanup");

        await host.SetCandidateDirectoriesAsync([ids[0]], cleanupAfterArchive: true);
        var edited = await host.UpdateJobQueueItemAsync(ids[0], true, "A", 1, "80%", 2, "", "");
        if (!edited.Snapshot.Candidates[0].CleanupAfterArchive)
            throw new Exception("Unrelated edit reset explicit cleanup");
        await host.ConfirmJobQueueCandidatesAsync([ids[0]]);
        var reset = await host.UpdateJobQueueItemAsync(ids[0], false, "A", 1, "80%", 3, "", "",
            calculationRootDir: "", cleanupAfterArchive: false);
        var row = reset.Snapshot.QueueItems.Single();
        if (row.Priority != 3 || row.CleanupAfterArchive || row.CalculationRootDir != "" ||
            row.ArchiveDir != archive || row.EffectiveWorkDir != source)
            throw new Exception("Formal queue edit did not clear root or preserve archive");
        try
        {
            await host.SetCandidateDirectoriesAsync(ids, archiveDir: "");
            throw new Exception("A stale selection should reject the entire batch");
        }
        catch (ControlPlaneException error) when (error.Code == "QUEUE_ITEM_NOT_FOUND") { }
        var latest = await host.GetJobQueuesAsync();
        if (latest.Candidates.Single().ArchiveDir != archive || latest.QueueItems.Single().ArchiveDir != archive)
            throw new Exception("Failed edit replaced directory settings");
        Console.WriteLine("Production queue directory client completed.");
    }
}
