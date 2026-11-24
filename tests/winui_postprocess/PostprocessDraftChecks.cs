using System.Text.Json;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;

static class PostprocessDraftChecks
{
    private static int _checks;
    private static void Check(bool ok, string message)
    {
        if (!ok) throw new InvalidOperationException(message);
        _checks++;
    }
    private static async Task Reject(Func<Task> action)
    {
        try { await action(); }
        catch (Exception error) when (error is IOException or InvalidDataException or ArgumentException or JsonException) { return; }
        throw new InvalidOperationException("Expected rejection");
    }
    private static RecoveryDraftFile<OdbPostprocessRecoveryDraft> Store(string path, int max = 8 * 1024 * 1024)
        => new(path, draft => draft.Validate(), max);

    private static async Task VerifyComparisonRecoveryAsync(string directory)
    {
        var root = Path.Combine(directory, "对照");
        var sources = Enumerable.Range(0, 300)
            .Select(i => new OdbDraftSource(Path.Combine(root, $"model-{i}.odb"), 123, 0)).ToList();
        var basis = OdbPostprocessDraftRecovery.SourceKey(sources);
        var target = OdbPostprocessDraftRecovery.ComparisonDialogKind + " · " + basis;
        var values = Enumerable.Range(0, sources.Count).ToDictionary(i => $"{i}/LoadDirection", _ => "3");
        OdbPostprocessRecoveryDraft Draft(string key, Dictionary<string, string> inputs) => new()
        {
            Basis = basis, Root = root, Sources = sources,
            Workspace = new() { Rows = sources.Select(s => new OdbPostprocessSavedRow { Path = s.Path }).ToList() },
            Dialogs = new() { [key] = new() { Basis = basis, Inputs = inputs } }
        };
        var store = Store(Path.Combine(directory, "comparison-300.json"));
        await store.SaveAsync(Draft(target, values));
        var loaded = store.Load()!;
        Check(loaded.Dialogs[target].Inputs.Count == 300 && loaded.Dialogs[target].Inputs["299/LoadDirection"] == "3",
            "A valid 300-model comparison could not save and restore all edits");
        await Reject(() => store.SaveAsync(Draft("普通弹窗", values)));
        await Reject(() => store.SaveAsync(Draft(target, new(values) { ["300/LoadDirection"] = "1" })));
        await Reject(() => store.SaveAsync(Draft(target, new(values) { ["0/Unknown"] = "1" })));
        await Reject(() => store.SaveAsync(Draft(target, new(values) { ["01/LoadDirection"] = "1" })));
        Check(store.Load()!.Dialogs[target].Inputs.Count == 300, "Invalid edits replaced the last valid comparison draft");
    }

