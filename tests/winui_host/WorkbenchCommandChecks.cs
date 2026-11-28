using AbaqusTools.WinUI.Services;

internal static class WorkbenchCommandChecks
{
    public static void Run()
    {
        var state = new WorkbenchCommandState();
        var count = 0;
        void Check(bool value, string label) { if (!value) throw new Exception(label); count++; }
        RemoteServersSnapshot Remote(string profile, string status = "connected", bool busy = false) => new()
        { Connection = new() { ProfileName = profile, Status = status, IsBusy = busy },
            Profiles = [new() { ProfileName = profile }] };
        Check(!state.CanStartQueue && !state.CanStopQueue && !state.CanUseRemote, "Unknown state enabled commands");
        var before = state.QueueRevision;
        state.ApplyQueue(new() { Active = false });
        Check(state.CanStartQueue && !state.CanStopQueue && state.CanEditQueueOptions, "Idle queue commands");
        Check(!state.QueueObservationIsCurrent(before), "Old observation accepted after newer snapshot");
        before = state.QueueRevision;
        state.SetQueueBusy(true);
        Check(!state.CanStartQueue && !state.CanStopQueue && !state.CanEditQueueOptions, "Mutation did not lock queue commands");
        Check(!state.QueueObservationIsCurrent(before), "Pre-mutation read could overwrite mutation");
        state.ApplyQueue(new() { Active = true, ActiveItemIds = ["running", "running-2"] });
        Check(!state.CanStopQueue, "Snapshot unlocked pending mutation");
        state.SetQueueBusy(false);
        Check(state.CanStopQueue && !state.CanStartQueue && !state.CanTerminateSelected, "Active queue commands");
        state.SelectQueueItems(["finished"]);
        Check(!state.CanTerminateSelected, "Completed selection allowed termination");
        state.SelectQueueItems(["finished", "running"]);
        Check(state.CanTerminateSelected && state.SelectedActiveIds.SequenceEqual(["running"]), "Termination included non-running item");
        state.ApplyQueue(new() { Active = false, ActiveItemIds = ["running"] });
        Check(state.CanStartQueue && !state.CanStopQueue && state.CanTerminateSelected, "Stopped scheduling hid running job termination");
        state.InvalidateQueue();
        Check(!state.CanStartQueue && !state.CanTerminateSelected, "Read failure left stale actions enabled");
        state.ApplyQueue(new() { Active = false });
        Check(state.CanStartQueue && !state.CanTerminateSelected, "Recovery did not clear finished active IDs");

        state.ApplyRemote(Remote("alpha"));
        Check(state.CanUseRemote && state.CanUseSelectedRemote("alpha") && !state.CanUseSelectedRemote("beta"), "Server identity mismatch");
        var remoteBefore = state.RemoteRevision;
        state.SetResourceBusy(true);
        Check(!state.CanUseRemote && !state.CanRefreshLocal && !state.RemoteObservationIsCurrent(remoteBefore), "Transfer/action busy guard");
        state.ApplyRemote(Remote("alpha"));
        Check(!state.CanUseRemote, "Snapshot unlocked local remote action");
        state.SetResourceBusy(false);
        remoteBefore = state.RemoteRevision;
        state.SetRemoteRefreshBusy(true);
        Check(!state.CanUseRemote && state.CanRefreshLocal && !state.ResourceBusy,
            "Background SSH refresh blocked unrelated local/profile interaction");
        Check(!state.RemoteObservationIsCurrent(remoteBefore), "Background refresh failed to invalidate older observation");
        state.SetRemoteRefreshBusy(false);
        state.ApplyRemote(Remote("alpha", busy: true));
        Check(!state.CanUseRemote, "Published SSH activity ignored");
        state.ApplyRemote(Remote("alpha", "confirmationRequired"));
        Check(!state.CanUseRemote && state.CanRefreshLocal, "Fingerprint confirmation treated as connected");
        state.ApplyRemote(Remote("alpha", "disconnected"));
        Check(!state.CanUseSelectedRemote("alpha"), "Disconnected refresh would fall back to local action");
        state.ApplyRemote(Remote("beta"));
        Check(state.CanUseRemote && !state.CanUseSelectedRemote("alpha"), "Connection changed while menu awaited page");
        state.InvalidateRemote();
        Check(!state.CanUseRemote && state.CanRefreshLocal, "Remote observation failure broke local refresh or enabled disconnect");
        state.ApplyRemote(Remote("beta"));
        state.SetLocalRefreshBusy(true);
        Check(!state.CanRefreshLocal && state.CanUseRemote, "Local refresh incorrectly blocked remote commands");
        state.SetLocalRefreshBusy(false);
        before = state.QueueRevision; remoteBefore = state.RemoteRevision;
        state.SetLocked(true);
        Check(!state.CanStartQueue && !state.CanUseRemote && !state.CanRefreshLocal
            && !state.QueueObservationIsCurrent(before) && !state.RemoteObservationIsCurrent(remoteBefore), "Close/reset did not lock both sources");
        state.SetLocked(false);
        Check(state.CanStartQueue && state.CanUseRemote && state.CanRefreshLocal, "Cancelled close did not restore commands");
        var notifications = 0;
        state.Changed += () => notifications++;
        state.SetResourceBusy(false); state.SetQueueBusy(false); state.SetLocked(false);
        Check(notifications == 0, "Unchanged busy flags recursively notified UI listeners");
        before = state.QueueRevision;
        for (var index = 0; index < 100; index++)
            state.ApplyQueue(new() { Active = false, MaxParallel = index + 1,
                SchedulerMessage = $"observation {index}", Queue = new() { CapturedAt = DateTimeOffset.UtcNow } });
        Check(notifications == 0, "Unchanged queue actions notified the toolbar on every poll");
        Check(state.QueueRevision == before + 100 && !state.QueueObservationIsCurrent(before),
            "Suppressing unchanged UI notifications accepted an older observation");
        state.ApplyQueue(new() { Active = true, ActiveItemIds = ["running", "running-2"] });
        Check(notifications == 1 && state.CanStopQueue && state.CanTerminateSelected,
            "Changed running state did not notify queue controls");
        state.ApplyQueue(new() { Active = true, ActiveItemIds = ["running-2", "running"] });
        Check(notifications == 1 && state.SelectedActiveIds.SequenceEqual(["running"]),
            "Reordered active IDs unnecessarily notified controls or changed the target");
        state.ApplyQueue(new() { Active = true, ActiveItemIds = ["running-2"] });
        Check(notifications == 2 && !state.CanTerminateSelected,
            "A completed selected job left its termination command enabled");
        before = state.QueueRevision;
        state.InvalidateQueue(); state.InvalidateQueue();
        Check(notifications == 3 && !state.CanStopQueue,
            "Repeated unavailable observations re-notified an already unavailable queue");
        Check(state.QueueRevision == before + 2 && !state.QueueObservationIsCurrent(before),
            "Unavailable observations lost their stale-response fence");
        state.ApplyQueue(new() { Active = true, ActiveItemIds = ["running-2"] });
        Check(notifications == 4 && state.CanStopQueue,
            "Recovery to the same runtime state did not restore queue controls");
        var entire = new WorkbenchCommandState();
        Check(!entire.CanTerminateEntireQueue, "Unknown queue enabled whole-queue termination");
        entire.ApplyQueue(new() { Queue = new() { QueueItems = [new() { IsExternal = true, Status = "待运行" },
            new() { Status = "待确认" }, new() { Status = "已完成" }] } });
        Check(!entire.CanTerminateEntireQueue, "External and protected rows enabled whole-queue termination");
        entire.ApplyQueue(new() { Queue = new() { QueueItems = [new() { Status = "等待前置" }] } });
        Check(entire.CanTerminateEntireQueue && !entire.CanTerminateSelected,
            "Pending jobs must allow a scope preview without an active selection");
        entire.ApplyQueue(new() { Active = true });
        Check(entire.CanTerminateEntireQueue, "Active scheduling alone must allow stop confirmation");
        entire.ApplyQueue(new() { ActiveItemIds = ["live"] });
        Check(entire.CanTerminateEntireQueue, "Stopped dispatch still has a running attempt");
        entire.SetQueueBusy(true);
        Check(!entire.CanTerminateEntireQueue, "Concurrent queue mutation enabled destructive confirmation");
        entire.SetQueueBusy(false); entire.SetLocked(true);
        Check(!entire.CanTerminateEntireQueue, "Closing workspace enabled destructive confirmation");

        QueueTerminationTarget Target(string id, string name, string attempt, string path, bool archive = false) =>
            new() { ItemId = id, JobName = name, AttemptId = attempt, InpPath = path, ArchiveOnly = archive };
        var preview = new QueueTerminationPreview { SchemaVersion = 1, ConfirmationId = "confirmed-scope",
            SchedulingActive = true, Pending = [Target("pending-a", "同名", "", @"G:\方案甲\同名.inp"),
                Target("pending-d", "同名", "", "G:/方案甲/同名.inp")],
            Running = [Target("running-b", "同名", "try-b", @"G:\方案乙\同名.inp"),
                Target("archive-c", "归档作业", "try-c", @"G:\归档作业.inp", true)],
            UntouchedCount = 3 };
        preview.Validate();
        var details = preview.Describe();
        Check(preview.HasWork && details.Contains(@"同名 · G:\方案乙\同名.inp") && !details.Contains("running-b"),
            "Distinct INP paths must disambiguate jobs with matching names");
        Check(details.Contains(@"G:\方案甲\同名.inp · 作业标识 pending-a") && details.Contains("G:/方案甲/同名.inp · 作业标识 pending-d"),
            "Same INP path in multiple formal rows requires the item IDs as well");
        Check(details.Contains("请求取消正在进行的归档（1）") && details.Contains("其余 3 个") && !details.Contains("archive-c"),
            "Confirmation summary lost archive or protected counts");
        var missingAttempt = new QueueTerminationPreview { SchemaVersion = 1, ConfirmationId = "bad",
            SchedulingActive = false, Pending = [], Running = [Target("id", "运行", "", "")], UntouchedCount = 0 };
        try { missingAttempt.Validate(); throw new Exception("Unbound active attempt accepted"); }
        catch (ControlPlaneException) { count++; }
        Console.WriteLine($"{count} shared command-state checks passed.");
    }

