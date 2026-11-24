using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;

internal static class ScopedRunChecks
{
    public static void Run(OdbPostprocessScanItem scan)
    {
        var root = Path.GetFullPath(Path.Combine(Path.GetTempPath(), "scope-fixture"));
        OdbFileRow Model(string relative, string membership, bool ready = true)
        {
            var row = new OdbFileRow(new() { Path = Path.Combine(root, relative), Name = Path.GetFileName(relative),
                RelativePath = relative }) { ComparisonGroup = membership };
            if (ready) row.ApplyPostprocessScan(scan);
            return row;
        }
        var shared = Model("one/same.odb", "same.odb；B；未分组");
        var second = Model("two/same.odb", "same.odb");
        var unrelated = Model("unfinished.odb", "B", false);
        var free = Model("free.odb", "");
        OdbFileRow[] workspace = [shared, second, unrelated, free];
        var named = new OdbRunScope(OdbRunScopeKind.NamedGroup, "same.odb");
        var independent = new OdbRunScope(OdbRunScopeKind.SingleModel);
        var all = new OdbRunScope(OdbRunScopeKind.Selection);
        var namedLegends = new Dictionary<string, IReadOnlyDictionary<string, OdbLegendOverride>>(StringComparer.OrdinalIgnoreCase)
        {
            ["same.odb"] = new Dictionary<string, OdbLegendOverride> { ["PILE_U_MAG"] = new() { Maximum = 89 } },
        };
        var order = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase) { ["same.odb"] = [second.Path, shared.Path] };
        OdbScopedRunPlan Resolve(OdbRunScope? scope, params OdbFileRow[] selected) =>
            OdbScopedRunPlan.Resolve(scope, selected, workspace, root, root, null);
        OdbPostprocessRunCreateRequest Request(OdbScopedRunPlan plan) =>
            OdbScopedRunPlan.BuildRequest(root, plan.Rows, plan.Groups, new() { AnimationTimingMode = "duration",
                AnimationDurationSeconds = 3.5, ParallelWorkers = 4 }, true, order, namedLegends);
        var checks = 0;
        void Check(bool success, string description)
        {
            if (!success) throw new InvalidOperationException(description);
            checks++;
        }

