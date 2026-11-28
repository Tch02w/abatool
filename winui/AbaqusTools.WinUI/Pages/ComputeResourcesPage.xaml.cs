using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Services;
using AbaqusTools.WinUI.Explorer;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class ComputeResourcesPage : Page, IWorkbenchExplorerPage
{
    private readonly DispatcherTimer _remoteRefreshTimer;
    private LocalResourceSnapshot? _localSnapshot;
    private RemoteServersSnapshot _remoteSnapshot = new();
    private string _activeTransferId = string.Empty;
    private bool _transferRecoveryPending = true;
    private bool _transferObservationWarning;
    private CancellationTokenSource _transferObservationSource = new();
    private bool _busy;
    private bool _backgroundRefreshBusy;
    private bool _resourceRowsInitialized;
    private readonly ResourceExplorerAdapter _explorerAdapter;
    private TaskCompletionSource<bool> _menuReady = new(TaskCreationOptions.RunContinuationsAsynchronously);

    public ObservableCollection<ResourceNodeRow> ResourceNodes { get; } = [];

    public ComputeResourcesPage()
    {
        InitializeComponent();
        App.Current.Commands.Changed += UpdateButtons;
        _explorerAdapter = new ResourceExplorerAdapter(
            RefreshSelectedAsync,
            SelectExplorerResource);
        _remoteRefreshTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(10) };
        _remoteRefreshTimer.Tick += OnRemoteRefreshTimerTick;
        ResourceStatusFilter.SelectionChanged += (_, _) => RebuildRows();
        App.Current.Session.Register(this, "compute-resources", [nameof(ResourceStatusFilter)],
            () => WorkbenchSession.WaitForIdleAsync(() => (_busy && string.IsNullOrEmpty(_activeTransferId)) || _backgroundRefreshBusy, "服务器操作"),
            _remoteRefreshTimer.Stop, _remoteRefreshTimer.Start);
        Loaded += OnPageLoaded;
        Unloaded += OnPageUnloaded;
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _explorerAdapter;

    public void ApplySnapshot(LocalResourceSnapshot snapshot)
    {
        _localSnapshot = snapshot;
        LocalStatusText.Text = $"在线 · {snapshot.CapturedAt.ToLocalTime():HH:mm:ss}";
        ToolTipService.SetToolTip(LocalStatusText, null);
        CpuSummaryText.Text = snapshot.CpuDisplay;
        CpuProgress.Value = snapshot.CpuPercent;
        QueueSummaryText.Text = $"队列作业：{snapshot.TotalJobs}";
        RebuildRows();
    }

    public void ShowResourceError(string message)
    {
        UpdateButtons();
        LocalStatusText.Text = "资源读取失败";
        ToolTipService.SetToolTip(LocalStatusText, message);
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        if (_transferObservationSource.IsCancellationRequested)
        {
            _transferObservationSource.Dispose();
            _transferObservationSource = new();
        }
        var ready = _menuReady;
        if (App.Current.MainWindow.LatestLocalResource is { } local)
        {
            ApplySnapshot(local);
        }
        try
        {
            await LoadRemoteSnapshotAsync();
            if (!ReferenceEquals(ready, _menuReady) || !IsLoaded || App.Current.Session.IsClosing) return;
            _remoteRefreshTimer.Start();
            await RecoverTransfersAsync(ready);
        }
        finally
        {
            ready.TrySetResult(ReferenceEquals(ready, _menuReady) && IsLoaded && !_busy && !_transferRecoveryPending);
        }
    }

    public Task<bool> WaitForMenuReadyAsync() => _menuReady.Task.IsCompleted
        ? Task.FromResult(IsLoaded && !_busy && !_transferRecoveryPending)
        : _menuReady.Task.WaitAsync(TimeSpan.FromSeconds(30));

    public bool SelectConnectedServer(string profile)
    {
        if (ResourceStatusFilter.SelectedIndex == 2 && _remoteSnapshot.Connection.Status == "connected"
            && _remoteSnapshot.Connection.ProfileName == profile)
            ResourceStatusFilter.SelectedIndex = 0;
        var row = ResourceNodes.FirstOrDefault(row => row.Key == $"remote:{profile}");
        if (row is null) return false;
        ResourceList.SelectedItem = row;
        return true;
    }

    private void OnPageUnloaded(object sender, RoutedEventArgs e)
    {
        _remoteRefreshTimer.Stop();
        // Stop observing this page; the backend transfer itself keeps running.
        _transferRecoveryPending = true;
        _transferObservationSource.Cancel();
        _menuReady.TrySetResult(false);
        _menuReady = new(TaskCreationOptions.RunContinuationsAsynchronously);
    }

    private async void OnRemoteRefreshTimerTick(object? sender, object e)
    {
        if (!IsLoaded || App.Current.Session.IsClosing || App.Current.Commands.Locked) return;
        if (!_busy && !_backgroundRefreshBusy && _transferRecoveryPending)
        {
            await RecoverTransfersAsync();
            return;
        }
        if (_busy || _backgroundRefreshBusy ||
            (_remoteSnapshot.Connection.Status != "connected" && !_remoteSnapshot.Connection.IsBusy))
        {
            return;
        }
        await RefreshRemoteSnapshotInBackgroundAsync();
    }

    private async Task RefreshRemoteSnapshotInBackgroundAsync()
    {
        if (_busy || _backgroundRefreshBusy)
        {
            return;
        }

        _backgroundRefreshBusy = true;
        App.Current.Commands.SetRemoteRefreshBusy(true);
        var revision = App.Current.Commands.RemoteRevision;
        try
        {
            // While another operation owns the SSH session, observe its published
            // state instead of adding another resource command behind it.
            var observing = _remoteSnapshot.Connection.IsBusy;
            var expected = App.Current.Commands.ConnectedProfile;
            var snapshot = observing || expected is null
                ? await App.Current.ControlPlane.GetRemoteServersAsync(CancellationToken.None)
                : await App.Current.ControlPlane.RefreshRemoteServerForProfileAsync(expected, CancellationToken.None);
            if (revision == App.Current.Commands.RemoteRevision && !_busy)
            {
                ApplyRemoteSnapshot(snapshot);
            }
        }
        catch (OperationCanceledException)
        {
            // Application shutdown cancelled the background refresh.
        }
        catch (Exception exception)
        {
            if (revision == App.Current.Commands.RemoteRevision && !_busy)
                await ShowRemoteActionErrorAsync(exception, notify: false);
        }
        finally
        {
            _backgroundRefreshBusy = false;
            App.Current.Commands.SetRemoteRefreshBusy(false);
        }
    }

    private async void OnRefreshClicked(object sender, RoutedEventArgs e)
    {
        await RefreshSelectedAsync();
    }

    public async Task RefreshSelectedAsync()
    {
        if (_transferRecoveryPending)
        {
            await RecoverTransfersAsync();
            if (_transferRecoveryPending) return;
        }
        var commands = App.Current.Commands;
        if (ResourceList.SelectedItem is null) return;
        if (ResourceList.SelectedItem is ResourceNodeRow { IsLocal: false })
        {
            if (SelectedRemoteProfile() is { } profile) await RefreshConnectedServerAsync(profile);
            return;
        }
        if (!commands.CanRefreshLocal) return;
        await App.Current.MainWindow.RefreshLocalResourceNowAsync(notify: true);
        await LoadRemoteSnapshotAsync();
    }

    public async Task RefreshConnectedServerAsync(RemoteServerProfile expected)
    {
        if (!App.Current.Commands.CanUseSelectedRemote(expected.ProfileName)) return;
        await RunRemoteActionAsync(token => App.Current.ControlPlane.RefreshRemoteServerForProfileAsync(expected, token),
            "远端资源已刷新");
    }

    private async void OnAddServerClicked(object sender, RoutedEventArgs e)
    {
        var draft = await ShowServerDialogAsync(null);
        if (draft is not null)
        {
            await ApplyServerDialogResultAsync(draft);
        }
    }

    private async void OnEditServerClicked(object sender, RoutedEventArgs e)
    {
        if (SelectedRemoteProfile() is not { } profile)
        {
            return;
        }
        var draft = await ShowServerDialogAsync(profile);
        if (draft is not null)
        {
            await ApplyServerDialogResultAsync(draft);
        }
    }

    private async void OnConnectClicked(object sender, RoutedEventArgs e)
    {
        if (SelectedRemoteProfile() is not { } profile)
        {
            return;
        }
        var draft = await ShowServerDialogAsync(profile, connectOnly: true);
        if (draft is not null)
        {
            await ConnectAsync(draft.Profile, draft.Credentials);
        }
    }

    private async void OnDisconnectClicked(object sender, RoutedEventArgs e)
    {
        await DisconnectAsync();
    }

    public async Task DisconnectAsync(RemoteServerProfile? expected = null)
    {
        expected ??= SelectedRemoteProfile();
        if (expected is null || !App.Current.Commands.CanUseSelectedRemote(expected.ProfileName)) return;
        await RunRemoteActionAsync(
            token => App.Current.ControlPlane.DisconnectRemoteServerForProfileAsync(expected, token),
            "远端服务器已断开");
    }

    private async void OnDeleteServerClicked(object sender, RoutedEventArgs e)
    {
        if (SelectedRemoteProfile() is not { } profile)
        {
            return;
        }
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"删除 {profile.ProfileName}？",
            Content = "只删除本机保存的非敏感连接配置，不会改动服务器上的任何文件。",
            PrimaryButtonText = "删除",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return;
        }
        await RunRemoteActionAsync(
            token => App.Current.ControlPlane.DeleteRemoteServerProfileAsync(
                profile.ProfileName,
                token),
            "服务器配置已删除");
    }

    private async void OnBrowseRemoteFilesClicked(object sender, RoutedEventArgs e)
    {
        if (SelectedRemoteProfile() is not { } profile) return;
        var browser = new RemoteFileBrowserDialog(
            XamlRoot,
            RemoteSelectionMode.File,
            "浏览服务器文件", expectedProfile: profile);
        var selection = await browser.ShowAsync(profile.ComputeRoot);
        if (selection is null)
        {
            return;
        }
        RemoteDownloadDestination? destination;
        try
        {
            destination = await RemoteDownloadDestination.PickAsync(XamlRoot, selection.Path, "下载到此处");
        }
        catch (Exception exception)
        {
            ShowError($"无法选择下载位置。{exception.Message}");
            return;
        }
        if (destination is not null)
        {
            await RunTransferAsync("download", selection.Path, destination.Path, destination.Overwrite, profile);
        }
    }

    private static async Task<Windows.Storage.StorageFile?> PickLocalFileAsync(string confirmText)
    {
        var picker = new FileOpenPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = confirmText,
        };
        picker.FileTypeFilter.Add("*");
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        return await picker.PickSingleFileAsync();
    }

    private async void OnUploadRemoteFileClicked(object sender, RoutedEventArgs e)
    {
        if (SelectedRemoteProfile() is not { } profile) return;
        Windows.Storage.StorageFile? source;
        try { source = await PickLocalFileAsync("选择要上传的文件"); }
        catch (Exception exception)
        {
            ShowError($"无法选择上传文件。{exception.Message}");
            return;
        }
        if (source is null)
        {
            return;
        }
        var browser = new RemoteFileBrowserDialog(
            XamlRoot,
            RemoteSelectionMode.Folder,
            "选择服务器目标目录", expectedProfile: profile);
        var selection = await browser.ShowAsync(profile.ComputeRoot);
        if (selection is null)
        {
            return;
        }
        var destination = selection.Path.TrimEnd('\\', '/') + "\\" + source.Name;
        var result = await RunTransferAsync(
            "upload",
            source.Path,
            destination,
            overwrite: false, expectedProfile: profile);
        if (result?.Status == "failed"
            && result.Error?.Message.Contains("已存在", StringComparison.Ordinal) is true
            && await ConfirmOverwriteAsync(destination))
        {
            await RunTransferAsync("upload", source.Path, destination, overwrite: true, expectedProfile: profile);
        }
    }

    private async void OnCancelTransferClicked(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_activeTransferId))
        {
            return;
        }
        CancelTransferButton.IsEnabled = false;
        TransferStatusText.Text = "正在取消文件传输…";
        try
        {
            await App.Current.ControlPlane.CancelRemoteTransferAsync(_activeTransferId);
        }
        catch (Exception exception)
        {
            ShowError(exception.Message);
            CancelTransferButton.IsEnabled = true;
        }
    }

    private async Task<RemoteTransferOperationSnapshot?> RunTransferAsync(
        string direction,
        string source,
        string destination,
        bool overwrite,
        RemoteServerProfile expectedProfile)
    {
        if (_busy)
        {
            return null;
        }
        if (_transferRecoveryPending)
        {
            ShowTransferObservationWarning("请先刷新并核对后台已有传输，避免重复提交。");
            return null;
        }
        _busy = true;
        var observationToken = _transferObservationSource.Token;
        UpdateButtons();
        TransferPanel.Visibility = Visibility.Visible;
        TransferProgressBar.Value = 0;
        TransferStatusText.Text = direction == "upload" ? "正在准备上传…" : "正在准备下载…";
        CancelTransferButton.IsEnabled = true;
        try
        {
            var operation = await App.Current.ControlPlane.StartRemoteTransferAsync(
                direction,
                source,
                destination,
                overwrite, expectedProfile: expectedProfile);
            _activeTransferId = operation.OperationId;
            _transferRecoveryPending = true;
            return await ObserveTransferAsync(operation, observationToken);
        }
        catch (OperationCanceledException) when (observationToken.IsCancellationRequested || App.Current.Session.IsClosing)
        {
            _transferRecoveryPending = true;
            return null;
        }
        catch (ControlPlaneException error) when (string.IsNullOrEmpty(_activeTransferId)
            && error.Code is not null && !error.Retryable)
        {
            _transferRecoveryPending = true;
            TransferStatusText.Text = "传输未开始";
            ShowError(error.Message);
            return null;
        }
        catch (Exception exception)
        {
            // A lost creation reply or a failed read does not establish the
            // transfer's terminal state. Recover by GET, never re-submit it.
            _transferRecoveryPending = true;
            ShowTransferObservationWarning(exception.Message, userInitiated: true);
            return null;
        }
        finally
        {
            _busy = false;
            UpdateButtons();
        }
    }

    private async Task<RemoteTransferOperationSnapshot> ObserveTransferAsync(
        RemoteTransferOperationSnapshot operation, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var direction = operation.Request.Direction;
        TransferPanel.Visibility = Visibility.Visible;
        CancelTransferButton.IsEnabled = true;
        _activeTransferId = operation.OperationId;
        var terminal = operation.IsTerminal ? operation : await App.Current.ControlPlane.PollRemoteTransferUntilTerminalAsync(
            operation.OperationId,
            snapshot =>
            {
                cancellationToken.ThrowIfCancellationRequested();
                TransferProgressBar.Value = snapshot.Progress.Percent;
                TransferStatusText.Text = snapshot.Progress.TotalBytes > 0
                    ? $"{(direction == "upload" ? "上传" : "下载")} {snapshot.Progress.Percent}% · {snapshot.Progress.CompletedBytes:N0} / {snapshot.Progress.TotalBytes:N0} 字节"
                    : direction == "upload" ? "正在上传…" : "正在下载…";
            }, cancellationToken);
        cancellationToken.ThrowIfCancellationRequested();
        _activeTransferId = string.Empty;
        _transferRecoveryPending = false;
        ClearTransferObservationWarning();
        CancelTransferButton.IsEnabled = false;
        if (terminal.Status == "succeeded")
        {
            TransferProgressBar.Value = 100;
            TransferStatusText.Text = direction == "upload" ? "上传完成" : "下载完成";
            ShowInfo(TransferStatusText.Text, InfoBarSeverity.Success);
            App.Current.MainWindow.ReportPageStatus(TransferStatusText.Text);
        }
        else if (terminal.Status == "cancelled")
        {
            TransferStatusText.Text = "文件传输已取消";
            ShowInfo(TransferStatusText.Text, InfoBarSeverity.Warning);
        }
        else
        {
            TransferStatusText.Text = terminal.Error?.Message ?? "文件传输失败";
            ShowError(TransferStatusText.Text);
        }
        return terminal;
    }

    private async Task RecoverTransfersAsync(TaskCompletionSource<bool>? menuReady = null)
    {
        if (_busy || !IsLoaded || App.Current.Session.IsClosing) return;
        var observationToken = _transferObservationSource.Token;
        _busy = true;
        _transferRecoveryPending = true;
        UpdateButtons();
        try
        {
            while (IsLoaded && !App.Current.Session.IsClosing)
            {
                observationToken.ThrowIfCancellationRequested();
                // Query the known identity first: it may have finished while
                // the page was away and therefore be absent from activeOnly.
                var operation = !string.IsNullOrEmpty(_activeTransferId)
                    ? await App.Current.ControlPlane.GetRemoteTransferAsync(_activeTransferId, observationToken)
                    : (await App.Current.ControlPlane.GetActiveRemoteTransfersAsync(observationToken))
                        .Operations.OrderBy(item => item.CreatedAt).FirstOrDefault();
                if (operation is null)
                {
                    _transferRecoveryPending = false;
                    ClearTransferObservationWarning();
                    break;
                }
                // A menu action must not wait behind an active transfer and run after it ends.
                if (!operation.IsTerminal) menuReady?.TrySetResult(false);
                await ObserveTransferAsync(operation, observationToken);
            }
        }
        catch (OperationCanceledException) when (observationToken.IsCancellationRequested || App.Current.Session.IsClosing)
        {
            _transferRecoveryPending = true;
        }
        catch (ControlPlaneException error) when (error.Code == "REMOTE_TRANSFER_NOT_FOUND")
        {
            // Transfers live in one backend instance. A replacement backend
            // cannot establish what the old task saved; keep that uncertainty
            // visible while allowing discovery of its own current operations.
            _activeTransferId = string.Empty;
            _transferRecoveryPending = true;
            CancelTransferButton.IsEnabled = false;
            TransferStatusText.Text = "原传输记录不可用，请核对文件";
            ShowInfo("后台已无原传输记录，无法确认是否完成。请核对原服务器与目标文件；不会自动重传。",
                InfoBarSeverity.Warning, "传输结果待核对");
        }
        catch (Exception error)
        {
            _transferRecoveryPending = true;
            ShowTransferObservationWarning(error.Message);
        }
        finally
        {
            _busy = false;
            UpdateButtons();
        }
    }

    private void ShowTransferObservationWarning(string message, bool userInitiated = false)
    {
        TransferStatusText.Text = "传输状态暂未确认";
        ToolTipService.SetToolTip(TransferStatusText, message);
        if (!_transferObservationWarning && (userInitiated || !string.IsNullOrEmpty(_activeTransferId)))
            ShowInfo("暂时未能读取最新状态，将自动重试查询。\n" + message,
                InfoBarSeverity.Warning, "正在核对传输状态");
        _transferObservationWarning = true;
        CancelTransferButton.IsEnabled = !string.IsNullOrEmpty(_activeTransferId);
    }

    private void ClearTransferObservationWarning()
    {
        if (!_transferObservationWarning) return;
        ToolTipService.SetToolTip(TransferStatusText, null);
        _transferObservationWarning = false;
    }

    private async Task<bool> ConfirmOverwriteAsync(string destination)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "覆盖服务器同名文件？",
            Content = destination,
            PrimaryButtonText = "覆盖并上传",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    private void OnResourceSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        ApplySelection();
    }

    private async Task LoadRemoteSnapshotAsync()
    {
        if (_busy)
        {
            return;
        }
        _busy = true;
        UpdateButtons();
        try
        {
            ApplyRemoteSnapshot(await App.Current.ControlPlane.GetRemoteServersAsync());
        }
        catch (OperationCanceledException)
        {
            // Navigation or application shutdown cancelled the refresh.
        }
        catch (Exception exception)
        {
            App.Current.Commands.InvalidateRemote();
            ShowError(exception.Message);
        }
        finally
        {
            _busy = false;
            UpdateButtons();
        }
    }

    private async Task RunRemoteActionAsync(
        Func<CancellationToken, Task<RemoteServersSnapshot>> action,
        string successMessage,
        bool showSuccess = true)
    {
        if (_busy)
        {
            return;
        }
        _busy = true;
        UpdateButtons();
        try
        {
            ApplyRemoteSnapshot(await action(CancellationToken.None));
            if (showSuccess)
            {
                ShowInfo(successMessage, InfoBarSeverity.Success);
            }
            App.Current.MainWindow.ReportPageStatus(successMessage);
        }
        catch (OperationCanceledException)
        {
            // Application shutdown cancelled the operation.
        }
        catch (Exception exception)
        {
            await ShowRemoteActionErrorAsync(exception);
        }
        finally
        {
            _busy = false;
            UpdateButtons();
        }
    }

    private async Task ShowRemoteActionErrorAsync(Exception original, bool notify = true)
    {
        var message = original.Message;
        try
        {
            ApplyRemoteSnapshot(await App.Current.ControlPlane.GetRemoteServersAsync());
        }
        catch (Exception readError)
        {
            // This is a view error, not a remote job failure or a disconnect.
            message += $"\n连接状态暂无法读取：{readError.Message}";
            ApplyRemoteSnapshot(new RemoteServersSnapshot
            {
                SchemaVersion = _remoteSnapshot.SchemaVersion,
                Profiles = _remoteSnapshot.Profiles,
                ProfilesError = _remoteSnapshot.ProfilesError,
                EventCursor = _remoteSnapshot.EventCursor,
                Connection = new RemoteServerConnection { Status = "error", LastError = message },
            });
        }
        if (notify) ShowError(message);
        else
        {
            RemoteConnectionText.Text = "远端资源刷新失败";
            ToolTipService.SetToolTip(RemoteConnectionText, message);
        }
    }

    private async Task ApplyServerDialogResultAsync(ServerDialogResult result)
    {
        if (result.Connect)
        {
            await ConnectAsync(result.Profile, result.Credentials);
            return;
        }
        await RunRemoteActionAsync(
            token => App.Current.ControlPlane.SaveRemoteServerProfileAsync(
                result.Profile,
                token),
            "服务器配置已保存");
    }

    private async Task ConnectAsync(
        RemoteServerProfile profile,
        RemoteServerCredentials credentials)
    {
        RemoteServersSnapshot? result = null;
        bool keyChanged = false;
        await RunRemoteActionAsync(
            async token =>
            {
                try
                {
                    result = await App.Current.ControlPlane.ConnectRemoteServerAsync(
                        profile, credentials, cancellationToken: token);
                }
                catch (ControlPlaneException error) when (error.Code == "REMOTE_HOST_KEY_CHANGED")
                {
                    var current = await App.Current.ControlPlane.GetRemoteServersAsync(token);
                    if (current.Connection.Status != "error" || current.Connection.ProfileName != profile.ProfileName
                        || string.IsNullOrWhiteSpace(current.Connection.PendingFingerprint))
                        throw;
                    result = current;
                    keyChanged = true;
                }
                return result;
            },
            "正在验证服务器连接",
            showSuccess: false);
        if (result?.Connection.Status == "connected")
        {
            ShowInfo("服务器连接已建立", InfoBarSeverity.Success);
            App.Current.MainWindow.ReportPageStatus("服务器连接已建立");
            return;
        }
        if (result is null || (!keyChanged && result.Connection.Status != "confirmationRequired"))
        {
            return;
        }
        App.Current.MainWindow.ReportPageStatus("请核对服务器主机指纹");

        var fingerprint = result.Connection.PendingFingerprint;
        var confirmation = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = "确认服务器主机指纹",
            Content = new StackPanel
            {
                Spacing = 10,
                Children =
                {
                    new TextBlock
                    {
                        Text = "这是首次连接。请与服务器管理员提供的指纹核对；只有完全一致时才继续。",
                        TextWrapping = TextWrapping.Wrap,
                    },
                    new TextBox
                    {
                        Header = "SHA256 指纹",
                        Text = fingerprint,
                        IsReadOnly = true,
                    },
                },
            },
            PrimaryButtonText = "指纹一致，继续",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        if (keyChanged)
        {
            var verified = new TextBox { Header = "管理员独立提供的 SHA256 指纹", PlaceholderText = "粘贴经其他可信渠道取得的完整指纹" };
            confirmation.Title = "服务器主机密钥已变化";
            confirmation.PrimaryButtonText = "验证并重新连接";
            confirmation.IsPrimaryButtonEnabled = false;
            confirmation.Content = new StackPanel
            {
                Spacing = 8,
                Children =
                {
                    new TextBlock { Text = $"连接 {profile.Username}@{profile.Host}:{profile.Port} 时发现指纹与记录不符。请先向管理员核实密钥更换。", TextWrapping = TextWrapping.Wrap },
                    new TextBox { Header = "已保存的指纹", Text = profile.HostFingerprint, IsReadOnly = true },
                    new TextBox { Header = "本次服务器提供的指纹", Text = fingerprint, IsReadOnly = true },
                    verified,
                },
            };
            verified.TextChanged += (_, _) => confirmation.IsPrimaryButtonEnabled =
                string.Equals(fingerprint, verified.Text.Trim().TrimEnd('='), StringComparison.Ordinal);
        }
        if (await confirmation.ShowAsync() != ContentDialogResult.Primary)
        {
            if (keyChanged)
            {
                await RunRemoteActionAsync(token => App.Current.ControlPlane.CancelHostKeyReviewAsync(
                    profile, fingerprint, token), "已取消重新连接，原主机指纹已保留", showSuccess: false);
            }
            else ShowInfo("服务器主机指纹尚未确认。", InfoBarSeverity.Informational, "已取消首次服务器连接");
            return;
        }

        await RunRemoteActionAsync(
            token => App.Current.ControlPlane.ConnectRemoteServerAsync(
                profile,
                credentials,
                fingerprint,
                cancellationToken: token),
            "服务器指纹已验证并连接");
    }

    private async Task<ServerDialogResult?> ShowServerDialogAsync(
        RemoteServerProfile? existing,
        bool connectOnly = false)
    {
        var profileNameBox = new TextBox
        {
            Header = "配置名称",
            Text = existing?.ProfileName ?? string.Empty,
            PlaceholderText = "例如：计算节点 01",
            IsReadOnly = existing is not null,
        };
        var hostBox = new TextBox
        {
            Header = "主机名或 IP",
            Text = existing?.Host ?? string.Empty,
            PlaceholderText = "192.168.1.20",
        };
        var portBox = new TextBox
        {
            Header = "SSH 端口",
            Text = (existing?.Port ?? 22).ToString(System.Globalization.CultureInfo.InvariantCulture),
            MaxLength = 5,
        };
        var usernameBox = new TextBox
        {
            Header = "用户名",
            Text = existing?.Username ?? string.Empty,
        };
        var authenticationBox = new ComboBox
        {
            Header = "认证方式",
            HorizontalAlignment = HorizontalAlignment.Stretch,
            ItemsSource = new[] { "用户名/密码", "SSH Agent", "SSH 私钥" },
            SelectedItem = existing?.Authentication ?? "用户名/密码",
        };
        var secretBox = new PasswordBox { Header = "密码" };
        var privateKeyBox = new TextBox
        {
            Header = "SSH 私钥路径",
            Text = existing?.PrivateKeyPath ?? string.Empty,
            PlaceholderText = @"C:\Keys\id_ed25519",
        };
        var computeRootBox = new TextBox
        {
            Header = "服务器计算目录",
            Text = existing?.ComputeRoot ?? string.Empty,
            PlaceholderText = @"D:\Abaqus_Cal",
        };
        var allowedRootsBox = new TextBox
        {
            Header = "允许访问的服务器根目录（每行一个）",
            Text = string.Join(Environment.NewLine, existing?.AllowedRoots ?? []),
            AcceptsReturn = true,
            MinHeight = 70,
        };
        var abaqusCommandBox = new TextBox
        {
            Header = "Abaqus 命令",
            Text = existing?.AbaqusCommand ?? "abaqus.bat",
        };
        var fingerprintBox = new TextBox
        {
            Header = "已验证主机指纹",
            Text = existing?.HostFingerprint ?? string.Empty,
            IsReadOnly = true,
            PlaceholderText = "首次连接确认后自动保存",
        };
        var validationText = new TextBlock
        {
            Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[
                "SystemFillColorCriticalBrush"],
            TextWrapping = TextWrapping.Wrap,
            Visibility = Visibility.Collapsed,
        };
        var browsePrivateKey = new Button
        {
            Content = "选择文件…",
            VerticalAlignment = VerticalAlignment.Bottom,
            Height = Controls.ServerDialogLayout.InputHeight,
        };
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(browsePrivateKey, "选择 SSH 私钥文件");
        var privateKeyRow = new Grid { ColumnSpacing = 8 };
        privateKeyRow.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        privateKeyRow.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        privateKeyRow.Children.Add(privateKeyBox);
        Grid.SetColumn(browsePrivateKey, 1);
        privateKeyRow.Children.Add(browsePrivateKey);
        browsePrivateKey.Click += async (_, _) =>
        {
            browsePrivateKey.IsEnabled = false;
            try
            {
                var key = await PickLocalFileAsync("选择 SSH 私钥");
                if (key is not null) privateKeyBox.Text = key.Path;
            }
            catch (Exception exception)
            {
                validationText.Text = $"无法选择私钥文件。{exception.Message}";
                validationText.Visibility = Visibility.Visible;
            }
            finally { browsePrivateKey.IsEnabled = true; }
        };

        void UpdateAuthenticationFields()
        {
            var mode = authenticationBox.SelectedItem?.ToString() ?? "用户名/密码";
            privateKeyRow.Visibility = mode == "SSH 私钥"
                ? Visibility.Visible
                : Visibility.Collapsed;
            secretBox.Visibility = mode == "SSH Agent"
                ? Visibility.Collapsed
                : Visibility.Visible;
            secretBox.Header = mode == "SSH 私钥" ? "私钥口令（如有）" : "密码";
        }
        authenticationBox.SelectionChanged += (_, _) => UpdateAuthenticationFields();
        UpdateAuthenticationFields();

        var panel = new StackPanel { Spacing = 10 };
        panel.Children.Add(profileNameBox);
        panel.Children.Add(Controls.ServerDialogLayout.EndpointRow(hostBox, portBox));
        panel.Children.Add(usernameBox);
        panel.Children.Add(authenticationBox);
        panel.Children.Add(privateKeyRow);
        panel.Children.Add(secretBox);
        panel.Children.Add(computeRootBox);
        panel.Children.Add(allowedRootsBox);
        panel.Children.Add(abaqusCommandBox);
        panel.Children.Add(fingerprintBox);
        panel.Children.Add(validationText);

        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = connectOnly
                ? $"连接 {existing?.ProfileName}"
                : existing is null ? "添加服务器" : "编辑服务器",
            Content = Controls.ServerDialogLayout.Content(panel),
            PrimaryButtonText = connectOnly ? "连接" : "保存并连接",
            SecondaryButtonText = connectOnly ? string.Empty : "仅保存",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Primary,
        };
        Controls.ServerDialogLayout.KeepExistingWidth(dialog);

        dialog.Closing += (_, args) =>
        {
            if (args.Result is not (ContentDialogResult.Primary or ContentDialogResult.Secondary))
            {
                return;
            }
            var errors = new List<string>();
            if (string.IsNullOrWhiteSpace(profileNameBox.Text)) errors.Add("请填写配置名称");
            if (string.IsNullOrWhiteSpace(hostBox.Text)) errors.Add("请填写主机名或 IP");
            if (string.IsNullOrWhiteSpace(usernameBox.Text)) errors.Add("请填写用户名");
            if (!int.TryParse(portBox.Text.Trim(), System.Globalization.NumberStyles.None,
                System.Globalization.CultureInfo.InvariantCulture, out var port) || port is < 1 or > 65535)
            {
                errors.Add("SSH 端口必须是 1–65535 之间的整数");
            }
            var mode = authenticationBox.SelectedItem?.ToString() ?? "用户名/密码";
            if (args.Result == ContentDialogResult.Primary
                && mode == "用户名/密码"
                && string.IsNullOrEmpty(secretBox.Password))
            {
                errors.Add("请输入服务器密码");
            }
            if (mode == "SSH 私钥" && string.IsNullOrWhiteSpace(privateKeyBox.Text))
            {
                errors.Add("请选择或填写 SSH 私钥路径");
            }
            if (errors.Count > 0)
            {
                args.Cancel = true;
                validationText.Text = string.Join("；", errors);
                validationText.Visibility = Visibility.Visible;
            }
        };

        var result = await dialog.ShowAsync();
        if (result == ContentDialogResult.None)
        {
            secretBox.Password = string.Empty;
            return null;
        }
        var mode = authenticationBox.SelectedItem?.ToString() ?? "用户名/密码";
        var profile = new RemoteServerProfile
        {
            ProfileName = profileNameBox.Text.Trim(),
            Host = hostBox.Text.Trim(),
            Port = int.Parse(portBox.Text.Trim(), System.Globalization.CultureInfo.InvariantCulture),
            Username = usernameBox.Text.Trim(),
            Authentication = mode,
            PrivateKeyPath = privateKeyBox.Text.Trim(),
            ComputeRoot = computeRootBox.Text.Trim(),
            AllowedRoots = allowedRootsBox.Text
                .Split(['\r', '\n'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .ToArray(),
            AbaqusCommand = string.IsNullOrWhiteSpace(abaqusCommandBox.Text)
                ? "abaqus.bat"
                : abaqusCommandBox.Text.Trim(),
            HostFingerprint = fingerprintBox.Text.Trim(),
        };
        var credentials = new RemoteServerCredentials
        {
            Password = mode == "用户名/密码" ? secretBox.Password : string.Empty,
            PrivateKeyPassphrase = mode == "SSH 私钥" ? secretBox.Password : string.Empty,
        };
        secretBox.Password = string.Empty;
        return new ServerDialogResult(
            profile,
            credentials,
            result == ContentDialogResult.Primary);
    }

    public void ApplyRemoteSnapshot(RemoteServersSnapshot snapshot)
    {
        _remoteSnapshot = snapshot;
        RemoteSummaryText.Text = $"{snapshot.Profiles.Count} 个配置";
        RemoteConnectionText.Text = snapshot.Connection.DisplayText;
        ToolTipService.SetToolTip(RemoteConnectionText, null);
        if (!string.IsNullOrWhiteSpace(snapshot.ProfilesError))
        {
            RemoteSummaryText.Text = "服务器配置读取失败";
        }
        ToolTipService.SetToolTip(RemoteSummaryText, snapshot.ProfilesError);
        App.Current.MainWindow.ApplyRemoteServerSnapshot(snapshot);
        RebuildRows();
    }

    private void RebuildRows()
    {
        var selectedKey = _resourceRowsInitialized ? (ResourceList.SelectedItem as ResourceNodeRow)?.Key : "local";
        _resourceRowsInitialized = true;
        var incoming = new List<ResourceNodeRow> { ResourceNodeRow.FromLocal(_localSnapshot) };
        foreach (var profile in _remoteSnapshot.Profiles)
        {
            var connected = _remoteSnapshot.Connection.Status == "connected" && string.Equals(
                _remoteSnapshot.Connection.ProfileName,
                profile.ProfileName,
                StringComparison.Ordinal);
            incoming.Add(ResourceNodeRow.FromRemote(profile, connected, connected ? _remoteSnapshot.Connection.Resource : null));
        }
        var filter = (ResourceStatusFilter.SelectedItem as ComboBoxItem)?.Tag as string;
        if (filter == "online") incoming.RemoveAll(row => !row.IsConnected);
        if (filter == "offline") incoming.RemoveAll(row => row.IsLocal || row.IsConnected);
        for (var i = 0; i < incoming.Count; i++)
        {
            var next = incoming[i];
            if (i == ResourceNodes.Count) ResourceNodes.Add(next);
            else
            {
                var previous = ResourceNodes[i];
                if (next.ActiveJobs.SequenceEqual(previous.ActiveJobs)) next.ActiveJobs = previous.ActiveJobs;
                if (previous != next) ResourceNodes[i] = next;
            }
        }
        while (ResourceNodes.Count > incoming.Count) ResourceNodes.RemoveAt(ResourceNodes.Count - 1);
        ResourceList.SelectedItem = ResourceNodes.FirstOrDefault(item => item.Key == selectedKey);
        NoMatchingResourcesText.Visibility = ResourceNodes.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        ApplySelection();
        UpdateExplorer();
    }

    private void UpdateExplorer()
    {
        var local = ResourceNodes.Where(row => row.IsLocal).Select(ResourceItem).ToArray();
        var remote = ResourceNodes.Where(row => !row.IsLocal).Select(ResourceItem).ToArray();
        _explorerAdapter.Update(
            _remoteSnapshot.Connection.Status == "connected"
                ? $"已连接 · {_remoteSnapshot.Connection.ProfileName}"
                : "本机与已保存服务器",
            $"本机 {local.Length} · 远端 {remote.Length}",
            [
                WorkbenchExplorerAdapterBase.Group("resources:local", "本机", local, local.Length.ToString()),
                WorkbenchExplorerAdapterBase.Group("resources:remote", "远端服务器", remote, remote.Length.ToString()),
            ]);
    }

    private static ExplorerItem ResourceItem(ResourceNodeRow row)
    {
        var item = new ExplorerItem
        {
            StableId = $"resource:{row.Key}",
            Kind = ExplorerItemKind.ResourceNode,
            EntityId = row.Key,
            Title = row.Name,
            Subtitle = $"{row.StatusDisplay} · CPU {row.CpuDisplay} · 内存 {row.MemoryDisplay}",
            Status = row.StatusDisplay,
            Badge = row.StatusDisplay,
            Path = row.ComputeRoot,
            IconGlyph = row.IsLocal ? "\uE770" : "\uE968",
        };
        foreach (var job in row.ActiveJobs)
        {
            item.Children.Add(new ExplorerItem
            {
                StableId = $"resource:{row.Key}:job:{job}",
                Kind = ExplorerItemKind.RemoteJob,
                Title = job,
                Subtitle = "活动作业",
                IconGlyph = "\uE9D5",
            });
        }
        return item;
    }

    private void SelectExplorerResource(ExplorerItem item)
    {
        if (item.Kind != ExplorerItemKind.ResourceNode)
        {
            return;
        }
        ResourceList.SelectedItem = ResourceNodes.FirstOrDefault(row =>
            string.Equals(row.Key, item.EntityId, StringComparison.Ordinal));
        ApplySelection();
    }

    private void ApplySelection()
    {
        if (ResourceList.SelectedItem is not ResourceNodeRow row)
        {
            DetailNameText.Text = "请选择资源";
            DetailEndpointText.Text = string.Empty;
            ResourceDetailFields.Visibility = Visibility.Collapsed;
            UpdateButtons();
            return;
        }
        ResourceDetailFields.Visibility = Visibility.Visible;
        DetailNameText.Text = row.Name;
        DetailEndpointText.Text = row.Endpoint;
        DetailStatusText.Text = row.StatusDisplay;
        DetailCpuText.Text = row.CpuDisplay;
        DetailMemoryText.Text = row.MemoryDisplay;
        DetailQueueText.Text = row.QueueDisplay;
        DetailRootText.Text = string.IsNullOrWhiteSpace(row.ComputeRoot)
            ? "尚未配置"
            : row.ComputeRoot;
        DetailAbaqusText.Text = row.AbaqusDisplay;
        DetailFingerprintText.Text = string.IsNullOrWhiteSpace(row.Fingerprint)
            ? "—"
            : row.Fingerprint;
        DetailUpdatedText.Text = row.UpdatedDisplay;
        DetailJobsText.Text = row.ActiveJobs.Count == 0
            ? "无"
            : string.Join("、", row.ActiveJobs);
        UpdateButtons();
    }

    private RemoteServerProfile? SelectedRemoteProfile()
    {
        var key = (ResourceList.SelectedItem as ResourceNodeRow)?.Key;
        return _remoteSnapshot.Profiles.FirstOrDefault(profile =>
            string.Equals($"remote:{profile.ProfileName}", key, StringComparison.Ordinal));
    }

    private void UpdateButtons()
    {
        var commands = App.Current.Commands;
        commands.SetResourceBusy(_busy);
        var row = ResourceList.SelectedItem as ResourceNodeRow;
        var isRemote = row is { IsLocal: false };
        var connected = commands.CanUseSelectedRemote(SelectedRemoteProfile()?.ProfileName);
        RefreshButton.IsEnabled = row is not null && (isRemote ? connected : commands.CanRefreshLocal);
        AddServerButton.IsEnabled = !_busy;
        ConnectButton.IsEnabled = !_busy && isRemote && row is { IsConnected: false };
        EditButton.IsEnabled = !_busy && isRemote;
        DisconnectButton.IsEnabled = connected;
        DeleteButton.IsEnabled = !_busy && isRemote && row is { IsConnected: false };
        BrowseFilesButton.IsEnabled = !_busy && !_transferRecoveryPending && row is { IsLocal: false, IsConnected: true };
        UploadFileButton.IsEnabled = !_busy && !_transferRecoveryPending && row is { IsLocal: false, IsConnected: true };
    }

    private void ShowError(string message)
    {
        ShowInfo(message, InfoBarSeverity.Error, "资源操作失败");
        App.Current.MainWindow.ReportPageStatus("计算资源操作失败");
    }

    private void ShowInfo(
        string message,
        InfoBarSeverity severity,
        string title = "计算资源")
    {
        App.Current.MainWindow.ShowFeedback(title, message, severity);
    }

    private sealed record ServerDialogResult(
        RemoteServerProfile Profile,
        RemoteServerCredentials Credentials,
        bool Connect);
}

