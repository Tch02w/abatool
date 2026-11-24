using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;

internal static class ParameterComparisonChecks
{
    // DTO-only models; no ODB, solver or filesystem access.
    private static OdbFileRow Row(string path, bool reinforced, bool legacy = false)
    {
        var row = new OdbFileRow(new OdbDiscoveryItem { Path = path, Name = "shared.odb" });
        var load = reinforced ? "LOAD_A" : "LOAD_B";
        var steps = new[] { "Gravity", "Load" };
        OdbStepDescriptor Step(string name, int count) => new()
        {
            Name = name, Frames = Enumerable.Range(0, count).Select(i => new OdbFrameDescriptor { Index = i }).ToArray()
        };
        row.ApplyPostprocessScan(new OdbPostprocessScanItem
        {
            Path = path, Steps = steps, AssemblyNodeSets = [load],
            AssemblyElementSets = reinforced ? ["Pile", "Soil", "Bars", "Steel"] : ["Pile", "Soil"],
            Suggested = new OdbPostprocessJobDraft
            {
                StartStep = "Gravity", EndStep = "Load", LoadDirection = "1", LoadSet = load,
                PileDisplaySet = "Pile", PileConcreteSet = "Pile", SoilSet = "Soil",
                ReinforcementMode = reinforced ? "required" : "none", RebarSet = reinforced ? "Bars" : "",
                PileSteelSet = reinforced ? "Steel" : "", LongitudinalMaterial = reinforced ? "steel-280" : "",
            },
            StructureCatalog = legacy ? new() : new OdbStructureCatalog
            {
                SchemaVersion = 1, Steps = [Step("Gravity", 2), Step("Load", 3)]
            }
        });
        return row;
    }

