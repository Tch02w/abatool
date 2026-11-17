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
        _controlPlane = controlPlane;
        _fallbackExplorerAdapter = new ProjectExplorerAdapter(
            controlPlane,
            ActivateFallbackExplorerItemAsync);
        _resourceTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(3) };
        _resourceTimer.Tick += OnResourceTimerTick;
        _controlPlane.StateChanged += OnControlPlaneStateChanged;
        Closed += OnWindowClosed;
        AppWindow.Closing += OnAppWindowClosing;
        Title = "Abaqus Tools — WinUI 3";
        ConfigureTitleBar();
        AppWindow.Changed += OnAppWindowChanged;
        UpdateWindowSizeLimits();
        if (AppWindow.Presenter is OverlappedPresenter presenter)
        {
            presenter.Maximize();
        }
        UpdateTitleBarInsets();

        ShellNavigation.SelectedItem = NewJobItem;
        if (ContentFrame.Content is null)
        {
            NavigateTo("new-job");
        }
    }

    public void ReportPageStatus(string message)
    {
        var status = string.IsNullOrWhiteSpace(message) ? "就绪" : message;
        PageStatusText.Text = status;
    }

    public void ApplyRemoteServerSnapshot(RemoteServersSnapshot snapshot)
    {
        RemoteStatusText.Text = snapshot.Connection.Status switch
        {
            "connected" => $"远端 ● {snapshot.Connection.ProfileName}",
            "confirmationRequired" => "远端 ◐ 等待指纹确认",
            "error" => "远端 △ 连接异常",
            _ => "远端 ○ 未连接",
        };
        RemoteStatusText.Foreground = snapshot.Connection.Status == "connected"
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

    public async Task RefreshLocalResourceNowAsync()
    {
        if (_resourceRefreshBusy || _shutdownStarted)
        {
            return;
        }

        _resourceRefreshBusy = true;
        try
        {
            var snapshot = await _controlPlane.GetLocalResourceAsync();
            LatestLocalResource = snapshot;
            ApplyLocalResourceSnapshot(snapshot);
        }
        catch (OperationCanceledException)
        {
            // Safe shutdown or a superseding lifecycle transition cancelled polling.
        }
        catch (Exception exception)
        {
            LocalResourceStatusText.Text = "本机资源不可用";
            if (ContentFrame.Content is ComputeResourcesPage page)
            {
                page.ShowResourceError(exception.Message);
            }
        }
        finally
        {
            _resourceRefreshBusy = false;
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
        await RefreshLocalResourceNowAsync();
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
            _resourceTimer.Start();
        }
        catch (ControlPlaneException exception)
        {
            StartupInfoBar.Severity = InfoBarSeverity.Error;
            StartupInfoBar.Title = "本地控制面不可用";
            StartupInfoBar.Message = exception.ToDisplayMessage();
            StartupInfoBar.IsOpen = true;
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
            ReportPageStatus("选择结果根目录以读取索引");
            if (ContentFrame.CurrentSourcePageType != typeof(ResultBrowserPage))
            {
                ContentFrame.Navigate(typeof(ResultBrowserPage));
            }
            AttachExplorerForCurrentPage();
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
        ExplorerHost.Attach(adapter);
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
                await postprocessingPage.LoadOdbPathAsync(item.Path);
            }
        }
    }

    public void NavigateToRoute(string route)
    {
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
        var item = ShellNavigation.MenuItems
            .OfType<NavigationViewItem>()
            .FirstOrDefault(candidate => string.Equals(candidate.Tag as string, route, StringComparison.Ordinal));
        if (item is not null)
        {
            ShellNavigation.SelectedItem = item;
        }
    }

    private void OnNewJobMenuClicked(object sender, RoutedEventArgs args)
    {
        SelectRoute("new-job");
    }

    private void OnQueueMenuClicked(object sender, RoutedEventArgs args)
    {
        SelectRoute("job-queue");
    }

    private async void OnStartQueueMenuClicked(object sender, RoutedEventArgs args)
    {
        NavigateToRoute("job-queue");
        if (ContentFrame.Content is JobQueuePage page)
        {
            await page.StartQueueAsync();
        }
    }

    private async void OnStopQueueMenuClicked(object sender, RoutedEventArgs args)
    {
        NavigateToRoute("job-queue");
        if (ContentFrame.Content is JobQueuePage page)
        {
            await page.StopQueueAsync();
        }
    }

    private void OnComputeResourcesMenuClicked(object sender, RoutedEventArgs args)
    {
        NavigateToRoute("compute-resources");
    }

    private async void OnRefreshResourcesMenuClicked(object sender, RoutedEventArgs args)
    {
        NavigateToRoute("compute-resources");
        if (ContentFrame.Content is ComputeResourcesPage page)
        {
            await page.RefreshSelectedAsync();
        }
    }

    private async void OnDisconnectServerMenuClicked(object sender, RoutedEventArgs args)
    {
        NavigateToRoute("compute-resources");
        if (ContentFrame.Content is ComputeResourcesPage page)
        {
            await page.DisconnectAsync();
        }
    }

    private void OnPostprocessingMenuClicked(object sender, RoutedEventArgs args)
    {
        SelectRoute("odb-postprocessing");
    }

    private void OnResultBrowserMenuClicked(object sender, RoutedEventArgs args)
    {
        SelectRoute("result-browser");
    }

    private void OnPostprocessingAcceleratorInvoked(
        KeyboardAccelerator sender,
        KeyboardAcceleratorInvokedEventArgs args)
    {
        SelectRoute("odb-postprocessing");
        args.Handled = true;
    }

    private void OnResultBrowserAcceleratorInvoked(
        KeyboardAccelerator sender,
        KeyboardAcceleratorInvokedEventArgs args)
    {
        SelectRoute("result-browser");
        args.Handled = true;
    }

    private void OnExitMenuClicked(object sender, RoutedEventArgs args)
    {
        Close();
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
                display.WorkArea.Width, display.WorkArea.Height, navigationHeight);
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
                StartupInfoBar.Severity = InfoBarSeverity.Error;
                StartupInfoBar.Title = "本地控制面不可用";
                StartupInfoBar.Message = args.Message;
                StartupInfoBar.IsOpen = true;
            }
            else if (args.State == ControlPlaneState.Ready)
            {
                StartupInfoBar.IsOpen = false;
            }
        });
    }

    private void OnWindowClosed(object sender, WindowEventArgs args)
    {
        _windowClosed = true;
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
        if (_shutdownComplete)
        {
            return;
        }

        args.Cancel = true;
        if (_shutdownStarted)
        {
            return;
        }

        _shutdownStarted = true;
        ReportPageStatus("正在安全关闭本地控制面…");
        try
        {
            await App.Current.PendingResultFileOperation;
            await _controlPlane.DisposeAsync();
            _shutdownComplete = true;
            AppWindow.Closing -= OnAppWindowClosing;
            Close();
        }
        catch (Exception exception)
        {
            _shutdownStarted = false;
            StartupInfoBar.Severity = InfoBarSeverity.Error;
            StartupInfoBar.Title = "无法安全关闭";
            StartupInfoBar.Message = exception.Message;
            StartupInfoBar.IsOpen = true;
            ReportPageStatus("关闭已取消 · 请处理错误后重试");
        }
    }
}
