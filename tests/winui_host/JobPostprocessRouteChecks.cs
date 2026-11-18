using AbaqusTools.WinUI.Services;

internal static class JobPostprocessRouteChecks
{
    public static async Task RunAsync(string root)
    {
        root = Path.GetFullPath(root);
        if (root.StartsWith("C:", StringComparison.OrdinalIgnoreCase))
            throw new InvalidOperationException("ODB fixtures must not be written on C:");
        var checks = 0;
        void Check(bool condition) { if (!condition) throw new Exception($"Routing check {checks + 1} failed"); checks++; }
        void Reject(Action action, string message)
        {
            try { action(); }
            catch (InvalidOperationException error) { Check(error.Message.Contains(message)); return; }
            throw new Exception("Expected route rejection: " + message);
        }
        var input = Path.Combine(root, "原始 输入");
        var work = Path.Combine(root, "实际 计算");
        var archive = Path.Combine(root, "已发布 归档");
        foreach (var directory in new[] { input, work, archive })
        {
            Directory.CreateDirectory(directory);
            File.WriteAllText(Path.Combine(directory, "运行名.odb"), "route-only fixture, not an Abaqus database");
        }
        JobQueueItem Item(string? effective = null, string status = "已完成", string archiveState = "", string attempt = "attempt-1", string name = "运行名") => new()
        {
            ItemId = "item-1", AttemptId = attempt, JobName = name, InpPath = Path.Combine(input, "输入名.inp"),
            EffectiveWorkDir = effective ?? work, Status = status, ArchiveDestination = archive, ArchiveStatus = archiveState,
        };
        LocalQueueRuntimeSnapshot Snapshot(params JobQueueItem[] rows) => new() { Queue = new() { QueueItems = rows } };
        JobPostprocessRoute Route(JobQueueItem item) => JobPostprocessRoute.Resolve(JobPostprocessTarget.Local(item), Snapshot(item));
        var selected = Item();
        var target = JobPostprocessTarget.Local(selected);
        Check(Route(selected).Path == Path.Combine(work, "运行名.odb"));
        Check(Route(Item(archiveState: "已归档")).Path == Path.Combine(archive, "运行名.odb"));
        Check(Route(Item(archiveState: "已归档，清理未完成")).Source == "已发布归档");
        Check(Route(Item(archiveState: "归档失败")).Path == Path.Combine(work, "运行名.odb"));
        Reject(() => Route(Item(effective: Path.Combine(root, "不存在"))), "没有可用");
        Reject(() => Route(Item(effective: "")), "未记录实际计算目录");
        Check(Route(Item(effective: "", attempt: "")).Path == Path.Combine(input, "运行名.odb"));
        Reject(() => JobPostprocessRoute.Resolve(target, Snapshot()), "不在队列");
        Reject(() => JobPostprocessRoute.Resolve(target, Snapshot(Item(attempt: "attempt-2"))), "运行批次");
        Reject(() => JobPostprocessRoute.Resolve(target, Snapshot(Item(name: "不同名"))), "运行批次");
        foreach (var status in new[] { "运行中", "启动中", "正在终止", "待确认", "状态未知", "状态确认中" })
            Reject(() => Route(Item(status: status)), "仍在执行");
        Reject(() => JobPostprocessRoute.Resolve(target, new() { Queue = Snapshot(selected).Queue, ActiveItemIds = ["item-1"] }), "仍在执行");
        Reject(() => JobPostprocessRoute.Resolve(target, new() { Queue = Snapshot(selected).Queue,
            Operations = [new() { ItemId = "item-1", Active = true, ArchiveOnly = true }] }), "归档");
        var draft = JobPostprocessTarget.Draft(selected.InpPath, "运行名", false);
        Check(JobPostprocessRoute.Resolve(draft, Snapshot(selected)).Path == Path.Combine(work, "运行名.odb"));
        Check(JobPostprocessRoute.Resolve(draft with { InputPath = Path.Combine(input, ".", "输入名.inp") }, Snapshot(selected)).Path
            == Path.Combine(work, "运行名.odb"));
        Check(JobPostprocessRoute.Resolve(draft, Snapshot()).Path == Path.Combine(input, "运行名.odb"));
        Reject(() => JobPostprocessRoute.Resolve(draft, Snapshot(selected, Item())), "多个作业记录");
        Reject(() => JobPostprocessRoute.Resolve(draft with { InputPath = "relative.inp" }, Snapshot()), "本地 INP");
        Reject(() => Route(Item(name: "../别的作业")), "名称或结果目录无效");
        var locked = Path.Combine(root, "锁定");
        Directory.CreateDirectory(locked);
        File.WriteAllText(Path.Combine(locked, "运行名.odb"), "fixture");
        File.WriteAllText(Path.Combine(locked, "运行名.lck"), "fixture");
        Reject(() => Route(Item(effective: locked)), "锁文件");
        var empty = Path.Combine(root, "空结果");
        Directory.CreateDirectory(empty);
        File.WriteAllBytes(Path.Combine(empty, "运行名.odb"), []);
        Reject(() => Route(Item(effective: empty)), "没有可用");
        // A published-but-missing archive must never fall back to the stale work copy.
        File.Delete(Path.Combine(archive, "运行名.odb"));
        Reject(() => Route(Item(archiveState: "已归档")), "已发布归档");
        var reads = 0;
        try { await JobPostprocessRoute.ResolveAsync(draft with { Kind = "remote" }, () => { reads++; return Task.FromResult(Snapshot()); }); }
        catch (InvalidOperationException error) { Check(error.Message.Contains("下载") && reads == 0); }
        var asyncResult = await JobPostprocessRoute.ResolveAsync(target, () => { reads++; return Task.FromResult(Snapshot(selected)); });
        Check(asyncResult.Path == Path.Combine(work, "运行名.odb") && reads == 1);
        var failed = false;
        try { await JobPostprocessRoute.ResolveAsync(target, () => throw new IOException("backend unavailable")); }
        catch (IOException) { failed = true; }
        Check(failed);
        Console.WriteLine($"{checks} job postprocess route checks passed");
    }

    public static async Task RunApiAsync(ControlPlaneHost host, string expectedPath)
    {
        var snapshot = await host.GetLocalQueueRuntimeAsync();
        var item = snapshot.Queue.QueueItems.Single();
        var target = JobPostprocessTarget.Local(item);
        var route = await JobPostprocessRoute.ResolveAsync(target, () => host.GetLocalQueueRuntimeAsync());
        if (!string.Equals(route.Path, expectedPath, StringComparison.OrdinalIgnoreCase))
            throw new Exception($"Wrong runtime result path: {route.Path}");
        var discovery = await host.DiscoverOdbsAsync(Path.GetDirectoryName(route.Path)!, false);
        if (!discovery.Odbs.Any(row => string.Equals(row.Path, route.Path, StringComparison.OrdinalIgnoreCase)))
            throw new Exception("Routed result missing from production discovery response");
        Console.WriteLine("2 production-client/live-HTTP job route checks passed");
    }
}
