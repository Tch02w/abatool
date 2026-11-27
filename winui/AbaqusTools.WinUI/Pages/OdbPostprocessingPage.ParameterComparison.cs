using AbaqusTools.WinUI.Controls;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private async Task ShowParameterComparisonAsync(OdbFileRow[] selected)
    {
        var root = _lastDiscoveryRoot;
        if (root is null) return;
        // A reopened selection can arrive in another order. Saved cells use these stable indices.
        var rows = selected.OrderBy(row => row.Path, StringComparer.OrdinalIgnoreCase).ToArray();
        var inputs = rows.Select(row => (Job: row.PostprocessJob!, Scan: row.ScanDetails!)).ToArray();
        var target = OdbPostprocessDraftRecovery.Fingerprint(rows.Select(row => PathKey(row.Path)).ToArray());
        var editor = new OdbParameterComparisonEditor(rows);
        var panel = new StackPanel { Spacing = 8 };
        panel.Children.Add(editor);
        var scroll = new ScrollViewer { Content = panel, HorizontalContentAlignment = HorizontalAlignment.Stretch,
            HorizontalScrollMode = ScrollMode.Disabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Padding = new(0, 0, 8, 0) };
        var dialogRoot = XamlRoot;
        var dialog = new ContentDialog { XamlRoot = dialogRoot, Title = $"对照提取参数 · {rows.Length} 个模型",
            Content = scroll, PrimaryButtonText = "保存到工作区", CloseButtonText = "取消" };
        void FitDialog()
        {
            var width = Math.Clamp(dialogRoot.Size.Width - 40, 280, 960);
            dialog.Resources["ContentDialogMinWidth"] = width;
            dialog.Resources["ContentDialogMaxWidth"] = width;
            scroll.MaxHeight = Math.Max(130, dialogRoot.Size.Height - 180);
            editor.FitHeight(dialogRoot.Size.Height);
        }
        void OnRootChanged(XamlRoot sender, XamlRootChangedEventArgs args) => FitDialog();
        FitDialog();
        var changedCount = 0;
        dialog.PrimaryButtonClick += (_, args) =>
        {
            args.Cancel = true;
            try
            {
                if (!editor.Session.TryBuild(out var changes, out var issues))
                {
                    editor.FocusCell(issues[0].Path, issues[0].FieldKey);
                    editor.ShowError(string.Join(Environment.NewLine, issues.Take(5).Select(issue =>
                        $"{Path.GetRelativePath(root, issue.Path)} · {issue.Message}"))
                        + (issues.Count > 5 ? $"{Environment.NewLine}另有 {issues.Count - 5} 项待修改。" : ""));
                    return;
                }
                if (!string.Equals(root, _lastDiscoveryRoot, StringComparison.OrdinalIgnoreCase)
                    || rows.Where((row, i) => !ReferenceEquals(FindRow(row.Path), row)
                        || !ReferenceEquals(row.PostprocessJob, inputs[i].Job)
                        || !ReferenceEquals(row.ScanDetails, inputs[i].Scan)).Any())
                    throw new InvalidOperationException("所选模型的结构或参数已经变化。请取消后重新打开对照。");
                if (changes.Count > 0)
                {
                    if (!TrySaveWorkspaceChange(workspace =>
                    {
                        foreach (var saved in workspace.Rows)
                            if (changes.TryGetValue(saved.Path, out var value)) saved.Draft = value;
                    }, editor.ShowError))
                    {
                        return;
                    }
                    foreach (var row in rows)
                        if (changes.TryGetValue(row.Path, out var value)) row.UpdatePostprocessJob(value);
                    changedCount = changes.Count;
                }
                args.Cancel = false;
            }
            catch (Exception error) { editor.ShowError(error.Message); }
        };

        var basis = inputs.Select(item => new { item.Job, item.Scan.Steps, item.Scan.AssemblyNodeSets,
            item.Scan.AssemblyElementSets, FrameCounts = item.Scan.StructureCatalog.Steps
                .Select(step => new { step.Name, Count = step.Frames.Count }).ToArray() }).ToArray();
        dialogRoot.Changed += OnRootChanged;
        try
        {
            if (await ShowRecoverableDialogAsync(dialog, panel, OdbPostprocessDraftRecovery.ComparisonDialogKind, target, basis, [],
                    editor.CaptureDraft, editor.RestoreDraft) == ContentDialogResult.Primary)
            {
                var draftSaved = await CompleteDialogDraftAsync(OdbPostprocessDraftRecovery.ComparisonDialogKind, target);
                RefreshInteractionState();
                if (changedCount > 0 && draftSaved) ShowSuccess($"已保存 {changedCount} 个模型的提取参数。", "提取参数已保存");
            }
        }
        finally { dialogRoot.Changed -= OnRootChanged; }
    }
}
