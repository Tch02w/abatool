using AbaqusTools.WinUI.Pages;
using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using System.Runtime.InteropServices;
using Windows.Graphics;

namespace AbaqusTools.WinUI;

public sealed partial class MainWindow : Window
{
    private static readonly IReadOnlyDictionary<string, (string Title, Type PageType, string Status)>
        WorkbenchPages = new Dictionary<string, (string, Type, string)>(StringComparer.Ordinal)
        {
            ["new-job"] = ("新建作业", typeof(NewJobPage), "配置 Abaqus 作业输入与运行参数"),
            ["job-queue"] = ("作业队列", typeof(JobQueuePage), "管理候选作业与正式调度队列"),
            ["job-overview"] = ("作业概览", typeof(JobOverviewPage), "查看作业状态、输出与运行日志"),
            ["compute-resources"] = ("计算资源", typeof(ComputeResourcesPage), "查看本机与远端计算资源"),
            ["restart-chain"] = ("重启动链", typeof(RestartChainPage), "查看和校验重启动依赖关系"),
            ["odb-merge"] = ("ODB 合并", typeof(OdbMergePage), "配置并验证 ODB 合并"),
        };

    private readonly ControlPlaneHost _controlPlane;
    private readonly DispatcherTimer _resourceTimer;
    private readonly ProjectExplorerAdapter _fallbackExplorerAdapter;
    private bool _resourceRefreshBusy;
    private bool _shutdownStarted;
    private bool _shutdownComplete;
    private bool _windowClosed;
    private bool _updatingSizeLimits;
    private double _restoredFrameWidthDip;
    private double _restoredFrameHeightDip;
    private XamlRoot? _sizeLimitXamlRoot;

    public LocalResourceSnapshot? LatestLocalResource { get; private set; }

