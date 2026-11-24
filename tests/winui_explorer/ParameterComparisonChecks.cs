using System.Text.Json;
using AbaqusTools.WinUI.Controls;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Windows.Foundation;

namespace ExplorerControlChecks;

public sealed partial class TestApp
{
    private async Task CheckParameterComparisonAsync()
    {
        var first = CreateComparisonSample("ModelA", "Load-U", true);
        var second = CreateComparisonSample("ModelB", "Lateral", false);
        await CheckTwoScansAsync([first, second]);
        await CheckComparisonPagingAsync();
        if (_comparisonScans is not null)
        {
            var scans = JsonSerializer.Deserialize<List<OdbPostprocessScanItem>>(File.ReadAllText(_comparisonScans))
                ?? throw new InvalidDataException("工程扫描报告为空。");
            await CheckTwoScansAsync(scans);
        }
    }

    private async Task CheckComparisonPagingAsync()
    {
        var rows = Enumerable.Range(0, 64).Select(i =>
        {
            var scan = CreateComparisonSample($"Case-{i:D2}", "Load-U", true);
            var row = new OdbFileRow(new OdbDiscoveryItem { Path = scan.Path, Name = scan.Name });
            row.ApplyPostprocessScan(scan);
            return row;
        }).ToArray();
        var editor = new OdbParameterComparisonEditor(rows) { Width = 850 };
        _root.Children.Add(editor);
        await LayoutComparisonAsync();
        int Cells() => Descendants<Button>(editor).Count(
            button => AutomationProperties.GetAutomationId(button).StartsWith("ComparisonCell_", StringComparison.Ordinal));
        var fields = OdbPostprocessParameterComparison.Fields.Count;
        Check(Cells() == 3 * fields, "64-model comparison realizes three model columns on a wide viewport");
        await ClickComparisonAsync(editor, "ComparisonNext");
        var source = Named<ComboBox>(editor, "ComparisonSource");
        Check(source.SelectedIndex == 3 && Named<Button>(editor, "ComparisonCell_3_StartStep").ActualWidth > 0,
            "moving a page also changes the editing source to its first model");
        editor.Width = 540;
        await LayoutComparisonAsync();
        Check(Cells() == 2 * fields && source.SelectedIndex == 3, "resizing retains the selected model with two realized columns");
        await ClickComparisonAsync(editor, "ComparisonCell_3_LoadDirection");
        Named<ComboBox>(editor, "ComparisonValue_LoadDirection").SelectedItem = "1+3";
        Named<CheckBox>(editor, "ComparisonField_LoadDirection").IsChecked = true;
        await ClickComparisonAsync(editor, "ComparisonApplyFields");
        Check(editor.Session.TryBuild(out var changed, out _) && changed.Count == 64,
            "explicitly checked fields reach selected models on other pages");
        source.SelectedIndex = 63;
        await LayoutComparisonAsync();
        Check(Cells() == 2 * fields && !Named<Button>(editor, "ComparisonNext").IsEnabled,
            "jumping to the last model realizes its page without extra columns");
        await ClickComparisonAsync(editor, "ComparisonResetValue");
        Check(editor.Session.GetValue(rows[63].Path, "LoadDirection") == "3" &&
              editor.Session.TryBuild(out var remaining, out _) && remaining.Count == 63 &&
              !Named<Button>(editor, "ComparisonResetValue").IsEnabled,
            "restoring one cell preserves changes made to the other 63 models");
        _root.Children.Clear();
        await LayoutComparisonAsync();
    }

    private OdbPostprocessScanItem CreateComparisonSample(string name, string step, bool reinforced)
    {
        // Only metadata is needed for this test; no ODB is created.
        var path = Path.Combine(Path.GetDirectoryName(_receipt)!, name + ".odb");
        return new OdbPostprocessScanItem
        {
            Name = name, Path = path, Steps = ["Initial", step], AssemblyNodeSets = ["LOAD"],
            AssemblyElementSets = reinforced ? ["PILE", "PILE_CON", "SOIL", "REBAR"] : ["PILE", "PILE_CON", "SOIL", "STEEL"],
            Suggested = new OdbPostprocessJobDraft
            {
                Path = path, StartStep = step, EndStep = step, LoadDirection = reinforced ? "3" : "1",
                LoadSet = "LOAD", PileDisplaySet = "PILE", PileConcreteSet = "PILE_CON", SoilSet = "SOIL",
                PileSteelSet = reinforced ? "" : "STEEL", RebarSet = reinforced ? "REBAR" : "",
                RebarDiameterMm = reinforced ? 22 : 32, ReinforcementMode = reinforced ? "required" : "none"
            }
        };
    }