    public static async Task RunApiAsync(ControlPlaneHost host)
    {
        var state = new WorkbenchCommandState();
        state.ApplyQueue(await host.GetLocalQueueRuntimeAsync());
        if (!state.CanStartQueue || state.CanStopQueue) throw new Exception("Idle backend queue not reflected");
        var remote = await host.GetRemoteServersAsync();
        state.ApplyRemote(remote);
        if (!state.CanUseSelectedRemote(remote.Connection.ProfileName)) throw new Exception("Connected backend not reflected");
        state.SetResourceBusy(true);
        state.ApplyRemote(await host.GetRemoteServersAsync());
        if (state.CanUseRemote) throw new Exception("Read-only observation unlocked in-flight action");
        state.SetResourceBusy(false);
        if (!state.CanUseRemote) throw new Exception("Read-only observation lost connection");
        Console.WriteLine("4 production-client/live-HTTP command-state checks passed.");
    }

    public static async Task RunTargetApiAsync(ControlPlaneHost host)
    {
        var snapshot = await host.GetRemoteServersAsync();
        var profile = snapshot.Profiles.Single(p => p.ProfileName == snapshot.Connection.ProfileName);
        var wrong = new RemoteServerProfile { ProfileName = profile.ProfileName, Host = "changed.invalid",
            Username = profile.Username, Port = profile.Port, Authentication = profile.Authentication,
            HostFingerprint = profile.HostFingerprint, ComputeRoot = profile.ComputeRoot,
            AllowedRoots = profile.AllowedRoots, AbaqusCommand = profile.AbaqusCommand };
        foreach (var action in new Func<Task<RemoteServersSnapshot>>[] {
            () => host.RefreshRemoteServerForProfileAsync(wrong), () => host.DisconnectRemoteServerForProfileAsync(wrong) })
        {
            try { await action(); throw new Exception("Different server was accepted"); }
            catch (ControlPlaneException error) when (error.Code == "REMOTE_CONNECTION_CHANGED") { }
        }
        var stillConnected = await host.GetRemoteServersAsync();
        if (stillConnected.Connection.Status != "connected") throw new Exception("Rejected target was disconnected");
        var refreshed = await host.RefreshRemoteServerForProfileAsync(profile);
        if (refreshed.Connection.Status != "connected") throw new Exception("Matched refresh failed");
        var disconnected = await host.DisconnectRemoteServerForProfileAsync(profile);
        if (disconnected.Connection.Status != "disconnected") throw new Exception("Matched disconnect failed");
        Console.WriteLine("5 production-client/live-HTTP target identity checks passed.");
    }
}
