using System.Text.Json;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;

internal static class GroupExecutionOrderChecks
{
    public static void Run(OdbPostprocessScanItem scan)
    {
        var directory = Directory.CreateTempSubdirectory("postprocess-execution-order-");
        try { Verify(directory.FullName, scan); }
        finally { directory.Delete(recursive: true); }
    }

    private static void Verify(string root, OdbPostprocessScanItem scan)
    {
        var checks = 0;
        void Check(bool condition, string message)
        {
            if (!condition) throw new InvalidOperationException(message);
            checks++;
        }
        OdbFileRow Model(string name, string membership)
        {
            var row = new OdbFileRow(new() { Path = Path.Combine(root, name), Name = name, RelativePath = name })
                { ComparisonGroup = membership };
            row.ApplyPostprocessScan(scan);
            return row;
        }
        var a = Model("alpha.odb", "A");
        var solo = Model("solo.odb", "");
        var ab = Model("overlap.odb", "A；solo.odb");
        var c = Model("literal.odb", "未分组");
        var d = Model("extra.odb", "D");
        OdbFileRow[] workspace = [a, solo, ab, c, d];
        List<string> preference = ["未分组", "空组", "SOLO.ODB", "solo.odb", "missing", "a"];
        OdbScopedRunPlan Plan(OdbRunScopeKind kind, OdbFileRow[] selection, IReadOnlyList<string>? order,
            IReadOnlyList<OdbPostprocessGroupQueueItem>? queue = null, string name = "") =>
            OdbScopedRunPlan.Resolve(new OdbRunScope(kind, name), selection, workspace, root, root,
                queue is null ? null : root, queue, groupExecutionOrder: order);
        const OdbRunScopeKind all = OdbRunScopeKind.Selection;
        static string[] Names(OdbScopedRunPlan plan) => plan.Groups.Select(group => group.Standalone ? "<model>" : group.Name).ToArray();
        var baseline = Plan(all, workspace, null);
        Check(Names(baseline).SequenceEqual(["A", "<model>", "solo.odb", "未分组", "D"]), "Initial order changed.");
        var ordered = Plan(all, workspace, preference);
        Check(Names(ordered).SequenceEqual(["未分组", "<model>", "solo.odb", "A", "D"]), "Preference changed a standalone slot, lost a group or inserted an empty group.");
        Check(ordered.Summary.Contains("对比组“未分组”、独立模型“solo.odb”、对比组“solo.odb”等 5 项"),
            "Preview does not match the bounded effective order.");
        Check(ordered.Groups[1].Members.Single() == solo && ordered.Groups[2].Members.Single() == ab,
            "Independent model was conflated with identically named group.");
        Check(ordered.Rows.SequenceEqual(workspace) && ordered.Groups.Single(g => g.Name == "A").Members.SequenceEqual([a, ab]),
            "Changing group priorities modified row selection or member order.");
        Check(Names(Plan(all, [c, ab, a], preference)).SequenceEqual(["未分组", "solo.odb", "A"]) &&
              Names(Plan(all, [ab, a, c], preference)).SequenceEqual(["未分组", "solo.odb", "A"]),
            "Selecting named groups in a different order changed their configured priority.");
        Check(Names(Plan(all, workspace, ["stale", "empty"])).SequenceEqual(Names(baseline)) &&
              Names(Plan(all, workspace, [])).SequenceEqual(Names(baseline)), "Irrelevant or empty preference changed defaults.");
        Check(Names(Plan(all, workspace, ["d"])).SequenceEqual(["D", "<model>", "A", "solo.odb", "未分组"]),
            "Unconfigured groups lost encounter order.");
        var live = new OdbPostprocessGroupQueueItem { GroupKey = "group:a", Name = "A", Status = "running" };
        var append = Plan(all, workspace, preference, [live]);
        Check(Names(append).SequenceEqual(["<model>", "未分组", "solo.odb", "D"]),
            "Standalone position in the actual appended groups was computed before deduplication.");
        Check(append.Summary.Contains("将追加独立模型“solo.odb”、对比组“未分组”、对比组“solo.odb”") &&
              append.Summary.Contains("跳过对比组“A”"), "Append preview disagreed with append request.");
        Check(Plan(OdbRunScopeKind.SingleModel, [ab], preference).Groups.Single().Standalone &&
              Plan(OdbRunScopeKind.NamedGroup, workspace, preference, name: "solo.odb").Groups.Single().Members.Single() == ab,
            "Preference widened a single-model or single-group request.");
        var memberOrder = new Dictionary<string, List<string>> { ["A"] = [ab.Path, a.Path] };
        var legends = new Dictionary<string, IReadOnlyDictionary<string, OdbLegendOverride>>
            { ["A"] = new Dictionary<string, OdbLegendOverride> { ["PILE_U_MAG"] = new() { Maximum = 31 } } };
        OdbPostprocessRunCreateRequest Request(OdbScopedRunPlan p) =>
            OdbScopedRunPlan.BuildRequest(root, p.Rows, p.Groups, new(), false, memberOrder, legends);
        var before = Request(baseline);
        var after = Request(ordered);
        Check(after.Groups.Select(g => g.Name).SequenceEqual(ordered.Groups.Select(g => g.Name)) &&
              after.Groups.Select(g => g.Id).ToHashSet().SetEquals(before.Groups.Select(g => g.Id)),
            "Building request changed actual priorities or stable identities.");
        var groupA = after.Groups.Single(g => g.Name == "A");
        Check(groupA.Members.SequenceEqual([ab.Path, a.Path]) && groupA.LegendOverrides["PILE_U_MAG"].Maximum == 31 &&
              after.Groups.Single(g => g.Standalone).LegendOverrides.Count == 0, "Group order disturbed a member list or legend.");
        Check(OdbComparisonGroups.OrderGroupNames(["A", "solo.odb", "未分组", "空组", "D", "d"], preference)
            .SequenceEqual(["未分组", "空组", "solo.odb", "A", "D"]), "Editor lost empty groups, casing or unique order.");

        var store = new OdbPostprocessWorkspaceStore(Path.Combine(root, "state"));
        var state = new OdbPostprocessWorkspace
        {
            Rows = workspace.Select(row => new OdbPostprocessSavedRow { Path = row.Path, Group = row.ComparisonGroup }).ToList(),
            GroupMemberOrder = new() { ["空组"] = [] },
        };
        var legacy = JsonSerializer.SerializeToElement(new { state.Version, state.Output, state.Rows, state.GroupMemberOrder, state.Legends });
        Check(OdbPostprocessDraftRecovery.Fingerprint(legacy) == OdbPostprocessDraftRecovery.Fingerprint(state) &&
              !JsonSerializer.SerializeToElement(state).TryGetProperty("GroupExecutionOrder", out _),
            "Adding an empty preference broke legacy recovery fingerprints.");
        Check(JsonSerializer.Deserialize<OdbPostprocessWorkspace>(legacy)!.GroupExecutionOrder.Count == 0,
            "An existing workspace did not keep the implicit default.");
        state.GroupExecutionOrder = [.. preference];
        store.Save(root, state);
        var saved = store.Load(root)!;
        Check(saved.GroupExecutionOrder.SequenceEqual(preference), "Workspace store did not round-trip preferences.");
        Check(OdbPostprocessDraftRecovery.Fingerprint(saved) != OdbPostprocessDraftRecovery.Fingerprint(legacy),
            "Saving a real ordering preference did not update the workspace basis.");
        OdbComparisonGroups.ChangeGroup(saved, "solo.odb", "B");
        Check(saved.GroupExecutionOrder.SequenceEqual(["未分组", "空组", "B", "a"]) &&
              saved.Rows.Single(row => row.Path == ab.Path).Group == "A；B", "Rename lost priority, left duplicates or changed membership.");
        OdbComparisonGroups.ChangeGroup(saved, "b", "b");
        Check(saved.GroupExecutionOrder.Contains("b", StringComparer.Ordinal), "Case-only rename lost display casing.");
        OdbComparisonGroups.ChangeGroup(saved, "未分组", null);
        Check(saved.GroupExecutionOrder.SequenceEqual(["空组", "b", "a"]), "Deleted name remained in execution order.");
        saved.GroupMemberOrder.Add("新组", []);
        Check(OdbComparisonGroups.OrderGroupNames(OdbComparisonGroups.CatalogNames(workspace, saved.GroupMemberOrder.Keys), saved.GroupExecutionOrder)
              .Contains("新组") && !saved.GroupExecutionOrder.Contains("新组"), "New group unnecessarily created an explicit preference.");
        store.Save(root, saved);
        Check(store.Load(root)!.GroupExecutionOrder.SequenceEqual(["空组", "b", "a"]), "Reopening lost rename/deletion ordering.");
        var beforeFailure = OdbPostprocessDraftRecovery.Fingerprint(saved);
        try
        {
            OdbComparisonGroups.ChangeGroup(saved, "a", "b");
            throw new InvalidOperationException("Conflicting rename unexpectedly succeeded.");
        }
        catch (ArgumentException) { }
        Check(OdbPostprocessDraftRecovery.Fingerprint(saved) == beforeFailure, "Failed rename changed a preference or membership.");
        saved.GroupExecutionOrder.Add(" ");
        try
        {
            store.Save(root, saved);
            throw new InvalidOperationException("Invalid preference unexpectedly overwrote the workspace.");
        }
        catch (InvalidDataException) { }
        Check(store.Load(root)!.GroupExecutionOrder.SequenceEqual(["空组", "b", "a"]), "A failed save overwrote the previous order.");
        saved.GroupExecutionOrder = [];
        store.Save(root, saved);
        Check(store.Load(root)!.GroupExecutionOrder.Count == 0, "Restoring default order required deleting the workspace.");
        List<string> liveOrder = ["D", "A", "空组"];
        var emptyOrders = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase) { ["空组"] = [] };
        OdbComparisonGroups.ChangeGroup(workspace, "A", "renamed", legends, emptyOrders, liveOrder);
        Check(liveOrder.SequenceEqual(["D", "renamed", "空组"]) && a.ComparisonGroup == "renamed" &&
              legends.ContainsKey("renamed"), "In-memory rename diverged from workspace rename semantics.");
        OdbComparisonGroups.ChangeGroup(workspace, "空组", null, legends, emptyOrders, liveOrder);
        Check(liveOrder.SequenceEqual(["D", "renamed"]) && emptyOrders.Count == 0,
            "Deleted empty group remained in the live priority list.");
        Console.WriteLine($"{checks} comparison group execution order checks passed.");
    }
}