public sealed record ResourceNodeRow
{
    public string Key { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string Endpoint { get; set; } = string.Empty;
    public string StatusDisplay { get; set; } = string.Empty;
    public string CpuDisplay { get; set; } = "未获取";
    public string MemoryDisplay { get; set; } = "未获取";
    public string QueueDisplay { get; set; } = "0 / 0";
    public string ComputeRoot { get; set; } = string.Empty;
    public string AbaqusDisplay { get; set; } = string.Empty;
    public string Fingerprint { get; set; } = string.Empty;
    public string UpdatedDisplay { get; set; } = "—";
    public IReadOnlyList<string> ActiveJobs { get; set; } = [];
    public bool IsLocal { get; set; }
    public bool IsConnected { get; set; }

    public static ResourceNodeRow FromLocal(LocalResourceSnapshot? snapshot) =>
        snapshot is null
            ? new ResourceNodeRow
            {
                Key = "local",
                Name = "本机",
                Endpoint = Environment.MachineName,
                StatusDisplay = "等待数据",
                IsLocal = true,
            }
            : new ResourceNodeRow
            {
                Key = "local",
                Name = "本机",
                Endpoint = Environment.MachineName,
                StatusDisplay = "在线",
                CpuDisplay = snapshot.CpuDisplay,
                MemoryDisplay = snapshot.MemoryDisplay,
                QueueDisplay = $"{snapshot.RunningJobs} / {snapshot.WaitingJobs}",
                AbaqusDisplay = snapshot.AbaqusDisplay,
                UpdatedDisplay = snapshot.CapturedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss"),
                ActiveJobs = snapshot.ActiveJobs,
                IsLocal = true,
                IsConnected = true,
            };

    public static ResourceNodeRow FromRemote(
        RemoteServerProfile profile,
        bool connected,
        RemoteResourceSnapshot? resource) =>
        new()
        {
            Key = $"remote:{profile.ProfileName}",
            Name = profile.ProfileName,
            Endpoint = $"{profile.Username}@{profile.Host}:{profile.Port}",
            StatusDisplay = connected ? "在线" : "未连接",
            CpuDisplay = resource?.CpuDisplay ?? "未获取",
            MemoryDisplay = resource?.MemoryDisplay ?? "未获取",
            QueueDisplay = resource is null
                ? "—"
                : $"{resource.RunningJobs} / {resource.WaitingJobs}",
            ComputeRoot = resource?.ComputeRoot ?? profile.ComputeRoot,
            AbaqusDisplay = resource is null
                ? profile.AbaqusCommand
                : resource.AbaqusCommandAvailable
                    ? $"{resource.AbaqusCommand} · 可用"
                    : $"{resource.AbaqusCommand} · 未发现",
            Fingerprint = resource?.HostFingerprint ?? profile.HostFingerprint,
            UpdatedDisplay = resource is null || resource.UpdatedAt == default
                ? "—"
                : resource.UpdatedAt.ToLocalTime().ToString("yyyy-MM-dd HH:mm:ss"),
            ActiveJobs = resource?.ActiveJobs ?? [],
            IsConnected = connected,
        };
}
