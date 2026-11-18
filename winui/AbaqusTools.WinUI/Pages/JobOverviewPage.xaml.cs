using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using Windows.Storage;
using Windows.Storage.Pickers;
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
    private long _snapshotRequest;
    private long _controlRequest;
    private long _jobViewRevision;
    private readonly RuntimeLogUpdateState _runtimeLog;

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

    public async Task<bool> SelectNotificationJobAsync(JobNotification notification)
    {
        var deadline = DateTime.UtcNow.AddSeconds(5);
        while ((!IsLoaded || _loading) && DateTime.UtcNow < deadline) await Task.Delay(50);
        if (!IsLoaded || _loading || App.Current.Session.IsClosing) return false;
        await RefreshAsync();
        if (!IsLoaded || App.Current.Session.IsClosing || JobSelector.ItemsSource is not IEnumerable<JobOverviewEntry> entries) return false;
        var entry = entries.FirstOrDefault(item => item.Key == notification.JobKey
            && (item.LocalItem is null || item.LocalItem.AttemptId == notification.ExecutionId));
        if (entry is null) return false;
        SelectJob(entry.Key);
        return true;
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
        if (IsLoaded)
        {
            _refreshTimer.Start();
        }
    }

    private void OnPageUnloaded(object sender, RoutedEventArgs e)
    {
        _refreshTimer.Stop();
        _snapshotRequest++;
        _controlRequest++;
        _jobViewRevision++;
        _logPointerDown = false;
    }

    private async void OnRefreshTimerTick(
        Microsoft.UI.Dispatching.DispatcherQueueTimer sender,
        object args)
    {
        if (App.Current.Session.IsClosing) return;
        await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        if (_loading)
        {
            return;
        }

        _loading = true;
        var request = ++_snapshotRequest;
        try
        {
            var localTask = App.Current.ControlPlane.GetLocalQueueRuntimeAsync();
            var remoteTask = App.Current.ControlPlane.ListRemoteJobsAsync();
            await Task.WhenAll(localTask, remoteTask);
            if (!IsLoaded || request != _snapshotRequest)
            {
                return;
            }

            // Read selection after the await: the user may switch jobs while polling.
            var selectedKey = _currentEntry?.Key;
            _runtime = await localTask;
            _remoteJobs = await remoteTask;
            var snapshot = _runtime.Queue;
            var entries = snapshot.QueueItems
                .Select(JobOverviewEntry.FromLocal)
                .Concat(_remoteJobs.Operations.Select(JobOverviewEntry.FromRemote))
                .ToArray();
            _jobExplorerAdapter.Update(snapshot, _remoteJobs.Operations);
            JobStatsText.Text = FormatStats(snapshot, _remoteJobs.Operations);
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
            OverviewMessageText.Text = selected is null
                ? "本机正式队列和远端会话中尚无作业。"
                : $"本机活动 {_runtime.ActiveItemIds.Count} · 远端活动 {_remoteJobs.Operations.Count(item => !item.IsTerminal)}";
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
            _controlRequest++;
            _jobViewRevision++;
        }
        _currentEntry = entry;
        var item = entry?.LocalItem;
        var remote = entry?.RemoteOperation;
        var operation = item is null
            ? null
            : _runtime?.Operations.FirstOrDefault(
                entry => string.Equals(entry.ItemId, item.ItemId, StringComparison.Ordinal));
        if (entry is null)
        {
            CurrentJobTitleText.Text = "Job: 未选择";
            StatusSummaryText.Text = "未运行";
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
        PauseResumeButton.IsEnabled = operation?.Active is true;
        TerminateButton.IsEnabled = operation?.Active is true;
        SetOutputButtons(item);
        App.Current.MainWindow.ReportPageStatus($"作业概览 · {item.JobName} · {item.Status}");
    }

    private void ApplyRemoteJob(RemoteJobOperationSnapshot operation)
    {
        CurrentJobTitleText.Text = $"Remote Job: {operation.Request.JobName}";
        StatusSummaryText.Text = operation.StatusDisplay;
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
        RuntimeLogUpdateText.Visibility = _runtimeLog.HasPendingText
            ? Visibility.Visible : Visibility.Collapsed;
        if (update is null)
        {
            return;
        }

        var scroll = FindLogScrollViewer(RuntimeLogTextBox);
        var horizontal = scroll?.HorizontalOffset ?? 0;
        var vertical = scroll?.VerticalOffset ?? 0;
        var followTail = update.ResetView || (scroll is not null
            && RuntimeLogUpdateState.ShouldFollowTail(vertical, scroll.ScrollableHeight));
        var caret = update.ResetView ? update.Text.Length : RuntimeLogTextBox.SelectionStart;
        _applyingLogText = true;
        try
        {
            // SetSnapshot returns no update for unchanged text or an active selection.
            RuntimeLogTextBox.Text = update.Text;
            RuntimeLogTextBox.Select(Math.Min(caret, update.Text.Length), 0);
            RuntimeLogTextBox.UpdateLayout();
            scroll?.ChangeView(
                update.ResetView ? 0 : horizontal,
                followTail ? scroll.ScrollableHeight : vertical,
                null,
                disableAnimation: true);
        }
        finally
        {
            _applyingLogText = false;
        }
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
            var action = ++_controlRequest;
            try
            {
                var updated = await App.Current.ControlPlane.ControlRemoteJobAsync(
                    remote.OperationId,
                    remote.Paused ? "resume" : "pause");
                if (IsLoaded && request == _snapshotRequest && _currentEntry?.Key == selectedKey)
                {
                    ApplyJob(JobOverviewEntry.FromRemote(updated));
                }
            }
            catch (ControlPlaneException exception)
            {
                if (IsLoaded && action == _controlRequest && _currentEntry?.Key == selectedKey)
                {
                    OverviewMessageText.Text = exception.ToDisplayMessage();
                }
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
        var localAction = ++_controlRequest;
        try
        {
            var runtime = await App.Current.ControlPlane.SetLocalQueueItemsPausedAsync(
                [currentJob.ItemId],
                !operation.Paused);
            if (!IsLoaded || localRequest != _snapshotRequest || _currentEntry?.Key != localSelectedKey)
            {
                return;
            }
            _runtime = runtime;
            var updated = _runtime.Queue.QueueItems.FirstOrDefault(
                item => string.Equals(item.ItemId, currentJob.ItemId, StringComparison.Ordinal));
            ApplyJob(updated is null ? null : JobOverviewEntry.FromLocal(updated));
        }
        catch (ControlPlaneException exception)
        {
            if (IsLoaded && localAction == _controlRequest && _currentEntry?.Key == localSelectedKey)
            {
                OverviewMessageText.Text = exception.ToDisplayMessage();
            }
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
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"终止 {jobName}？",
            Content = "将向 Abaqus 发送 terminate，并等待求解进程安全退出。",
            PrimaryButtonText = "终止作业",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }

        var request = ++_snapshotRequest;
        var action = ++_controlRequest;
        try
        {
            if (remote is not null)
            {
                var updated = await App.Current.ControlPlane.ControlRemoteJobAsync(
                    remote.OperationId,
                    "cancel");
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
            if (!IsLoaded || request != _snapshotRequest || _currentEntry?.Key != selectedKey)
            {
                return;
            }
            _runtime = runtime;
            var updatedLocal = _runtime.Queue.QueueItems.FirstOrDefault(
                item => string.Equals(item.ItemId, currentJob.ItemId, StringComparison.Ordinal));
            ApplyJob(updatedLocal is null ? null : JobOverviewEntry.FromLocal(updatedLocal));
        }
        catch (ControlPlaneException exception)
        {
            if (IsLoaded && action == _controlRequest && _currentEntry?.Key == selectedKey)
            {
                OverviewMessageText.Text = exception.ToDisplayMessage();
            }
        }
    }

    private static string BuildRuntimeLog(
        JobQueueItem item,
        LocalJobRuntimeOperation? operation)
    {
        var header =
            $"状态：{item.Status}\r\n调度：{item.SchedulingDisplay}\r\n消息：{item.Message}\r\n"
            + $"Core：{item.CoresDisplay}\r\n内存配置：{item.Memory}";
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
        var view = _jobViewRevision;
        if (_currentEntry?.RemoteOperation is { } remote)
        {
            var browser = new RemoteFileBrowserDialog(
                XamlRoot,
                RemoteSelectionMode.File,
                $"{remote.Request.JobName} · 服务器工作目录");
            await browser.ShowAsync(remote.WorkDirectory);
            return;
        }
        var currentJob = _currentEntry?.LocalItem;
        var workDirectory = currentJob is null ? null : ResolveWorkDirectory(currentJob);
        if (workDirectory is null || !Directory.Exists(workDirectory))
        {
            return;
        }

        try
        {
            await Launcher.LaunchFolderAsync(await StorageFolder.GetFolderFromPathAsync(workDirectory));
        }
        catch (Exception exception)
        {
            if (IsLoaded && view == _jobViewRevision)
            {
                OverviewMessageText.Text = exception.Message;
            }
        }
    }

    private async void OnOpenOutputFileClicked(object sender, RoutedEventArgs e)
    {
        var view = _jobViewRevision;
        if (sender is not Button { Tag: string extension })
        {
            return;
        }

        if (_currentEntry?.RemoteOperation is { } remote)
        {
            var key = extension.TrimStart('.');
            if (remote.Files.TryGetValue(key, out var remotePath))
            {
                await DownloadRemoteOutputAsync(remotePath);
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
            return;
        }

        try
        {
            await Launcher.LaunchFileAsync(await StorageFile.GetFileFromPathAsync(path));
        }
        catch (Exception exception)
        {
            if (IsLoaded && view == _jobViewRevision)
            {
                OverviewMessageText.Text = exception.Message;
            }
        }
    }

    private async Task DownloadRemoteOutputAsync(string remotePath)
    {
        var view = _jobViewRevision;
        var extension = Path.GetExtension(remotePath);
        var picker = new FileSavePicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            SuggestedFileName = Path.GetFileName(remotePath),
            CommitButtonText = "下载并打开",
        };
        picker.FileTypeChoices.Add(
            string.IsNullOrWhiteSpace(extension) ? "数据文件" : $"{extension} 文件",
            [string.IsNullOrWhiteSpace(extension) ? ".dat" : extension]);
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        var destination = await picker.PickSaveFileAsync();
        if (destination is null)
        {
            return;
        }
        try
        {
            var operation = await App.Current.ControlPlane.StartRemoteTransferAsync(
                "download",
                remotePath,
                destination.Path,
                overwrite: true);
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
                if (IsLoaded && view == _jobViewRevision)
                {
                    OverviewMessageText.Text = terminal.Error?.Message ?? "远端输出下载失败";
                }
                return;
            }
            if (IsLoaded && view == _jobViewRevision)
            {
                OverviewMessageText.Text = "远端输出已下载";
            }
            await Launcher.LaunchFileAsync(
                await StorageFile.GetFileFromPathAsync(destination.Path));
        }
        catch (Exception exception)
        {
            if (IsLoaded && view == _jobViewRevision)
            {
                OverviewMessageText.Text = exception.Message;
            }
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
        if (!string.IsNullOrWhiteSpace(item.ArchiveDestination)
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
