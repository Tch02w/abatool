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
    private CancellationTokenSource? _batchCancellation;
    private bool _batchBusy;
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
        if (_operationBusy || _previewBusy || _batchBusy || !batch.Valid || batch.Plans.Count == 0)
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
        IReadOnlyList<RestartResultPlan> plans = _batchPlan?.Plans
            ?? (_materializationPlan is null ? [] : new[] { _materializationPlan });
        if (plans.Count == 0 || _batchBusy)
        {
            return;
        }
        _batchBusy = true;
        _cancelRequested = false;
        using var cancellation = new CancellationTokenSource();
        _batchCancellation = cancellation;
        _batchResults.Clear();
        BatchResultsList.Visibility = Visibility.Visible;
        _lastResultPath = string.Empty;
        OpenResultButton.IsEnabled = false;
        RevealResultButton.IsEnabled = false;
        _batchTotalSteps = plans.Sum(plan => plan.Steps.Count);
        _batchCompletedSteps = 0;
        MergeLogExpander.IsExpanded = true;
        MergeOperationLogTextBox.Text = string.Empty;
        RefreshInteractionState();
        try
        {
            // Recheck document revision before starting any operations in this batch.
            if (_batchPlan is { } savedBatch)
            {
                var current = await App.Current.ControlPlane.GetOdbResultGraphAsync(cancellation.Token);
                if (current.Revision != savedBatch.GraphRevision || ResultGraphEditor.HasUnsavedChanges)
                {
                    _planReady = false;
                    throw new InvalidOperationException("结果图已修改，请重新检查并生成计划。");
                }
            }
            await OdbResultBatchRunner.RunAsync(plans, ExecuteResultStepAsync, ApplyBatchProgress, cancellation.Token);
            MergeProgressBar.Value = 100;
            ShowPlanState("完整结果生成完成", $"已生成 {_batchResults.Count} 个目标结果，可在下方或左侧浏览器中选择。", InfoBarSeverity.Success);
        }
        catch (OperationCanceledException)
        {
            ShowPlanState("整批合并已停止", $"已完成 {_batchResults.Count} 个目标；后续步骤未启动，已验证的结果保留。", InfoBarSeverity.Warning);
        }
        catch (Exception exception)
        {
            var message = exception is ControlPlaneException control ? control.ToDisplayMessage() : exception.Message;
            ShowPlanState("整批合并未完成", message + $" 已保留 {_batchResults.Count} 个完整目标结果。", InfoBarSeverity.Error);
        }
        finally
        {
            _batchCancellation = null;
            _batchBusy = false;
            _previewBusy = false;
            _cancelRequested = false;
            SetOperationBusy(false);
            UpdateExplorer();
            App.Current.MainWindow.ReportPageStatus($"整批合并结束 · 完整结果 {_batchResults.Count}/{plans.Count}");
        }
    }

    private async Task<string> ExecuteResultStepAsync(RestartResultStep step, string original, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        ApplyMaterializationStep(step, original);
        var preview = await PreviewDraftAsync(cancellationToken);
        if (!preview.Valid)
        {
            throw new InvalidOperationException(preview.ValidationMessage);
        }
        ApplyDraftPreview(preview);
        cancellationToken.ThrowIfCancellationRequested();
        SetOperationBusy(true);
        // Do not abandon a POST after it may have created an operation: obtain its ID,
        // cancel it if requested meanwhile, and observe cleanup before releasing the UI.
        var initial = await App.Current.ControlPlane.StartOdbMergeAsync(
            original, step.RestartOdb, preview.NormalizedOutputOdb,
            IncludeHistoryCheckBox.IsChecked is true, CompressResultCheckBox.IsChecked is true,
            CopyOriginalCheckBox.IsChecked is true, "auto_number", Guid.NewGuid());
        if (cancellationToken.IsCancellationRequested)
        {
            try
            {
                await App.Current.ControlPlane.CancelOdbMergeOperationAsync(initial.OperationId);
            }
            catch (Exception exception)
            {
                ShowPlanState("正在等待当前步骤结束", exception.Message + "；后续步骤保持停止。", InfoBarSeverity.Warning);
            }
        }
        var completed = await ObserveOperationAsync(initial, applyCompletion: false);
        cancellationToken.ThrowIfCancellationRequested();
        if (completed.Status == "cancelled")
        {
            throw new OperationCanceledException("当前合并步骤已取消。");
        }
        if (!completed.IsSuccessful || completed.Result is null)
        {
            throw new InvalidOperationException(completed.Error?.Message ?? $"阶段 {step.JobName} 未成功完成。");
        }
        return completed.Result.OutputOdb;
    }

    private void ApplyBatchProgress(OdbBatchProgress progress)
    {
        _batchCompletedSteps = progress.CompletedSteps;
        _batchTotalSteps = progress.TotalSteps;
        MergeProgressBar.IsIndeterminate = false;
        MergeProgressBar.Value = progress.TotalSteps == 0 ? 0 : 100.0 * progress.CompletedSteps / progress.TotalSteps;
        MergePlanSummaryText.Text = $"目标 {progress.CompletedTargets}/{progress.TotalTargets} · 阶段 {progress.CompletedSteps}/{progress.TotalSteps}"
            + (progress.Reused ? " · 已复用本批次验证结果" : string.Empty);
        if (progress.Result is { } result)
        {
            _batchResults.Add(result);
            BatchResultsList.SelectedItem = result;
            UpdateExplorer();
        }
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