    private async Task CheckTwoScansAsync(IReadOnlyList<OdbPostprocessScanItem> scans)
    {
        if (scans.Count != 2) throw new InvalidDataException("此场景需要有纵筋和无纵筋两个不同模型。");
        var rows = scans.Select(scan =>
        {
            var row = new OdbFileRow(new OdbDiscoveryItem { Path = scan.Path, RelativePath = Path.GetFileName(scan.Path), Name = scan.Name });
            row.ApplyPostprocessScan(scan);
            if (string.IsNullOrEmpty(scan.Suggested.RebarSet))
            {
                var draft = row.PostprocessJob!.Clone();
                draft.PileType = "CFST";
                draft.ReinforcementMode = "none";
                draft.LongitudinalMaterial = "";
                row.UpdatePostprocessJob(draft);
            }
            return row;
        }).ToArray();
        var prefix = rows[0].Name + " / " + rows[1].Name + " · ";
        var paths = rows.Select(row => row.Path).ToArray();
        var original = rows.Select(row => JsonSerializer.Serialize(row.PostprocessJob)).ToArray();
        Check(rows.All(row => row.HasPostprocessConfiguration), prefix + "both original configurations are usable");
        Check(!scans[1].Steps.Contains(scans[0].Suggested.StartStep), prefix + "different analysis steps");
        _root.Children.Clear();
        _window!.AppWindow.Resize(new Windows.Graphics.SizeInt32(1200, 920));
        var editor = new OdbParameterComparisonEditor(rows) { Width = 850, RequestedTheme = ElementTheme.Light };
        _root.Children.Add(editor);
        await LayoutComparisonAsync();
        await CheckComparisonGeometryAsync(editor, prefix);
        await ClickComparisonAsync(editor, "ComparisonCell_0_RebarDiameterMm");
        var diameter = Named<WorkbenchNumberBox>(editor, "ComparisonValue_RebarDiameterMm");
        diameter.Text = "28";
        await LayoutComparisonAsync();
        Check(editor.Session.GetValue(paths[0], "RebarDiameterMm") == "28", prefix + "per-model numeric input writes to its own draft");
        await ClickComparisonAsync(editor, "ComparisonCell_1_FrameMode");
        Named<ComboBox>(editor, "ComparisonValue_FrameMode").SelectedIndex = 1;
        await LayoutComparisonAsync();
        Check(editor.Session.GetValue(paths[1], "FrameMode") == "all", prefix + "second model changes its own frame mode");
        Check(!Named<Button>(editor, "ComparisonApplyFields").IsEnabled, prefix + "broadcast requires explicit fields");
        await ClickComparisonAsync(editor, "ComparisonCell_0_StartStep");
        Named<CheckBox>(editor, "ComparisonField_StartStep").IsChecked = true;
        await ClickComparisonAsync(editor, "ComparisonApplyFields");
        Check(!editor.Session.TryBuild(out var none, out var invalid) && none.Count == 0
              && invalid.Any(issue => issue.Path == paths[1] && issue.FieldKey == "StartStep"),
            prefix + "copying an unavailable step identifies the target and blocks all writes");
        Check(rows.Select(row => JsonSerializer.Serialize(row.PostprocessJob)).SequenceEqual(original),
            prefix + "cancelling the pending changes leaves both originals untouched");
        _root.Children.Clear();
        var fresh = new OdbParameterComparisonEditor(rows) { Width = 540, RequestedTheme = ElementTheme.Dark };
        _root.Children.Add(fresh);
        await LayoutComparisonAsync();
        await CheckComparisonGeometryAsync(fresh, prefix);
        Check(fresh.CaptureDraft().Count == 0, prefix + "reopening after cancel starts with the saved values");
        await ClickComparisonAsync(fresh, "ComparisonCell_0_LoadDirection");
        Named<ComboBox>(fresh, "ComparisonValue_LoadDirection").SelectedItem = "1+3";
        Named<CheckBox>(fresh, "ComparisonField_LoadDirection").IsChecked = true;
        await ClickComparisonAsync(fresh, "ComparisonApplyFields");
        var capture = fresh.CaptureDraft();
        Check(capture.Count == 2 && fresh.Session.TryBuild(out var changes, out _) && changes.Count == 2,
            prefix + "explicit compatible field copied to the other model");
        var expander = Named<Expander>(fresh, "ComparisonChanges");
        Check(expander.IsExpanded && ((TextBox)expander.Content).Text.Contains(rows[1].RelativePath),
            prefix + "preview identifies the changed model");
        fresh.RestoreDraft(capture);
        Check(fresh.Session.TryBuild(out var confirmed, out var issues) && issues.Count == 0, prefix + "recovered differences validate");
        foreach (var row in rows)
        {
            var expected = row.PostprocessJob!.Clone();
            expected.LoadDirection = "1+3";
            Check(JsonSerializer.Serialize(confirmed[row.Path]) == JsonSerializer.Serialize(expected),
                prefix + "only the selected field changed on " + row.Name);
        }
        var store = new OdbPostprocessWorkspaceStore(Path.Combine(Path.GetDirectoryName(_receipt)!, "comparison-workspace"));
        var workspace = Path.GetDirectoryName(_receipt)!;
        store.Save(workspace, new() { Rows = rows.Select(row => new OdbPostprocessSavedRow
            { Path = row.Path, Group = row.ComparisonGroup, Draft = confirmed[row.Path] }).ToList() });
        var restored = store.Load(workspace)!.Rows;
        Check(rows.All(row => JsonSerializer.Serialize(restored.Single(item => item.Path == row.Path).Draft)
            == JsonSerializer.Serialize(confirmed[row.Path])), prefix + "production workspace round trip retains differences");
        _root.Children.Clear();
        await LayoutComparisonAsync();
    }