    public MainWindow(ControlPlaneHost controlPlane)
    {
        InitializeComponent();
        App.Current.Commands.Changed += UpdateCommandMenus;
        _controlPlane = controlPlane;
        _fallbackExplorerAdapter = new ProjectExplorerAdapter(
            controlPlane,
            ActivateFallbackExplorerItemAsync);
        _resourceTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(3) };
        _draftTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(2) };
        _sessionEnd = new SystemSessionEndState(SaveForSystemSessionEnd, TimeSpan.FromSeconds(2));
        _resourceTimer.Tick += OnResourceTimerTick;
        _controlPlane.StateChanged += OnControlPlaneStateChanged;
        Closed += OnWindowClosed;
        AppWindow.Closing += OnAppWindowClosing;
        Title = "Abaqus Tools — WinUI 3";
        ConfigureTitleBar();
        AppWindow.Changed += OnAppWindowChanged;
        UpdateWindowSizeLimits();
        RestoreWindowState();
        UpdateTitleBarInsets();
    }

    internal void RestoreWorkspace()
    {
        ApplyExplorerVisibility();
        // Explorer attachment can synchronously call page code that needs App.MainWindow.
        // App must publish this fully constructed window before restoring any page.
        SelectRoute(App.Current.Session.State.LastRoute);
        if (ContentFrame.Content is null)
        {
            NavigateTo("new-job");
        }
        InitializeSessionSaving();
        if (App.Current.Session.LoadError is { } error)
            ShowFeedback("工作台配置读取提示", error, InfoBarSeverity.Warning);
    }

    public void ShowFeedback(string title, string message, InfoBarSeverity severity = InfoBarSeverity.Informational)
    {
        if (!DispatcherQueue.HasThreadAccess)
        {
            DispatcherQueue.TryEnqueue(() => ShowFeedback(title, message, severity));
            return;
        }
        if (!_windowClosed) FeedbackHost.Show(title, message, severity);
    }

    public void ReportPageStatus(string message)
    {
        var status = string.IsNullOrWhiteSpace(message) ? "就绪" : message;
        PageStatusText.Text = status;
    }

    public void ApplyRemoteServerSnapshot(RemoteServersSnapshot snapshot)
    {
        App.Current.Commands.ApplyRemote(snapshot);
        RemoteStatusText.Text = snapshot.Connection.StatusBarText;
        RemoteStatusText.Foreground = snapshot.Connection.Status == "connected" && !snapshot.Connection.IsBusy
            ? (Brush)Application.Current.Resources["AbaqusSuccessBrush"]
            : (Brush)Application.Current.Resources["TextFillColorSecondaryBrush"];
    }

    public async Task OpenResultBrowserAsync(string root)
    {
        SelectRoute("result-browser");
        if (ContentFrame.Content is not ResultBrowserPage page)
        {
            NavigateTo("result-browser");
            page = ContentFrame.Content as ResultBrowserPage
                ?? throw new InvalidOperationException("结果浏览页面未能创建。");
        }

        await page.SetResultRootAsync(root);
    }

    public async Task RefreshLocalResourceNowAsync(bool notify = false)
    {
        if (_resourceRefreshBusy || _shutdownStarted)
        {
            return;
        }

        _resourceRefreshBusy = true;
        App.Current.Commands.SetLocalRefreshBusy(true);
        try
        {
            var snapshot = await _controlPlane.GetLocalResourceAsync();
            LatestLocalResource = snapshot;
            ApplyLocalResourceSnapshot(snapshot);
            if (notify) ShowFeedback("本机资源已刷新", LocalResourceStatusText.Text, InfoBarSeverity.Success);
        }
        catch (OperationCanceledException)
        {
            // Safe shutdown or a superseding lifecycle transition cancelled polling.
        }
        catch (Exception exception)
        {
            LocalResourceStatusText.Text = "本机资源不可用";
            if (notify) ShowFeedback("本机资源刷新失败", exception.Message, InfoBarSeverity.Error);
            if (ContentFrame.Content is ComputeResourcesPage page)
            {
                page.ShowResourceError(exception.Message);
            }
        }
        finally
        {
            _resourceRefreshBusy = false;
            App.Current.Commands.SetLocalRefreshBusy(false);
        }

    }

    private void ApplyLocalResourceSnapshot(LocalResourceSnapshot snapshot)
    {
        LocalResourceStatusText.Text =
            $"本机 CPU {snapshot.BusyCpus}/{snapshot.LogicalCpus} · 内存 {snapshot.MemoryPercent:0}%";
        QueueStatusText.Text =
            $"队列 {snapshot.TotalJobs} · 运行 {snapshot.RunningJobs} · 等待 {snapshot.WaitingJobs}";
        AbaqusStatusText.Text = snapshot.AbaqusAvailable
            ? string.IsNullOrWhiteSpace(snapshot.AbaqusRelease)
                ? "Abaqus ● 可用"
                : $"Abaqus ● {snapshot.AbaqusRelease}"
            : "Abaqus △ 未发现";
        AbaqusStatusText.Foreground = snapshot.AbaqusAvailable
            ? (Brush)Application.Current.Resources["AbaqusSuccessBrush"]
            : (Brush)Application.Current.Resources["AbaqusWarningBrush"];
        if (ContentFrame.Content is ComputeResourcesPage page)
        {
            page.ApplySnapshot(snapshot);
        }
    }

    public void UpdateSelectedInputPath(string path)
    {
        _fallbackExplorerAdapter.UsePath(path);
    }

    private async void OnResourceTimerTick(object? sender, object e)
    {
        if (App.Current.Session.IsClosing) return;
        await Task.WhenAll(RefreshLocalResourceNowAsync(), RefreshJobNotificationsAsync(), RefreshCommandSnapshotsAsync());
    }

    private async void OnRootLoaded(object sender, RoutedEventArgs e)
    {
        if (Content.XamlRoot is { } xamlRoot && _sizeLimitXamlRoot != xamlRoot)
        {
            if (_sizeLimitXamlRoot is not null)
            {
                _sizeLimitXamlRoot.Changed -= OnWindowXamlRootChanged;
            }
            _sizeLimitXamlRoot = xamlRoot;
            _sizeLimitXamlRoot.Changed += OnWindowXamlRootChanged;
        }
        UpdateWindowSizeLimits();
        try
        {
            await _controlPlane.EnsureReadyAsync();
            await RefreshLocalResourceNowAsync();
            await RefreshJobNotificationsAsync();
            await RefreshCommandSnapshotsAsync();
            if (!App.Current.Session.IsClosing) _resourceTimer.Start();
        }
        catch (ControlPlaneException exception)
        {
            ShowFeedback("本地控制面不可用", exception.ToDisplayMessage(), InfoBarSeverity.Error);
        }
        catch (OperationCanceledException)
        {
            // Window shutdown cancels an in-flight local control-plane startup.
        }
    }

    private void OnNavigationSelectionChanged(
        NavigationView sender,
        NavigationViewSelectionChangedEventArgs args)
    {
        if (args.SelectedItemContainer?.Tag is string route)
        {
            NavigateTo(route);
        }
    }

    private void NavigateTo(string route)
    {
        if (_shutdownStarted || App.Current.Session.IsResettingNewJob) return;
        if (route is "odb-postprocessing" or "result-browser" || WorkbenchPages.ContainsKey(route))
            App.Current.Session.State.LastRoute = route;
        if (route == "odb-postprocessing")
        {
            WindowTitleText.Text = "Abaqus Workbench — ODB 后处理";
            ReportPageStatus("选择目录以发现 ODB 文件");
            if (ContentFrame.CurrentSourcePageType != typeof(OdbPostprocessingPage))
            {
                ContentFrame.Navigate(typeof(OdbPostprocessingPage));
            }
            AttachExplorerForCurrentPage();
            return;
        }

        if (route == "result-browser")
        {
            WindowTitleText.Text = "Abaqus Workbench — 结果浏览";
            if (ContentFrame.CurrentSourcePageType != typeof(ResultBrowserPage))
            {
                ContentFrame.Navigate(typeof(ResultBrowserPage));
            }
            AttachExplorerForCurrentPage();
            if (ContentFrame.Content is ResultBrowserPage page) ReportPageStatus(page.StatusBarMessage);
            return;
        }

        if (!WorkbenchPages.TryGetValue(route, out var descriptor))
        {
            return;
        }

        WindowTitleText.Text = $"Abaqus Workbench — {descriptor.Title}";
        ReportPageStatus(descriptor.Status);
        if (ContentFrame.CurrentSourcePageType != descriptor.PageType)
        {
            ContentFrame.Navigate(descriptor.PageType);
        }
        if (ContentFrame.Content is ComputeResourcesPage resourcePage
            && LatestLocalResource is not null)
        {
            resourcePage.ApplySnapshot(LatestLocalResource);
        }
        AttachExplorerForCurrentPage();
    }

    private void AttachExplorerForCurrentPage()
    {
        var adapter = (ContentFrame.Content as IWorkbenchExplorerPage)?.ExplorerAdapter
            ?? _fallbackExplorerAdapter;
        ExplorerHost.Attach(adapter, refreshOnAttach: ContentFrame.Content is not ResultBrowserPage { HasLoadedDirectory: true });
    }

    private async Task ActivateFallbackExplorerItemAsync(ExplorerItem item)
    {
        if (item.Kind == ExplorerItemKind.QueueJob && !string.IsNullOrWhiteSpace(item.EntityId))
        {
            NavigateToQueueItem(item.EntityId);
            return;
        }
        if (item.Kind == ExplorerItemKind.RestartChain && !string.IsNullOrWhiteSpace(item.EntityId))
        {
            NavigateToQueueItem(item.EntityId);
            return;
        }
        if (item.Kind == ExplorerItemKind.InputFile)
        {
            NavigateToRoute("new-job");
            if (ContentFrame.Content is NewJobPage newJobPage)
            {
                newJobPage.LoadInputPath(item.Path);
            }
            return;
        }
        if (item.Kind == ExplorerItemKind.OdbFile)
        {
            NavigateToRoute("odb-postprocessing");
            if (ContentFrame.Content is OdbPostprocessingPage postprocessingPage)
            {
                await postprocessingPage.LoadOdbPathAsync(item.Path,
                    () => !App.Current.Commands.Locked && ReferenceEquals(ContentFrame.Content, postprocessingPage));
            }
        }
    }

    public void NavigateToRoute(string route)
    {
        if (_shutdownStarted || App.Current.Session.IsResettingNewJob) return;
        var item = ShellNavigation.MenuItems
            .OfType<NavigationViewItem>()
            .FirstOrDefault(entry => string.Equals(entry.Tag?.ToString(), route, StringComparison.Ordinal));
        if (item is not null)
        {
            ShellNavigation.SelectedItem = item;
        }
        NavigateTo(route);
    }

    public void NavigateToQueueItem(string itemId)
    {
        NavigateToRoute("job-queue");
        if (ContentFrame.Content is JobQueuePage page)
        {
            page.SelectFormalItem(itemId);
        }
    }

    public void NavigateToJobOverview(string key)
    {
        NavigateToRoute("job-overview");
        if (ContentFrame.Content is JobOverviewPage page)
        {
            page.SelectJob(key);
        }
    }

    public void NavigateToOdbMergePlan(RestartResultPlan plan)
    {
        NavigateToRoute("odb-merge");
        if (ContentFrame.Content is OdbMergePage page)
        {
            page.LoadMaterializationPlan(plan);
        }
    }

    private void SelectRoute(string route)
    {
        if (_shutdownStarted || App.Current.Session.IsResettingNewJob) return;
        var item = ShellNavigation.MenuItems
            .OfType<NavigationViewItem>()
            .FirstOrDefault(candidate => string.Equals(candidate.Tag as string, route, StringComparison.Ordinal));
        if (item is not null)
        {
            ShellNavigation.SelectedItem = item;
        }
    }

    private async void OnNewJobMenuClicked(object sender, RoutedEventArgs args)
    {
        var session = App.Current.Session;
        if (_shutdownStarted || _sessionEnd.IsEnding || session.IsResettingNewJob) return;
        var page = session.GetRestoredPage(NewJobDraftReset.Route) as NewJobPage;
        if (page?.IsDraftBusy is true)
        {
            ReportPageStatus("请等待作业提交或命令预览结束后再新建");
            return;
        }
        var focusNewJob = false;
        SetCloseInteractionEnabled(false);
        try
        {
            var result = await session.ResetNewJobAsync(CaptureWindowState(), async () =>
            {
                var dialog = new ContentDialog
                {
                    XamlRoot = Content.XamlRoot, Title = "新建作业",
                    Content = CloseText("清空当前作业名称、INP、重启动依赖和子程序路径，并回到本机执行？\n\nCPU、内存等常用设置会保留，已有队列和运行任务不受影响。"),
                    PrimaryButtonText = "清空并新建", CloseButtonText = "保留当前填写",
                    DefaultButton = ContentDialogButton.Close,
                };
                return await dialog.ShowAsync() == ContentDialogResult.Primary;
            }, () => page?.ApplyNewJobReset(),
                () => !_shutdownStarted && !_sessionEnd.IsEnding && page?.IsDraftBusy is not true);
            if (_sessionEnd.IsEnding) return;
            if (result == NewJobResetResult.Completed)
            {
                UpdateSelectedInputPath(string.Empty);
                NavigateToRoute(NewJobDraftReset.Route);
                focusNewJob = true;
                ReportPageStatus("已新建作业 · 常用资源设置已保留");
            }
            else ReportPageStatus(result == NewJobResetResult.Cancelled ? "已保留当前填写" : "当前操作尚未结束，请稍后新建");
        }
        catch (Exception error)
        {
            if (_sessionEnd.IsEnding) return;
            ShowDraftSaveError(error.Message);
            ReportPageStatus("新建未完成 · 请检查草稿保存错误");
        }
        finally
        {
            if (!_shutdownStarted && !_windowClosed && !_sessionEnd.IsEnding)
            {
                SetCloseInteractionEnabled(true);
                if (focusNewJob && ContentFrame.Content is NewJobPage newPage) newPage.FocusNewJobInput();
            }
        }
    }

    private void OnQueueMenuClicked(object sender, RoutedEventArgs args)
    {
        SelectRoute("job-queue");
    }

    private async void OnStartQueueMenuClicked(object sender, RoutedEventArgs args)
    {
        await RunQueueMenuAsync(() => App.Current.Commands.CanStartQueue, page => page.StartQueueAsync());
    }

    private async void OnStopQueueMenuClicked(object sender, RoutedEventArgs args)
    {
        await RunQueueMenuAsync(() => App.Current.Commands.CanStopQueue, page => page.StopQueueAsync());
    }

    private async void OnTerminateQueueMenuClicked(object sender, RoutedEventArgs args)
    {
        var selected = App.Current.Commands.SelectedActiveIds.ToHashSet(StringComparer.Ordinal);
        await RunQueueMenuAsync(() => App.Current.Commands.CanTerminateSelected
            && selected.SetEquals(App.Current.Commands.SelectedActiveIds), page => page.TerminateSelectedAsync());
    }

    private void OnComputeResourcesMenuClicked(object sender, RoutedEventArgs args)
    {
        NavigateToRoute("compute-resources");
    }

    private async void OnRefreshResourcesMenuClicked(object sender, RoutedEventArgs args)
    {
        await RunRemoteMenuAsync(disconnect: false);
    }

    private async void OnDisconnectServerMenuClicked(object sender, RoutedEventArgs args)
    {
        await RunRemoteMenuAsync(disconnect: true);
    }

    private void OnPostprocessingMenuClicked(object sender, RoutedEventArgs args)
    {
        SelectRoute("odb-postprocessing");
    }

    private async void OnResultBrowserMenuClicked(object sender, RoutedEventArgs args)
    {
        await OpenResultsFromCurrentPageAsync();
    }

    private Task OpenResultsFromCurrentPageAsync()
    {
        if (_shutdownStarted || App.Current.Commands.Locked) return Task.CompletedTask;
        if (ContentFrame.Content is OdbPostprocessingPage postprocessing)
            return postprocessing.OpenResultsAsync();
        SelectRoute("result-browser");
        return Task.CompletedTask;
    }

    private void OnPostprocessingAcceleratorInvoked(
        KeyboardAccelerator sender,
        KeyboardAcceleratorInvokedEventArgs args)
    {
        SelectRoute("odb-postprocessing");
        args.Handled = true;
    }

    private async void OnResultBrowserAcceleratorInvoked(
        KeyboardAccelerator sender,
        KeyboardAcceleratorInvokedEventArgs args)
    {
        args.Handled = true;
        await OpenResultsFromCurrentPageAsync();
    }

    private async void OnExitMenuClicked(object sender, RoutedEventArgs args)
    {
        await RequestCloseAsync();
    }

    private void ConfigureTitleBar()
    {
        if (!AppWindowTitleBar.IsCustomizationSupported())
        {
            return;
        }

        ExtendsContentIntoTitleBar = true;
        SetTitleBar(TitleBarDragRegion);
        UpdateTitleBarInsets();
    }

    private void UpdateTitleBarInsets()
    {
        if (!AppWindowTitleBar.IsCustomizationSupported())
        {
            return;
        }
        var scale = GetWindowScale();
        TitleBarLeftInsetColumn.Width = new GridLength(AppWindow.TitleBar.LeftInset / scale);
        TitleBarRightInsetColumn.Width = new GridLength(AppWindow.TitleBar.RightInset / scale);
    }

    private void OnAppWindowChanged(AppWindow sender, AppWindowChangedEventArgs args)
    {
        if (args.DidPositionChange || args.DidSizeChange || args.DidPresenterChange)
        {
            UpdateWindowSizeLimits();
            UpdateTitleBarInsets();
            RememberRestoredWindowBounds();
        }
    }

    private void OnWindowXamlRootChanged(XamlRoot sender, XamlRootChangedEventArgs args)
    {
        UpdateWindowSizeLimits();
        UpdateTitleBarInsets();
    }

    private double GetWindowScale()
    {
        // The HWND's DPI is valid before XamlRoot is loaded and changes when crossing monitors.
        var dpi = GetDpiForWindow(WinRT.Interop.WindowNative.GetWindowHandle(this));
        return dpi > 0 ? dpi / 96d : Content.XamlRoot?.RasterizationScale ?? 1d;
    }

    private void UpdateWindowSizeLimits()
    {
        if (_windowClosed || _updatingSizeLimits
            || AppWindow.Presenter is not OverlappedPresenter presenter)
        {
            return;
        }
        var display = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Nearest);
        if (display is null || display.WorkArea.Width <= 0 || display.WorkArea.Height <= 0)
        {
            return;
        }

        _updatingSizeLimits = true;
        try
        {
            var scale = GetWindowScale();
            if (presenter.State == OverlappedPresenterState.Restored
                && AppWindow.ClientSize.Width > 0 && AppWindow.ClientSize.Height > 0)
            {
                // Measure the real restored nonclient area after custom title-bar setup.
                // Maximized/minimized geometry must never replace this restored-frame measurement.
                _restoredFrameWidthDip = Math.Max(0, AppWindow.Size.Width - AppWindow.ClientSize.Width) / scale;
                _restoredFrameHeightDip = Math.Max(0, AppWindow.Size.Height - AppWindow.ClientSize.Height) / scale;
            }
            var navigationHeight = Math.Max(WindowLayoutConstraints.DefaultNavigationHeight,
                ShellNavigation.ActualHeight - ContentFrame.ActualHeight);
            var minimum = WindowLayoutConstraints.MinimumOuterSize(scale,
                _restoredFrameWidthDip, _restoredFrameHeightDip,
                display.WorkArea.Width, display.WorkArea.Height, navigationHeight,
                explorerVisible: App.Current.Session.State.ExplorerVisible);
            if (presenter.PreferredMinimumWidth != minimum.Width)
            {
                presenter.PreferredMinimumWidth = minimum.Width;
            }
            if (presenter.PreferredMinimumHeight != minimum.Height)
            {
                presenter.PreferredMinimumHeight = minimum.Height;
            }
            if (presenter.State == OverlappedPresenterState.Restored)
            {
                var clamped = WindowLayoutConstraints.ClampToMinimum(
                    AppWindow.Size.Width, AppWindow.Size.Height, minimum);
                if (clamped.Width != AppWindow.Size.Width || clamped.Height != AppWindow.Size.Height)
                {
                    AppWindow.Resize(new SizeInt32(clamped.Width, clamped.Height));
                }
            }
        }
        finally
        {
            _updatingSizeLimits = false;
        }
    }

    [DllImport("user32.dll", ExactSpelling = true)]
    private static extern uint GetDpiForWindow(IntPtr window);

    private void OnControlPlaneStateChanged(object? sender, ControlPlaneStateChangedEventArgs args)
    {
        DispatcherQueue.TryEnqueue(() =>
        {
            ControlPlaneStatusText.Text = args.State switch
            {
                ControlPlaneState.Ready => "控制面 ● 已连接",
                ControlPlaneState.Connecting => "控制面 ◌ 连接中",
                ControlPlaneState.Starting => "控制面 ◌ 启动中",
                ControlPlaneState.Error => "控制面 × 错误",
                _ => "控制面 ○ 未连接",
            };

            ControlPlaneStatusText.Foreground = args.State switch
            {
                ControlPlaneState.Ready => (Brush)Application.Current.Resources["AbaqusSuccessBrush"],
                ControlPlaneState.Error => (Brush)Application.Current.Resources["AbaqusErrorBrush"],
                ControlPlaneState.Starting or ControlPlaneState.Connecting
                    => (Brush)Application.Current.Resources["AbaqusWarningBrush"],
                _ => (Brush)Application.Current.Resources["AbaqusMutedBrush"],
            };

            if (args.State == ControlPlaneState.Error)
            {
                ShowFeedback("本地控制面不可用", args.Message, InfoBarSeverity.Error);
            }
        });
    }

    private void OnWindowClosed(object sender, WindowEventArgs args)
    {
        _windowClosed = true;
        FeedbackHost.Stop();
        App.Current.Commands.Changed -= UpdateCommandMenus;
        DisposeSessionSaving();
        AppWindow.Changed -= OnAppWindowChanged;
        if (_sizeLimitXamlRoot is not null)
        {
            _sizeLimitXamlRoot.Changed -= OnWindowXamlRootChanged;
            _sizeLimitXamlRoot = null;
        }
        _resourceTimer.Stop();
        _resourceTimer.Tick -= OnResourceTimerTick;
        Closed -= OnWindowClosed;
        AppWindow.Closing -= OnAppWindowClosing;
        _controlPlane.StateChanged -= OnControlPlaneStateChanged;
    }

    private async void OnAppWindowClosing(AppWindow sender, AppWindowClosingEventArgs args)
    {
        if (_shutdownComplete || _sessionEnd.IsEnding)
        {
            return;
        }

        args.Cancel = true;
        await RequestCloseAsync();
    }

    private async Task CloseWorkbenchAsync()
    {
        if (_sessionEnd.IsEnding) return;
        if (App.Current.Session.IsResettingNewJob)
        {
            ReportPageStatus("请先完成新建作业确认或保存，再关闭窗口");
            return;
        }
        _shutdownStarted = true;
        SetCloseInteractionEnabled(false);
        _resourceTimer.Stop();
        ReportPageStatus("正在保存工作台并检查后台任务…");
        try
        {
            await App.Current.Session.SaveForCloseAsync(CaptureWindowState());
            if (_sessionEnd.IsEnding) return;
            if (!await ConfirmAndCommitCloseAsync()) return;
            if (_sessionEnd.IsEnding) return;
            await _controlPlane.DetachForCloseAsync();
            _shutdownComplete = true;
            AppWindow.Closing -= OnAppWindowClosing;
            Close();
        }
        catch (Exception exception)
        {
            if (_sessionEnd.IsEnding) return;
            ShowFeedback("无法安全关闭", exception.Message, InfoBarSeverity.Error);
            ReportPageStatus("关闭已取消 · 请处理错误后重试");
        }
        finally
        {
            if (!_shutdownComplete && !_sessionEnd.IsEnding)
            {
                try { await _controlPlane.AbortCloseAsync(); }
                catch (Exception error) { ReportPageStatus("关闭已取消 · 后台确认暂不可达，准备状态会在一分钟内失效。" + error.Message); }
                _shutdownStarted = false;
                App.Current.Session.ResumeAfterCancelledClose();
                SetCloseInteractionEnabled(true);
                if (!_windowClosed) _resourceTimer.Start();
            }
        }
    }
}
