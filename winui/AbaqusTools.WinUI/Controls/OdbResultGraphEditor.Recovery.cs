using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Controls;

public sealed partial class OdbResultGraphEditor
{
    private readonly OdbResultGraphDraftStore _recoveryStore = new(Path.Combine(
        WorkbenchProfile.Current.StateDirectory, "result-graph-draft.json"));
    private OdbResultGraphDraft? _recoveryDraft;
    private string? _recoveryError;
    private bool _checkpointPaused;
    private bool RecoveryPending => _recoveryDraft is not null || _recoveryError is not null;

    private void InitializeDraftRecovery()
    {
        try { _recoveryDraft = _recoveryStore.Load(); }
        catch (Exception error) { _recoveryError = error.Message; }
        App.Current.Session.RegisterCheckpoint("result-graph", SaveDraftCheckpointAsync);
    }

    private Task SaveDraftCheckpointAsync()
    {
        // Keep an unresolved/corrupt draft intact, even while loading the formal graph.
        if (_checkpointPaused || RecoveryPending || _savedSnapshot is null) return Task.CompletedTask;
        // A session-end checkpoint can precede the selected node's TextChanged event.
        var nodes = _nodes.Select(CloneNode).ToArray();
        if (nodes.FirstOrDefault(n => n.NodeId == _selectedNodeId) is { } selected)
            ReadInspectorInto(selected);
        var directory = OutputDirectoryTextBox.Text;
        if (!_savedSnapshot.HasEdits(directory, nodes)) return _recoveryStore.SaveAsync(null);
        return _recoveryStore.SaveAsync(new OdbResultGraphDraft
        {
            Context = App.Current.ControlPlane.DescriptorPath,
            Basis = _savedSnapshot,
            Edited = new OdbResultGraphSnapshot
            {
                SchemaVersion = _savedSnapshot.SchemaVersion, Revision = _savedSnapshot.Revision,
                OutputDirectory = directory, Nodes = nodes,
            },
            SelectedNodeId = _selectedNodeId,
            Targets = _targets.Order(StringComparer.Ordinal).ToList(),
        });
    }

    private void RefreshDraftRecovery()
    {
        GraphRecoveryInfoBar.IsOpen = RecoveryPending;
        var matching = _recoveryDraft is not null && _savedSnapshot is not null
            && _recoveryDraft.Matches(App.Current.ControlPlane.DescriptorPath, _savedSnapshot);
        var available = !_requestBusy && !_executionBusy;
        RestoreGraphDraftButton.IsEnabled = available && matching;
        PreviewGraphDraftButton.IsEnabled = available && _recoveryDraft is not null;
        PreserveGraphDraftButton.IsEnabled = available && RecoveryPending;
        GraphRecoveryInfoBar.Message = _recoveryError is not null
            ? "草稿无法读取，原文件已保留：" + _recoveryStore.FilePath + "\n" + _recoveryError
            : _savedSnapshot is null ? "发现上次未保存的编辑。读取正式结果图后可核对并恢复。"
            : matching ? "发现上次未保存的编辑，可恢复继续修改；恢复不会提交正式图或启动合并。"
            : "正式结果图或工作环境已变化，暂不自动恢复。可查看并复制草稿内容，或保留副本后使用当前正式图。";
    }

    private async void OnRestoreGraphDraftClicked(object sender, RoutedEventArgs args)
    {
        if (_requestBusy || _executionBusy || _recoveryDraft is null || _savedSnapshot is null) return;
        var draft = _recoveryDraft;
        if (!draft.Matches(App.Current.ControlPlane.DescriptorPath, _savedSnapshot)) return;
        // Keep the formal base revision. The ordinary save API still checks for later conflicts.
        _nodes.Clear();
        _nodes.AddRange(draft.Edited.Nodes.Select(CloneNode));
        _targets.Clear();
        _targets.UnionWith(draft.Targets);
        _selectedNodeId = draft.SelectedNodeId;
        _updatingFields = true;
        OutputDirectoryTextBox.Text = draft.Edited.OutputDirectory;
        _updatingFields = false;
        _recoveryDraft = null;
        HasUnsavedChanges = true;
        PopulateInspector();
        RenderGraph();
        RefreshInteractionState();
        GraphChanged?.Invoke(this, EventArgs.Empty);
        try
        {
            await SaveDraftCheckpointAsync();
            ShowState("已恢复未保存编辑", "请核对后点击保存；正式图仍保持原版本。", InfoBarSeverity.Informational);
        }
        catch (Exception error) { ShowError("编辑已恢复，但草稿检查点未能更新", error); }
    }

    private async void OnPreviewGraphDraftClicked(object sender, RoutedEventArgs args)
    {
        if (_requestBusy || _executionBusy || _recoveryDraft is not { } draft) return;
        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            var names = draft.Edited.Nodes.ToDictionary(n => n.NodeId, DisplayName, StringComparer.Ordinal);
            var text = $"草稿基于版本 {draft.Basis.Revision} · {draft.Edited.Nodes.Count} 个节点\n输出目录：{draft.Edited.OutputDirectory}\n\n"
                + string.Join("\n\n", draft.Edited.Nodes.Select(node =>
                    $"{DisplayName(node)}\n前置：{names.GetValueOrDefault(node.ParentNodeId, "无")}\nODB：{node.OdbPath}\nINP：{node.InpPath}"));
            await new ContentDialog
            {
                XamlRoot = XamlRoot, Title = "上次未保存的结果图", CloseButtonText = "关闭",
                Content = new ScrollViewer { MaxHeight = 440, Content = new TextBlock
                    { Text = text, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true, MaxWidth = 560 } },
            }.ShowAsync();
        }
        catch (Exception error) { ShowError("无法查看草稿", error); }
        finally { _requestBusy = false; RefreshInteractionState(); }
    }

    private async void OnPreserveGraphDraftClicked(object sender, RoutedEventArgs args)
    {
        if (_requestBusy || _executionBusy || !RecoveryPending) return;
        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            var archive = await _recoveryStore.ArchiveAndClearAsync();
            _recoveryDraft = null;
            _recoveryError = null;
            ShowState("继续使用正式结果图", archive is null ? "没有待恢复草稿。" : "草稿副本保留在：" + archive, InfoBarSeverity.Informational);
        }
        catch (Exception error) { ShowError("草稿副本未能保存，原件未清除", error); }
        finally { _requestBusy = false; RefreshInteractionState(); }
    }
}