    private async Task CheckComparisonGeometryAsync(OdbParameterComparisonEditor editor, string prefix)
    {
        var a = Named<Button>(editor, "ComparisonCell_0_StartStep");
        var b = Named<Button>(editor, "ComparisonCell_1_StartStep");
        var lower = Named<Button>(editor, "ComparisonCell_1_EndStep");
        var origin = new Point(0, 0);
        var aPos = a.TransformToVisual(editor).TransformPoint(origin);
        var bPos = b.TransformToVisual(editor).TransformPoint(origin);
        var lowerPos = lower.TransformToVisual(editor).TransformPoint(origin);
        Check(a.ActualWidth > 60 && b.ActualWidth > 60 && Math.Abs(aPos.Y - bPos.Y) <= 1
              && aPos.X + a.ActualWidth <= bPos.X + 1 && Math.Abs(bPos.X - lowerPos.X) <= 1
              && bPos.X + b.ActualWidth <= editor.ActualWidth + 1,
            prefix + $"native cells align in {editor.ActualTheme} at {editor.ActualWidth:0} DIP");
        await DispatchAsync();
    }

    private async Task LayoutComparisonAsync()
    {
        await DispatchAsync();
        _root.UpdateLayout();
        await DispatchAsync();
    }

    private static T Named<T>(DependencyObject parent, string id) where T : FrameworkElement
        => Descendants<T>(parent).Single(element => AutomationProperties.GetAutomationId(element) == id);

    private async Task ClickComparisonAsync(OdbParameterComparisonEditor editor, string id)
    {
        var button = Named<Button>(editor, id);
        if (!button.IsEnabled) throw new InvalidOperationException(id + " is disabled");
        var peer = new ButtonAutomationPeer(button);
        ((IInvokeProvider)peer.GetPattern(PatternInterface.Invoke)).Invoke();
        await LayoutComparisonAsync();
    }
}
