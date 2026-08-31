using AbaqusTools.WinUI.Pages;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

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
    private readonly Dictionary<TreeViewNode, string> _projectNodePaths = [];
    private bool _resourceRefreshBusy;
    private bool _projectRefreshBusy;
    private bool _shutdownStarted;
    private bool _shutdownComplete;
    private string _selectedInputPath = string.Empty;
    private JobQueueSnapshot? _latestQueueSnapshot;

    public LocalResourceSnapshot? LatestLocalResource { get; private set; }

    public MainWindow(ControlPlaneHost controlPlane)
    {
        InitializeComponent();
        _controlPlane = controlPlane;
        _resourceTimer = new DispatcherTimer { Interval = TimeSpan.FromSeconds(3) };
        _resourceTimer.Tick += OnResourceTimerTick;
        _controlPlane.StateChanged += OnControlPlaneStateChanged;
        Closed += OnWindowClosed;
        AppWindow.Closing += OnAppWindowClosing;
        Title = "Abaqus Tools — WinUI 3";
        ConfigureTitleBar();
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
        ProjectRemoteText.Text = snapshot.Connection.Status switch
        {
            "connected" => $"远端 · {snapshot.Connection.ProfileName}",
            "confirmationRequired" => "远端 · 等待指纹确认",
            "error" => "远端 · 连接异常",
            _ => "远端 · 未连接",
        };
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
            ProjectNodeStatusText.Text = "本机 · 资源不可用";
            if (ContentFrame.Content is ComputeResourcesPage page)
            {
                page.ShowResourceError(exception.Message);
            }
        }
        finally
        {
            _resourceRefreshBusy = false;
        }

        await RefreshProjectExplorerAsync();
    }

    private void ApplyLocalResourceSnapshot(LocalResourceSnapshot snapshot)
    {
        LocalResourceStatusText.Text =
            $"本机 CPU {snapshot.BusyCpus}/{snapshot.LogicalCpus} · 内存 {snapshot.MemoryPercent:0}%";
        QueueStatusText.Text =
            $"队列 {snapshot.TotalJobs} · 运行 {snapshot.RunningJobs} · 等待 {snapshot.WaitingJobs}";
        ProjectNodeStatusText.Text = string.IsNullOrWhiteSpace(snapshot.Name)
            ? "本机 · 在线"
            : $"{snapshot.Name} · 在线";
        ProjectCpuText.Text = $"CPU {snapshot.BusyCpus}/{snapshot.LogicalCpus} · {snapshot.CpuPercent:0}%";
        ProjectCpuProgress.Value = Math.Clamp(snapshot.CpuPercent, 0, 100);
        ProjectMemoryText.Text = $"内存 {snapshot.MemoryPercent:0}%";
        ProjectMemoryProgress.Value = Math.Clamp(snapshot.MemoryPercent, 0, 100);
        ProjectJobsText.Text = $"作业 {snapshot.TotalJobs} · 运行 {snapshot.RunningJobs} · 等待 {snapshot.WaitingJobs}";
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
        _selectedInputPath = path.Trim();
        ApplyProjectSnapshot(_latestQueueSnapshot ?? new JobQueueSnapshot());
    }

    private async Task RefreshProjectExplorerAsync()
    {
        if (_shutdownStarted || _projectRefreshBusy)
        {
            return;
        }

        _projectRefreshBusy = true;
        try
        {
            var snapshot = await _controlPlane.GetJobQueuesAsync();
            _latestQueueSnapshot = snapshot;
            ApplyProjectSnapshot(snapshot);
        }
        catch (OperationCanceledException)
        {
            // Window shutdown cancels the explorer refresh together with the control plane.
        }
        catch (Exception)
        {
            // Preserve the most recent project tree when a transient refresh fails.
        }
        finally
        {
            _projectRefreshBusy = false;
        }
    }

    private void ApplyProjectSnapshot(JobQueueSnapshot snapshot)
    {
        _projectNodePaths.Clear();
        var inputs = new List<string>();
        AddDistinctPath(inputs, _selectedInputPath);
        foreach (var item in snapshot.Candidates.Concat(snapshot.QueueItems))
        {
            AddDistinctPath(inputs, item.InpPath);
        }

        CurrentProjectNode.Content = ProjectName(inputs);
        InputFilesNode.Children.Clear();
        if (inputs.Count == 0)
        {
            InputFilesNode.Children.Add(new TreeViewNode { Content = "尚未选择 INP" });
        }
        else
        {
            foreach (var path in inputs)
            {
                AddPathNode(InputFilesNode, Path.GetFileName(path), path);
            }
        }

        var results = DiscoverResultFiles(inputs);
        ResultFilesNode.Children.Clear();
        if (results.Count == 0)
        {
            ResultFilesNode.Children.Add(new TreeViewNode { Content = "尚无 ODB 结果" });
        }
        else
        {
            foreach (var path in results)
            {
                AddPathNode(ResultFilesNode, Path.GetFileName(path), path);
            }
        }

        JobsNode.Children.Clear();
        if (snapshot.QueueItems.Count == 0)
        {
            JobsNode.Children.Add(new TreeViewNode { Content = "尚无调度作业" });
        }
        else
        {
            foreach (var item in snapshot.QueueItems)
            {
                var name = string.IsNullOrWhiteSpace(item.JobName) ? "未命名作业" : item.JobName;
                var status = string.IsNullOrWhiteSpace(item.Status) ? "未提交" : item.Status;
                JobsNode.Children.Add(new TreeViewNode { Content = $"{name}　{status}" });
            }
        }

        var restartItems = snapshot.QueueItems
            .Where(item => !string.IsNullOrWhiteSpace(item.OldjobName)
                || !string.IsNullOrWhiteSpace(item.OldjobPath))
            .ToArray();
        MergePlansNode.Children.Clear();
        if (restartItems.Length == 0)
        {
            MergePlansNode.Children.Add(new TreeViewNode { Content = "尚无重启动合并计划" });
        }
        else
        {
            foreach (var item in restartItems)
            {
                var parent = string.IsNullOrWhiteSpace(item.OldjobName)
                    ? Path.GetFileNameWithoutExtension(item.OldjobPath)
                    : item.OldjobName;
                MergePlansNode.Children.Add(
                    new TreeViewNode { Content = $"{parent} → {item.JobName}" });
            }
        }

        CurrentProjectNode.IsExpanded = true;
        InputFilesNode.IsExpanded = true;
        ResultFilesNode.IsExpanded = true;
        JobsNode.IsExpanded = true;
        MergePlansNode.IsExpanded = true;
    }

    private void AddPathNode(TreeViewNode parent, string label, string path)
    {
        var node = new TreeViewNode
        {
            Content = string.IsNullOrWhiteSpace(label) ? path : label,
        };
        parent.Children.Add(node);
        _projectNodePaths[node] = path;
    }

    private static void AddDistinctPath(List<string> paths, string path)
    {
        var trimmed = path.Trim();
        if (!string.IsNullOrWhiteSpace(trimmed)
            && !paths.Contains(trimmed, StringComparer.OrdinalIgnoreCase))
        {
            paths.Add(trimmed);
        }
    }

    private static string ProjectName(IReadOnlyList<string> inputs)
    {
        if (inputs.Count == 0)
        {
            return "当前项目";
        }

        var directory = Path.GetDirectoryName(inputs[0]);
        return string.IsNullOrWhiteSpace(directory)
            ? "当前项目"
            : new DirectoryInfo(directory).Name;
    }

    private static IReadOnlyList<string> DiscoverResultFiles(IEnumerable<string> inputs)
    {
        var results = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var input in inputs)
        {
            var directory = Path.GetDirectoryName(input);
            if (string.IsNullOrWhiteSpace(directory) || !Directory.Exists(directory))
            {
                continue;
            }

            try
            {
                foreach (var path in Directory.EnumerateFiles(directory, "*.odb"))
                {
                    results.Add(path);
                }
            }
            catch (IOException)
            {
                // A project directory can disappear while the explorer is refreshing.
            }
            catch (UnauthorizedAccessException)
            {
                // Keep other visible project entries when one directory is inaccessible.
            }
        }

        return results.OrderBy(path => Path.GetFileName(path), StringComparer.OrdinalIgnoreCase).ToArray();
    }

    private async void OnRefreshProjectExplorerClicked(object sender, RoutedEventArgs e)
    {
        ProjectRefreshButton.IsEnabled = false;
        try
        {
            await RefreshLocalResourceNowAsync();
        }
        finally
        {
            ProjectRefreshButton.IsEnabled = true;
        }
    }

    private async void OnProjectTreeDoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
    {
        if (ProjectTree.SelectedNode is not { } node
            || !_projectNodePaths.TryGetValue(node, out var path))
        {
            return;
        }

        var extension = Path.GetExtension(path);
        if (string.Equals(extension, ".inp", StringComparison.OrdinalIgnoreCase))
        {
            NavigateToRoute("new-job");
            if (ContentFrame.Content is NewJobPage newJobPage)
            {
                newJobPage.LoadInputPath(path);
            }
        }
        else if (string.Equals(extension, ".odb", StringComparison.OrdinalIgnoreCase))
        {
            NavigateToRoute("odb-postprocessing");
            if (ContentFrame.Content is OdbPostprocessingPage postprocessingPage)
            {
                await postprocessingPage.LoadOdbPathAsync(path);
            }
        }

        e.Handled = true;
    }

    private async void OnResourceTimerTick(object? sender, object e)
    {
        await RefreshLocalResourceNowAsync();
    }

    private async void OnRootLoaded(object sender, RoutedEventArgs e)
    {
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
        TitleBarLeftInsetColumn.Width = new GridLength(AppWindow.TitleBar.LeftInset);
        TitleBarRightInsetColumn.Width = new GridLength(AppWindow.TitleBar.RightInset);
    }

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
