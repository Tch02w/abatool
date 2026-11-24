using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;

internal static class PostprocessEmptyGroupChecks
{
    public static void Run()
    {
        var folder = Directory.CreateTempSubdirectory("postprocess-empty-groups-");
        try
        {
            var store = new OdbPostprocessWorkspaceStore(folder.FullName);
            var row = new OdbFileRow(new OdbDiscoveryItem { Path = Path.Combine(folder.FullName, "model.odb") })
                { ComparisonGroup = "Occupied" };
            var state = new OdbPostprocessWorkspace();
            var plan = OdbComparisonGroups.PlanNewGroups("First\r\nSecond；first\nOccupied",
                OdbComparisonGroups.CatalogNames([row], []));
            Check(plan.NewNames.SequenceEqual(["First", "Second"])
                && plan.DuplicateNames.SequenceEqual(["first", "Occupied"]), "Pasted group names or duplicates changed.");
            foreach (var name in plan.NewNames) state.GroupMemberOrder[name] = [];
            state.Rows.Add(new() { Path = row.Path, Group = row.ComparisonGroup });
            store.Save(folder.FullName, state);
            state = store.Load(folder.FullName)!;
            Check(OdbComparisonGroups.CatalogNames([row], state.GroupMemberOrder.Keys).SequenceEqual(["First", "Occupied", "Second"]),
                "Reopening lost an empty group or a member-defined group.");
            Check(OdbComparisonGroups.ForExecution([row]).Select(group => group.Name).SequenceEqual(["Occupied"])
                  && OdbComparisonGroups.ForExecution([]).Count == 0, "An empty group became an extraction job.");
            state.Legends["First"] = new() { ["PILE_U_MAG"] = new() { Minimum = 0, Maximum = 9 } };
            OdbComparisonGroups.ChangeGroup(state, "first", "Renamed");
            Check(state.GroupMemberOrder["Renamed"].Count == 0 && state.Legends["Renamed"]["PILE_U_MAG"].Maximum == 9,
                "Case-insensitive empty group rename did not transfer its settings.");
            try
            {
                OdbComparisonGroups.ChangeGroup(state, "Renamed", "Second");
                throw new InvalidOperationException("Rename accepted a collision with an empty group.");
            }
            catch (ArgumentException) { }
            state.Rows[0].Group = OdbComparisonGroups.UpdateMembership(state.Rows[0].Group, "Renamed", "add");
            OdbComparisonGroups.ChangeGroup(state, "Renamed", null);
            Check(state.Rows[0].Group == "Occupied" && !state.Legends.ContainsKey("Renamed")
                && state.GroupMemberOrder.Keys.SequenceEqual(["Second"]), "Delete changed an unrelated group.");
            store.Save(folder.FullName, state);
            Check(store.Load(folder.FullName)!.GroupMemberOrder.Keys.SequenceEqual(["Second"]),
                "Removed group came back after reopening.");
            Console.WriteLine("Empty group creation, membership, rename, deletion and persistence passed.");
        }
        finally { folder.Delete(recursive: true); }
    }

    private static void Check(bool condition, string message)
    {
        if (!condition) throw new InvalidOperationException(message);
    }
}