    public static async Task RunAsync(string directory)
    {
        directory = Path.GetFullPath(directory);
        if (!directory.StartsWith(@"G:\PythonProject\abaqusTool\GPTWork\", StringComparison.OrdinalIgnoreCase)
            || Directory.Exists(directory)) throw new ArgumentException("Use a fresh G: GPTWork evidence directory");
        Directory.CreateDirectory(directory);
        // These paths are metadata only: no ODB placeholder, copy or solver is needed.
        var root = Path.Combine(directory, "中文 工作区");
        var source = new OdbDraftSource(Path.Combine(root, "GJB-1.odb"), 1234, DateTime.UtcNow.Ticks);
        var workspace = new OdbPostprocessWorkspace { Rows = [new() { Path = source.Path, Group = "组 A", Selected = true,
            Draft = new() { Path = source.Path, ReinforcementMode = "none", ManualSequenceExpression = "0,5-9" } }],
            GroupMemberOrder = new() { ["组 A"] = [source.Path] } };
        var formal = new OdbPostprocessWorkspaceStore(Path.Combine(directory, "formal"));
        formal.Save(root, workspace);
        var formalPath = Directory.GetFiles(Path.Combine(directory, "formal")).Single();
        var formalBytes = File.ReadAllBytes(formalPath);
        var basis = OdbPostprocessDraftRecovery.Fingerprint(workspace);
        var raw = new Dictionary<string, string>
        {
            ["图像单位"] = "px", ["图像宽度"] = "1500", ["图像高度"] = "1000", ["并行进程"] = "2",
            ["全部帧"] = "false", ["纵筋方法"] = "element_cut", ["预期纵筋数"] = "0", ["GIF方式"] = "fps",
            ["GIF帧率"] = "25.0", ["GIF时长"] = "4", ["纵筋容差"] = "1e-4", ["白底"] = "true", ["透明底"] = "true",
        };
        Check(!OdbPostprocessDraftRecovery.OutputChanged(workspace.Output, raw), "Equivalent numeric formatting detected as a change");
        foreach (var bad in new[] { "", "-", "1e", "NaN", "Infinity", "30" })
        {
            raw["GIF帧率"] = bad;
            Check(OdbPostprocessDraftRecovery.OutputChanged(workspace.Output, raw), "Raw GIF edit lost: " + bad);
        }
        var dialogs = new Dictionary<string, OdbDialogInputDraft>();
        foreach (var kind in new[] { "提取参数", "图例范围", "管理分组", "组内顺序" })
            dialogs[kind] = new() { Basis = basis, Inputs = new() { ["未确认填写"] = " 0,5-\n中文 " } };
        var draft = new OdbPostprocessRecoveryDraft { Root = root, Basis = basis, Sources = [source],
            Workspace = workspace, OutputInputs = raw, Dialogs = dialogs };
        var path = Path.Combine(directory, "恢复.json");
        var store = Store(path);
        Check(store.Load() is null, "Fresh checkpoint not empty");
        raw["GIF帧率"] = "1e";
        var writing = store.SaveAsync(draft);
        raw["GIF帧率"] = "60";
        dialogs["提取参数"].Inputs["未确认填写"] = "later";
        await writing;
        var restored = Store(path).Load()!;
        Check(restored.OutputInputs["GIF帧率"] == "1e" && restored.Dialogs["提取参数"].Inputs["未确认填写"] == " 0,5-\n中文 "
            && restored.Dialogs.Count == 4, "Raw/immutable modal capture lost");
        Check(formalBytes.SequenceEqual(File.ReadAllBytes(formalPath)), "Recovery checkpoint published formal workspace");
        Check(restored.Matches(root.ToLowerInvariant() + "\\", basis, [source with { Path = source.Path.ToLowerInvariant() }]), "Path normalization changed identity");
        Check(!restored.Matches(root + "-other", basis, [source]), "Different root accepted");
        Check(!restored.Matches(root, new string('0', 64), [source]), "Different formal basis accepted");
        Check(!restored.Matches(root, basis, [source with { Size = source.Size + 1 }]), "Changed file size accepted");
        Check(!restored.Matches(root, basis, [source with { ModifiedUtcTicks = source.ModifiedUtcTicks + 1 }]), "Changed file timestamp accepted");
        Check(!restored.Matches(root, basis, []), "Missing source accepted");
        Check(!restored.Matches(root, basis, [source, source with { Path = Path.Combine(root, "extra.odb") }]), "Extra source accepted");
        Check(OdbPostprocessDraftRecovery.FileName(root) == OdbPostprocessDraftRecovery.FileName(root.ToLowerInvariant() + "\\")
            && !OdbPostprocessDraftRecovery.FileName(root).Contains("中文"), "Root filename identity is unstable");
        Check(OdbPostprocessDraftRecovery.Fingerprint(new Dictionary<string, int> { ["b"] = 2, ["a"] = 1 })
            == OdbPostprocessDraftRecovery.Fingerprint(new Dictionary<string, int> { ["a"] = 1, ["b"] = 2 }), "Dictionary order created false conflict");
        Check(OdbPostprocessDraftRecovery.Fingerprint(new[] { "a", "b" }) != OdbPostprocessDraftRecovery.Fingerprint(new[] { "b", "a" }), "Member order lost in fingerprint");
        var item = new OdbFileRow(new() { Path = source.Path, Name = "GJB-1.odb", SizeBytes = source.Size,
            ModifiedAt = new DateTimeOffset(source.ModifiedUtcTicks, TimeSpan.Zero) });
        var rows = OdbPostprocessDraftRecovery.PrepareRows(restored, [item]);
        Check(rows.Single().PostprocessJob?.ReinforcementMode == "none" && rows.Single().ComparisonGroup == "组 A"
            && rows.Single().ScanDetails is null && !rows.Single().HasPostprocessConfiguration && item.PostprocessJob is null,
            "Recovery mutated live row or falsely restored scan validity");
        await Reject(() => Task.FromResult(OdbPostprocessDraftRecovery.PrepareRows(restored, [])));
        Check(item.ComparisonGroup == "对比组 1", "Failed preparation changed live page");

        var bytes = File.ReadAllBytes(path);
        var archive = await store.PreserveAsync();
        Check(archive is not null && bytes.SequenceEqual(File.ReadAllBytes(archive)) && bytes.SequenceEqual(File.ReadAllBytes(path)),
            "Preserve-only changed active file or archive bytes");
        using (var held = new FileStream(path, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
            await Reject(() => store.ArchiveAndClearAsync());
        Check(bytes.SequenceEqual(File.ReadAllBytes(path)), "Failed archive cleared active checkpoint");

        foreach (var json in new[]
        {
            JsonSerializer.Serialize(restored).Replace("\"Version\":1", "\"Version\":9"),
            JsonSerializer.Serialize(restored).Replace("\"OutputInputs\":{", "\"OutputInputs\":null,\"ignored\":{"),
            JsonSerializer.Serialize(restored).Replace("\"Size\":1234", "\"Size\":-1"),
            "{broken",
        })
        {
            var damagedPath = Path.Combine(directory, "damaged-" + _checks + ".json");
            File.WriteAllText(damagedPath, json);
            var damaged = Store(damagedPath);
            await Reject(() => Task.FromResult(damaged.Load()));
            await Reject(() => damaged.SaveAsync(restored));
            var copy = await damaged.ArchiveAndClearAsync();
            Check(copy is not null && File.ReadAllText(copy) == json && damaged.Load() is null, "Corrupt original was overwritten/lost");
            await damaged.SaveAsync(restored);
            Check(damaged.Load()!.Basis == basis, "Store could not recover after preserving damaged original");
        }
        await Reject(() => store.SaveAsync(new() { Root = root, Basis = basis, Workspace = workspace, Sources = [] }));
        await Reject(() => store.SaveAsync(new() { Root = root, Basis = basis, Workspace = workspace, Sources = [source, source] }));
        Check(bytes.SequenceEqual(File.ReadAllBytes(path)), "Invalid row/source mapping overwrote checkpoint");
        await Reject(() => Store(path, 100).SaveAsync(restored));
        var smallReader = Store(path, 100);
        await Reject(() => Task.FromResult(smallReader.Load()));
        Check(bytes.SequenceEqual(File.ReadAllBytes(path)), "Oversize save/read modified original");
        var first = store.SaveAsync(draft);
        var second = store.SaveAsync(null);
        await store.PendingWrites;
        Check(first.IsCompletedSuccessfully && second.IsCompletedSuccessfully && store.Load() is null, "Ordered clear lost to late save");
        await store.SaveAsync(restored);
        var time = File.GetLastWriteTimeUtc(path);
        await store.SaveAsync(restored);
        Check(File.GetLastWriteTimeUtc(path) == time, "Unchanged checkpoint rewrote file");
        archive = await store.ArchiveAndClearAsync();
        Check(archive is not null && Store(archive).Load()!.Dialogs.Count == 4 && store.Load() is null, "Preserve and clear lost pending dialogs");
        Check(formalBytes.SequenceEqual(File.ReadAllBytes(formalPath)) && Directory.GetFiles(directory, "*.odb", SearchOption.AllDirectories).Length == 0,
            "Tests altered formal settings or created an ODB");
        await VerifyComparisonRecoveryAsync(directory);
        Console.WriteLine($"{_checks} postprocess recovery draft checks passed.");
    }
}
