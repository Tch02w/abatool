using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbMergePage
{
    private readonly ObservableCollection<OdbBatchTargetResult> _batchResults = [];
    private OdbResultBatchPlan? _batchPlan;
    private bool _batchBusy;
    private string? _activeBatchId;
    private string? _resumableBatchId;
    private string? _displayedBatchId;
    private int _batchTotalSteps;
    private int _batchCompletedSteps;

    private void OnMergeModeChanged(object sender, SelectionChangedEventArgs e)
    {
        // SelectionChanged can run while InitializeComponent is constructing later controls.
        if (ResultGraphEditor is null || ManualOdbCard is null || _explorerAdapter is null)
        {
            return;
        }
        var manual = MergeModeComboBox.SelectedIndex == 1;
        ResultGraphEditor.Visibility = manual ? Visibility.Collapsed : Visibility.Visible;
        ManualOdbCard.Visibility = manual ? Visibility.Visible : Visibility.Collapsed;
        ManualNamingPanel.Visibility = manual ? Visibility.Visible : Visibility.Collapsed;
        DetachMaterializationPlan();
        InvalidatePlan();
        UpdateExplorer();
    }

    private void OnResultGraphChanged(object? sender, EventArgs e)
    {
        if (!_batchBusy && _batchPlan is not null)
        {
            DetachMaterializationPlan();
            InvalidatePlan();
        }
        UpdateExplorer();
    }

    private void OnGraphPlansRequested(object? sender, OdbResultBatchPlan batch)
    {
        if (MergeModeComboBox.SelectedIndex != 0 || _operationBusy || _previewBusy || _batchBusy
            || !batch.Valid || batch.Plans.Count == 0)
        {
            return;
        }
        _materializationPlan = null;
        _batchPlan = batch;
        _planReady = true;
        MaterializationPlanCard.Visibility = Visibility.Visible;
        MaterializationTargetText.Text = $"{batch.Plans.Count} 个完整结果目标："
            + string.Join("、", batch.Plans.Select(plan => plan.TargetJobName));
        MaterializationAncestryList.ItemsSource = batch.Plans.Count == 1 ? batch.Plans[0].Ancestry : null;
        MaterializationStepsList.ItemsSource = batch.Plans.SelectMany(plan => plan.Steps).ToArray();
        MergePlanSummaryText.Text = $"已检查 {batch.Plans.Count} 个目标；点击执行合并开始整批生成。";
        ShowPlanState("链式合并计划已就绪", "每个目标仅包含其祖先路径；共享阶段在本批次内复用，源 ODB 保持只读。", InfoBarSeverity.Success);
        RefreshInteractionState();
        UpdateExplorer();
    }

    private async Task ExecuteResultBatchAsync()
    {
        if (_batchBusy) return;
        object source;
        if (_batchPlan is { } batch)
        {
            if (ResultGraphEditor.HasUnsavedChanges)
            {
                ShowPlanState("结果图已修改", "请重新检查并生成计划。", InfoBarSeverity.Warning);
                return;
            }
            source = new { kind = "graph", revision = batch.GraphRevision,
                targetNodeIds = batch.Plans.Select(p => p.TargetJobId).ToArray() };
        }
        else if (_materializationPlan is { } plan)
            source = new { kind = "restart", expectedPlan = plan };
        else return;
        _batchBusy = true;
        _cancelRequested = false;
        _resumableBatchId = null;
        RefreshInteractionState();
        try
        {
            var initial = await App.Current.ControlPlane.StartOdbResultBatchAsync(source,
                new OdbResultBatchOptions { IncludeHistory = IncludeHistoryCheckBox.IsChecked is true,
                    CompressResult = CompressResultCheckBox.IsChecked is true, CopyOriginal = CopyOriginalCheckBox.IsChecked is true },
                Guid.NewGuid());
            _activeBatchId = initial.OperationId;
            if (_cancelRequested) initial = await App.Current.ControlPlane.CancelOdbResultBatchAsync(initial.OperationId);
            await ObserveBatchAsync(initial);
        }
        catch (Exception exception)
        {
            // A lost POST response does not prove that no batch was created.
            _planReady = false;
            _recoveryAttempted = false;
            ShowPlanState("批量状态需要重新读取", exception.Message + "；请点击读取后台任务，确认后再开始新的批次。", InfoBarSeverity.Warning);
        }
        finally
        {
            _batchBusy = false;
            _cancelRequested = false;
            RefreshInteractionState();
        }
    }

    private async Task ObserveBatchAsync(OdbResultBatchSnapshot snapshot)
    {
        _activeBatchId = snapshot.OperationId;
        _batchBusy = snapshot.IsActive;
        try
        {
            ApplyBatchSnapshot(snapshot);
            while (snapshot.IsActive)
            {
                await Task.Delay(400);
                snapshot = await App.Current.ControlPlane.GetOdbResultBatchAsync(snapshot.OperationId);
                ApplyBatchSnapshot(snapshot);
            }
        }
        finally
        {
            _batchBusy = false;
            _activeBatchId = null;
            _cancelRequested = false;
            RefreshInteractionState();
        }
    }

    private void ApplyBatchSnapshot(OdbResultBatchSnapshot snapshot)
    {
        _resumableBatchId = snapshot.CanResume ? snapshot.OperationId : null;
        _batchTotalSteps = snapshot.TotalSteps;
        _batchCompletedSteps = snapshot.CompletedSteps;
        _planReady = false;
        if (_displayedBatchId != snapshot.OperationId)
        {
            _displayedBatchId = snapshot.OperationId;
            MaterializationPlanCard.Visibility = Visibility.Visible;
            MaterializationTargetText.Text = $"{snapshot.Plans.Count} 个完整结果目标：" + string.Join("、", snapshot.Plans.Select(p => p.TargetJobName));
            MaterializationStepsList.ItemsSource = snapshot.Plans.SelectMany(p => p.Steps).ToArray();
            IncludeHistoryCheckBox.IsChecked = snapshot.Options.IncludeHistory;
            CompressResultCheckBox.IsChecked = snapshot.Options.CompressResult;
            CopyOriginalCheckBox.IsChecked = snapshot.Options.CopyOriginal;
        }
        BatchResultsList.Visibility = Visibility.Visible;
        // Keep the selected result and avoid rebuilding the list on every poll.
        var results = snapshot.Results.Select(r => new OdbBatchTargetResult(r.TargetJobName, r.OutputOdb)).ToArray();
        if (!_batchResults.SequenceEqual(results))
        {
            var selected = BatchResultsList.SelectedItem as OdbBatchTargetResult;
            _batchResults.Clear();
            foreach (var result in results) _batchResults.Add(result);
            BatchResultsList.SelectedItem = _batchResults.FirstOrDefault(r => r == selected) ?? _batchResults.LastOrDefault();
        }
        if (_batchResults.Count == 0)
        {
            _lastResultPath = string.Empty;
            OpenResultButton.IsEnabled = RevealResultButton.IsEnabled = false;
            MergeResultText.Text = "当前批次尚无完成校验的目标结果。";
        }
        var childProgress = snapshot.CurrentOperation is { IsTerminal: false } child ? child.Progress.Percent / 100.0 : 0;
        MergeProgressBar.Value = 100.0 * (snapshot.CompletedSteps + childProgress) / snapshot.TotalSteps;
        MergePlanSummaryText.Text = $"目标 {snapshot.Results.Count}/{snapshot.Plans.Count} · 独立阶段 {snapshot.CompletedSteps}/{snapshot.TotalSteps}";
        MergeLogExpander.IsExpanded = true;
        var text = snapshot.CurrentOperation is { } current ? string.Join(Environment.NewLine, current.Logs) : snapshot.Phase;
        if (MergeOperationLogTextBox.SelectionLength == 0 && MergeOperationLogTextBox.Text != text)
            MergeOperationLogTextBox.Text = text;
        var severity = snapshot.Status == "succeeded" ? (snapshot.Warnings.Count > 0 ? InfoBarSeverity.Warning : InfoBarSeverity.Success)
            : snapshot.Status == "failed" ? InfoBarSeverity.Error
            : snapshot.IsActive ? InfoBarSeverity.Informational : InfoBarSeverity.Warning;
        var message = snapshot.Phase + (snapshot.Warnings.Count > 0 ? "；" + string.Join("；", snapshot.Warnings) : string.Empty);
        ShowPlanState(snapshot.IsActive ? "正在生成完整结果" : snapshot.CanResume ? "批量任务等待继续" : "批量任务已结束", message, severity);
        RefreshInteractionState();
        UpdateExplorer();
    }

    private async void OnResumeBatchClicked(object sender, RoutedEventArgs e)
    {
        if (_resumableBatchId is not { } id || _batchBusy) return;
        _displayedBatchId = null;
        _batchBusy = true;
        RefreshInteractionState();
        try { await ObserveBatchAsync(await App.Current.ControlPlane.ResumeOdbResultBatchAsync(id)); }
        catch (Exception exception) { ShowPlanState("未能继续批量任务", exception.Message, InfoBarSeverity.Warning); }
        finally { _batchBusy = false; RefreshInteractionState(); }
    }

    private void OnRefreshBatchClicked(object sender, RoutedEventArgs e)
    {
        if (_batchBusy || _operationBusy) return;
        _recoveryAttempted = false;
        _displayedBatchId = null;
        OnPageLoaded(sender, e);
    }

    private void OnBatchResultSelected(object sender, SelectionChangedEventArgs e)
    {
        if (BatchResultsList.SelectedItem is not OdbBatchTargetResult result)
        {
            return;
        }
        _lastResultPath = result.OutputOdb;
        MergeResultText.Text = $"{result.TargetJobName}：{result.OutputOdb}";
        OpenResultButton.IsEnabled = File.Exists(result.OutputOdb);
        RevealResultButton.IsEnabled = Directory.Exists(Path.GetDirectoryName(result.OutputOdb));
    }

    private void UpdateResultGraphExplorer()
    {
        var graph = ResultGraphEditor.Snapshot;
        if (graph is null) return;
        var nodes = graph.Nodes.Select(node => new ExplorerItem
        {
            StableId = $"merge:node:{node.NodeId}", EntityId = node.NodeId,
            Kind = ExplorerItemKind.MergeSource, Title = node.Name,
            Subtitle = Path.GetFileName(node.OdbPath), Path = node.OdbPath,
            Badge = string.IsNullOrWhiteSpace(node.OdbPath) ? "待配置" : "阶段 ODB",
            IconGlyph = "\uE8B7",
        });
        var plans = _batchPlan?.Plans ?? (_materializationPlan is null ? [] : new[] { _materializationPlan });
        var steps = plans.SelectMany(plan => plan.Steps).GroupBy(step => step.OutputOdb).Select(group => group.First())
            .Select(step => MergeFileItem($"step:{step.JobId}", step.Title, step.OutputOdb));
        var results = _batchResults.Select((result, index) => MergeFileItem($"batch:{index}", result.TargetJobName, result.OutputOdb, true));
        _explorerAdapter.Update("独立结果图 · 链式 / 批量合并", $"节点 {graph.Nodes.Count} · 完整结果 {_batchResults.Count}",
            [WorkbenchExplorerAdapterBase.Group("merge:sources", "阶段 ODB", nodes, graph.Nodes.Count.ToString()),
             WorkbenchExplorerAdapterBase.Group("merge:steps", "生成步骤", steps),
             WorkbenchExplorerAdapterBase.Group("merge:results", "完整结果", results, _batchResults.Count.ToString())]);
    }
}
