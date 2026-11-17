using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Windows.Storage.Pickers;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class JobQueuePage : Page, IWorkbenchExplorerPage
{
    private readonly ObservableCollection<JobQueueItem> _candidates = [];
    private readonly ObservableCollection<JobQueueItem> _queueItems = [];
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _runtimeTimer;
    private readonly QueueExplorerAdapter _queueExplorerAdapter;
    private bool _busy;
    private bool _runtimeRefreshBusy;
    private int? _lastRuntimeParallel;
    private string? _lastRuntimePolicy;
    private string? _pendingFormalSelectionId;

    public JobQueuePage()
    {
        InitializeComponent();
        CandidateList.ItemsSource = _candidates;
        FormalQueueList.ItemsSource = _queueItems;
        _queueExplorerAdapter = new QueueExplorerAdapter(
            App.Current.ControlPlane,
            () => PickFolderAsync("选择队列工作目录"),
            ActivateExplorerItemAsync,
            SelectExplorerItem);
        _runtimeTimer = DispatcherQueue.CreateTimer();
        _runtimeTimer.Interval = TimeSpan.FromSeconds(1.5);
        _runtimeTimer.Tick += OnRuntimeTimerTick;
        App.Current.Session.Register(this, "job-queue",
            ["ExternalWorkDirTextBox", "RecursiveScanCheckBox", "SkipRestartNamesCheckBox", "SkipExistingResultsCheckBox",
             "ExistingResultPolicyComboBox", "ParallelLimitNumberBox"],
            () => WorkbenchSession.WaitForIdleAsync(() => _busy || _runtimeRefreshBusy, "队列修改"), _runtimeTimer.Stop, _runtimeTimer.Start);
        Loaded += OnPageLoaded;
        Unloaded += OnPageUnloaded;
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _queueExplorerAdapter;

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
        if (App.Current.Session.IsClosing) return;
        await RefreshRuntimeAsync(showError: false);
        _runtimeTimer.Start();
    }

    private void OnPageUnloaded(object sender, RoutedEventArgs e)
    {
        _runtimeTimer.Stop();
    }

    private async void OnRuntimeTimerTick(
        Microsoft.UI.Dispatching.DispatcherQueueTimer sender,
        object args)
    {
        if (App.Current.Session.IsClosing) return;
        await RefreshRuntimeAsync(showError: false);
    }

    private async void OnRefreshClicked(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true, "正在读取作业队列…");
        try
        {
            var snapshot = await App.Current.ControlPlane.GetJobQueuesAsync();
            ApplySnapshot(snapshot);
            ShowSuccess(
                "队列已恢复",
                $"读取 {snapshot.CandidateCount} 个候选和 {snapshot.QueueCount} 个正式作业。",
                $"队列已读取 · {snapshot.QueueCount} 个正式作业");
        }
        catch (ControlPlaneException exception)
        {
            ShowError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowError(exception.Message);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void OnAddCurrentInputClicked(object sender, RoutedEventArgs e)
    {
        var paths = await PickInpFilesAsync(multiple: false);
        if (paths.Count > 0)
        {
            await AddCandidatePathsAsync(paths);
        }
    }

    private async void OnAddCandidateFilesClicked(object sender, RoutedEventArgs e)
    {
        var paths = await PickInpFilesAsync(multiple: true);
        if (paths.Count > 0)
        {
            await AddCandidatePathsAsync(paths);
        }
    }

    private Task AddCandidatePathsAsync(IReadOnlyList<string> paths) =>
        RunMutationAsync(
            () => App.Current.ControlPlane.AddJobQueueCandidatesAsync(
                paths,
                SkipRestartNamesCheckBox.IsChecked is true,
                SkipExistingResultsCheckBox.IsChecked is true),
            "正在添加候选作业…");

    private async void OnScanCandidateFolderClicked(object sender, RoutedEventArgs e)
    {
        var root = await PickFolderAsync("选择 INP 扫描目录");
        if (root is null)
        {
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.ScanJobQueueCandidatesAsync(
                root,
                RecursiveScanCheckBox.IsChecked is true,
                SkipRestartNamesCheckBox.IsChecked is true,
                SkipExistingResultsCheckBox.IsChecked is true),
            "正在扫描 INP 文件…");
    }

    private async void OnChooseExternalWorkDirClicked(object sender, RoutedEventArgs e)
    {
        var root = await PickFolderAsync("选择外部作业工作目录");
        if (root is not null)
        {
            ExternalWorkDirTextBox.Text = root;
        }
    }

    private async void OnScanExternalJobsClicked(object sender, RoutedEventArgs e)
    {
        var root = ExternalWorkDirTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(root))
        {
            root = await PickFolderAsync("选择并扫描外部作业目录") ?? string.Empty;
            if (string.IsNullOrWhiteSpace(root))
            {
                return;
            }
            ExternalWorkDirTextBox.Text = root;
        }
        await ScanExternalJobsAsync(root);
    }

    private Task ScanExternalJobsAsync(string root) =>
        RunMutationAsync(
            () => App.Current.ControlPlane.ScanExternalJobsAsync(root),
            "正在检测本机运行的 Abaqus 作业…");

    private async void OnCandidateCheckClicked(object sender, RoutedEventArgs e)
    {
        if (sender is not CheckBox checkBox
            || checkBox.DataContext is not JobQueueItem item)
        {
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.SetJobQueueCandidateSelectionAsync(
                [item.ItemId],
                checkBox.IsChecked is true),
            "正在更新候选选择…",
            showSuccess: false);
    }

    private async void OnSelectAllCandidatesClicked(object sender, RoutedEventArgs e)
    {
        if (_candidates.Count == 0)
        {
            ShowNotice("没有候选作业", "请先添加或扫描 INP 文件。");
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.SetJobQueueCandidateSelectionAsync(
                _candidates.Select(item => item.ItemId).ToArray(),
                true),
            "正在全选候选作业…");
    }

    private async void OnInvertCandidatesClicked(object sender, RoutedEventArgs e)
    {
        await RunMutationAsync(
            () => App.Current.ControlPlane.InvertJobQueueCandidateSelectionAsync(),
            "正在反选候选作业…");
    }

    private async void OnRemoveCandidatesClicked(object sender, RoutedEventArgs e)
    {
        var selectedRows = CandidateList.SelectedItems.OfType<JobQueueItem>().ToArray();
        var targets = selectedRows.Length > 0
            ? selectedRows
            : _candidates.Where(item => item.Selected).ToArray();
        if (targets.Length == 0)
        {
            ShowNotice("没有选中候选", "请选择表格行或勾选要移除的候选作业。");
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.RemoveJobQueueCandidatesAsync(
                targets.Select(item => item.ItemId).ToArray()),
            "正在移除候选作业…");
    }

    private async void OnConfirmCandidatesClicked(object sender, RoutedEventArgs e)
    {
        var itemIds = _candidates
            .Where(item => item.Selected)
            .Select(item => item.ItemId)
            .ToArray();
        if (itemIds.Length == 0)
        {
            ShowNotice("没有勾选候选", "请先勾选通过检查的候选作业。");
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.ConfirmJobQueueCandidatesAsync(itemIds),
            "正在加入正式队列…");
    }

    private async void OnEditQueueItemClicked(object sender, RoutedEventArgs e)
    {
        await EditSelectedFormalItemAsync();
    }

    private async void OnStartQueueClicked(object sender, RoutedEventArgs e)
    {
        await StartQueueAsync();
    }

    public async Task StartQueueAsync()
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true, "正在启动本机队列…");
        try
        {
            var runtime = await App.Current.ControlPlane.StartLocalQueueAsync(
                Math.Max(1, NumberValue(ParallelLimitNumberBox)),
                ExistingResultPolicy());
            ApplyRuntime(runtime);
            ShowSuccess(
                "本机队列已启动",
                $"最大并行 {runtime.MaxParallel}；同名结果策略：{PolicyDisplay(runtime.ExistingResultPolicy)}。",
                "本机队列正在调度");
        }
        catch (ControlPlaneException exception)
        {
            ShowError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowError(exception.Message);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void OnStopQueueClicked(object sender, RoutedEventArgs e)
    {
        await StopQueueAsync();
    }

    public async Task StopQueueAsync()
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true, "正在停止后续调度…");
        try
        {
            var runtime = await App.Current.ControlPlane.StopLocalQueueAsync();
            ApplyRuntime(runtime);
            ShowSuccess(
                "已停止后续调度",
                "正在运行的作业会继续计算；尚未启动的作业保留在正式队列。",
                "本机队列已停止调度");
        }
        catch (ControlPlaneException exception)
        {
            ShowError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowError(exception.Message);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void OnTerminateQueueItemsClicked(object sender, RoutedEventArgs e)
    {
        var selected = RequireFormalSelection();
        if (selected is null
            || !await ConfirmAsync(
                "终止所选运行中作业？",
                "将向 Abaqus 发送 terminate，并等待 LCK 与求解进程退出后写回终止状态。"))
        {
            return;
        }

        SetBusy(true, "正在发送终止请求…");
        try
        {
            var runtime = await App.Current.ControlPlane.TerminateLocalQueueItemsAsync(
                selected.Select(item => item.ItemId).ToArray());
            ApplyRuntime(runtime);
            ShowSuccess(
                "终止请求已发送",
                "正在等待 Abaqus 完成安全终止。",
                "正在终止所选作业");
        }
        catch (ControlPlaneException exception)
        {
            ShowError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowError(exception.Message);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async void OnFormalQueueDoubleTapped(
        object sender,
        DoubleTappedRoutedEventArgs e)
    {
        await EditSelectedFormalItemAsync();
    }

    private async Task EditSelectedFormalItemAsync()
    {
        var selected = SelectedFormalItems();
        if (selected.Length != 1)
        {
            ShowNotice("请选择一个作业", "编辑操作一次只支持一个正式队列作业。");
            return;
        }

        var item = selected[0];
        var jobNameBox = new TextBox { Header = "作业名称", Text = item.JobName };
        var coresBox = new Controls.WorkbenchNumberBox
        {
            Header = "Core（0 表示未指定）",
            Minimum = 0,
            Maximum = 999,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline,
            Value = item.Cores,
        };
        var memoryBox = new TextBox
        {
            Header = "内存（例如 80%、4096MB、8GB）",
            Text = item.Memory,
        };
        var priorityBox = new Controls.WorkbenchNumberBox
        {
            Header = "优先级",
            Minimum = -10000,
            Maximum = 10000,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline,
            Value = item.Priority,
        };
        Controls.ParameterHelpButton.AddToHeader(coresBox, "cpu");
        Controls.ParameterHelpButton.AddToHeader(priorityBox, "queue-priority");
        var oldjobBox = new TextBox
        {
            Header = "Restart 前置 ODB",
            Text = item.OldjobPath,
            PlaceholderText = "普通作业留空",
        };
        var fortranBox = new TextBox
        {
            Header = "Fortran 用户子程序",
            Text = item.FortranPath,
            PlaceholderText = "可选",
        };
        var panel = new StackPanel { Spacing = 10, Width = 520 };
        panel.Children.Add(jobNameBox);
        panel.Children.Add(coresBox);
        panel.Children.Add(memoryBox);
        panel.Children.Add(priorityBox);
        panel.Children.Add(oldjobBox);
        panel.Children.Add(fortranBox);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"编辑 {item.JobName}",
            Content = panel,
            PrimaryButtonText = "保存",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Primary,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.UpdateJobQueueItemAsync(
                item.ItemId,
                candidate: false,
                jobNameBox.Text,
                NumberValue(coresBox),
                memoryBox.Text,
                NumberValue(priorityBox),
                oldjobBox.Text,
                fortranBox.Text),
            "正在保存作业设置…");
    }

    private async void OnHoldQueueItemsClicked(object sender, RoutedEventArgs e)
    {
        await SetSelectedHoldAsync(true);
    }

    private async void OnResumeQueueItemsClicked(object sender, RoutedEventArgs e)
    {
        await SetSelectedHoldAsync(false);
    }

    private async Task SetSelectedHoldAsync(bool held)
    {
        var selected = RequireFormalSelection();
        if (selected is null)
        {
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.SetJobQueueHoldAsync(
                selected.Select(item => item.ItemId).ToArray(),
                held),
            held ? "正在暂停调度…" : "正在恢复调度…");
    }

    private async void OnRequeueItemsClicked(object sender, RoutedEventArgs e)
    {
        var selected = RequireFormalSelection();
        if (selected is null)
        {
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.RequeueJobQueueItemsAsync(
                selected.Select(item => item.ItemId).ToArray()),
            "正在重新排队…");
    }

    private async void OnRemoveQueueItemsClicked(object sender, RoutedEventArgs e)
    {
        var selected = RequireFormalSelection();
        if (selected is null
            || !await ConfirmAsync(
                "移除正式队列作业？",
                $"将从队列记录中移除 {selected.Length} 个作业；不会删除 INP 或结果文件。"))
        {
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.RemoveJobQueueItemsAsync(
                selected.Select(item => item.ItemId).ToArray()),
            "正在移除正式队列作业…");
    }

    private async void OnClearFinishedClicked(object sender, RoutedEventArgs e)
    {
        if (!await ConfirmAsync(
                "清理完成记录？",
                "将移除已完成、失败、取消或终止的队列记录；不会删除结果文件。"))
        {
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.ClearFinishedJobQueueItemsAsync(),
            "正在清理完成记录…");
    }

    private async void OnMoveQueueItemUpClicked(object sender, RoutedEventArgs e)
    {
        await MoveSelectedAsync("up");
    }

    private async void OnMoveQueueItemDownClicked(object sender, RoutedEventArgs e)
    {
        await MoveSelectedAsync("down");
    }

    private async Task MoveSelectedAsync(string direction)
    {
        var selected = SelectedFormalItems();
        if (selected.Length != 1)
        {
            ShowNotice("请选择一个作业", "队列排序一次只支持一个作业。");
            return;
        }

        await RunMutationAsync(
            () => App.Current.ControlPlane.MoveJobQueueItemAsync(
                selected[0].ItemId,
                direction),
            "正在调整队列顺序…");
    }

    private async Task RunMutationAsync(
        Func<Task<JobQueueCommandResponse>> operation,
        string busyStatus,
        bool showSuccess = true)
    {
        if (_busy)
        {
            return;
        }

        SetBusy(true, busyStatus);
        QueueInfoBar.IsOpen = false;
        try
        {
            var result = await operation();
            ApplySnapshot(result.Snapshot);
            if (showSuccess)
            {
                ShowSuccess("队列已更新", result.Message, result.Message);
            }
        }
        catch (ControlPlaneException exception)
        {
            ShowError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowError(exception.Message);
        }
        finally
        {
            SetBusy(false);
        }
    }

    private async Task RefreshRuntimeAsync(bool showError)
    {
        if (_runtimeRefreshBusy || _busy)
        {
            return;
        }

        _runtimeRefreshBusy = true;
        try
        {
            var runtime = await App.Current.ControlPlane.GetLocalQueueRuntimeAsync();
            ApplyRuntime(runtime);
        }
        catch (ControlPlaneException exception)
        {
            if (showError)
            {
                ShowError(exception.ToDisplayMessage());
            }
        }
        catch (Exception exception)
        {
            if (showError)
            {
                ShowError(exception.Message);
            }
        }
        finally
        {
            _runtimeRefreshBusy = false;
        }
    }

    private void ApplyRuntime(LocalQueueRuntimeSnapshot runtime)
    {
        ApplySnapshot(runtime.Queue);
        var drafts = App.Current.Session.State.Pages.GetValueOrDefault("job-queue");
        // Runtime polling must not replace a setting the user is still editing.
        if (runtime.Active || (_lastRuntimeParallel is { } previousParallel
                ? ParallelLimitNumberBox.Text == previousParallel.ToString()
                : drafts?.ContainsKey("ParallelLimitNumberBox") != true))
            ParallelLimitNumberBox.Value = runtime.MaxParallel;
        var updatePolicy = runtime.Active || (_lastRuntimePolicy is { } previousPolicy
            ? ExistingResultPolicy() == previousPolicy
            : drafts?.ContainsKey("ExistingResultPolicyComboBox") != true);
        _lastRuntimeParallel = runtime.MaxParallel;
        _lastRuntimePolicy = runtime.ExistingResultPolicy;
        for (var index = 0; updatePolicy && index < ExistingResultPolicyComboBox.Items.Count; index++)
        {
            if (ExistingResultPolicyComboBox.Items[index] is ComboBoxItem item
                && string.Equals(
                    item.Tag?.ToString(),
                    runtime.ExistingResultPolicy,
                    StringComparison.Ordinal))
            {
                ExistingResultPolicyComboBox.SelectedIndex = index;
                break;
            }
        }
        StartQueueButton.IsEnabled = !runtime.Active;
        StopQueueButton.IsEnabled = runtime.Active;
        TerminateQueueItemsButton.IsEnabled = runtime.ActiveItemIds.Count > 0;
        ParallelLimitNumberBox.IsEnabled = !runtime.Active;
        ExistingResultPolicyComboBox.IsEnabled = !runtime.Active;
        if (runtime.Active)
        {
            App.Current.MainWindow.ReportPageStatus(
                $"本机队列运行中 · {runtime.ActiveItemIds.Count}/{runtime.MaxParallel} 个活动作业");
        }
    }

    private void ApplySnapshot(JobQueueSnapshot snapshot)
    {
        var selectedFormalItemIds = CaptureSelectedFormalItemIds();
        _queueExplorerAdapter.Update(snapshot);
        ReplaceItems(_candidates, snapshot.Candidates);
        ReplaceItems(_queueItems, snapshot.QueueItems);
        RestoreFormalSelection(selectedFormalItemIds);
        SelectPendingFormalItem();
        CandidateSummaryText.Text =
            $"候选：{snapshot.CandidateCount} · 已选 {snapshot.SelectedCandidateCount} · 异常 {snapshot.InvalidCandidateCount}";
        FormalQueueSummaryText.Text = FormatQueueSummary(snapshot);
        if (string.IsNullOrWhiteSpace(ExternalWorkDirTextBox.Text))
        {
            ExternalWorkDirTextBox.Text = snapshot.QueueItems
                .FirstOrDefault(item => item.IsExternal
                    && !string.IsNullOrWhiteSpace(item.EffectiveWorkDir))
                ?.EffectiveWorkDir
                ?? string.Empty;
        }
        CandidateEmptyPanel.Visibility = snapshot.CandidateCount == 0
            ? Visibility.Visible
            : Visibility.Collapsed;
        FormalQueueEmptyText.Visibility = snapshot.QueueCount == 0
            ? Visibility.Visible
            : Visibility.Collapsed;
    }

    public void SelectFormalItem(string itemId)
    {
        _pendingFormalSelectionId = itemId.Trim();
        SelectPendingFormalItem();
    }

    private void SelectExplorerItem(ExplorerItem item)
    {
        if (item.Kind == ExplorerItemKind.CandidateJob)
        {
            CandidateList.SelectedItem = _candidates.FirstOrDefault(
                candidate => string.Equals(candidate.ItemId, item.EntityId, StringComparison.Ordinal));
        }
        else if (item.Kind == ExplorerItemKind.QueueJob)
        {
            SelectFormalItem(item.EntityId);
        }
    }

    private async Task ActivateExplorerItemAsync(ExplorerItem item)
    {
        if (item.Kind == ExplorerItemKind.InputFile && !string.IsNullOrWhiteSpace(item.Path))
        {
            await AddCandidatePathsAsync([item.Path]);
            return;
        }
        if (item.Kind == ExplorerItemKind.QueueJob)
        {
            App.Current.MainWindow.NavigateToJobOverview($"local:{item.EntityId}");
            return;
        }
        SelectExplorerItem(item);
    }

    private void SelectPendingFormalItem()
    {
        if (string.IsNullOrWhiteSpace(_pendingFormalSelectionId))
        {
            return;
        }

        var item = _queueItems.FirstOrDefault(candidate => string.Equals(
            candidate.ItemId,
            _pendingFormalSelectionId,
            StringComparison.Ordinal));
        if (item is null)
        {
            return;
        }

        FormalQueueList.SelectedItem = item;
        FormalQueueList.ScrollIntoView(item);
        FormalQueueList.Focus(FocusState.Programmatic);
        _pendingFormalSelectionId = null;
    }

    private void SetBusy(bool busy, string? status = null)
    {
        _busy = busy;
        RefreshQueueButton.IsEnabled = !busy;
        AddCurrentInputButton.IsEnabled = !busy;
        AddCandidateFilesButton.IsEnabled = !busy;
        ScanCandidateFolderButton.IsEnabled = !busy;
        ChooseExternalWorkDirButton.IsEnabled = !busy;
        ScanExternalJobsButton.IsEnabled = !busy;
        ExternalWorkDirTextBox.IsEnabled = !busy;
        if (!string.IsNullOrWhiteSpace(status))
        {
            App.Current.MainWindow.ReportPageStatus(status);
        }
    }

    private JobQueueItem[] SelectedFormalItems() =>
        FormalQueueList.SelectedItems.OfType<JobQueueItem>().ToArray();

    private HashSet<string> CaptureSelectedFormalItemIds() =>
        SelectedFormalItems()
            .Select(item => item.ItemId)
            .Where(itemId => !string.IsNullOrWhiteSpace(itemId))
            .ToHashSet(StringComparer.Ordinal);

    private void RestoreFormalSelection(IReadOnlySet<string> selectedItemIds)
    {
        foreach (var item in _queueItems.Where(item => selectedItemIds.Contains(item.ItemId)))
        {
            FormalQueueList.SelectedItems.Add(item);
        }
    }

    private JobQueueItem[]? RequireFormalSelection()
    {
        var selected = SelectedFormalItems();
        if (selected.Length > 0)
        {
            return selected;
        }

        ShowNotice("没有选中作业", "请先在正式队列表格中选择作业。");
        return null;
    }

    private void ShowSuccess(string title, string message, string status)
    {
        QueueInfoBar.Title = title;
        QueueInfoBar.Message = message;
        QueueInfoBar.Severity = InfoBarSeverity.Success;
        QueueInfoBar.IsOpen = true;
        App.Current.MainWindow.ReportPageStatus(status);
    }

    private void ShowNotice(string title, string message)
    {
        QueueInfoBar.Title = title;
        QueueInfoBar.Message = message;
        QueueInfoBar.Severity = InfoBarSeverity.Informational;
        QueueInfoBar.IsOpen = true;
    }

    private void ShowError(string message)
    {
        QueueInfoBar.Title = "队列操作失败";
        QueueInfoBar.Message = message;
        QueueInfoBar.Severity = InfoBarSeverity.Error;
        QueueInfoBar.IsOpen = true;
        App.Current.MainWindow.ReportPageStatus("队列操作失败");
    }

    private async Task<bool> ConfirmAsync(string title, string message)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = title,
            Content = message,
            PrimaryButtonText = "继续",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    private static void ReplaceItems(
        ObservableCollection<JobQueueItem> target,
        IReadOnlyList<JobQueueItem> source)
    {
        target.Clear();
        foreach (var item in source)
        {
            target.Add(item);
        }
    }

    private static string FormatQueueSummary(JobQueueSnapshot snapshot)
    {
        if (snapshot.StatusCounts.Count == 0)
        {
            return $"队列：{snapshot.QueueCount}";
        }

        return $"队列：{snapshot.QueueCount} · "
            + string.Join(
                " · ",
                snapshot.StatusCounts.Select(pair => $"{pair.Key} {pair.Value}"));
    }

    private static int NumberValue(NumberBox numberBox) =>
        double.IsNaN(numberBox.Value) ? 0 : Convert.ToInt32(numberBox.Value);

    private string ExistingResultPolicy() =>
        (ExistingResultPolicyComboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString()
        ?? "backup";

    private static string PolicyDisplay(string policy) => policy switch
    {
        "overwrite" => "覆盖旧结果",
        "cancel" => "遇到同名结果时取消该作业",
        _ => "备份旧结果",
    };

    private static async Task<IReadOnlyList<string>> PickInpFilesAsync(bool multiple)
    {
        var picker = new FileOpenPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = multiple ? "添加候选" : "加入当前 INP",
        };
        picker.FileTypeFilter.Add(".inp");
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        if (multiple)
        {
            return (await picker.PickMultipleFilesAsync()).Select(file => file.Path).ToArray();
        }

        var file = await picker.PickSingleFileAsync();
        return file is null ? [] : [file.Path];
    }

    private static async Task<string?> PickFolderAsync(string commitButtonText)
    {
        var picker = new FolderPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = commitButtonText,
        };
        picker.FileTypeFilter.Add("*");
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        return (await picker.PickSingleFolderAsync())?.Path;
    }
}
