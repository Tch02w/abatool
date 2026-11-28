using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.Storage;
using Windows.System;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class JobOverviewPage : Page, IWorkbenchExplorerPage
{
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _refreshTimer;
    private readonly JobMonitorExplorerAdapter _jobExplorerAdapter;
    private JobOverviewEntry? _currentEntry;
    private LocalQueueRuntimeSnapshot? _runtime;
    private RemoteJobListResponse _remoteJobs = new();
    private bool _loading;
    private bool _updatingJobSelector;
    private bool _applyingLogText;
    private bool _logPointerDown;
    private bool _retryingArchive;
    private long _snapshotRequest;
    private long _jobViewRevision;
    private readonly RuntimeLogUpdateState _runtimeLog;
    private string? _staContext;
    private string? _staPath;
    private StaIncrementReader? _staReader;
    private StaIncrementReader? _staReadInFlight;
    private StaIncrementPreview? _pendingSta;
    private StaIncrementPreview? _displayedSta;
    private bool _staPointerDown;

    public JobOverviewPage()
    {
        InitializeComponent();
        _runtimeLog = new RuntimeLogUpdateState(RuntimeLogTextBox.Text);
        RuntimeLogTextBox.SelectionChanged += OnRuntimeLogSelectionChanged;
        RuntimeLogTextBox.AddHandler(PointerPressedEvent,
            new PointerEventHandler(OnRuntimeLogPointerPressed), handledEventsToo: true);
        RuntimeLogTextBox.AddHandler(PointerReleasedEvent,
            new PointerEventHandler(OnRuntimeLogPointerFinished), handledEventsToo: true);
        RuntimeLogTextBox.AddHandler(PointerCanceledEvent,
            new PointerEventHandler(OnRuntimeLogPointerFinished), handledEventsToo: true);
        RuntimeLogTextBox.AddHandler(PointerCaptureLostEvent,
            new PointerEventHandler(OnRuntimeLogPointerFinished), handledEventsToo: true);
        StaRowsTextBox.SelectionChanged += (_, _) => DispatcherQueue.TryEnqueue(FlushStaPreview);
        StaRowsTextBox.AddHandler(PointerPressedEvent, new PointerEventHandler((_, _) => _staPointerDown = true), true);
        foreach (var routedEvent in new[] { PointerReleasedEvent, PointerCanceledEvent, PointerCaptureLostEvent })
            StaRowsTextBox.AddHandler(routedEvent, new PointerEventHandler((_, _) =>
            {
                _staPointerDown = false;
                DispatcherQueue.TryEnqueue(FlushStaPreview);
            }), true);
        _jobExplorerAdapter = new JobMonitorExplorerAdapter(
            App.Current.ControlPlane,
            SelectExplorerItem);
        _refreshTimer = DispatcherQueue.CreateTimer();
        _refreshTimer.Interval = TimeSpan.FromSeconds(1.5);
        _refreshTimer.Tick += OnRefreshTimerTick;
        App.Current.Session.Register(this, "job-overview", [], pause: _refreshTimer.Stop, resume: _refreshTimer.Start);
        Loaded += OnPageLoaded;
        Unloaded += OnPageUnloaded;
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _jobExplorerAdapter;

    public JobPostprocessTarget? PostprocessTarget => _currentEntry?.LocalItem is { } local
        ? JobPostprocessTarget.Local(local)
        : _currentEntry?.RemoteOperation is { } remote
            ? new("remote", remote.OperationId, "", remote.Request.JobName, remote.Request.InputPath) : null;

    public async Task<bool> SelectNotificationJobAsync(JobNotification notification)
    {
        var deadline = DateTime.UtcNow.AddSeconds(5);
        while ((!IsLoaded || _loading) && DateTime.UtcNow < deadline) await Task.Delay(50);
        if (!IsLoaded || _loading || App.Current.Session.IsClosing) return false;
        await RefreshAsync();
        if (!IsLoaded || App.Current.Session.IsClosing || JobSelector.ItemsSource is not IEnumerable<JobOverviewEntry> entries) return false;
        var entry = entries.FirstOrDefault(item => item.Key == notification.JobKey
            && (item.LocalItem is null || item.LocalItem.AttemptId == notification.LocalAttemptId));
        if (entry is null) return false;
        SelectJob(entry.Key);
        return true;
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        await RefreshAsync(deferIfBusy: true);
        if (IsLoaded)
        {
            _refreshTimer.Start();
        }
    }

    private void OnPageUnloaded(object sender, RoutedEventArgs e)
    {
        _refreshTimer.Stop();
        _snapshotRequest++;
        _jobViewRevision++;
        _logPointerDown = false;
        ResetStaPreview();
    }

    private async void OnRefreshTimerTick(
        Microsoft.UI.Dispatching.DispatcherQueueTimer sender,
        object args)
    {
        if (App.Current.Session.IsClosing) return;
        await RefreshAsync(deferIfBusy: true);
    }

    private async Task RefreshAsync(bool deferIfBusy = false)
    {
        if (_loading)
        {
            return;
        }

        _loading = true;
        var request = ++_snapshotRequest;
        try
        {
            var localTask = App.Current.ControlPlane.GetLocalQueueRuntimeAsync(deferIfBusy: deferIfBusy);
            var remoteTask = App.Current.ControlPlane.ListRemoteJobsAsync();
            await Task.WhenAll(localTask, remoteTask);
            if (!IsLoaded || request != _snapshotRequest)
            {
                return;
            }

            // Read selection after the await: the user may switch jobs while polling.
            var local = await localTask;
            var selectedKey = _currentEntry?.Key;
            if (!local.RefreshPending) _runtime = local;
            _remoteJobs = await remoteTask;
            var snapshot = _runtime?.Queue;
            var entries = (snapshot?.QueueItems ?? [])
                .Select(JobOverviewEntry.FromLocal)
                .Concat(_remoteJobs.Operations.Select(JobOverviewEntry.FromRemote))
                .ToArray();
            _jobExplorerAdapter.Update(snapshot, _remoteJobs.Operations);
            JobStatsText.Text = snapshot is null ? $"远端作业 {_remoteJobs.Operations.Count}" : FormatStats(snapshot, _remoteJobs.Operations);
            var selected = entries.FirstOrDefault(
                item => string.Equals(item.Key, selectedKey, StringComparison.Ordinal))
                ?? entries.FirstOrDefault(item => item.Active)
                ?? entries.FirstOrDefault();
            _updatingJobSelector = true;
            try
            {
                JobSelector.ItemsSource = entries;
                JobSelector.IsEnabled = entries.Length > 0;
                JobSelector.SelectedItem = selected;
            }
            finally
            {
                _updatingJobSelector = false;
            }
            ApplyJob(selected);
            var localStatus = local.RefreshPending
                ? (_runtime is null ? "正在读取本机队列…" : "正在更新本机队列…")
                : $"本机活动 {local.ActiveItemIds.Count}";
            OverviewMessageText.Text = selected is null && !local.RefreshPending ? "本机正式队列和远端会话中尚无作业。"
                : $"{localStatus} · 远端活动 {_remoteJobs.Operations.Count(item => !item.IsTerminal)}";
        }
        catch (ControlPlaneException exception)
        {
            if (IsLoaded && request == _snapshotRequest)
            {
                OverviewMessageText.Text = exception.ToDisplayMessage();
            }
        }
        catch (Exception exception)
        {
            if (IsLoaded && request == _snapshotRequest)
            {
                OverviewMessageText.Text = exception.Message;
            }
        }
        finally
        {
            _loading = false;
        }
    }

    private void OnJobSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_updatingJobSelector)
        {
            ApplyJob(JobSelector.SelectedItem as JobOverviewEntry);
        }
    }

    public void SelectJob(string key)
    {
        if (JobSelector.ItemsSource is not IEnumerable<JobOverviewEntry> entries)
        {
            return;
        }
        var selected = entries.FirstOrDefault(
            item => string.Equals(item.Key, key, StringComparison.Ordinal));
        if (selected is null)
        {
            return;
        }
        JobSelector.SelectedItem = selected;
        ApplyJob(selected);
    }

    private void SelectExplorerItem(ExplorerItem item) => SelectJob(item.StableId);

    private void ApplyJob(JobOverviewEntry? entry)
    {
        if (!string.Equals(_currentEntry?.Key, entry?.Key, StringComparison.Ordinal))
        {
            _jobViewRevision++;
        }
        _currentEntry = entry;
        var item = entry?.LocalItem;
        StaIncrementsButton.Visibility = item is null ? Visibility.Collapsed : Visibility.Visible;
        if (item is null) StaIncrementsButton.IsChecked = false;
        UpdateStaView();
        var remote = entry?.RemoteOperation;
        var operation = item is null
            ? null
            : _runtime?.Operations.FirstOrDefault(
                entry => string.Equals(entry.ItemId, item.ItemId, StringComparison.Ordinal));
        if (entry is null)
        {
            CurrentJobTitleText.Text = "Job: 未选择";
            StatusSummaryText.Text = "未运行";
            ArchiveStatusText.Visibility = Visibility.Collapsed;
            ProgressSummaryText.Text = "—";
            RuntimeProgressBar.Value = 0;
            ElapsedSummaryText.Text = "00:00:00";
            MemorySummaryText.Text = "—";
            ToolTipService.SetToolTip(MemorySummaryText, null);
            InputPathText.Text = "未记录";
            WorkDirectoryText.Text = "尚未分配";
            RestartDependencyText.Text = "无";
            UpdateRuntimeLog(null, "选择作业后显示状态与运行信息。");
            PauseResumeButton.IsEnabled = false;
            TerminateButton.IsEnabled = false;
            RetryArchiveButton.Visibility = Visibility.Collapsed;
            SetOutputButtons(null);
            return;
        }

        if (remote is not null)
        {
            ApplyRemoteJob(remote);
            return;
        }

        if (item is null)
        {
            return;
        }

        CurrentJobTitleText.Text = $"Job: {item.JobName}";
        StatusSummaryText.Text = string.IsNullOrWhiteSpace(item.Status) ? "未知" : item.Status;
        ArchiveStatusText.Text = item.ArchiveStatus;
        ArchiveStatusText.Visibility = string.IsNullOrWhiteSpace(item.ArchiveStatus) ? Visibility.Collapsed : Visibility.Visible;
        ToolTipService.SetToolTip(ArchiveStatusText, item.ArchiveDetailsDisplay);
        var progress = operation?.Progress ?? 0;
        ProgressSummaryText.Text = operation is null
            ? "—"
            : string.IsNullOrWhiteSpace(operation.Detail)
                ? $"{progress}%"
                : operation.Detail;
        RuntimeProgressBar.Value = progress;
        ElapsedSummaryText.Text = operation is null
            ? (string.IsNullOrWhiteSpace(item.Elapsed) ? "00:00:00" : item.Elapsed)
            : FormatElapsed(operation);
        MemorySummaryText.Text = item.RuntimeMemoryDisplay;
        ToolTipService.SetToolTip(MemorySummaryText, item.MemoryDetailsDisplay);
        InputPathText.Text = string.IsNullOrWhiteSpace(item.InpPath) ? "未记录" : item.InpPath;
        WorkDirectoryText.Text = ResolveWorkDirectory(item) ?? "尚未分配";
        RestartDependencyText.Text = string.IsNullOrWhiteSpace(item.OldjobName)
            ? "无"
            : item.OldjobName;
        UpdateRuntimeLog(entry.Key, BuildRuntimeLog(item, operation));
        PauseResumeButton.Content = operation?.Paused is true ? "恢复" : "暂停";
        PauseResumeButton.IsEnabled = operation?.Active is true && !operation.IsArchiving;
        TerminateButton.Content = operation?.IsArchiving is true ? "取消归档" : "终止";
        TerminateButton.IsEnabled = operation?.Active is true;
        RetryArchiveButton.Visibility = item.ArchiveRecoveryAvailable ? Visibility.Visible : Visibility.Collapsed;
        RetryArchiveButton.IsEnabled = item.ArchiveRecoveryAvailable && operation?.Active is not true && !_retryingArchive;
        SetOutputButtons(item);
        App.Current.MainWindow.ReportPageStatus($"作业概览 · {item.JobName} · {item.Status}");
    }

    private void ApplyRemoteJob(RemoteJobOperationSnapshot operation)
    {
        RetryArchiveButton.Visibility = Visibility.Collapsed;
        TerminateButton.Content = "终止";
        CurrentJobTitleText.Text = $"Remote Job: {operation.Request.JobName}";
        StatusSummaryText.Text = operation.StatusDisplay;
        ArchiveStatusText.Visibility = Visibility.Collapsed;
        ProgressSummaryText.Text = string.IsNullOrWhiteSpace(operation.Phase)
            ? $"{operation.Percent}%"
            : operation.Phase;
        if (!string.IsNullOrWhiteSpace(operation.PersistenceWarning))
            ProgressSummaryText.Text += $" · {operation.PersistenceWarning}";
        RuntimeProgressBar.Value = operation.Percent;
        var elapsed = (operation.IsTerminal ? operation.UpdatedAt : DateTimeOffset.Now)
            - operation.CreatedAt;
        if (elapsed < TimeSpan.Zero)
        {
            elapsed = TimeSpan.Zero;
        }
        ElapsedSummaryText.Text =
            $"{(int)elapsed.TotalHours:00}:{elapsed.Minutes:00}:{elapsed.Seconds:00}";
        MemorySummaryText.Text = string.IsNullOrWhiteSpace(operation.Request.Memory)
            ? "服务器默认"
            : operation.Request.Memory;
        ToolTipService.SetToolTip(MemorySummaryText, null);
        InputPathText.Text = operation.Request.InputPath;
        WorkDirectoryText.Text = string.IsNullOrWhiteSpace(operation.WorkDirectory)
            ? "正在分配"
            : operation.WorkDirectory;
        RestartDependencyText.Text = operation.Request.InputMode == "upload"
            ? "本机文件上传"
            : "服务器现有文件";
        UpdateRuntimeLog($"remote:{operation.OperationId}", operation.Logs.Count == 0
            ? $"阶段：{operation.Phase}\r\n状态：{operation.Status}"
            : string.Join("\r\n", operation.Logs));
        PauseResumeButton.Content = operation.Paused ? "恢复" : "暂停";
        PauseResumeButton.IsEnabled = operation.CanPauseResume;
        TerminateButton.IsEnabled = !operation.IsTerminal
            && operation.Status is "starting" or "running";
        SetRemoteOutputButtons(operation);
        App.Current.MainWindow.ReportPageStatus(
            $"远端作业 · {operation.Request.JobName} · {operation.StatusDisplay}");
    }

    private bool IsInteractingWithRuntimeLog =>
        _logPointerDown || RuntimeLogTextBox.SelectionLength > 0;

    private void UpdateRuntimeLog(string? jobKey, string text) =>
        ApplyRuntimeLogUpdate(_runtimeLog.SetSnapshot(jobKey, text, IsInteractingWithRuntimeLog));

    private void OnRuntimeLogSelectionChanged(object sender, RoutedEventArgs args)
    {
        if (!_applyingLogText)
        {
            FlushRuntimeLogAfterInput();
        }
    }

    private void OnRuntimeLogPointerPressed(object sender, PointerRoutedEventArgs args) =>
        _logPointerDown = true;

    private void OnRuntimeLogPointerFinished(object sender, PointerRoutedEventArgs args)
    {
        _logPointerDown = false;
        FlushRuntimeLogAfterInput();
    }

    private void FlushRuntimeLogAfterInput()
    {
        // Let the current mouse/key action finish before inspecting the final selection.
        DispatcherQueue.TryEnqueue(() =>
        {
            if (IsLoaded && !_applyingLogText)
            {
                ApplyRuntimeLogUpdate(_runtimeLog.Flush(IsInteractingWithRuntimeLog));
            }
        });
    }

    private void ApplyRuntimeLogUpdate(RuntimeLogTextUpdate? update)
    {
        RuntimeLogUpdateText.Visibility = _runtimeLog.HasPendingText && StaIncrementsButton.IsChecked != true
            ? Visibility.Visible : Visibility.Collapsed;
        if (update is null)
        {
            return;
        }

        _applyingLogText = true;
        try
        {
            ApplyLogText(RuntimeLogTextBox, update);
        }
        finally
        {
            _applyingLogText = false;
        }
    }

    private static void ApplyLogText(TextBox box, RuntimeLogTextUpdate update)
    {
        var scroll = FindLogScrollViewer(box);
        var horizontal = scroll?.HorizontalOffset ?? 0;
        var vertical = scroll?.VerticalOffset ?? 0;
        var followTail = update.ResetView || (scroll is not null
            && RuntimeLogUpdateState.ShouldFollowTail(vertical, scroll.ScrollableHeight));
        var caret = update.ResetView ? update.Text.Length : box.SelectionStart;
        box.Text = update.Text;
        box.Select(Math.Min(caret, update.Text.Length), 0);
        box.UpdateLayout();
        scroll?.ChangeView(update.ResetView ? 0 : horizontal,
            followTail ? scroll.ScrollableHeight : vertical, null, disableAnimation: true);
    }

    private void OnStaIncrementsChanged(object sender, RoutedEventArgs args) => UpdateStaView();

    private void UpdateStaView()
    {
        var item = _currentEntry?.LocalItem;
        bool show = item is not null && StaIncrementsButton.IsChecked == true;
        StaIncrementsButton.Content = show ? "返回运行日志" : "STA 增量";
        StaPreviewPanel.Visibility = show ? Visibility.Visible : Visibility.Collapsed;
        RuntimeLogTextBox.Visibility = show ? Visibility.Collapsed : Visibility.Visible;
        RuntimeLogUpdateText.Visibility = !show && _runtimeLog.HasPendingText ? Visibility.Visible : Visibility.Collapsed;
        if (!show)
        {
            if (_staContext is not null) ResetStaPreview();
            return;
        }

        var path = Path.GetFileName(item!.JobName) == item.JobName ? OutputFilePath(item, ".sta") : null;
        var context = $"{item.ItemId}\n{item.AttemptId}\n{path}";
        if (_staContext != context)
        {
            ResetStaPreview();
            _staContext = context;
            _staReader = new StaIncrementReader();
            _staPath = path;
            ToolTipService.SetToolTip(StaPreviewStatus, path);
            StaPreviewStatus.Text = path is null ? "当前作业没有可读取的 STA 路径。" : "正在读取 STA 增量…";
        }
        if (path is not null && _staReader is not null && _staReadInFlight != _staReader)
            _ = ReadStaPreviewAsync(path, _staReader);
    }

    private async Task ReadStaPreviewAsync(string path, StaIncrementReader reader)
    {
        _staReadInFlight = reader;
        try
        {
            var preview = await Task.Run(() => reader.Read(path));
            if (IsLoaded && _staReader == reader)
            {
                _pendingSta = preview;
                FlushStaPreview();
            }
        }
        finally
        {
            if (_staReadInFlight == reader) _staReadInFlight = null;
        }
    }

    private void ResetStaPreview()
    {
        _staContext = null;
        _staPath = null;
        _staReader = null;
        _pendingSta = null;
        _displayedSta = null;
        _staPointerDown = false;
        StaRowsTextBox.Text = "";
        StaHeaderText.Text = "";
        StaHorizontalScroll.ChangeView(0, null, null, true);
    }

    private void FlushStaPreview()
    {
        if (_pendingSta is not { } preview || _staPointerDown || StaRowsTextBox.SelectionLength > 0) return;
        _pendingSta = null;
        var previous = _displayedSta;
        if (preview == previous) return;
        _displayedSta = preview;
        StaPreviewStatus.Text = $"{Path.GetFileName(_staPath)} · {preview.Status}";
        StaHorizontalScroll.Visibility = preview.Rows.Length == 0 ? Visibility.Collapsed : Visibility.Visible;
        if (previous?.Header != preview.Header) StaHeaderText.Text = preview.Header;
        if (previous?.Rows != preview.Rows)
            ApplyLogText(StaRowsTextBox, new(preview.Rows, ResetView: string.IsNullOrEmpty(previous?.Rows)));
    }

    private static ScrollViewer? FindLogScrollViewer(DependencyObject parent)
    {
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(parent); index++)
        {
            var child = VisualTreeHelper.GetChild(parent, index);
            if (child is ScrollViewer scroll)
            {
                return scroll;
            }

            if (FindLogScrollViewer(child) is { } descendant)
            {
                return descendant;
            }
        }

        return null;
    }

    private async void OnPauseResumeClicked(object sender, RoutedEventArgs e)
    {
        if (_currentEntry?.RemoteOperation is { } remote)
        {
            var selectedKey = _currentEntry.Key;
            var request = ++_snapshotRequest;
            try
            {
                var updated = await App.Current.ControlPlane.ControlRemoteJobAsync(
                    remote.OperationId,
                    remote.Paused ? "resume" : "pause");
                ShowRemoteControlResult(updated, remote.Paused ? "已请求恢复远端作业" : "已请求暂停远端作业");
                if (IsLoaded && request == _snapshotRequest && _currentEntry?.Key == selectedKey)
                {
                    ApplyJob(JobOverviewEntry.FromRemote(updated));
                }
            }
            catch (Exception exception)
            {
                ShowActionError(remote.Paused ? "恢复远端作业失败" : "暂停远端作业失败", remote.Request.JobName, exception);
            }
            return;
        }

        var currentJob = _currentEntry?.LocalItem;
        if (currentJob is null)
        {
            return;
        }
        var operation = _runtime?.Operations.FirstOrDefault(
            entry => string.Equals(entry.ItemId, currentJob.ItemId, StringComparison.Ordinal));
        if (operation?.Active is not true)
        {
            return;
        }

        var localSelectedKey = _currentEntry?.Key;
        var localRequest = ++_snapshotRequest;
        try
        {
            var runtime = await App.Current.ControlPlane.SetLocalQueueItemsPausedAsync(
                [currentJob.ItemId],
                !operation.Paused);
            App.Current.MainWindow.ShowFeedback(operation.Paused ? "已请求恢复本机作业" : "已请求暂停本机作业",
                currentJob.JobName, InfoBarSeverity.Success);
            if (!IsLoaded || localRequest != _snapshotRequest || _currentEntry?.Key != localSelectedKey)
            {
                return;
            }
            _runtime = runtime;
            var updated = _runtime.Queue.QueueItems.FirstOrDefault(
                item => string.Equals(item.ItemId, currentJob.ItemId, StringComparison.Ordinal));
            ApplyJob(updated is null ? null : JobOverviewEntry.FromLocal(updated));
        }
        catch (Exception exception)
        {
            ShowActionError(operation.Paused ? "恢复本机作业失败" : "暂停本机作业失败", currentJob.JobName, exception);
        }
    }

    private async void OnRetryArchiveClicked(object sender, RoutedEventArgs e)
    {
        var item = _currentEntry?.LocalItem;
        if (_retryingArchive || item?.ArchiveRecoveryAvailable is not true) return;
        var selectedKey = _currentEntry!.Key;
        var request = ++_snapshotRequest;
        _retryingArchive = true;
        RetryArchiveButton.IsEnabled = false;
        try
        {
            var updated = await App.Current.ControlPlane.RetryLocalArchiveAsync(item.ItemId);
            App.Current.MainWindow.ShowFeedback("已请求恢复归档", item.JobName, InfoBarSeverity.Success);
            if (!IsLoaded || request != _snapshotRequest || _currentEntry?.Key != selectedKey) return;
            _runtime = updated;
            var row = updated.Queue.QueueItems.FirstOrDefault(x => x.ItemId == item.ItemId);
            ApplyJob(row is null ? null : JobOverviewEntry.FromLocal(row));
        }
        catch (Exception exception)
        {
            ShowActionError("恢复归档失败", item.JobName, exception);
        }
        finally
        {
            _retryingArchive = false;
            if (IsLoaded) ApplyJob(_currentEntry);
        }
    }

    private async void OnTerminateClicked(object sender, RoutedEventArgs e)
    {
        var remote = _currentEntry?.RemoteOperation;
        var currentJob = _currentEntry?.LocalItem;
        var selectedKey = _currentEntry?.Key;
        if (remote is null && currentJob is null)
        {
            return;
        }
        var jobName = remote?.Request.JobName ?? currentJob?.JobName ?? "作业";
        var archiving = remote is null && _runtime?.Operations.FirstOrDefault(x => x.ItemId == currentJob?.ItemId)?.IsArchiving is true;
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = archiving ? $"取消 {jobName} 的归档？" : $"终止 {jobName}？",
            Content = archiving ? "停止后续归档和清理，保留已有文件；可以稍后恢复归档。已完成的计算结果不变。"
                : "将向 Abaqus 发送 terminate，并等待求解进程安全退出。",
            PrimaryButtonText = archiving ? "取消归档" : "终止作业",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }

        var request = ++_snapshotRequest;
        try
        {
            if (remote is not null)
            {
                var updated = await App.Current.ControlPlane.ControlRemoteJobAsync(
                    remote.OperationId,
                    "cancel");
                ShowRemoteControlResult(updated, "已请求终止远端作业");
                if (IsLoaded && request == _snapshotRequest && _currentEntry?.Key == selectedKey)
                {
                    ApplyJob(JobOverviewEntry.FromRemote(updated));
                }
                return;
            }
            if (currentJob is null)
            {
                return;
            }
            var runtime = await App.Current.ControlPlane.TerminateLocalQueueItemsAsync(
                [currentJob.ItemId]);
            App.Current.MainWindow.ShowFeedback(archiving ? "已请求取消归档" : "已请求终止本机作业",
                jobName, InfoBarSeverity.Informational);
            if (!IsLoaded || request != _snapshotRequest || _currentEntry?.Key != selectedKey)
            {
                return;
            }
            _runtime = runtime;
            var updatedLocal = _runtime.Queue.QueueItems.FirstOrDefault(
                item => string.Equals(item.ItemId, currentJob.ItemId, StringComparison.Ordinal));
            ApplyJob(updatedLocal is null ? null : JobOverviewEntry.FromLocal(updatedLocal));
        }
        catch (Exception exception)
        {
            ShowActionError(archiving ? "取消归档失败" : "终止作业失败", jobName, exception);
        }
    }

    private static void ShowRemoteControlResult(RemoteJobOperationSnapshot updated, string requested)
    {
        App.Current.MainWindow.ShowFeedback(updated.IsTerminal ? "远端作业已结束" : requested,
            $"{updated.Request.JobName} · {updated.Error?.Message ?? updated.StatusDisplay}",
            updated.Status == "failed" ? InfoBarSeverity.Error : InfoBarSeverity.Informational);
    }

    private static void ShowActionError(string title, string subject, Exception exception)
    {
        var message = exception is ControlPlaneException problem ? problem.ToDisplayMessage() : exception.Message;
        App.Current.MainWindow.ShowFeedback(title, $"{subject} · {message}", InfoBarSeverity.Error);
    }

    private static string BuildRuntimeLog(
        JobQueueItem item,
        LocalJobRuntimeOperation? operation)
    {
        var header =
            $"状态：{item.Status}\r\n调度：{item.SchedulingDisplay}\r\n消息：{item.Message}\r\n"
            + $"Core：{item.CoresDisplay}\r\n内存配置：{item.Memory}";
        if (!string.IsNullOrWhiteSpace(item.ArchiveDetailsDisplay))
            header += "\r\n" + item.ArchiveDetailsDisplay;
        if (operation is null)
        {
            return header;
        }

        var runtime =
            $"\r\n阶段：{operation.Phase}\r\n进度：{operation.Progress}%"
            + (string.IsNullOrWhiteSpace(operation.Detail)
                ? string.Empty
                : $" · {operation.Detail}");
        return operation.Logs.Count == 0
            ? header + runtime
            : header + runtime + "\r\n\r\n" + string.Join("\r\n", operation.Logs);
    }

    private static string FormatElapsed(LocalJobRuntimeOperation operation)
    {
        var end = operation.FinishedAt ?? DateTimeOffset.Now;
        var elapsed = end - operation.StartedAt;
        if (elapsed < TimeSpan.Zero)
        {
            elapsed = TimeSpan.Zero;
        }
        return $"{(int)elapsed.TotalHours:00}:{elapsed.Minutes:00}:{elapsed.Seconds:00}";
    }

    private void SetOutputButtons(JobQueueItem? item)
    {
        var workDirectory = item is null ? null : ResolveWorkDirectory(item);
        OpenDirectoryButton.IsEnabled = workDirectory is not null && Directory.Exists(workDirectory);
        OpenStaButton.IsEnabled = OutputFileExists(item, ".sta");
        OpenMsgButton.IsEnabled = OutputFileExists(item, ".msg");
        OpenDatButton.IsEnabled = OutputFileExists(item, ".dat");
    }

    private void SetRemoteOutputButtons(RemoteJobOperationSnapshot operation)
    {
        OpenDirectoryButton.IsEnabled = !string.IsNullOrWhiteSpace(operation.WorkDirectory);
        OpenStaButton.IsEnabled = operation.Files.ContainsKey("sta");
        OpenMsgButton.IsEnabled = operation.Files.ContainsKey("msg");
        OpenDatButton.IsEnabled = operation.Files.ContainsKey("dat");
    }

    private async void OnOpenDirectoryClicked(object sender, RoutedEventArgs e)
    {
        if (_currentEntry?.RemoteOperation is { } remote)
        {
            try
            {
                var browser = new RemoteFileBrowserDialog(
                    XamlRoot, RemoteSelectionMode.Browse,
                    $"{remote.Request.JobName} · 服务器工作目录", remote.OperationId);
                await browser.ShowAsync(remote.WorkDirectory);
            }
            catch (Exception exception)
            {
                ShowActionError("打开服务器工作目录失败", remote.Request.JobName, exception);
            }
            return;
        }
        var currentJob = _currentEntry?.LocalItem;
        var workDirectory = currentJob is null ? null : ResolveWorkDirectory(currentJob);
        if (currentJob is null) return;
        if (workDirectory is null || !Directory.Exists(workDirectory))
        {
            App.Current.MainWindow.ShowFeedback("作业目录不可用", workDirectory ?? currentJob.JobName, InfoBarSeverity.Warning);
            return;
        }

        try
        {
            var opened = await Launcher.LaunchFolderAsync(await StorageFolder.GetFolderFromPathAsync(workDirectory));
            App.Current.MainWindow.ShowFeedback(opened ? "已打开作业目录" : "Windows 未能打开作业目录", workDirectory,
                opened ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
        }
        catch (Exception exception)
        {
            ShowActionError("打开作业目录失败", workDirectory, exception);
        }
    }

    private async void OnOpenOutputFileClicked(object sender, RoutedEventArgs e)
    {
        if (sender is not Button { Tag: string extension })
        {
            return;
        }

        if (_currentEntry?.RemoteOperation is { } remote)
        {
            var key = extension.TrimStart('.');
            if (remote.Files.TryGetValue(key, out var remotePath))
            {
                await DownloadRemoteOutputAsync(remote.OperationId, remotePath);
            }
            else
            {
                App.Current.MainWindow.ShowFeedback("远端输出文件不可用", remote.Request.JobName + extension, InfoBarSeverity.Warning);
            }
            return;
        }

        var currentJob = _currentEntry?.LocalItem;
        if (currentJob is null)
        {
            return;
        }

        var path = OutputFilePath(currentJob, extension);
        if (path is null || !File.Exists(path))
        {
            App.Current.MainWindow.ShowFeedback("输出文件不可用", path ?? currentJob.JobName + extension, InfoBarSeverity.Warning);
            return;
        }

        try
        {
            var opened = await Launcher.LaunchFileAsync(await StorageFile.GetFileFromPathAsync(path));
            App.Current.MainWindow.ShowFeedback(opened ? "已打开作业输出" : "Windows 未能打开作业输出", path,
                opened ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
        }
        catch (Exception exception)
        {
            ShowActionError("打开作业输出失败", path, exception);
        }
    }

    private async Task DownloadRemoteOutputAsync(string sourceOperationId, string remotePath)
    {
        var view = _jobViewRevision;
        string? downloadedPath = null;
        try
        {
            var destination = await RemoteDownloadDestination.PickAsync(XamlRoot, remotePath, "下载并打开");
            if (destination is null) return;
            var operation = await App.Current.ControlPlane.StartRemoteTransferAsync(
                "download",
                remotePath,
                destination.Path,
                overwrite: destination.Overwrite,
                sourceOperationId: sourceOperationId);
            var terminal = await App.Current.ControlPlane.PollRemoteTransferUntilTerminalAsync(
                operation.OperationId,
                snapshot =>
                {
                    if (IsLoaded && view == _jobViewRevision)
                    {
                        RuntimeProgressBar.Value = snapshot.Progress.Percent;
                        OverviewMessageText.Text = $"正在下载远端输出 · {snapshot.Progress.Percent}%";
                    }
                });
            if (terminal.Status != "succeeded")
            {
                var cancelled = terminal.Status == "cancelled";
                App.Current.MainWindow.ShowFeedback(cancelled ? "已取消下载远端输出" : "远端输出下载失败",
                    terminal.Error is null ? remotePath : $"{remotePath} · {terminal.Error.Message}",
                    cancelled ? InfoBarSeverity.Informational : InfoBarSeverity.Error);
                return;
            }
            downloadedPath = destination.Path;
            var opened = await Launcher.LaunchFileAsync(await StorageFile.GetFileFromPathAsync(downloadedPath));
            App.Current.MainWindow.ShowFeedback(opened ? "远端输出已下载并打开" : "远端输出已下载，Windows 未能打开文件",
                downloadedPath, opened ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
        }
        catch (Exception exception)
        {
            if (downloadedPath is null) ShowActionError("远端输出下载失败", remotePath, exception);
            else App.Current.MainWindow.ShowFeedback("远端输出已下载，打开失败",
                $"{downloadedPath} · {exception.Message}", InfoBarSeverity.Warning);
        }
    }

    private static bool OutputFileExists(JobQueueItem? item, string extension)
    {
        var path = item is null ? null : OutputFilePath(item, extension);
        return path is not null && File.Exists(path);
    }

    private static string? OutputFilePath(JobQueueItem item, string extension)
    {
        var directory = ResolveWorkDirectory(item);
        return string.IsNullOrWhiteSpace(directory) || string.IsNullOrWhiteSpace(item.JobName)
            ? null
            : Path.Combine(directory, item.JobName + extension);
    }

    private static string? ResolveWorkDirectory(JobQueueItem item)
    {
        if (item.HasPublishedArchive
            && Directory.Exists(item.ArchiveDestination))
        {
            return item.ArchiveDestination;
        }
        if (!string.IsNullOrWhiteSpace(item.EffectiveWorkDir))
        {
            return item.EffectiveWorkDir;
        }

        return string.IsNullOrWhiteSpace(item.InpPath)
            ? null
            : Path.GetDirectoryName(item.InpPath);
    }

    private static string FormatStats(
        JobQueueSnapshot snapshot,
        IReadOnlyList<RemoteJobOperationSnapshot> remoteJobs)
    {
        var running = snapshot.QueueItems.Count(item => item.Status is "运行中" or "正在启动");
        var completed = snapshot.QueueItems.Count(
            item => item.Status is "已完成" or "完成" or "Datacheck Completed");
        var abnormal = snapshot.QueueItems.Count(item =>
            item.Status.Contains("失败", StringComparison.Ordinal)
            || item.Status.Contains("中断", StringComparison.Ordinal)
            || item.Status.Contains("终止", StringComparison.Ordinal));
        running += remoteJobs.Count(item => item.Status is "starting" or "running" or "cancelling");
        completed += remoteJobs.Count(item => item.Status == "succeeded");
        abnormal += remoteJobs.Count(item => item.Status is "failed" or "cancelled");
        return $"运行中 {running} · 完成 {completed} · 异常 {abnormal}";
    }

}

public sealed class JobOverviewEntry
{
    public string Key { get; set; } = string.Empty;
    public string DisplayName { get; set; } = string.Empty;
    public bool Active { get; set; }
    public JobQueueItem? LocalItem { get; set; }
    public RemoteJobOperationSnapshot? RemoteOperation { get; set; }

    public static JobOverviewEntry FromLocal(JobQueueItem item) => new()
    {
        Key = $"local:{item.ItemId}",
        DisplayName = $"本机 · {item.JobName}",
        Active = item.Status is "运行中" or "正在启动",
        LocalItem = item,
    };

    public static JobOverviewEntry FromRemote(RemoteJobOperationSnapshot operation) => new()
    {
        Key = $"remote:{operation.OperationId}",
        DisplayName = $"远端 · {operation.Request.JobName}",
        Active = !operation.IsTerminal,
        RemoteOperation = operation,
    };
}