        var subset = Resolve(named, shared, unrelated, free);
        Check(subset.CanRun && subset.Rows.SequenceEqual([shared]) && subset.Groups.Count == 1, "Filtered jobs leaked outside the group.");
        Check(subset.Summary.Contains("1 / 2"), "Partial group preview lost denominator.");
        var selectedGroup = Request(subset);
        var selectedMember = selectedGroup.Groups.Single();
        Check(!selectedMember.Standalone && selectedMember.Members.SequenceEqual([shared.Path]) &&
              selectedGroup.Jobs.Select(job => job.Path).SequenceEqual([shared.Path]), "Member paths and job snapshots disagree.");
        Check(selectedMember.LegendOverrides["PILE_U_MAG"].Maximum == 89, "Lost scoped manual legend.");
        var ordered = Request(Resolve(named, shared, second));
        Check(ordered.Groups.Single().Members.SequenceEqual([second.Path, shared.Path]), "Configured order lost for named run.");
        Check(ordered.Groups.Single().Id == selectedMember.Id && selectedGroup.ClientRequestId != ordered.ClientRequestId,
            "Changed membership changed named identity or repeated the command identity.");
        var one = Request(Resolve(independent, shared));
        var standalone = one.Groups.Single();
        Check(standalone.Name == selectedMember.Name && standalone.Standalone && standalone.Id != selectedMember.Id,
            "A group and an identically named standalone model collided.");
        Check(standalone.LegendOverrides.Count == 0 && standalone.Members.SequenceEqual([shared.Path]),
            "Independent model inherited group legend/order.");
        Check(Request(Resolve(independent, second)).Groups.Single().Id != standalone.Id,
            "Different paths with identical file names collided.");
        Check(Resolve(independent, shared).Summary.Contains(shared.RelativePath), "Standalone preview omitted relative model path.");
        Check(one.AnimationDurationSeconds == 3.5 && one.ParallelWorkers == 4 && one.ForceRescan, "Lost output options.");
        Check(Resolve(all, shared, free).Groups.Select(group => (group.Name, group.Standalone))
            .SequenceEqual([("same.odb", false), ("B", false), ("未分组", false), ("free.odb", true)]), "Default behavior changed.");
        Check(Request(Resolve(new(OdbRunScopeKind.NamedGroup, "未分组"), shared, free)).Groups.Single().Members.SequenceEqual([shared.Path]),
            "Literal group name confused with unassigned models.");
        Check(!Resolve(named, free).CanRun && !Resolve(named).CanRun, "Selected group ran without any selected members.");
        Check(!Resolve(new(OdbRunScopeKind.NamedGroup, "empty"), free).CanRun && !Resolve(null, shared).CanRun,
            "Missing/empty group widened to all jobs.");
        Check(!Resolve(independent, shared, second).CanRun && !Resolve(independent).CanRun, "Standalone accepted zero/multiple models.");
        Check(!Resolve(independent, unrelated).CanRun && !Resolve(all, unrelated, shared).CanRun &&
              !Resolve(new(OdbRunScopeKind.NamedGroup, "B"), shared, unrelated).CanRun, "Unready scope member was silently omitted.");
        Check(Resolve(named, shared, shared).Rows.Length == 1, "Duplicate model selection produced duplicate jobs.");
        Check(!OdbScopedRunPlan.Resolve(named, [shared], workspace, root, null, null).CanRun &&
              !OdbScopedRunPlan.Resolve(named, [shared], workspace, root, root + "-previous", null).CanRun,
            "Used selections from an unread/changed root.");
        Check(!OdbScopedRunPlan.Resolve(named, [shared], workspace, root, root, root + "-queue").CanRun,
            "Appended to a queue rooted elsewhere.");
        var appendPlan = OdbScopedRunPlan.Resolve(named, [shared], workspace, root + Path.DirectorySeparatorChar, root, root);
        Check(appendPlan.CanRun && Request(appendPlan).Groups.Single().Id == selectedMember.Id, "Append changed target identity.");
        Check(shared.ComparisonGroup == "same.odb；B；未分组" && unrelated.ComparisonGroup == "B",
            "Run scope modified saved group membership.");
        Check(!ReferenceEquals(one.Jobs.Single(), shared.PostprocessJob), "Submitted request still refers to an editable draft.");
        static OdbPostprocessGroupQueueItem Entry(string key, string status) => new() { GroupKey = key, Status = status };
        OdbScopedRunPlan Append(OdbRunScope scope, OdbFileRow[] selection, params OdbPostprocessGroupQueueItem[] entries) =>
            OdbScopedRunPlan.Resolve(scope, selection, workspace, root, root, root, entries);
        foreach (var state in new[] { "queued", "running", "cancelling" })
        {
            var existing = Append(named, [second], Entry("group:same.odb", state));
            Check(!existing.CanRun && existing.Summary.Contains("已在队列中"), "Duplicate active group was offered for append: " + state);
        }
        foreach (var state in new[] { "succeeded", "failed", "cancelled", "skipped", "interrupted" })
            Check(Append(named, [shared], Entry("group:same.odb", state)).CanRun, "A previous group attempt blocked retry: " + state);
        var mixed = Append(all, [shared, second, unrelated, free], Entry("group:same.odb", "queued"), Entry("group:b", "running"));
        Check(mixed.CanRun && mixed.Groups.Select(group => group.Name).SequenceEqual(["未分组", "free.odb"]) &&
              mixed.Rows.SequenceEqual([shared, free]), "Mixed append included busy groups or jobs only referenced by busy groups.");
        Check(mixed.Summary.Contains("将追加对比组“未分组”、独立模型“free.odb”") &&
              mixed.Summary.Contains("跳过对比组“same.odb”、对比组“B”"), "Mixed append preview skipped names or conflated group/model.");
        var activePath = "odb:" + Path.GetFullPath(shared.Path).ToLowerInvariant();
        Check(!Append(independent, [shared], Entry(activePath, "running")).CanRun &&
              Append(independent, [second], Entry(activePath, "running")).CanRun, "Standalone keys ignored normalized paths.");
        Check(Append(independent, [shared], Entry("group:same.odb", "running")).CanRun &&
              Append(named, [shared], Entry(activePath, "running")).CanRun, "Standalone/group keys collided in append.");
        var unicode = Model("unicode.odb", "Straßeﬃﬃİ");
        var unicodePlan = OdbScopedRunPlan.Resolve(new(OdbRunScopeKind.NamedGroup, unicode.ComparisonGroup), [unicode], [unicode],
            root, root, root, [Entry("group:strasseffiffii\u0307", "queued")]);
        Check(!unicodePlan.CanRun && unicodePlan.Summary.Contains("跳过"), "Full Unicode group case folding disagrees with backend.");
        Check(!OdbScopedRunPlan.Resolve(named, [shared], workspace, root, root, null, workspaceReadable: false).CanRun &&
              !OdbScopedRunPlan.Resolve(named, [shared], workspace, root, root, root, workspaceReadable: false).CanRun,
            "Unreadable workspace still allowed a start or append.");
        var many = Model("many.odb", string.Join("；", Enumerable.Range(1, 120).Select(index => $"G{index}")));
        var occupied = Enumerable.Range(1, 60).Select(index => Entry($"group:g{index}", "running")).ToArray();
        var longPlan = OdbScopedRunPlan.Resolve(all, [many], [many], root, root, root, occupied);
        Check(longPlan.CanRun && longPlan.Groups.Count == 60 && longPlan.Summary.Length < 130 &&
              longPlan.Summary.Contains("G61") && longPlan.Summary.Split("等 60 项").Length == 3, "Large queue preview was not bounded.");
        Console.WriteLine($"{checks} scoped extraction request checks passed.");
    }
}
