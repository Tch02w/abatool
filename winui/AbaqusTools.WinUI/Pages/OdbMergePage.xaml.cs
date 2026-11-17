using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.System;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbMergePage : Page, IWorkbenchExplorerPage
{
    private bool _previewBusy;
    private bool _operationBusy;
    private bool _cancelRequested;
    private bool _planReady;
    private bool _recoveryAttempted;
    private string? _activeOperationId;
    private long _lastOperationVersion = -1;
    private string _lastResultPath = string.Empty;
    private RestartResultPlan? _materializationPlan;
    private readonly OdbMergeExplorerAdapter _explorerAdapter;

    public OdbMergePage()
    {
        InitializeComponent();
        NavigationCacheMode = Microsoft.UI.Xaml.Navigation.NavigationCacheMode.Required;
        _explorerAdapter = new OdbMergeExplorerAdapter(SelectExplorerItem);
        ResultGraphEditor.PlansRequested += OnGraphPlansRequested;
        ResultGraphEditor.GraphChanged += OnResultGraphChanged;
        BatchResultsList.ItemsSource = _batchResults;
        Loaded += OnPageLoaded;
        UpdateExplorer();
        RefreshInteractionState();
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _explorerAdapter;

    public void LoadMaterializationPlan(RestartResultPlan plan)
    {
        if (_batchBusy || _operationBusy || _previewBusy)
        {
            ShowPlanState("合并正在运行", "当前操作结束后再加载其他计划。", InfoBarSeverity.Warning);
            return;
        }
        MergeModeComboBox.SelectedIndex = 0;
        _batchPlan = null;
        _materializationPlan = plan;
        MaterializationPlanCard.Visibility = Visibility.Visible;
        MaterializationTargetText.Text =
            $"目标节点：{plan.TargetJobName} · 仅沿该节点的唯一祖先路径生成完整 ODB；兄弟分支不会参与。";
        MaterializationAncestryList.ItemsSource = plan.Ancestry;
        MaterializationStepsList.ItemsSource = plan.Steps;
        if (plan.Steps.FirstOrDefault() is { } first)
        {
            ApplyMaterializationStep(first, first.OriginalOdb);
        }
        _planReady = plan.Valid;
        MergePlanSummaryText.Text = plan.Valid
            ? $"完整结果计划包含 {plan.Steps.Count} 个顺序合并步骤。"
            : string.Join(Environment.NewLine, plan.Issues);
        ShowPlanState(
            plan.Valid ? "完整结果计划已加载" : "完整结果计划不可执行",
            plan.Valid
                ? "计算依赖图与结果生成链保持分离；执行时将逐步验证并发布结果。"
                : MergePlanSummaryText.Text,
            plan.Valid ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
        UpdateExplorer();
        RefreshInteractionState();
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        if (_recoveryAttempted || _batchBusy || _operationBusy || _previewBusy)
        {
            return;
        }

        _recoveryAttempted = true;
        _previewBusy = true;
        RefreshInteractionState();
        try
        {
            var batches = await App.Current.ControlPlane.ListOdbResultBatchesAsync();
            var batch = batches.Operations.FirstOrDefault(b => b.IsActive || b.CanResume);
            if (batch is not null)
            {
                await ObserveBatchAsync(batch);
                return;
            }
            var active = await App.Current.ControlPlane.ListOdbMergeOperationsAsync(
                activeOnly: true);
            var snapshot = active.Operations.FirstOrDefault();
            if (snapshot is not null && _materializationPlan is null && _batchPlan is null)
            {
                MergeModeComboBox.SelectedIndex = 1;
                RestoreDraft(snapshot.Request);
                SetOperationBusy(true);
                await ObserveOperationAsync(snapshot);
                return;
            }

            var history = await App.Current.ControlPlane.ListOdbMergeOperationsAsync();
            var latest = history.Operations.FirstOrDefault(item => item.Request?.ClientRequestId.StartsWith("batch:", StringComparison.Ordinal) != true);
            var latestBatch = batches.Operations.FirstOrDefault();
            if (latestBatch is not null && _materializationPlan is null && _batchPlan is null
                && (latest is null || latestBatch.CreatedAt >= latest.CreatedAt))
            {
                ApplyBatchSnapshot(latestBatch);
                return;
            }
            if (latest is not null && _materializationPlan is null && _batchPlan is null)
            {
                MergeModeComboBox.SelectedIndex = 1;
                RestoreDraft(latest.Request);
                if (!latest.IsTerminal)
                {
                    // Another client can admit work between the two list calls.
                    SetOperationBusy(true);
                    await ObserveOperationAsync(latest);
                    return;
                }
                ApplyOperationSnapshot(latest);
                ApplyCompletedOperation(latest);
                _activeOperationId = null;
            }
        }
        catch (OperationCanceledException)
        {
            // Normal during application shutdown.
        }
        catch (ControlPlaneException exception)
        {
            _recoveryAttempted = false;
            ShowPlanState("无法恢复合并状态", exception.ToDisplayMessage(), InfoBarSeverity.Warning);
        }
        catch (Exception exception)
        {
            ShowPlanState("无法恢复合并状态", exception.Message, InfoBarSeverity.Warning);
        }
        finally
        {
            _previewBusy = false;
            RefreshInteractionState();
        }
    }

    private async void OnChooseOriginalClicked(object sender, RoutedEventArgs e)
    {
        var path = await PickOdbAsync("选择原始 ODB");
        if (path is null)
        {
            return;
        }

        OriginalOdbTextBox.Text = path;
        DetachMaterializationPlan();
        ApplySuggestedOutput(force: false);
        InvalidatePlan();
        UpdateExplorer();
    }

    private async void OnChooseRestartClicked(object sender, RoutedEventArgs e)
    {
        var path = await PickOdbAsync("选择重启动 ODB");
        if (path is null)
        {
            return;
        }

        RestartOdbTextBox.Text = path;
        DetachMaterializationPlan();
        ApplySuggestedOutput(force: false);
        InvalidatePlan();
        UpdateExplorer();
    }

    private async void OnChooseOutputClicked(object sender, RoutedEventArgs e)
    {
        var folder = await PickOutputFolderAsync();
        if (folder is null)
        {
            return;
        }

        OutputOdbTextBox.Text = Path.Combine(folder, $"{SuggestedResultStem()}_joined.odb");
        InvalidatePlan();
        UpdateExplorer();
    }

    private void OnResultNamingChanged(object sender, SelectionChangedEventArgs e)
    {
        if (IsLoaded && ResultNamingComboBox.SelectedIndex != 2)
        {
            ApplySuggestedOutput(force: true);
            InvalidatePlan();
        }
    }

    private async void OnPreviewClicked(object sender, RoutedEventArgs e)
    {
        if (_previewBusy || _operationBusy)
        {
            return;
        }

        _previewBusy = true;
        RefreshInteractionState();
        MergePlanInfoBar.IsOpen = false;
        MergeProgressBar.IsIndeterminate = true;
        App.Current.MainWindow.ReportPageStatus("正在检查 ODB 安全合并计划…");
        try
        {
            var preview = await PreviewDraftAsync();
            ApplyDraftPreview(preview);
        }
        catch (ControlPlaneException exception)
        {
            ShowPlanError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowPlanError(exception.Message);
        }
        finally
        {
            _previewBusy = false;
            MergeProgressBar.IsIndeterminate = false;
            RefreshInteractionState();
        }
    }

    private async void OnExecuteClicked(object sender, RoutedEventArgs e)
    {
        if (_previewBusy || _operationBusy)
        {
            return;
        }

        if (MergeModeComboBox.SelectedIndex == 0)
        {
            ShowPlanState("在结果图中选择目标", "勾选节点后生成计划，或批量生成所有末端节点的计划。", InfoBarSeverity.Informational);
            return;
        }

        if (_batchPlan is not null || _materializationPlan is not null)
        {
            await ExecuteMaterializationPlanAsync();
            return;
        }

        _previewBusy = true;
        RefreshInteractionState();
        try
        {
            var preview = await PreviewDraftAsync();
            ApplyDraftPreview(preview);
            if (!preview.Valid)
            {
                return;
            }

            if (preview.WillOverwrite && !await ConfirmOverwriteAsync(preview.NormalizedOutputOdb))
            {
                App.Current.MainWindow.ReportPageStatus("已取消覆盖现有 ODB");
                return;
            }

            _previewBusy = false;
            SetOperationBusy(true);
            MergeOperationLogTextBox.Text = string.Empty;
            MergeLogExpander.IsExpanded = true;
            MergePlanInfoBar.IsOpen = false;
            App.Current.MainWindow.ReportPageStatus("正在创建 ODB 合并操作…");
            var initial = await App.Current.ControlPlane.StartOdbMergeAsync(
                OriginalOdbTextBox.Text,
                RestartOdbTextBox.Text,
                preview.NormalizedOutputOdb,
                IncludeHistoryCheckBox.IsChecked is true,
                CompressResultCheckBox.IsChecked is true,
                CopyOriginalCheckBox.IsChecked is true,
                ConflictPolicyComboBox.SelectedIndex == 1 ? "overwrite" : "auto_number",
                Guid.NewGuid());
            await ObserveOperationAsync(initial);
        }
        catch (OperationCanceledException)
        {
            if (!_cancelRequested)
            {
                ShowPlanState("ODB 合并已停止", "操作在完成前被取消。", InfoBarSeverity.Warning);
            }
        }
        catch (ControlPlaneException exception)
        {
            ShowPlanState("ODB 合并失败", exception.ToDisplayMessage(), InfoBarSeverity.Error);
            App.Current.MainWindow.ReportPageStatus("ODB 合并失败");
        }
        catch (Exception exception)
        {
            ShowPlanState("ODB 合并失败", exception.Message, InfoBarSeverity.Error);
            App.Current.MainWindow.ReportPageStatus("ODB 合并失败");
        }
        finally
        {
            _previewBusy = false;
            if (_operationBusy)
            {
                SetOperationBusy(false);
            }
            RefreshInteractionState();
        }
    }

    private async void OnStopClicked(object sender, RoutedEventArgs e)
    {
        if (_batchBusy)
        {
            _cancelRequested = true;
            MergePlanSummaryText.Text = "正在停止整批合并，后续步骤不会启动。";
            RefreshInteractionState();
            if (!string.IsNullOrWhiteSpace(_activeBatchId))
            {
                try
                {
                    await App.Current.ControlPlane.CancelOdbResultBatchAsync(_activeBatchId);
                }
                catch (Exception exception)
                {
                    ShowPlanState("停止请求未确认", exception.Message + "；尚不能确认后台已停止，请重新读取任务。", InfoBarSeverity.Warning);
                }
            }
            return;
        }
        var operationId = _activeOperationId;
        if (!_operationBusy || string.IsNullOrWhiteSpace(operationId) || _cancelRequested)
        {
            return;
        }

        _cancelRequested = true;
        MergePlanSummaryText.Text = "正在请求停止；当前进程结束后将清理隔离工作区。";
        App.Current.MainWindow.ReportPageStatus("正在停止 ODB 合并…");
        RefreshInteractionState();
        try
        {
            var snapshot = await App.Current.ControlPlane.CancelOdbMergeOperationAsync(operationId);
            ApplyOperationSnapshot(snapshot);
        }
        catch (OperationCanceledException)
        {
            // Normal during application shutdown.
        }
        catch (ControlPlaneException exception)
        {
            _cancelRequested = false;
            ShowPlanState("无法停止 ODB 合并", exception.ToDisplayMessage(), InfoBarSeverity.Error);
            RefreshInteractionState();
        }
        catch (Exception exception)
        {
            _cancelRequested = false;
            ShowPlanState("无法停止 ODB 合并", exception.Message, InfoBarSeverity.Error);
            RefreshInteractionState();
        }
    }

    private async Task<OdbMergeOperationSnapshot> ObserveOperationAsync(
        OdbMergeOperationSnapshot initial,
        bool applyCompletion = true)
    {
        _activeOperationId = initial.OperationId;
        _lastOperationVersion = -1;
        _cancelRequested = string.Equals(initial.Status, "cancelling", StringComparison.Ordinal);
        ApplyOperationSnapshot(initial);
        try
        {
            var progress = new Progress<OdbMergeOperationSnapshot>(ApplyOperationSnapshot);
            var final = await App.Current.ControlPlane.PollOdbMergeUntilTerminalAsync(
                initial,
                progress);
            ApplyOperationSnapshot(final);
            if (applyCompletion)
            {
                ApplyCompletedOperation(final);
            }
            return final;
        }
        finally
        {
            _activeOperationId = null;
            _lastOperationVersion = -1;
            if (!_batchBusy)
            {
                _cancelRequested = false;
            }
            SetOperationBusy(false);
        }
    }

    private Task ExecuteMaterializationPlanAsync() => ExecuteResultBatchAsync();

    private void ApplyMaterializationStep(RestartResultStep step, string originalOdb)
    {
        OriginalOdbTextBox.Text = originalOdb;
        RestartOdbTextBox.Text = step.RestartOdb;
        OutputOdbTextBox.Text = step.OutputOdb;
        ResultNamingComboBox.SelectedIndex = 2;
        _planReady = true;
    }

    private void OnClearMaterializationClicked(object sender, RoutedEventArgs e)
    {
        DetachMaterializationPlan();
        InvalidatePlan();
        MergePlanSummaryText.Text = "已清除当前执行计划。";
    }

    private void DetachMaterializationPlan()
    {
        _displayedBatchId = null;
        _resumableBatchId = null;
        _batchPlan = null;
        _materializationPlan = null;
        MaterializationPlanCard.Visibility = Visibility.Collapsed;
        MaterializationAncestryList.ItemsSource = null;
        MaterializationStepsList.ItemsSource = null;
        UpdateExplorer();
    }

    private void UpdateExplorer()
    {
        if (MergeModeComboBox.SelectedIndex == 0 && ResultGraphEditor.Snapshot is not null)
        {
            UpdateResultGraphExplorer();
            return;
        }
        var sources = new List<ExplorerItem>();
        if (!string.IsNullOrWhiteSpace(OriginalOdbTextBox.Text))
        {
            sources.Add(MergeFileItem("original", "原始 ODB", OriginalOdbTextBox.Text));
        }
        if (!string.IsNullOrWhiteSpace(RestartOdbTextBox.Text))
        {
            sources.Add(MergeFileItem("restart", "重启动 ODB", RestartOdbTextBox.Text));
        }
        var steps = _materializationPlan?.Steps.Select(step => new ExplorerItem
        {
            StableId = $"merge:step:{step.Index}:{step.JobId}",
            Kind = ExplorerItemKind.MergeResult,
            Title = step.Title,
            Subtitle = Path.GetFileName(step.OutputOdb),
            Path = step.OutputOdb,
            Badge = step.Status,
            IconGlyph = "\uE895",
        }).ToArray() ?? [];
        var results = string.IsNullOrWhiteSpace(_lastResultPath)
            ? Array.Empty<ExplorerItem>()
            : [MergeFileItem("result", "已验证完整结果", _lastResultPath, true)];
        _explorerAdapter.Update(
            _materializationPlan is null
                ? "手工单次合并"
                : $"目标：{_materializationPlan.TargetJobName}",
            $"源 {sources.Count} · 步骤 {steps.Length} · 结果 {results.Length}",
            [
                WorkbenchExplorerAdapterBase.Group("merge:sources", "源 ODB", sources, sources.Count.ToString()),
                WorkbenchExplorerAdapterBase.Group("merge:steps", "生成步骤", steps, steps.Length.ToString()),
                WorkbenchExplorerAdapterBase.Group("merge:results", "完整结果", results, results.Length.ToString()),
            ]);
    }

    private static ExplorerItem MergeFileItem(string id, string title, string path, bool result = false) =>
        new()
        {
            StableId = $"merge:{id}:{path.ToUpperInvariant()}",
            Kind = result ? ExplorerItemKind.MergeResult : ExplorerItemKind.MergeSource,
            Title = title,
            Subtitle = Path.GetFileName(path),
            Path = path,
            Status = File.Exists(path) ? "可用" : "等待生成",
            IconGlyph = result ? "\uE73E" : "\uE8B7",
        };

    private void SelectExplorerItem(ExplorerItem item)
    {
        if (item.Kind == ExplorerItemKind.MergeSource && !string.IsNullOrWhiteSpace(item.EntityId))
        {
            ResultGraphEditor.SelectNode(item.EntityId);
        }
        if (item.Kind == ExplorerItemKind.MergeResult && File.Exists(item.Path))
        {
            _lastResultPath = item.Path;
            OpenResultButton.IsEnabled = true;
            RevealResultButton.IsEnabled = true;
        }
    }

    private void ApplyOperationSnapshot(OdbMergeOperationSnapshot snapshot)
    {
        if (_activeOperationId is not null
            && !string.Equals(_activeOperationId, snapshot.OperationId, StringComparison.Ordinal))
        {
            return;
        }
        if (snapshot.Version < _lastOperationVersion)
        {
            return;
        }

        _lastOperationVersion = snapshot.Version;
        _activeOperationId ??= snapshot.OperationId;
        MergeProgressBar.IsIndeterminate = !_batchBusy && snapshot.Status is "queued" or "starting"
            && snapshot.Progress.Percent == 0;
        MergeProgressBar.Value = _batchBusy && _batchTotalSteps > 0
            ? 100.0 * (_batchCompletedSteps + snapshot.Progress.Percent / 100.0) / _batchTotalSteps
            : snapshot.Progress.Percent;
        MergePlanSummaryText.Text = string.IsNullOrWhiteSpace(snapshot.Progress.Phase)
            ? $"ODB 合并状态：{snapshot.Status}"
            : snapshot.Progress.Phase;
        MergeOperationLogTextBox.Text = string.Join(Environment.NewLine, snapshot.Logs);
        if (!string.IsNullOrWhiteSpace(snapshot.PersistenceWarning))
            ShowPlanState("任务记录保存失败", snapshot.PersistenceWarning, InfoBarSeverity.Warning);
        if (snapshot.Logs.Count > 0)
        {
            MergeLogExpander.IsExpanded = true;
        }
        App.Current.MainWindow.ReportPageStatus(
            $"ODB 合并 {snapshot.Progress.Percent}% · {MergePlanSummaryText.Text}");
    }

    private void ApplyCompletedOperation(OdbMergeOperationSnapshot snapshot)
    {
        MergeProgressBar.IsIndeterminate = false;
        if (snapshot.IsSuccessful && snapshot.Result is not null)
        {
            _lastResultPath = snapshot.Result.OutputOdb;
            MergeResultText.Text =
                $"结果：{snapshot.Result.OutputOdb}\n"
                + $"原始备份：{snapshot.Result.OriginalBackup}\n"
                + $"重启动备份：{snapshot.Result.RestartBackup}";
            if (!string.IsNullOrWhiteSpace(snapshot.Result.ValidationReport))
                MergeResultText.Text += $"\n校验回执：{snapshot.Result.ValidationReport}";
            OpenResultButton.IsEnabled = File.Exists(_lastResultPath);
            RevealResultButton.IsEnabled = Directory.Exists(Path.GetDirectoryName(_lastResultPath));
            UpdateExplorer();
            ShowPlanState(
                string.IsNullOrWhiteSpace(snapshot.PersistenceWarning) ? "ODB 合并完成" : "结果已保存，任务记录待核对",
                snapshot.CompletionMessage,
                string.IsNullOrWhiteSpace(snapshot.PersistenceWarning) ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
            App.Current.MainWindow.ReportPageStatus(snapshot.CompletionMessage);
            return;
        }

        _lastResultPath = string.Empty;
        MergeResultText.Text = string.Empty;
        OpenResultButton.IsEnabled = false;
        RevealResultButton.IsEnabled = false;
        UpdateExplorer();

        if (string.Equals(snapshot.Status, "cancelled", StringComparison.Ordinal))
        {
            ShowPlanState(
                "ODB 合并已停止",
                snapshot.CompletionMessage,
                InfoBarSeverity.Warning);
            App.Current.MainWindow.ReportPageStatus("ODB 合并已停止");
            return;
        }

        var title = snapshot.IsInterrupted ? "合并中断，待核对" : "ODB 合并失败";
        ShowPlanState(title, snapshot.CompletionMessage,
            snapshot.IsInterrupted ? InfoBarSeverity.Warning : InfoBarSeverity.Error);
        App.Current.MainWindow.ReportPageStatus(title);
    }

    private async void OnOpenResultClicked(object sender, RoutedEventArgs e)
    {
        try
        {
            if (!File.Exists(_lastResultPath))
            {
                throw new FileNotFoundException("合并结果已不存在。", _lastResultPath);
            }
            var file = await StorageFile.GetFileFromPathAsync(_lastResultPath);
            await Launcher.LaunchFileAsync(file);
        }
        catch (Exception exception)
        {
            ShowPlanState("无法打开合并结果", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async void OnRevealResultClicked(object sender, RoutedEventArgs e)
    {
        try
        {
            var directory = Path.GetDirectoryName(_lastResultPath);
            if (string.IsNullOrWhiteSpace(directory) || !Directory.Exists(directory))
            {
                throw new DirectoryNotFoundException("合并结果目录已不存在。");
            }
            var folder = await StorageFolder.GetFolderFromPathAsync(directory);
            await Launcher.LaunchFolderAsync(folder);
        }
        catch (Exception exception)
        {
            ShowPlanState("无法打开结果目录", exception.Message, InfoBarSeverity.Error);
        }
    }

    private async Task<OdbMergeDraftPreviewResponse> PreviewDraftAsync(CancellationToken cancellationToken = default)
    {
        return await App.Current.ControlPlane.PreviewOdbMergeDraftAsync(
            OriginalOdbTextBox.Text,
            RestartOdbTextBox.Text,
            OutputOdbTextBox.Text,
            IncludeHistoryCheckBox.IsChecked is true,
            CompressResultCheckBox.IsChecked is true,
            CopyOriginalCheckBox.IsChecked is true,
            _batchBusy ? "auto_number" : ConflictPolicyComboBox.SelectedIndex == 1 ? "overwrite" : "auto_number",
            cancellationToken);
    }

    private void ApplyDraftPreview(OdbMergeDraftPreviewResponse preview)
    {
        _planReady = preview.Valid;
        if (!preview.Valid)
        {
            ShowPlanState("合并计划需要修正", preview.ValidationMessage, InfoBarSeverity.Warning);
            MergePlanSummaryText.Text = preview.ValidationMessage;
            MergePlanExpander.IsExpanded = false;
            MergeProgressBar.Value = 0;
            App.Current.MainWindow.ReportPageStatus("ODB 合并计划需要修正");
            RefreshInteractionState();
            return;
        }

        OutputOdbTextBox.Text = preview.NormalizedOutputOdb;
        MergePlanSummaryText.Text = preview.AutoNumbered
            ? "目标文件已存在，已自动选择不冲突的新编号。"
            : preview.WillOverwrite
                ? "目标文件已存在；执行前必须再次确认覆盖。"
                : "路径保护和结果命名已通过检查。";
        MergePlanDetailsText.Text =
            $"输出：{preview.NormalizedOutputOdb}\n"
            + $"原始备份：{preview.OriginalBackup}\n"
            + $"重启动备份：{preview.RestartBackup}\n"
            + $"源文件总计：{FormatBytes(preview.SourceTotalBytes)}\n"
            + $"命令：{preview.Command}";
        MergeStepsList.ItemsSource = preview.ExecutionSteps;
        MergePlanExpander.IsExpanded = true;
        if (!_batchBusy)
        {
            MergeProgressBar.Value = 25;
        }
        ShowPlanState("安全合并计划已生成", preview.ValidationMessage, InfoBarSeverity.Success);
        App.Current.MainWindow.ReportPageStatus("ODB 合并计划检查通过");
        RefreshInteractionState();
    }

    private async Task<bool> ConfirmOverwriteAsync(string outputPath)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "覆盖已有合并结果？",
            Content = $"现有文件将被替换：\n{outputPath}\n\n两个源 ODB 仍保持不变。",
            PrimaryButtonText = "确认覆盖",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    private void RestoreDraft(OdbMergeOperationRequest? request)
    {
        if (request is null)
        {
            return;
        }
        OriginalOdbTextBox.Text = request.OriginalOdb;
        RestartOdbTextBox.Text = request.RestartOdb;
        OutputOdbTextBox.Text = request.OutputOdb;
        IncludeHistoryCheckBox.IsChecked = request.IncludeHistory;
        CompressResultCheckBox.IsChecked = request.CompressResult;
        CopyOriginalCheckBox.IsChecked = request.CopyOriginal;
        ConflictPolicyComboBox.SelectedIndex = string.Equals(
            request.ConflictPolicy,
            "overwrite",
            StringComparison.Ordinal) ? 1 : 0;
        ResultNamingComboBox.SelectedIndex = 2;
        UpdateExplorer();
    }

    private void ApplySuggestedOutput(bool force)
    {
        if (!force && !string.IsNullOrWhiteSpace(OutputOdbTextBox.Text))
        {
            return;
        }

        var source = ResultNamingComboBox.SelectedIndex == 1
            ? OriginalOdbTextBox.Text.Trim()
            : RestartOdbTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(source))
        {
            source = !string.IsNullOrWhiteSpace(RestartOdbTextBox.Text)
                ? RestartOdbTextBox.Text.Trim()
                : OriginalOdbTextBox.Text.Trim();
        }
        if (string.IsNullOrWhiteSpace(source))
        {
            return;
        }

        var directory = !string.IsNullOrWhiteSpace(OutputOdbTextBox.Text)
            ? Path.GetDirectoryName(OutputOdbTextBox.Text.Trim())
            : Path.GetDirectoryName(source);
        if (!string.IsNullOrWhiteSpace(directory))
        {
            OutputOdbTextBox.Text = Path.Combine(directory, $"{SuggestedResultStem()}_joined.odb");
        }
    }

    private string SuggestedResultStem()
    {
        var path = ResultNamingComboBox.SelectedIndex == 1
            ? OriginalOdbTextBox.Text.Trim()
            : RestartOdbTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(path))
        {
            path = OriginalOdbTextBox.Text.Trim();
        }

        var stem = string.IsNullOrWhiteSpace(path)
            ? "joined"
            : Path.GetFileNameWithoutExtension(path);
        return stem.EndsWith("_original", StringComparison.OrdinalIgnoreCase)
            ? stem[..^"_original".Length]
            : stem;
    }

    private void InvalidatePlan()
    {
        _planReady = false;
        MergePlanInfoBar.IsOpen = false;
        MergePlanSummaryText.Text = "参数已更改，请重新检查合并计划。";
        RefreshInteractionState();
    }

    private void SetOperationBusy(bool busy)
    {
        _operationBusy = busy;
        if (!busy)
        {
            MergeProgressBar.IsIndeterminate = false;
        }
        RefreshInteractionState();
    }

    private void RefreshInteractionState()
    {
        ResumeBatchButton.Visibility = _resumableBatchId is null ? Visibility.Collapsed : Visibility.Visible;
        ResumeBatchButton.IsEnabled = !_batchBusy && !_operationBusy && !_previewBusy;
        RefreshBatchButton.IsEnabled = !_batchBusy && !_operationBusy && !_previewBusy;
        var editingEnabled = !_previewBusy && !_operationBusy && !_batchBusy;
        MergeModeComboBox.IsEnabled = editingEnabled;
        ResultGraphEditor.SetExecutionBusy(!editingEnabled);
        ClearMaterializationButton.IsEnabled = editingEnabled;
        ChooseOriginalButton.IsEnabled = editingEnabled;
        ChooseRestartButton.IsEnabled = editingEnabled;
        ChooseOutputButton.IsEnabled = editingEnabled;
        OutputOdbTextBox.IsEnabled = editingEnabled;
        IncludeHistoryCheckBox.IsEnabled = editingEnabled;
        CompressResultCheckBox.IsEnabled = editingEnabled;
        CopyOriginalCheckBox.IsEnabled = editingEnabled;
        ResultNamingComboBox.IsEnabled = editingEnabled;
        ConflictPolicyComboBox.IsEnabled = editingEnabled;
        PreviewButton.IsEnabled = editingEnabled && MergeModeComboBox.SelectedIndex == 1;
        ExecuteButton.IsEnabled = editingEnabled && _planReady
            && (MergeModeComboBox.SelectedIndex == 1 || _materializationPlan is not null || _batchPlan is not null);
        StopButton.IsEnabled = (_operationBusy || _batchBusy) && !_cancelRequested;
    }

    private void ShowPlanError(string message)
    {
        _planReady = false;
        ShowPlanState("合并计划检查失败", message, InfoBarSeverity.Error);
        MergePlanSummaryText.Text = message;
        MergeProgressBar.Value = 0;
        App.Current.MainWindow.ReportPageStatus("ODB 合并计划检查失败");
    }

    private void ShowPlanState(string title, string message, InfoBarSeverity severity)
    {
        MergePlanInfoBar.Title = title;
        MergePlanInfoBar.Message = message;
        MergePlanInfoBar.Severity = severity;
        MergePlanInfoBar.IsOpen = true;
    }

    private static string FormatBytes(long bytes)
    {
        if (bytes >= 1024L * 1024 * 1024)
        {
            return $"{bytes / (1024d * 1024 * 1024):0.##} GB";
        }
        if (bytes >= 1024L * 1024)
        {
            return $"{bytes / (1024d * 1024):0.##} MB";
        }
        return $"{Math.Max(0, bytes) / 1024d:0.##} KB";
    }

    private static async Task<string?> PickOdbAsync(string commitButtonText)
    {
        var picker = new FileOpenPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = commitButtonText,
        };
        picker.FileTypeFilter.Add(".odb");
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        return (await picker.PickSingleFileAsync())?.Path;
    }

    private static async Task<string?> PickOutputFolderAsync()
    {
        var picker = new FolderPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = "选择 ODB 合并结果目录",
        };
        picker.FileTypeFilter.Add("*");
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        return (await picker.PickSingleFolderAsync())?.Path;
    }
}
