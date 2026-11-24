using AbaqusTools.WinUI.Services;
using AbaqusTools.WinUI.Models;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private readonly Dictionary<string, RecoveryDraftFile<OdbPostprocessRecoveryDraft>> _draftFiles = [];
    private RecoveryDraftFile<OdbPostprocessRecoveryDraft>? _draftFile;
    private OdbPostprocessRecoveryDraft? _pendingDraft;
    private string? _draftError;
    private string _workspaceBasis = OdbPostprocessDraftRecovery.Fingerprint<object?>(null);
    private OdbPostprocessOutputOptions _lastSavedOutput = new();
    private Dictionary<string, OdbDialogInputDraft> _dialogDrafts = [];
    private Action? _captureOpenDialog;
    private bool _draftActionBusy;
    private bool DraftPending => _pendingDraft is not null || _draftError is not null;

    private Dictionary<string, Control> OutputDraftFields() => new()
    {
        ["图像单位"] = ImageUnitComboBox, ["图像宽度"] = ImageWidthNumberBox, ["图像高度"] = ImageHeightNumberBox,
        ["并行进程"] = ParallelWorkersNumberBox, ["全部帧"] = FullTimehistoryCheckBox,
        ["纵筋方法"] = RebarMethodComboBox, ["预期纵筋数"] = ExpectedRebarCountNumberBox,
        ["GIF方式"] = AnimationTimingModeComboBox, ["GIF帧率"] = AnimationFpsNumberBox,
        ["GIF时长"] = AnimationDurationNumberBox, ["纵筋容差"] = RebarToleranceNumberBox,
        ["白底"] = WhiteBackgroundCheckBox, ["透明底"] = TransparentBackgroundCheckBox,
    };

    private static string ChoiceValue(object? item) => item is ComboBoxItem option
        ? option.Tag?.ToString() ?? option.Content?.ToString() ?? "" : item?.ToString() ?? "";

    private static Dictionary<string, string> CaptureInputs(Dictionary<string, Control> fields) => fields.ToDictionary(
        p => p.Key, p => p.Value switch
        {
            TextBox text => text.Text, NumberBox number => number.Text,
            ComboBox combo => ChoiceValue(combo.SelectedItem), CheckBox check => check.IsChecked == true ? "true" : "false",
            _ => throw new InvalidOperationException("未登记的草稿输入类型。"),
        });

    private static void RestoreInputs(Dictionary<string, Control> fields, IReadOnlyDictionary<string, string> values)
    {
        // Validate choices first so a changed option list does not partially apply a draft.
        foreach (var (key, control) in fields)
        {
            if (!values.TryGetValue(key, out var value)) throw new InvalidDataException($"草稿缺少“{key}”，未套用旧输入。");
            if (control is ComboBox combo && !combo.Items.Any(item => ChoiceValue(item) == value))
                throw new InvalidDataException($"{key}中的“{value}”已不在当前可选项中，草稿副本仍保留。");
            if (control is CheckBox && value is not ("true" or "false")) throw new InvalidDataException($"{key}的选择状态无效。");
        }
        foreach (var (key, control) in fields)
        {
            if (!values.TryGetValue(key, out var value)) continue;
            switch (control)
            {
                case TextBox text: text.Text = value; break;
                case NumberBox number:
                    number.Text = value;
                    if (number.Text != value && !(double.TryParse(value, out var expected) && double.IsFinite(expected)
                        && double.TryParse(number.Text, out var actual) && actual == expected))
                        throw new InvalidDataException($"“{key}”的原始填写无法直接放回数字框，请查看草稿或副本后重新填写；原文未清除。");
                    break;
                case ComboBox combo: combo.SelectedItem = combo.Items.First(item => ChoiceValue(item) == value); break;
                case CheckBox check: check.IsChecked = value == "true"; break;
            }
        }
    }

    private List<OdbDraftSource> CurrentDraftSources() => _odbItems.Select(row =>
        new OdbDraftSource(row.Path, row.SizeBytes, row.ModifiedAt.UtcDateTime.Ticks)).ToList();

    private OdbPostprocessWorkspace CaptureEditableWorkspace(OdbPostprocessOutputOptions output)
    {
        var selection = OdbList.SelectedItems.OfType<OdbFileRow>().ToHashSet();
        return new()
        {
            Output = output,
            GroupMemberOrder = _groupMemberOrder.ToDictionary(pair => pair.Key, pair => pair.Value.ToList(), StringComparer.OrdinalIgnoreCase),
            Rows = _odbItems.Select(row => new OdbPostprocessSavedRow { Path = row.Path, Group = row.ComparisonGroup,
                Selected = selection.Contains(row), Draft = row.PostprocessJob?.Clone() }).ToList(),
            Legends = _legendOverridesByGroup.ToDictionary(pair => pair.Key, pair => pair.Value.ToDictionary(), StringComparer.OrdinalIgnoreCase),
        };
    }

    private async Task LoadWorkspaceRecoveryAsync(string root, OdbPostprocessWorkspace? saved)
    {
        _workspaceBasis = OdbPostprocessDraftRecovery.Fingerprint(saved);
        _lastSavedOutput = saved?.Output ?? new();
        _dialogDrafts = [];
        _pendingDraft = null;
        _draftError = null;
        var key = OdbPostprocessDraftRecovery.RootKey(root);
        if (!_draftFiles.TryGetValue(key, out _draftFile))
        {
            _draftFile = new(Path.Combine(WorkbenchProfile.Current.StateDirectory,
                "postprocess-recovery", OdbPostprocessDraftRecovery.FileName(root)), draft => draft.Validate(), 8 * 1024 * 1024);
            _draftFiles[key] = _draftFile;
        }
        try { await _draftFile.PendingWrites; _pendingDraft = _draftFile.Load(); }
        catch (Exception error) { _draftError = error.Message; }
    }

    private Task SavePostprocessDraftAsync()
    {
        if (_draftFile is null || _lastDiscoveryRoot is null || _discoveryBusy || _postprocessRecoveryBusy
            || DraftPending || _draftActionBusy || _unreadableWorkspaces.Contains(PathKey(_lastDiscoveryRoot))) return Task.CompletedTask;
        _captureOpenDialog?.Invoke();
        var workspace = CaptureEditableWorkspace(_lastSavedOutput);
        var inputs = CaptureInputs(OutputDraftFields());
        if (_dialogDrafts.Count == 0 && _workspaceBasis == OdbPostprocessDraftRecovery.Fingerprint(workspace)
            && !OdbPostprocessDraftRecovery.OutputChanged(_lastSavedOutput, inputs)) return _draftFile.SaveAsync(null);
        return _draftFile.SaveAsync(new()
        {
            Root = _lastDiscoveryRoot, Basis = _workspaceBasis, Sources = CurrentDraftSources(),
            Workspace = workspace, OutputInputs = inputs, Dialogs = _dialogDrafts.ToDictionary(),
        });
    }

    private void RefreshDraftActions()
    {
        WorkspaceRecoveryInfoBar.IsOpen = DraftPending;
        var idle = !_draftActionBusy && !_discoveryBusy && !_postprocessBusy && !_compatibilityBusy && !UpgradeBlocksEditing;
        var matches = _pendingDraft is not null && _lastDiscoveryRoot is not null
            && _pendingDraft.Matches(_lastDiscoveryRoot, _workspaceBasis, CurrentDraftSources());
        RestoreWorkspaceDraftButton.IsEnabled = idle && matches && !_unreadableWorkspaces.Contains(PathKey(_lastDiscoveryRoot!));
        PreviewWorkspaceDraftButton.IsEnabled = idle && _pendingDraft is not null;
        PreserveWorkspaceDraftButton.IsEnabled = idle && DraftPending;
        WorkspaceRecoveryInfoBar.Message = _draftError is not null ? _draftError + "\n原件：" + _draftFile?.FilePath
            : matches ? "发现未保存的输出设置或弹窗填写。恢复后请核对；弹窗中的输入仍须点击其保存按钮才应用。"
            : "ODB文件或正式配置已变化，未套用旧草稿。可查看内容，或保留副本后使用当前配置。";
    }

    private async void OnRestoreWorkspaceDraftClicked(object sender, RoutedEventArgs args)
    {
        if (!RestoreWorkspaceDraftButton.IsEnabled || _pendingDraft is not { } draft || _draftFile is null) return;
        _draftActionBusy = true;
        RefreshInteractionState();
        try
        {
            await _draftFile.PreserveAsync();
            if (_lastDiscoveryRoot is null || !draft.Matches(_lastDiscoveryRoot, _workspaceBasis, CurrentDraftSources()))
                throw new InvalidDataException("工作区已变化，未套用旧草稿。");
            var restoredRows = OdbPostprocessDraftRecovery.PrepareRows(draft, _odbItems);
            var before = CaptureEditableWorkspace(_lastSavedOutput);
            var beforeInputs = CaptureInputs(OutputDraftFields());
            var beforeRows = _odbItems.ToArray();
            try { ApplyRecoveredWorkspace(draft.Workspace, draft.OutputInputs, restoredRows); }
            catch
            {
                ApplyRecoveredWorkspace(before, beforeInputs, beforeRows);
                throw;
            }
            _dialogDrafts = draft.Dialogs.ToDictionary();
            _pendingDraft = null;
            UpdateExplorer();
            ShowWarning("已恢复工作区编辑；请重新读取结构。打开原参数、图例或分组弹窗可恢复尚未确认的填写。", "恢复草稿已载入");
        }
        catch (Exception error) { ShowWarning(error.Message, "未完成草稿恢复，原件和副本保留"); }
        finally { _draftActionBusy = false; RefreshInteractionState(); }
    }

    private void ApplyRecoveredWorkspace(OdbPostprocessWorkspace workspace, IReadOnlyDictionary<string, string> inputs,
        IReadOnlyList<OdbFileRow> rows)
    {
        RestoreOutputOptions(workspace.Output);
        RestoreInputs(OutputDraftFields(), inputs);
        _groupMemberOrder.Clear();
        foreach (var pair in workspace.GroupMemberOrder) _groupMemberOrder[pair.Key] = pair.Value.ToList();
        _legendOverridesByGroup.Clear();
        foreach (var pair in workspace.Legends) _legendOverridesByGroup[pair.Key] = pair.Value.ToDictionary();
        var selected = workspace.Rows.Where(row => row.Selected).Select(row => PathKey(row.Path)).ToHashSet(StringComparer.OrdinalIgnoreCase);
        OdbList.SelectedItems.Clear();
        _odbItems.Clear(); _odbByPath.Clear();
        foreach (var row in rows)
        {
            _odbItems.Add(row); _odbByPath[PathKey(row.Path)] = row;
            if (selected.Contains(PathKey(row.Path))) OdbList.SelectedItems.Add(row);
        }
    }

    private async void OnPreserveWorkspaceDraftClicked(object sender, RoutedEventArgs args)
    {
        if (!PreserveWorkspaceDraftButton.IsEnabled || _draftFile is null) return;
        _draftActionBusy = true;
        RefreshInteractionState();
        try
        {
            var archive = await _draftFile.ArchiveAndClearAsync();
            _pendingDraft = null; _draftError = null;
            ShowWarning("继续使用当前配置。草稿副本：" + archive, "草稿已保留");
        }
        catch (Exception error) { ShowWarning(error.Message, "未能保留副本，原件未清除"); }
        finally { _draftActionBusy = false; RefreshInteractionState(); }
    }

    private async void OnPreviewWorkspaceDraftClicked(object sender, RoutedEventArgs args)
    {
        if (_pendingDraft is not { } draft || _draftActionBusy) return;
        _draftActionBusy = true;
        RefreshInteractionState();
        try
        {
            await ShowDraftTextAsync("上次后处理填写", "目录：" + draft.Root + "\n\n"
                + InputSummary(draft.OutputInputs) + "\n\n"
                + string.Join("\n", draft.Workspace.Rows.Select(row => row.Path + " · " + row.Group + (row.Selected ? " · 已选" : "")))
                + "\n\n" + string.Join("\n\n", draft.Dialogs.Select(p => p.Key + "\n" + InputSummary(p.Value.Inputs))));
        }
        catch (Exception error) { ShowWarning(error.Message, "无法查看草稿"); }
        finally { _draftActionBusy = false; RefreshInteractionState(); }
    }

    private static string InputSummary(IReadOnlyDictionary<string, string> values) => string.Join("\n", values.Select(p => p.Key + "：" + p.Value));
    private async Task ShowDraftTextAsync(string title, string text) => await new ContentDialog
    {
        XamlRoot = XamlRoot, Title = title, CloseButtonText = "关闭",
        Content = new ScrollViewer { MaxHeight = 440, Content = new TextBlock
            { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true, MaxWidth = 560 } },
    }.ShowAsync();
}
