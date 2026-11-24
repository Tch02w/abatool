using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;

PostprocessResultLocationChecks.Run();

static void Check(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

foreach (var input in new[] { "-1E30", "1E30", "0", "-143" })
    Check(OdbComparisonGroups.TryParseLegendBound(input, out _), "Expected finite legend bound " + input);
foreach (var input in new[] { "", "NaN", "Infinity", "-2E30", "1E31", "value" })
    Check(!OdbComparisonGroups.TryParseLegendBound(input, out _), "Unexpected legend bound " + input);
Console.WriteLine("10 legend editor numeric checks passed");

static OdbPostprocessScanItem Scan(string error = "", bool removePile = false) => new()
{
    Path = "case.odb", Error = error, Steps = ["Load"], AssemblyNodeSets = ["LoadSet"],
    AssemblyElementSets = removePile ? ["Concrete", "Soil", "Rebar"] : ["Pile", "Concrete", "Soil", "Rebar"],
    Suggested = new()
    {
        StartStep = "Load", EndStep = "Load", LoadDirection = "1", LoadSet = "LoadSet",
        PileDisplaySet = "Pile", PileConcreteSet = "Concrete", SoilSet = "Soil", RebarSet = "Rebar",
    },
};

try
{
    // Verify this executable's failure contract without a Windows crash dialog.
    if (args.Contains("--verify-failure-exit"))
        throw new InvalidOperationException("Intentional test-runner failure-exit verification");
    if (args.Length == 2 && args[0] == "--draft-checks") await PostprocessDraftChecks.RunAsync(args[1]);
    else RunChecks();
}
catch (Exception error)
{
    // Return a normal failed-test exit code instead of invoking Windows crash UI.
    Console.Error.WriteLine(error);
    Environment.ExitCode = 1;
}

static void RunChecks()
{
OdbRegionExtractionMethodsChecks.Run();
OdbPostprocessRecoveryChecks.Run();
var structureScan = System.Text.Json.JsonSerializer.Deserialize<OdbPostprocessScanItem>("""
{"path":"case.odb","structureCatalog":{"schemaVersion":1,"regions":[
 {"id":"node-A","scope":"instance","instance":"A","kind":"node_set","name":"Same","nodeCount":2},
 {"id":"element-A","scope":"instance","instance":"A","kind":"element_set","name":"Same","elementCount":1,"elementTypes":{"T3D2":1}}
],"steps":[{"name":"Load","frames":[{"index":0,"value":0,"fields":[]},{"index":1,"value":1,"fields":[{"name":"S","components":["S11"],"positions":["INTEGRATION_POINT"]}]}]}]}}
""")!;
Check(structureScan.StructureCatalog.Regions.Count == 2, "Same-name node and element sets must remain distinct");
Check(structureScan.StructureCatalog.Regions[1].ElementTypes["T3D2"] == 1, "Element type metadata must survive deserialization");
Check(structureScan.StructureCatalog.Steps[0].Frames[0].Fields.Count == 0, "Empty frame must not inherit later output");
Check(structureScan.StructureCatalog.Steps[0].Frames[1].Fields[0].Components[0] == "S11", "Output components must survive deserialization");
Check(structureScan.StructureCatalog.Regions[0].DisplayName != structureScan.StructureCatalog.Regions[1].DisplayName, "Region labels must distinguish kinds");
Console.WriteLine("5 structure catalog contract checks passed");
var row = new OdbFileRow(new OdbDiscoveryItem { Path = "case.odb", Name = "case.odb" });
row.ApplyPostprocessScan(Scan());
Check(row.HasPostprocessConfiguration, "Valid defaults should be ready");
var noBars = new OdbFileRow(new OdbDiscoveryItem { Path = "plain.odb" });
var plainScan = Scan();
plainScan.Suggested.ReinforcementMode = "none";
plainScan.Suggested.RebarSet = "";
noBars.ApplyPostprocessScan(plainScan);
Check(noBars.HasPostprocessConfiguration, "Explicit no-bars mode must not require a rebar set");
var requiresBars = noBars.PostprocessJob!.Clone();
requiresBars.ReinforcementMode = "required";
noBars.UpdatePostprocessJob(requiresBars);
Check(!noBars.HasPostprocessConfiguration, "Switching back to reinforced must require a valid set");
Console.WriteLine("2 reinforcement mode checks passed");
var edited = row.PostprocessJob!.Clone();
edited.LoadDirection = "3";
edited.RebarDiameterMm = 28;
edited.FrameMode = "manual";
edited.ManualSequenceExpression = "0,2";
row.UpdatePostprocessJob(edited);
row.ComparisonGroup = "A;B";
var browserGroups = OdbComparisonGroups.ForBrowser([row]).ToArray();
Check(browserGroups.Length == 2 && browserGroups.All(group => group.Single() == row), "Multi-group ODB must appear under both browser groups");
Check(OdbComparisonGroups.ParseNames(" A；a; B;; ").SequenceEqual(new[] { "A", "B" }), "Group parsing must trim and deduplicate names");
var ungrouped = new OdbFileRow(new OdbDiscoveryItem { Path = "ungrouped.odb" });
ungrouped.ComparisonGroup = " ;； ";
Check(OdbComparisonGroups.ForBrowser([ungrouped]).Single().Key == "未分组", "Empty memberships must stay visible");
Console.WriteLine("3 comparison browser checks passed");
Check(OdbComparisonGroups.UpdateMembership("A；B", "b;C", "add") == "A；B；C", "Append must preserve existing groups and deduplicate");
Check(OdbComparisonGroups.UpdateMembership("A；B", "a", "remove") == "B", "Removal must preserve other memberships");
Check(OdbComparisonGroups.UpdateMembership("A；B", "C", "replace") == "C", "Replacement must remain explicit");
Check(OdbComparisonGroups.UpdateMembership("A；B", "", "clear") == "", "Clear must return the ODB to ungrouped");
Console.WriteLine("4 membership editing checks passed");
var sameNameA = new OdbFileRow(new OdbDiscoveryItem { Path = "a/model.odb", Name = "model.odb" });
var sameNameB = new OdbFileRow(new OdbDiscoveryItem { Path = "b/model.odb", Name = "model.odb" });
sameNameA.ComparisonGroup = "";
sameNameB.ComparisonGroup = "";
var namedMember = new OdbFileRow(new OdbDiscoveryItem { Path = "other.odb", Name = "other.odb" });
namedMember.ComparisonGroup = "model.odb";
var executionGroups = OdbComparisonGroups.ForExecution([sameNameA, sameNameB, namedMember]);
Check(executionGroups.Count == 3, "Same-named standalone ODBs must not merge with each other or named groups");
Check(executionGroups.Count(group => group.Standalone) == 2, "Standalone identity lost");
Check(executionGroups.Single(group => !group.Standalone).Members.Single() == namedMember,
    "Named group gained an unrelated standalone ODB");
Check(OdbComparisonGroups.ForExecution([sameNameA, sameNameA]).Count == 1,
    "Duplicate path became duplicate execution");
var multiMember = new OdbFileRow(new OdbDiscoveryItem { Path = "multi.odb" });
multiMember.ComparisonGroup = "MODEL.ODB;Second";
var multiple = OdbComparisonGroups.ForExecution([namedMember, multiMember]);
Check(multiple.Count == 2 && multiple[0].Members.SequenceEqual(new[] { namedMember, multiMember }),
    "Named groups must preserve member order and case-insensitive membership");
Console.WriteLine("5 execution group isolation checks passed");
Check(OdbComparisonGroups.OrderMembers([sameNameA, sameNameB], [sameNameB.Path, sameNameA.Path])
    .SequenceEqual(new[] { sameNameB, sameNameA }), "Saved member order ignored");
Check(OdbComparisonGroups.OrderMembers([sameNameA, sameNameB], ["missing.odb", sameNameB.Path, sameNameB.Path])
    .SequenceEqual(new[] { sameNameB, sameNameA }), "Stale/duplicate order entries must not lose new members");
Check(OdbComparisonGroups.OrderMembers([sameNameA], [sameNameB.Path, sameNameA.Path]).Single() == sameNameA,
    "Ordering reintroduced an unselected ODB");
Console.WriteLine("3 group member ordering checks passed");
var managedRow = new OdbFileRow(new OdbDiscoveryItem { Path = "managed.odb" });
managedRow.ComparisonGroup = "Old；Other";
var managedLegends = new Dictionary<string, IReadOnlyDictionary<string, OdbLegendOverride>>(StringComparer.OrdinalIgnoreCase)
    { ["Old"] = new Dictionary<string, OdbLegendOverride>() };
var managedOrders = new Dictionary<string, List<string>>(StringComparer.OrdinalIgnoreCase) { ["Old"] = [managedRow.Path] };
OdbComparisonGroups.ChangeGroup([managedRow], "old", "Renamed", managedLegends, managedOrders);
Check(managedRow.ComparisonGroup == "Renamed；Other" && managedLegends.ContainsKey("Renamed")
    && managedOrders["Renamed"].Single() == managedRow.Path && !managedOrders.ContainsKey("Old"),
    "Rename must preserve memberships and transfer settings");
var renameRejected = false;
try { OdbComparisonGroups.ChangeGroup([managedRow], "Renamed", "Other", managedLegends, managedOrders); }
catch (ArgumentException) { renameRejected = true; }
Check(renameRejected && managedRow.ComparisonGroup == "Renamed；Other" && managedLegends.ContainsKey("Renamed"),
    "Conflicting rename changed state");
renameRejected = false;
try { OdbComparisonGroups.ChangeGroup([managedRow], "Renamed", "A;B", managedLegends, managedOrders); }
catch (ArgumentException) { renameRejected = true; }
Check(renameRejected && managedOrders.ContainsKey("Renamed"), "Rename accepted multiple names");
OdbComparisonGroups.ChangeGroup([managedRow], "Renamed", "RENAMED", managedLegends, managedOrders);
Check(managedRow.ComparisonGroup == "RENAMED；Other" && managedOrders.ContainsKey("RENAMED"), "Case-only rename lost settings");
OdbComparisonGroups.ChangeGroup([managedRow], "RENAMED", null, managedLegends, managedOrders);
Check(managedRow.ComparisonGroup == "Other" && managedLegends.Count == 0 && managedOrders.Count == 0,
    "Delete must preserve other memberships and remove only group settings");
Console.WriteLine("5 group management checks passed");
row.ApplyPostprocessScan(Scan());
Check(row.PostprocessJob!.LoadDirection == "3" && row.PostprocessJob.RebarDiameterMm == 28, "Rescan overwrote edited parameters");
Check(row.PostprocessJob.ManualSequenceExpression == "0,2" && row.ComparisonGroup == "A;B", "Rescan lost frame/group choices");
edited.RebarDiameterMm = 99;
Check(row.PostprocessJob.RebarDiameterMm == 28, "Row shares mutable editor input");
row.ApplyPostprocessScan(Scan(error: "unreadable"));
Check(!row.HasPostprocessConfiguration && row.PostprocessJob.RebarDiameterMm == 28, "Scan failure must preserve draft but block run");
row.ApplyPostprocessScan(Scan(removePile: true));
Check(!row.HasPostprocessConfiguration && row.PostprocessJob.PileDisplaySet == "Pile", "Removed role should require correction, not silently reset");
row.ApplyPostprocessScan(Scan());
Check(row.HasPostprocessConfiguration, "Valid rescan should restore readiness");
var incomplete = Scan();
incomplete.Suggested.LoadDirection = "";
var newRow = new OdbFileRow(new OdbDiscoveryItem { Path = "other.odb" });
newRow.ApplyPostprocessScan(incomplete);
Check(!newRow.HasPostprocessConfiguration, "Unselected direction must not be marked ready");
row.MarkStructureAnalysisIncomplete("no result");
Check(!row.HasPostprocessConfiguration && row.ScanDetails is null && row.PostprocessJob!.RebarDiameterMm == 28, "Missing scan result must invalidate readiness without discarding edits");
Console.WriteLine("9 postprocess state checks passed");

row.ApplyPostprocessScan(Scan());
var same = new OdbDiscoveryItem { Path = "case.odb", Name = "case.odb" };
var added = new OdbDiscoveryItem { Path = "new.odb", Name = "new.odb" };
var merged = OdbDiscoveryReconciler.Reconcile([same, added], [row], [row.Path], true);
Check(merged.Rows[0].PostprocessJob!.RebarDiameterMm == 28 && merged.Rows[0].ComparisonGroup == "A;B", "Directory refresh discarded configuration");
Check(merged.SelectedRows.Count == 1 && merged.SelectedRows[0].Path == row.Path, "Directory refresh changed selection");
var changed = row.WithDiscovery(new OdbDiscoveryItem { Path = row.Path, SizeBytes = 42 });
Check(!changed.HasPostprocessConfiguration && changed.ScanDetails is null && changed.PostprocessJob!.RebarDiameterMm == 28, "Changed ODB must invalidate structure but preserve edits");
Check(row.HasPostprocessConfiguration, "Reconciliation mutated previous row before commit");
Check(OdbDiscoveryReconciler.Reconcile([same], [row], [], true).SelectedRows.Count == 0, "Empty selection was not preserved");
Check(OdbDiscoveryReconciler.Reconcile([added], [row], [row.Path], true).SelectedRows.Count == 0, "Deleted selection restored");
var otherRoot = OdbDiscoveryReconciler.Reconcile([added], [row], [], false);
Check(otherRoot.SelectedRows.Count == 1 && otherRoot.Rows[0].PostprocessJob is null, "New root inherited unrelated configuration");
Console.WriteLine("7 directory refresh checks passed");

var stateDirectory = Path.Combine(Path.GetTempPath(), "abatool-workspace-test-" + Guid.NewGuid().ToString("N"));
try
{
    var store = new OdbPostprocessWorkspaceStore(stateDirectory);
    var root = Path.Combine(stateDirectory, "project");
    Check(store.Load(root) is null, "Missing workspace should not create defaults on disk");
    store.Save(root, new OdbPostprocessWorkspace
    {
        Rows = [new() { Path = row.Path, Group = "A;B", Selected = false, Draft = row.PostprocessJob!.Clone() }],
        Legends = new() { ["A"] = new() },
        GroupMemberOrder = new() { ["A"] = [sameNameB.Path, sameNameA.Path] },
        Output = new() { ImageUnit = "mm", ImageWidth = 200, ImageHeight = 150,
            AnimationFps = 12, AnimationTimingMode = "duration", AnimationDurationSeconds = 3.25,
            WhiteBackground = false, FullTimehistory = true, ParallelWorkers = 32 },
    });
    var loaded = new OdbPostprocessWorkspaceStore(stateDirectory).Load(root)!;
    Check(loaded.GroupMemberOrder["A"].SequenceEqual(new[] { sameNameB.Path, sameNameA.Path }),
        "Group order lost on restart");
    Console.WriteLine("1 group ordering persistence check passed");
    Check(loaded.Output.ImageUnit == "mm" && loaded.Output.ImageWidth == 200
        && loaded.Output.ImageHeight == 150 && loaded.Output.AnimationFps == 12
        && loaded.Output.AnimationTimingMode == "duration" && loaded.Output.AnimationDurationSeconds == 3.25
        && !loaded.Output.WhiteBackground && loaded.Output.FullTimehistory && loaded.Output.ParallelWorkers == 32,
        "Restart lost output settings");
    var invalidOutputRejected = false;
    try { store.Save(root, new() { Output = new() { ImageWidth = 0 } }); }
    catch (InvalidDataException) { invalidOutputRejected = true; }
    Check(invalidOutputRejected && store.Load(root)!.Output.ImageWidth == 200,
        "Invalid output settings overwrote valid workspace");
    Console.WriteLine("2 output settings persistence checks passed");
    Check(loaded.Rows.Count == 1 && !loaded.Rows[0].Selected && loaded.Rows[0].Group == "A;B", "Restart lost selection or groups");
    Check(loaded.Rows[0].Draft!.RebarDiameterMm == 28 && loaded.Legends.ContainsKey("A"), "Restart lost parameters or legends");
    Check(store.Load(root + "-other") is null, "Directory configurations leaked across projects");
    var restoredRow = new OdbFileRow(same);
    restoredRow.UpdatePostprocessJob(loaded.Rows[0].Draft!);
    Check(!restoredRow.HasPostprocessConfiguration, "Persisted draft bypassed structure validation");
    restoredRow.ApplyPostprocessScan(Scan());
    Check(restoredRow.HasPostprocessConfiguration && restoredRow.PostprocessJob!.RebarDiameterMm == 28, "Scan lost restored draft");
    store.Save(root, new OdbPostprocessWorkspace());
    Check(store.Load(root)!.Rows.Count == 0, "Atomic replacement failed");
    Check(Directory.GetFiles(stateDirectory, "*.tmp").Length == 0, "Temporary state file leaked");
    File.WriteAllText(Directory.GetFiles(stateDirectory, "*.json").Single(), "invalid");
    var rejected = false;
    try { store.Load(root); } catch (System.Text.Json.JsonException) { rejected = true; }
    Check(rejected, "Corrupt state silently replaced with defaults");
    Console.WriteLine("9 workspace persistence checks passed");
    var stateFile = Directory.GetFiles(stateDirectory, "*.json").Single();
    File.WriteAllText(stateFile, "{\"Version\":1,\"Rows\":[],\"Legends\":{}}");
    Check(store.Load(root)!.Output.ImageWidth == 1500,
        "Legacy workspace without output settings failed to load defaults");
    Console.WriteLine("1 legacy output settings compatibility check passed");
    Check(store.Load(root)!.Output.AnimationFps == 25, "New workspace should start at 25 fps");
    File.WriteAllText(stateFile, """{"Version":1,"Output":{"AnimationFps":5}}""");
    Check(store.Load(root)!.Output is { AnimationFps: 5, AnimationTimingMode: "fps" },
        "Existing workspace should retain its saved frame rate");
    var fpsJson = System.Text.Json.JsonSerializer.Serialize(new OdbPostprocessRunCreateRequest());
    var durationJson = System.Text.Json.JsonSerializer.Serialize(new OdbPostprocessRunCreateRequest { AnimationDurationSeconds = 4.25 });
    Check(!fpsJson.Contains("animationDurationSeconds") && durationJson.Contains("\"animationDurationSeconds\":4.25"),
        "Only duration mode should send a target duration");
    Console.WriteLine("3 GIF timing compatibility checks passed");
    foreach (var invalidJson in new[]
    {
        """{"Output":{"AnimationTimingMode":"other"}}""",
        """{"Output":{"AnimationDurationSeconds":0}}""",
        "{\"Rows\":[null]}",
        "{\"Rows\":[{\"Path\":\"case.odb\",\"Draft\":{\"pileSteelSet\":null}}]}",
        "{\"Legends\":{\"A\":null}}",
        "{\"Legends\":{\"A\":{\"S\":null}}}",
        "{\"Rows\":[{\"Path\":\"case.odb\"},{\"Path\":\"CASE.odb\"}]}",
    })
    {
        File.WriteAllText(stateFile, invalidJson);
        rejected = false;
        try { store.Load(root); }
        catch (Exception error) when (error is System.Text.Json.JsonException or InvalidDataException) { rejected = true; }
        Check(rejected && File.ReadAllText(stateFile) == invalidJson, "Malformed nested state was accepted or modified");
    }
    var protectedContent = File.ReadAllText(stateFile);
    rejected = false;
    try { store.Save(root, new() { Rows = [new() { Path = "case.odb" }, new() { Path = "CASE.odb" }] }); }
    catch (InvalidDataException) { rejected = true; }
    Check(rejected && File.ReadAllText(stateFile) == protectedContent, "Invalid save overwrote previous state");
    Console.WriteLine("8 invalid workspace protection checks passed");
}
finally
{
    // Only this test's uniquely-created directory is removed.
    if (Directory.Exists(stateDirectory)) Directory.Delete(stateDirectory, recursive: true);
}
}
