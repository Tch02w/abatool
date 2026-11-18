using System.Text.Json;
using AbaqusTools.WinUI.Services;

static class ResultGraphDraftChecks
{
    public static async Task RunApiAsync(ControlPlaneHost host, string context, string directory)
    {
        Directory.CreateDirectory(directory);
        var basis = await host.GetOdbResultGraphAsync();
        var edited = new OdbResultGraphSnapshot { SchemaVersion = 1, Revision = basis.Revision,
            OutputDirectory = directory, Nodes = [new() { NodeId = "draft", Name = "尚未提交的编辑" }] };
        var draft = new OdbResultGraphDraft { Context = context, Basis = basis, Edited = edited };
        var path = Path.Combine(directory, "local-draft.json");
        await new OdbResultGraphDraftStore(path).SaveAsync(draft);
        Require(draft.Matches(context, await host.GetOdbResultGraphAsync()), "Checkpoint changed the formal graph");
        var external = await host.SaveOdbResultGraphAsync(basis.Revision, directory,
            [new() { NodeId = "other", Name = "另一个编辑" }]);
        Require(!draft.Matches(context, external), "Changed backend accepted for automatic recovery");
        var conflict = false;
        try { await host.SaveOdbResultGraphAsync(draft.Basis.Revision, edited.OutputDirectory, edited.Nodes); }
        catch (ControlPlaneException error) when (error.Code == "RESULT_GRAPH_REVISION_CONFLICT") { conflict = true; }
        Require(conflict && (await host.GetOdbResultGraphAsync()).Nodes.Single().NodeId == "other",
            "Stale restored draft overwrote a newer formal graph");
        Require(new OdbResultGraphDraftStore(path).Load()!.Edited.Nodes.Single().NodeId == "draft",
            "Revision conflict lost the local draft");
        Console.WriteLine("4 production-client/live-HTTP graph draft checks passed.");
    }

    public static async Task RunAsync(string directory)
    {
        if (Directory.Exists(directory)) throw new Exception("Use a fresh evidence directory");
        Directory.CreateDirectory(directory);
        var path = Path.Combine(directory, "结果图 草稿.json");
        var context = Path.Combine(directory, "runtime", "control-plane.json");
        var basis = Graph(7, "正式");
        var edited = Graph(7, "中文 未完成编辑 ");
        var draft = new OdbResultGraphDraft { Context = context, Basis = basis, Edited = edited,
            SelectedNodeId = "child", Targets = ["child"] };
        var store = new OdbResultGraphDraftStore(path);
        Require(store.Load() is null, "Fresh store unexpectedly contains a draft");
        var saving = store.SaveAsync(draft);
        edited.Nodes[1].Name = "later change";
        await saving;
        var restored = new OdbResultGraphDraftStore(path).Load()!;
        Require(restored.Edited.Nodes[1].Name == "中文 未完成编辑 " && restored.SelectedNodeId == "child"
            && restored.Targets.SequenceEqual(["child"]), "Raw draft, selection or immutable capture lost");
        Require(restored.Matches(context, basis), "Matching formal base rejected");
        Require(!restored.Matches(context, Graph(8, "正式")), "Revision conflict accepted");
        Require(!restored.Matches(context, Graph(7, "changed elsewhere")), "Same-revision content conflict accepted");
        Require(!restored.Matches(Path.Combine(directory, "other", "control-plane.json"), basis), "Different runtime accepted");
        Require(restored.Matches(context, new() { SchemaVersion = 1, Revision = 7, OutputDirectory = basis.OutputDirectory,
            Nodes = basis.Nodes.Reverse().ToArray() }), "Node serialization order created a false conflict");
        var before = File.ReadAllText(path);
        var invalid = new OdbResultGraphDraft { Context = context, Basis = basis,
            Edited = new() { SchemaVersion = 1, Revision = 7, Nodes = [new() { NodeId = "loop", ParentNodeId = "loop" }] } };
        await Reject(() => store.SaveAsync(invalid));
        Require(File.ReadAllText(path) == before, "Invalid graph overwrote prior checkpoint");

        var large = new OdbResultGraphSnapshot { SchemaVersion = 1, Revision = 7,
            Nodes = Enumerable.Range(0, 256).Select(i => new OdbResultGraphNode { NodeId = "n" + i,
                Name = new string('中', 60), OdbPath = @"G:\中文目录\" + i + ".odb" }).ToArray() };
        await store.SaveAsync(new() { Context = context, Basis = basis, Edited = large });
        Require(new FileInfo(path).Length > 32768 && new OdbResultGraphDraftStore(path).Load()!.Edited.Nodes.Count == 256,
            "Full-sized graph was truncated by the ordinary input limit");
        var largeBytes = File.ReadAllBytes(path);
        using (var held = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            await Reject(() => store.ArchiveAndClearAsync());
        Require(largeBytes.SequenceEqual(File.ReadAllBytes(path)), "Failed archive cleared active draft");
        var archive = await store.ArchiveAndClearAsync();
        Require(archive is not null && largeBytes.SequenceEqual(File.ReadAllBytes(archive))
            && new OdbResultGraphDraftStore(path).Load() is null, "Archive was not preserved before clearing");

        File.WriteAllText(path, "damaged original");
        var damaged = new OdbResultGraphDraftStore(path);
        await Reject(() => Task.FromResult(damaged.Load()));
        await Reject(() => damaged.SaveAsync(draft));
        Require(File.ReadAllText(path) == "damaged original", "Corrupt checkpoint overwritten");
        archive = await damaged.ArchiveAndClearAsync();
        Require(archive is not null && File.ReadAllText(archive) == "damaged original", "Corrupt original not preserved");
        await damaged.SaveAsync(draft);
        Require(new OdbResultGraphDraftStore(path).Load() is not null, "Explicit preservation did not restore saving");
        var stamp = new DateTime(2021, 2, 3, 4, 5, 6, DateTimeKind.Utc);
        File.SetLastWriteTimeUtc(path, stamp);
        await damaged.SaveAsync(draft);
        Require(File.GetLastWriteTimeUtc(path) == stamp, "Identical checkpoint rewrote the file");
        Require(Directory.GetFiles(directory, "*.tmp").Length == 0, "Temporary checkpoint leaked");
        Console.WriteLine("16 result-graph draft checks passed; formal graph/backend/solver were not modified.");
    }

    private static OdbResultGraphSnapshot Graph(int revision, string name) => new()
    {
        SchemaVersion = 1, Revision = revision, OutputDirectory = @"G:\输出 目录",
        Nodes = [new() { NodeId = "root", Name = "基础", OdbPath = "base.odb" },
            new() { NodeId = "child", ParentNodeId = "root", Name = name, OdbPath = "incomplete " }],
    };
    private static void Require(bool condition, string message) { if (!condition) throw new Exception(message); }
    private static async Task Reject(Func<Task> action)
    {
        try { await action(); }
        catch (Exception error) when (error is IOException or InvalidDataException or JsonException or UnauthorizedAccessException) { return; }
        throw new Exception("Invalid or blocked draft operation was accepted");
    }
}