    public static void Run()
    {
        var a = Row(@"G:\test\A\shared.odb", true);
        var b = Row(@"G:\test\B\shared.odb", false);
        var legacy = Row(@"G:\test\C\legacy.odb", false, legacy: true);
        var matrix = new OdbPostprocessParameterComparison([a, b]);
        const string diameter = nameof(OdbPostprocessJobDraft.RebarDiameterMm);
        const string material = nameof(OdbPostprocessJobDraft.LongitudinalMaterial);
        const string direction = nameof(OdbPostprocessJobDraft.LoadDirection);
        const string frames = nameof(OdbPostprocessJobDraft.ManualSequenceExpression);
        const string mode = nameof(OdbPostprocessJobDraft.FrameMode);
        const string load = nameof(OdbPostprocessJobDraft.LoadSet);
        const string step = nameof(OdbPostprocessJobDraft.StartStep);
        const string pre = nameof(OdbPostprocessJobDraft.PrefractureSequenceIndex);
        var checks = 0;
        void Check(bool value, string message)
        {
            if (!value) throw new InvalidOperationException(message);
            checks++;
        }
        void ExpectInvalid(OdbPostprocessParameterComparison editor, string path, string key)
        {
            Check(!editor.TryBuild(out var drafts, out var issues) && drafts.Count == 0 &&
                issues.Any(issue => issue.Path == path && issue.FieldKey == key), $"Missing {path} {key} validation");
        }
        var allFields = typeof(OdbPostprocessJobDraft).GetProperties().Select(p => p.Name)
            .Where(name => name != nameof(OdbPostprocessJobDraft.Path)).ToHashSet();
        Check(allFields.SetEquals(OdbPostprocessParameterComparison.Fields.Select(f => f.Key)), "Every editable field is represented");
        Check(matrix.TryBuild(out var changed, out _) && changed.Count == 0, "Unchanged rows should retain their state");
        Check(matrix.GetChoices(a.Path, load).SequenceEqual(["LOAD_A"]) && matrix.GetChoices(b.Path, load).SequenceEqual(["LOAD_B"]),
            "Each column must use its own node set options");
        Check(matrix.GetChoices(b.Path, nameof(OdbPostprocessJobDraft.PileSteelSet)).Contains(""), "Optional steel set may be cleared");
        Check(matrix.GetChoices(a.Path, material).Count == 0, "Material is free text");
        matrix.SetValue(a.Path, diameter, "28.5");
        matrix.SetValue(a.Path, material, "未列入扫描目录的材料");
        matrix.SetValue(a.Path, direction, "3");
        matrix.CopyFields(a.Path, [b.Path], []);
        Check(matrix.GetValue(b.Path, direction) == "1", "An empty selection must not broadcast");
        matrix.CopyFields(a.Path, [b.Path], [direction, load]);
        ExpectInvalid(matrix, b.Path, load);
        Check(b.PostprocessJob!.LoadSet == "LOAD_B" && a.PostprocessJob!.RebarDiameterMm == 32, "Failed validation leaked into workspace");
        matrix.SetValue(b.Path, load, "LOAD_B");
        Check(matrix.TryBuild(out changed, out _) && changed.Count == 2 && changed[a.Path].RebarDiameterMm == 28.5
            && changed[b.Path].RebarDiameterMm == 32 && changed[b.Path].LoadDirection == "3"
            && changed[b.Path].LongitudinalMaterial == "" && changed[a.Path].LongitudinalMaterial == "未列入扫描目录的材料",
            "Only explicitly selected fields should be applied to target");
        changed[a.Path].LoadDirection = "1+3";
        Check(matrix.GetValue(a.Path, direction) == "3" && matrix.GetOriginalValue(a.Path, direction) == "1"
            && changed[b.Path].LoadDirection == "3", "Returned values share mutable job drafts");
        matrix.CopyFields(a.Path, [b.Path], [diameter]);
        ExpectInvalid(matrix, b.Path, diameter);
        matrix.SetValue(b.Path, diameter, "32.000");
        matrix.SetValue(a.Path, mode, "manual");
        matrix.SetValue(a.Path, frames, "3-1，0,3");
        matrix.SetValue(a.Path, pre, "3");
        Check(matrix.TryBuild(out _, out _), "Last canonical frame of two steps or reversed range was rejected");
        matrix.SetValue(a.Path, frames, "+０_３,１-０");
        Check(matrix.TryBuild(out _, out _), "The editor must accept the same Unicode decimal indices as the Python worker");
        matrix.SetValue(a.Path, frames, "0-4");
        ExpectInvalid(matrix, a.Path, frames);
        matrix.SetValue(a.Path, frames, "0,1");
        matrix.SetValue(a.Path, pre, "4");
        ExpectInvalid(matrix, a.Path, pre);
        matrix.SetValue(a.Path, pre, "-1");
        foreach (var input in new[] { "0-2-3", ",,", "-1", "2..5", "1e2", "0-999999999999" })
        {
            matrix.SetValue(a.Path, frames, input);
            ExpectInvalid(matrix, a.Path, frames);
        }
        matrix.SetValue(a.Path, frames, "2");
        matrix.SetValue(a.Path, step, "Load");
        Check(matrix.TryBuild(out _, out _), "First frame of newly selected start step was incorrectly excluded");
        matrix.SetValue(a.Path, nameof(OdbPostprocessJobDraft.EndStep), "Gravity");
        ExpectInvalid(matrix, a.Path, nameof(OdbPostprocessJobDraft.EndStep));
        matrix.SetValue(a.Path, nameof(OdbPostprocessJobDraft.EndStep), "Load");
        foreach (var input in new[] { "", "3,5", "NaN", "Infinity", "0", "101" })
        {
            matrix.SetValue(a.Path, diameter, input);
            ExpectInvalid(matrix, a.Path, diameter);
        }
        matrix.SetValue(a.Path, diameter, "30");
        matrix.SetValue(a.Path, pre, "1.5");
        ExpectInvalid(matrix, a.Path, pre);
        var old = new OdbPostprocessParameterComparison([legacy, b]);
        old.SetValue(legacy.Path, mode, "manual");
        old.SetValue(legacy.Path, frames, "0-120");
        Check(old.TryBuild(out changed, out _) && changed.Count == 1 && changed.ContainsKey(legacy.Path),
            "A legacy scan without a frame catalog cannot prove upper bounds");
        old.SetValue(legacy.Path, nameof(OdbPostprocessJobDraft.ReinforcementMode), "required");
        ExpectInvalid(old, legacy.Path, nameof(OdbPostprocessJobDraft.RebarSet));
        ExpectInvalid(old, legacy.Path, material);
        Check(legacy.PostprocessJob!.ReinforcementMode == "none" && legacy.HasPostprocessConfiguration,
            "Discarding the comparison must preserve the original job configuration");
        var incomplete = b.PostprocessJob.Clone();
        incomplete.LoadSet = "OldSet";
        b.UpdatePostprocessJob(incomplete);
        Check(!b.HasPostprocessConfiguration, "Model with an obsolete set should require correction");
        var partialEdit = new OdbPostprocessParameterComparison([a, b]);
        partialEdit.SetValue(b.Path, load, "Temporary");
        partialEdit.SetValue(b.Path, load, "OldSet");
        partialEdit.SetValue(b.Path, diameter, "32.00000");
        Check(partialEdit.TryBuild(out changed, out _) && changed.Count == 0,
            "Cancelled edits or numerically equivalent input must not validate or modify an unrelated model");
        partialEdit.SetValue(a.Path, diameter, "29.1");
        Check(partialEdit.TryBuild(out changed, out _) && changed.Count == 1 && changed.ContainsKey(a.Path)
            && !b.HasPostprocessConfiguration && b.PostprocessJob!.LoadSet == "OldSet",
            "An unchanged model's existing error must not block valid edits to another model");
        partialEdit.SetValue(b.Path, direction, "3");
        ExpectInvalid(partialEdit, b.Path, load);
        Console.WriteLine($"{checks} multi-model parameter comparison checks passed");
    }
}
