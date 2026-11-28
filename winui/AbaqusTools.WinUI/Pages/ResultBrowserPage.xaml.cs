using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media.Imaging;
using Microsoft.UI.Xaml.Navigation;
using Windows.ApplicationModel.DataTransfer;
using Windows.Storage;
using Windows.Storage.Pickers;
using Windows.System;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class ResultBrowserPage : Page, IWorkbenchExplorerPage
{
    private static readonly IReadOnlyList<SectionOption> Sections =
    [
        new("common", "常用"),
        new("data", "数据"),
        new("plots", "曲线图"),
        new("contours", "云图"),
        new("animations", "动画"),
        new("info", "说明与日志"),
        new("all", "全部"),
    ];

    private readonly ObservableCollection<ResultRecordItem> _records = [];
    private readonly Dictionary<string, TreeViewNode> _treeNodes =
        new(StringComparer.OrdinalIgnoreCase);

    private ResultScopeNode? _selectedScope;
    private string? _activeIndexOperationId;
    private string? _activeIndexBatchId;
    private readonly ResultBrowserLoadCoordinator _loads = new();
    private readonly ResultBrowserLocation _location = new();
    private ResultDirectLocation? _direct => _location.VisibleDirect(_selectedScope?.Path);
    private bool _scopeBusy => _loads.IsRefreshingScopes;
    private bool _recordsBusy;
    private bool _recycleBusy;
    private ResultRecordsRequest? _appliedQuery;
    private ResultRecordsResponse? _displayedPage;
    private (string Key, bool Descending) _sort = ("default", false);
    private (string Key, bool Descending)? _pendingSort;
    private bool _indexBusy => _loads.IsIndexing;
    private bool _cancelIndexRequested;
    private bool _updatingFilters;
    private bool _recoveryAttempted;
    private long _previewRequest;
    private ResultPreviewResponse? _displayedWorkbook;
    private bool _updatingWorksheets;
    private bool _worksheetPending;
    private IReadOnlyList<ResultScopeNode> _scopeNodes = [];
    private readonly ResultExplorerAdapter _explorerAdapter;

    public ResultBrowserPage()
    {
        InitializeComponent();
        Controls.InfoBarLayout.Track(StatusMessagesPanel, IndexInfoBar);
        _explorerAdapter = new ResultExplorerAdapter(
            () => !_loads.InitialIndexChecked || FileOperationBusy || _scopeBusy || _indexBusy
                || (_location.LoadedRoot is null && string.IsNullOrWhiteSpace(RootTextBox.Text))
                ? Task.CompletedTask : RefreshScopesAsync(_selectedScope?.Path, _location.LoadedRoot),
            SelectExplorerItem,
            ActivateExplorerItemAsync);
        NavigationCacheMode = NavigationCacheMode.Required;
        ResultList.ItemsSource = _records;
        SectionComboBox.ItemsSource = Sections;
        SectionComboBox.SelectedIndex = 0;
        UseCaseComboBox.ItemsSource = new[] { "全部用途" };
        UseCaseComboBox.SelectedIndex = 0;
        var session = App.Current.Session;
        if (session.State.Pages.TryGetValue("result-browser", out var values))
            _location.DirectBookmark = ResultDirectLocation.Restore(values);
        session.Register(this, "result-browser", ["RootTextBox", "ShowInternalCheckBox"],
            async () => { InvalidatePreview(); await App.Current.PendingResultFileOperation.WaitAsync(TimeSpan.FromSeconds(30)); },
            captureContext: fields => _location.DirectBookmark?.Capture(fields));
        _location.DraftRoot = RootTextBox.Text;
        Loaded += OnPageLoaded;
        UpdateSortIndicators();
        RefreshInteractionState();
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _explorerAdapter;
    internal bool HasLoadedDirectory => _location.LoadedRoot is not null;
    internal string StatusBarMessage { get; private set; } = "选择结果根目录以读取索引";

    private void ReportPageStatus(string message)
    {
        StatusBarMessage = message;
        if (ReferenceEquals(Frame?.Content, this)) App.Current.MainWindow.ReportPageStatus(message);
    }

    protected override void OnNavigatedFrom(NavigationEventArgs e)
    {
        _loads.LeavePage();
        if (_worksheetPending) InvalidatePreview();
        if (_recordsBusy && _displayedPage is { } page)
        {
            _loads.InvalidateRecords();
            _recordsBusy = false;
            _pendingSort = null;
            ResultStatusText.Text = ResultPageStatus(page);
            RefreshInteractionState();
        }
        base.OnNavigatedFrom(e);
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        if (_recoveryAttempted)
        {
            if (_loads.CanAutoReadRoot && !_scopeBusy && !_indexBusy && ScopeTree.RootNodes.Count == 0
                && _location.DirectBookmark is { } bookmark)
                await RefreshScopesAsync(bookmark.Scope, bookmark.Root);
            return;
        }

        _recoveryAttempted = true;
        var defaultRoot = Path.Combine(
            Environment.CurrentDirectory,
            "AbaqusODBPostProcessor_Results");
        if (string.IsNullOrWhiteSpace(RootTextBox.Text) && Directory.Exists(defaultRoot))
        {
            RootTextBox.Text = defaultRoot;
        }

        var recoveredIndex = await RecoverActiveIndexOperationAsync();
        if (!recoveredIndex && _loads.CanAutoReadRoot && !_scopeBusy && IsLoaded && ScopeTree.RootNodes.Count == 0)
        {
            if (_location.DirectBookmark is { } saved) await RefreshScopesAsync(saved.Scope, saved.Root);
            else if (Directory.Exists(RootTextBox.Text)) await RefreshScopesAsync();
        }
    }

    public Task SetResultRootAsync(string root)
    {
        if (string.IsNullOrWhiteSpace(root))
        {
            throw new ArgumentException("结果根目录不能为空。", nameof(root));
        }

        return _loads.OpenRootAsync(Path.GetFullPath(root.Trim()), () => FileOperationBusy,
            () => ShowWarning("请等待当前结果索引、导出或清理结束后再打开目标目录。", "暂时无法切换目录"),
            target =>
            {
                RootTextBox.Text = target;
                return RefreshScopesAsync(explicitRoot: target);
            });
    }

    private async Task<bool> RecoverActiveIndexOperationAsync()
    {
        var recoveredIndex = false;
        long? indexRequest = null;
        var context = _loads.ContextRevision;
        var requestedRoot = RootTextBox.Text;
        try
        {
            var operations = await App.Current.ControlPlane.ListResultIndexOperationsAsync(
                activeOnly: true);
            if (context != _loads.ContextRevision
                || !string.Equals(requestedRoot, RootTextBox.Text, StringComparison.Ordinal))
            {
                // The user has already changed root or started an operation during discovery.
                return true;
            }

            var snapshot = operations.Operations.FirstOrDefault(
                operation => !operation.IsTerminal
                    && !string.IsNullOrWhiteSpace(operation.Request.Root)
                    && !string.IsNullOrWhiteSpace(operation.Request.TimeDirectory));
            if (snapshot is null)
            {
                return false;
            }

            recoveredIndex = true;
            _location.DirectBookmark = null;
            _loads.BeginIndex();
            _loads.CompleteInitialIndexCheck();
            indexRequest = _loads.IndexRevision;
            var owner = indexRequest.Value;
            if (!string.IsNullOrWhiteSpace(snapshot.BatchId))
            {
                var batch = await App.Current.ControlPlane.GetResultIndexBatchAsync(snapshot.BatchId);
                if (string.IsNullOrWhiteSpace(RootTextBox.Text)) RootTextBox.Text = batch.Root;
                await RefreshScopesAsync(batch.ScopeDirectory, batch.Root);
                await ObserveIndexBatchAsync(batch, owner);
                return true;
            }
            _activeIndexOperationId = snapshot.OperationId;
            if (string.IsNullOrWhiteSpace(RootTextBox.Text)) RootTextBox.Text = snapshot.Request.Root;
            await RefreshScopesAsync(snapshot.Request.TimeDirectory, snapshot.Request.Root);
            _cancelIndexRequested = string.Equals(
                snapshot.Status,
                "cancelling",
                StringComparison.Ordinal);
            ApplyIndexSnapshot(snapshot, owner);
            RefreshInteractionState();

            var progress = new Progress<ResultIndexOperationSnapshot>(
                update => ApplyIndexSnapshot(update, owner));
            var finalSnapshot = await App.Current.ControlPlane.PollResultIndexUntilTerminalAsync(
                snapshot,
                progress);
            ApplyIndexSnapshot(finalSnapshot, owner);
            await CompleteIndexOperationAsync(finalSnapshot);
        }
        catch (OperationCanceledException)
        {
            ResultStatusText.Text = "索引恢复已取消";
        }
        catch (ControlPlaneException exception)
        {
            ShowWarning(exception.ToDisplayMessage(), "未能恢复结果索引");
        }
        catch (Exception exception)
        {
            ShowWarning(exception.Message, "未能恢复结果索引");
        }
        finally
        {
            _loads.CompleteInitialIndexCheck();
            if (indexRequest is { } owner)
            {
                ClearIndexBusyState(owner);
            }
        }

        return recoveredIndex;
    }

    private async void OnBrowseClicked(object sender, RoutedEventArgs e)
    {
        try
        {
            var picker = new FolderPicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
                CommitButtonText = "选择结果根目录",
            };
            picker.FileTypeFilter.Add("*");
            var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
            var folder = await picker.PickSingleFolderAsync();
            if (folder is not null)
            {
                RootTextBox.Text = folder.Path;
                await RefreshScopesAsync(notify: true);
            }
        }
        catch (Exception exception)
        {
            ShowError("无法选择结果目录。" + Environment.NewLine + exception.Message);
        }
    }

    private async void OnRefreshScopesClicked(object sender, RoutedEventArgs e)
    {
        await RefreshScopesAsync(_selectedScope?.Path, notify: true);
    }

    private async void OnRootTextBoxKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == Windows.System.VirtualKey.Enter && !_scopeBusy)
        {
            e.Handled = true;
            await RefreshScopesAsync(notify: true);
        }
    }

    private async void OnShowInternalChanged(object sender, RoutedEventArgs e)
    {
        if (IsLoaded && !_scopeBusy && !_indexBusy && !FileOperationBusy && _location.LoadedRoot is not null)
        {
            await RefreshScopesAsync(_selectedScope?.Path, _location.LoadedRoot);
        }
    }

    private void OnRootTextChanged(object sender, TextChangedEventArgs e)
    {
        _location.DraftRoot = ((TextBox)sender).Text;
        UpdateRootContextHint();
    }

    private void UpdateRootContextHint()
    {
        if (RootContextHint is null) return; // TextChanged can fire while XAML is loading.
        RootContextHint.Text = _location.HasPendingRoot
            ? $"输入的目录尚未读取；当前显示及操作目录：{_location.LoadedRoot}" : string.Empty;
        RootContextHint.Visibility = _location.HasPendingRoot ? Visibility.Visible : Visibility.Collapsed;
    }

    private async Task RefreshScopesAsync(string? selectPath = null, string? explicitRoot = null, bool notify = false,
        Func<Task>? loadSelectedScope = null)
    {
        _location.DraftRoot = RootTextBox.Text;
        var locationRead = _location.BeginRead(explicitRoot, selectPath);
        var root = locationRead.Root;
        IndexInfoBar.IsOpen = false;
        ScopeStatusText.Text = "正在读取目录结构…";
        ReportPageStatus("正在读取结果目录结构…");
        await _loads.RefreshScopesAsync(
            () => string.IsNullOrWhiteSpace(root)
                ? Task.FromException<ResultScopesResponse>(
                    new ArgumentException("请选择或输入结果根目录。"))
                : App.Current.ControlPlane.DiscoverResultScopesAsync(
                    root,
                    ShowInternalCheckBox.IsChecked is true),
            ClearScopesAndResults,
            response =>
            {
                _location.Apply(locationRead, response.Root);
                if (RootTextBox.Text != _location.DraftRoot) RootTextBox.Text = _location.DraftRoot;
                UpdateRootContextHint();
                _scopeNodes = response.Nodes;
                BuildScopeTree(response.Nodes);
                UpdateExplorer();
                ScopeStatusText.Text = $"{response.Count} 个范围节点";
                if (response.Warnings.Count > 0)
                {
                    ShowWarning(string.Join(Environment.NewLine, response.Warnings), "目录读取有警告");
                }
                else if (notify)
                    App.Current.MainWindow.ShowFeedback("结果目录已读取", $"{response.Count} 个范围节点", InfoBarSeverity.Success);

                var targetPath = string.IsNullOrWhiteSpace(selectPath)
                    ? response.Root
                    : selectPath;
                if (_treeNodes.TryGetValue(targetPath, out var targetNode)
                    || _treeNodes.TryGetValue(response.Root, out targetNode))
                {
                    _selectedScope = targetNode.Content as ResultScopeNode;
                    ScopeTree.SelectedNode = targetNode;
                    ExpandAncestors(targetNode);
                }
                _location.RetainMatchingBookmark(response.Root, _selectedScope?.Path);
                ReportPageStatus($"结果目录已读取 · {response.Count} 个范围");
            },
            loadSelectedScope ?? RefreshSelectedScopeAsync,
            exception =>
            {
                ScopeStatusText.Text = "目录读取失败";
                var detail = exception is ControlPlaneException controlPlaneException
                    ? controlPlaneException.ToDisplayMessage()
                    : exception.Message;
                if (locationRead.UsesDraft && _location.DraftRoot == locationRead.DraftAtStart
                    && (exception is ArgumentException || exception is ControlPlaneException rootError
                    && rootError.Code?.StartsWith("RESULT_ROOT_", StringComparison.Ordinal) == true))
                {
                    RootContextHint.Text = detail;
                    RootContextHint.Visibility = Visibility.Visible;
                }
                else ShowError(detail, "结果目录读取失败");
            },
            () =>
            {
                ScopeProgressRing.IsActive = _scopeBusy;
                ScopeProgressRing.Visibility = _scopeBusy ? Visibility.Visible : Visibility.Collapsed;
                RefreshInteractionState();
            });
    }

    private void ClearScopesAndResults()
    {
        _location.ClearLoadedRoot();
        UpdateRootContextHint();
        _selectedScope = null;
        _scopeNodes = [];
        ScopeTree.SelectedNode = null;
        ScopeTree.RootNodes.Clear();
        _treeNodes.Clear();
        ClearResults();
        UpdateUseCases([], string.Empty);
    }

    private void ClearResults()
    {
        _appliedQuery = null;
        _displayedPage = null;
        _pendingSort = null;
        RecordPager.Visibility = Visibility.Collapsed;
        _loads.InvalidateRecords();
        _recordsBusy = false;
        ResultList.SelectedItems.Clear();
        _records.Clear();
        ResetPreview();
        IndexInfoBar.IsOpen = false;
        EmptyResultsPanel.Visibility = Visibility.Visible;
        EmptyResultsText.Text = "请选择结果范围";
        ResultStatusText.Text = "尚未读取结果记录";
        UpdateExplorer();
    }

    private void BuildScopeTree(IReadOnlyList<ResultScopeNode> scopes)
    {
        ScopeTree.RootNodes.Clear();
        _treeNodes.Clear();
        foreach (var scope in scopes)
        {
            _treeNodes[scope.Path] = new TreeViewNode { Content = scope };
        }

        foreach (var scope in scopes)
        {
            var node = _treeNodes[scope.Path];
            if (string.IsNullOrWhiteSpace(scope.ParentPath))
            {
                ScopeTree.RootNodes.Add(node);
            }
            else if (_treeNodes.TryGetValue(scope.ParentPath, out var parent))
            {
                parent.Children.Add(node);
            }
        }

        foreach (var rootNode in ScopeTree.RootNodes)
        {
            rootNode.IsExpanded = true;
        }
    }

    private void UpdateExplorer()
    {
        var byParent = _scopeNodes
            .GroupBy(scope => scope.ParentPath ?? string.Empty, StringComparer.OrdinalIgnoreCase)
            .ToDictionary(group => group.Key, group => group.ToArray(), StringComparer.OrdinalIgnoreCase);
        var knownPaths = _scopeNodes.Select(scope => scope.Path).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var roots = _scopeNodes
            .Where(scope => string.IsNullOrWhiteSpace(scope.ParentPath)
                || !knownPaths.Contains(scope.ParentPath))
            .Select(scope => ScopeExplorerItem(scope, byParent))
            .ToArray();
        var records = _records.Select(record => new ExplorerItem
        {
            StableId = $"result:record:{record.Path.ToUpperInvariant()}",
            Kind = ExplorerItemKind.ResultRecord,
            Title = record.Name,
            Subtitle = string.IsNullOrWhiteSpace(record.Description)
                ? record.UseCase
                : record.Description,
            Path = record.Path,
            Status = record.Section,
            Badge = record.Recommended ? "推荐" : record.Suffix,
            IconGlyph = record.IsDirectory ? "\uE8B7" : "\uE8A5",
        }).ToArray();
        _explorerAdapter.Update(
            _location.LoadedRoot ?? string.Empty,
            $"范围 {_scopeNodes.Count} · 当前结果 {records.Length}",
            [
                WorkbenchExplorerAdapterBase.Group("results:scopes", "结果范围", roots, roots.Length.ToString()),
                WorkbenchExplorerAdapterBase.Group("results:records", "当前结果", records, records.Length.ToString()),
            ]);
    }

    private static ExplorerItem ScopeExplorerItem(
        ResultScopeNode scope,
        IReadOnlyDictionary<string, ResultScopeNode[]> byParent)
    {
        var item = new ExplorerItem
        {
            StableId = $"result:scope:{scope.Path.ToUpperInvariant()}",
            Kind = ExplorerItemKind.ResultScope,
            Title = scope.Name,
            Subtitle = scope.KindDisplay,
            Path = scope.Path,
            Status = scope.IndexState,
            Badge = scope.IndexStateDisplay,
            IconGlyph = "\uE8B7",
            IsExpanded = true,
        };
        if (byParent.TryGetValue(scope.Path, out var children))
        {
            foreach (var child in children)
            {
                item.Children.Add(ScopeExplorerItem(child, byParent));
            }
        }
        return item;
    }

    private void SelectExplorerItem(ExplorerItem item)
    {
        if (_scopeBusy || _indexBusy || FileOperationBusy)
        {
            return;
        }

        if (item.Kind == ExplorerItemKind.ResultScope
            && _treeNodes.TryGetValue(item.Path, out var node))
        {
            if (!ReferenceEquals(ScopeTree.SelectedNode, node)) ScopeTree.SelectedNode = node;
            ExpandAncestors(node);
            return;
        }
        if (!_recordsBusy && item.Kind == ExplorerItemKind.ResultRecord)
        {
            var record = _records.FirstOrDefault(candidate => string.Equals(
                candidate.Path,
                item.Path,
                StringComparison.Ordinal));
            if (record is not null)
            {
                ResultList.SelectedItem = record;
                ResultList.ScrollIntoView(record);
            }
        }
    }

    private async Task ActivateExplorerItemAsync(ExplorerItem item)
    {
        if (FileOperationBusy) return;
        SelectExplorerItem(item);
        if (!_recordsBusy && !_indexBusy && !_scopeBusy && item.Kind == ExplorerItemKind.ResultRecord
            && _records.FirstOrDefault(candidate => string.Equals(
                candidate.Path,
                item.Path,
                StringComparison.Ordinal)) is { } record
            && !record.Internal)
        {
            if (record.IsDirectory) await EnterDirectFolderAsync(record);
            else await LoadPreviewAsync(record);
        }
    }

    private static void ExpandAncestors(TreeViewNode node)
    {
        for (var parent = node.Parent; parent is not null; parent = parent.Parent)
        {
            parent.IsExpanded = true;
        }
    }

    private async void OnScopeSelectionChanged(
        TreeView sender,
        TreeViewSelectionChangedEventArgs args)
    {
        // RefreshScopesAsync explicitly loads the selection after releasing its busy state.
        if (_scopeBusy || _indexBusy)
        {
            return;
        }

        var scope = sender.SelectedNode?.Content as ResultScopeNode;
        if (ReferenceEquals(_selectedScope, scope)) return;
        _location.DirectBookmark = null;
        _selectedScope = scope;
        await RefreshSelectedScopeAsync();
    }

    private async Task RefreshSelectedScopeAsync()
    {
        if (!_loads.CanLoadRecords) return;
        ClearResults();
        if (_selectedScope is null)
        {
            RefreshInteractionState();
            return;
        }

        if (_selectedScope.Kind is "root" or "group" or "shared_root" or "shared_odb")
        {
            EmptyResultsPanel.Visibility = Visibility.Visible;
            EmptyResultsText.Text = "请选择时间目录、ODB 或公共数据版本";
            IndexInfoBar.IsOpen = false;
            ResultStatusText.Text = "上级节点只显示目录结构";
            RefreshInteractionState();
            return;
        }

        if (_direct is null && _selectedScope.IndexState == "missing"
            && !string.IsNullOrWhiteSpace(_selectedScope.TimeDirectory))
        {
            EmptyResultsPanel.Visibility = Visibility.Visible;
            EmptyResultsText.Text = "当前时间目录尚未建立索引";
            IndexInfoBar.Message = _selectedScope.TimeDirectory;
            IndexInfoBar.IsOpen = true;
            ResultStatusText.Text = "直接浏览可逐层查看文件，创建索引后可跨目录筛选。";
            RefreshInteractionState();
            return;
        }

        await LoadRecordsAsync();
    }

    private async void OnDirectBrowseClicked(object sender, RoutedEventArgs e)
    {
        if (_scopeBusy || _recordsBusy || _indexBusy || FileOperationBusy || !IndexInfoBar.IsOpen
            || _location.LoadedRoot is not { } root || _selectedScope is not { Kind: "batch" or "odb" } scope) return;
        _location.DirectBookmark = new(root, scope.Path, scope.Path);
        await RefreshSelectedScopeAsync();
    }

    private async Task EnterDirectFolderAsync(ResultRecordItem record)
    {
        if (_recordsBusy || FileOperationBusy || !record.IsDirectory || !_records.Contains(record)
            || _direct?.Child(record.Path) is not { } child) return;
        _location.DirectBookmark = child;
        await RefreshSelectedScopeAsync();
    }

    private async void OnResultRowDoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
    {
        if (_direct is null || sender is not FrameworkElement { DataContext: ResultRecordItem { IsDirectory: true } record }) return;
        e.Handled = true;
        await EnterDirectFolderAsync(record);
    }

    private async void OnDirectUpClicked(object sender, RoutedEventArgs e)
    {
        if (_direct?.Parent() is not { } parent) return;
        _location.DirectBookmark = parent;
        await RefreshSelectedScopeAsync();
    }

    private async void OnDirectRefreshClicked(object sender, RoutedEventArgs e) => await RefreshSelectedScopeAsync();

    private async void OnDirectExitClicked(object sender, RoutedEventArgs e)
    {
        if (_direct is not { } position) return;
        _location.DirectBookmark = null;
        await RefreshScopesAsync(position.Scope, position.Root);
    }

    private async void OnPreviousPageClicked(object sender, RoutedEventArgs e)
    {
        if (!_recordsBusy && _displayedPage is { Offset: > 0 } page)
            await LoadRecordsAsync(Math.Max(0, page.Offset - page.Limit), page.PageAnchor(before: true));
    }

    private async void OnNextPageClicked(object sender, RoutedEventArgs e)
    {
        if (!_recordsBusy && _displayedPage is { HasMore: true } page)
            await LoadRecordsAsync(page.Offset + page.Records.Count, page.PageAnchor(before: false));
    }

    private async void OnSortClicked(object sender, RoutedEventArgs e)
    {
        if (sender is not FrameworkElement { Tag: string key } || _appliedQuery is null ||
            _scopeBusy || _indexBusy || FileOperationBusy || App.Current.Session.IsClosing) return;

        var current = _pendingSort ?? _sort;
        var descending = key != "default" && (key == current.Key ? !current.Descending : key is "recommended" or "size" or "modified");
        await LoadRecordsAsync(0, sort: (key, descending));
    }

    private static string ResultPageStatus(ResultRecordsResponse page)
    {
        var status = $"{page.FilteredCount} 个结果 · {SourceDisplay(page.Source)}";
        if (page.SortBy is "path" or "description")
            status += $" · {(page.SortBy == "path" ? "文件路径" : "文件说明")}{(page.SortDescending ? "降序" : "升序")}";
        return status;
    }

    private void UpdateSortIndicators()
    {
        var arrow = _sort.Descending ? " ↓" : " ↑";
        var direction = _sort.Descending ? "降序" : "升序";
        void SetHeader(Button button, string label, string sortLabel)
        {
            var active = (string)button.Tag == _sort.Key;
            button.Content = active ? label + arrow : label;
            var action = $"按{sortLabel}排序" + (active ? $"，当前{direction}" : "");
            AutomationProperties.SetName(button, action);
            ToolTipService.SetToolTip(button, action);
        }
        void SetMenu(MenuFlyoutItem item, string label)
        {
            var active = (string)item.Tag == _sort.Key;
            item.Text = active ? label + arrow : label;
            AutomationProperties.SetName(item, active ? $"{label}，当前{direction}" : label);
        }
        SetHeader(SortRecommendedButton, "推荐", "推荐状态");
        SetHeader(SortUseCaseButton, "数据用途", "数据用途");
        SetHeader(SortNameButton, "文件与内容", "文件名");
        SetHeader(SortSizeButton, "大小", "文件大小");
        SetHeader(SortModifiedButton, "修改时间", "修改时间");
        SetMenu(SortPathMenuItem, "按文件路径排序");
        SetMenu(SortDescriptionMenuItem, "按文件说明排序");
    }

    private async Task LoadRecordsAsync(int? pageOffset = null, ResultDirectPageAnchor? directAnchor = null,
        (string Key, bool Descending)? sort = null, HashSet<string>? selectedPaths = null)
    {
        var scope = _selectedScope;
        if (scope is null || !_loads.CanLoadRecords || _location.LoadedRoot is null)
        {
            return;
        }

        // Paging and sorting operate on the applied query, even with unsubmitted text in the editor.
        var query = pageOffset.HasValue ? _appliedQuery : new ResultRecordsRequest
        {
            Root = _location.RequireLoadedRoot(),
            Scope = scope.Path, TimeDirectory = scope.TimeDirectory,
            DirectDirectory = _direct?.DirectoryPath,
            Section = _direct is null ? (SectionComboBox.SelectedItem as SectionOption)?.Key ?? "all" : "all",
            Query = _direct is null ? SearchTextBox.Text : "",
            UseCase = _direct is not null || UseCaseComboBox.SelectedIndex <= 0 ? "" : UseCaseComboBox.SelectedItem?.ToString() ?? "",
            IncludeInternal = ShowInternalCheckBox.IsChecked is true,
        };
        if (query is null) return;
        var requestedSort = sort ?? _sort;
        if (sort.HasValue) selectedPaths ??= SelectedRecords().Select(record => record.Path).ToHashSet(StringComparer.Ordinal);
        var request = _loads.InvalidateRecords();
        var restorePreview = false;
        _pendingSort = sort;
        _recordsBusy = true;
        IndexInfoBar.IsOpen = false;
        ResultStatusText.Text = "正在读取结果记录…";
        RefreshInteractionState();
        try
        {
            var response = await App.Current.ControlPlane.GetResultRecordsAsync(
                query.Root, query.Scope, query.TimeDirectory, query.Section, query.Query,
                query.UseCase, query.IncludeInternal, offset: pageOffset ?? 0, directDirectory: query.DirectDirectory,
                directAnchor: directAnchor, sortBy: requestedSort.Key, sortDescending: requestedSort.Descending);
            if (!_loads.IsCurrentRecordRequest(request))
            {
                return;
            }

            ResultList.SelectedItems.Clear();
            ResetPreview();
            _appliedQuery = query;
            _displayedPage = response;
            if (_sort != (response.SortBy, response.SortDescending))
            {
                _sort = (response.SortBy, response.SortDescending);
                UpdateSortIndicators();
            }
            _records.Clear();
            foreach (var record in response.Records)
            {
                _records.Add(record);
                if (selectedPaths?.Contains(record.Path) == true) ResultList.SelectedItems.Add(record);
            }
            UpdateExplorer();

            if (_direct is null) UpdateUseCases(response.UseCases, query.UseCase);
            EmptyResultsPanel.Visibility = _records.Count == 0
                ? Visibility.Visible
                : Visibility.Collapsed;
            EmptyResultsText.Text = response.FilteredCount == 0
                ? (_direct is null ? "当前筛选条件没有结果" : "此目录没有可浏览的文件或文件夹")
                : "请选择结果";
            if (response.Offset > 0 && _records.Count == 0)
                EmptyResultsText.Text = "当前页已无结果，请返回上一页或重新筛选。";
            else if (_records.Count == 0 && response.HasMore)
                EmptyResultsText.Text = "此位置之前已无结果，点击「下一页」查看当前目录。";
            PageRange.Text = _records.Count == 0 ? $"共 {response.FilteredCount} 条" :
                $"第 {response.Offset + 1}–{response.Offset + _records.Count} 条，共 {response.FilteredCount} 条";
            RecordPager.Visibility = response.Offset > 0 || response.HasMore ? Visibility.Visible : Visibility.Collapsed;
            ResultStatusText.Text = ResultPageStatus(response);
            if (_records.Count > 0) ResultList.ScrollIntoView(_records[0]);
            ScopeStatusText.Text = scope.IndexStateDisplay.Length > 0
                ? $"{scope.Name} · {scope.IndexStateDisplay}"
                : scope.Name;
            ReportPageStatus(
                $"结果浏览 · {response.FilteredCount} 个匹配文件");
            restorePreview = selectedPaths is { Count: > 0 } && ResultList.SelectedItems.Count > 0;
        }
        catch (ControlPlaneException exception) when (
            _loads.IsCurrentRecordRequest(request)
            && exception.Code is "RESULT_INDEX_MISSING" or "RESULT_INDEX_INVALID")
        {
            ClearResults();
            EmptyResultsPanel.Visibility = Visibility.Visible;
            EmptyResultsText.Text = "结果索引不可用";
            IndexInfoBar.Message = exception.ToDisplayMessage();
            IndexInfoBar.IsOpen = true;
            ResultStatusText.Text = "请创建或刷新当前索引";
            RefreshInteractionState();
        }
        catch (Exception exception)
        {
            if (_loads.IsCurrentRecordRequest(request))
            {
                ResultStatusText.Text = sort.HasValue ? "排序失败，仍显示原页" :
                    pageOffset.HasValue ? "翻页失败，仍显示原页" : "结果记录读取失败";
                ShowError(exception is ControlPlaneException problem ? problem.ToDisplayMessage() : exception.Message,
                    "结果记录读取失败");
            }
        }
        finally
        {
            if (_loads.IsCurrentRecordRequest(request))
            {
                _recordsBusy = false;
                _pendingSort = null;
                RefreshInteractionState();
            }
        }
        if (restorePreview && _loads.IsCurrentRecordRequest(request)) await UpdateSelectionPreviewAsync();
    }

    private void UpdateUseCases(IReadOnlyList<string> useCases, string selected)
    {
        _updatingFilters = true;
        try
        {
            var items = new[] { "全部用途" }.Concat(useCases).ToArray();
            UseCaseComboBox.ItemsSource = items;
            var index = Array.FindIndex(
                items,
                item => string.Equals(item, selected, StringComparison.Ordinal));
            UseCaseComboBox.SelectedIndex = Math.Max(index, 0);
        }
        finally
        {
            _updatingFilters = false;
        }
    }

    private async void OnFilterChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!_updatingFilters && IsLoaded && _selectedScope is not null)
        {
            await RefreshSelectedScopeAsync();
        }
    }

    private async void OnApplyFilterClicked(object sender, RoutedEventArgs e)
    {
        await RefreshSelectedScopeAsync();
    }

    private async void OnSearchKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == Windows.System.VirtualKey.Enter)
        {
            e.Handled = true;
            await RefreshSelectedScopeAsync();
        }
    }

    private async void OnBuildIndexClicked(object sender, RoutedEventArgs e)
    {
        await BuildIndexAsync();
    }

    private async Task BuildIndexAsync()
    {
        var scope = _selectedScope;
        var root = _location.LoadedRoot;
        if (scope is null
            || root is null
            || (!scope.CanBuildMissingIndexes && !scope.CanRefreshIndex)
            || _scopeBusy || _recordsBusy || _indexBusy)
        {
            ShowWarning("请选择结果根目录、对比组、时间目录或模型。", "无法创建索引");
            return;
        }

        _loads.BeginIndex();
        var indexRequest = _loads.IndexRevision;
        _cancelIndexRequested = false;
        _activeIndexOperationId = null;
        _activeIndexBatchId = null;
        IndexProgressBar.Visibility = Visibility.Visible;
        ResultStatusText.Text = scope.CanBuildMissingIndexes ? "正在查找缺失索引的时间目录…" : "正在创建结果索引…";
        RefreshInteractionState();
        try
        {
            if (scope.CanBuildMissingIndexes)
            {
                var batch = await App.Current.ControlPlane.StartResultIndexBatchAsync(root, scope.Path, Guid.NewGuid());
                await ObserveIndexBatchAsync(batch, indexRequest);
                return;
            }
            var initial = await App.Current.ControlPlane.StartResultIndexBuildAsync(
                root,
                scope.TimeDirectory,
                Guid.NewGuid());
            _activeIndexOperationId = initial.OperationId;
            RefreshInteractionState();
            ApplyIndexSnapshot(initial, indexRequest);
            var progress = new Progress<ResultIndexOperationSnapshot>(
                update => ApplyIndexSnapshot(update, indexRequest));
            var finalSnapshot = await App.Current.ControlPlane.PollResultIndexUntilTerminalAsync(
                initial,
                progress);
            ApplyIndexSnapshot(finalSnapshot, indexRequest);
            await CompleteIndexOperationAsync(finalSnapshot);
        }
        catch (OperationCanceledException)
        {
            ResultStatusText.Text = "结果索引已取消";
        }
        catch (ControlPlaneException exception)
        {
            ShowError(exception.ToDisplayMessage(), "结果索引失败");
        }
        catch (Exception exception)
        {
            ShowError(exception.Message, "结果索引失败");
        }
        finally
        {
            ClearIndexBusyState(indexRequest);
        }
    }

    private async Task ObserveIndexBatchAsync(ResultIndexBatchSnapshot batch, long indexRequest)
    {
        _activeIndexBatchId = batch.BatchId;
        IndexProgressBar.Visibility = Visibility.Visible;
        IndexProgressBar.IsIndeterminate = false;
        while (!batch.IsTerminal)
        {
            if (!_loads.IsCurrentIndexRequest(indexRequest)) return;
            _cancelIndexRequested |= batch.Status == "cancelling";
            IndexProgressBar.Maximum = Math.Max(1, batch.Total);
            IndexProgressBar.Value = batch.Processed;
            var state = _cancelIndexRequested ? "正在取消补建" : "正在补建索引";
            var progress = $"{state} · {batch.Processed}/{batch.Total} 个目录 · 跳过 {batch.Skipped} · 失败 {batch.Failed}";
            ResultStatusText.Text = string.IsNullOrWhiteSpace(batch.CurrentDirectory)
                ? progress : $"{progress} · {batch.CurrentDirectory}";
            ReportPageStatus(progress);
            RefreshInteractionState();
            await Task.Delay(400);
            batch = await App.Current.ControlPlane.GetResultIndexBatchAsync(batch.BatchId);
        }

        if (!_loads.IsCurrentIndexRequest(indexRequest)) return;
        _loads.EndIndex();
        await RefreshScopesAsync(batch.ScopeDirectory, batch.Root);
        if (!_loads.IsCurrentIndexRequest(indexRequest)) return;
        var counts = $"共 {batch.Total} 个目录 · 成功 {batch.Succeeded} · 跳过 {batch.Skipped} · 失败 {batch.Failed} · 取消 {batch.Cancelled}";
        ResultStatusText.Text = counts;
        if (batch.Failed > 0 || batch.Status == "failed")
        {
            var details = string.Join(Environment.NewLine, batch.Failures.Select(f => $"{f.TimeDirectory} · {f.Message}"));
            ShowError(string.IsNullOrEmpty(details) ? counts : counts + Environment.NewLine + details, "补建索引存在失败");
        }
        else if (batch.Status == "cancelled")
            ShowWarning(counts, "补建索引已取消");
        else
            App.Current.MainWindow.ShowFeedback("补建索引完成", counts, InfoBarSeverity.Success);
    }

    private void ApplyIndexSnapshot(ResultIndexOperationSnapshot snapshot, long indexRequest)
    {
        if (!_indexBusy || !_loads.IsCurrentIndexRequest(indexRequest)
            || (_activeIndexOperationId is not null
            && !string.Equals(
                _activeIndexOperationId,
                snapshot.OperationId,
                StringComparison.Ordinal)))
        {
            return;
        }

        _activeIndexOperationId ??= snapshot.OperationId;
        var current = string.IsNullOrWhiteSpace(snapshot.Progress.CurrentItem)
            ? string.Empty
            : $" · {snapshot.Progress.CurrentItem}";
        ResultStatusText.Text =
            $"{IndexStatusDisplay(snapshot.Status)} · 已处理 {snapshot.Progress.Processed} 个{current}";
        ReportPageStatus(
            $"结果索引 · {IndexStatusDisplay(snapshot.Status)} · {snapshot.Progress.Processed} 个");
    }

    private async Task CompleteIndexOperationAsync(ResultIndexOperationSnapshot snapshot)
    {
        await _loads.CompleteIndexAsync(
            snapshot.Status,
            () => ReloadPublishedIndexAsync(snapshot.Request));
        switch (snapshot.Status)
        {
            case "succeeded":
                App.Current.MainWindow.ShowFeedback("结果索引已建立", snapshot.Request.TimeDirectory, InfoBarSeverity.Success);
                break;
            case "cancelled":
                ResultStatusText.Text = "结果索引已取消，旧索引保持不变";
                ShowWarning("索引取消前产生的临时文件已清理，原有索引未被覆盖。", "结果索引已取消");
                break;
            case "failed":
                var message = snapshot.Error?.Message ?? "结果索引未能完成。";
                ResultStatusText.Text = "结果索引失败";
                ShowError(message, "结果索引失败");
                break;
        }
    }

    private Task ReloadPublishedIndexAsync(ResultIndexOperationRequest request)
    {
        if (_selectedScope is not { } scope
            || !string.Equals(_location.LoadedRoot, request.Root, StringComparison.OrdinalIgnoreCase)
            || !string.Equals(scope.TimeDirectory, request.TimeDirectory, StringComparison.OrdinalIgnoreCase))
            return RefreshScopesAsync(request.TimeDirectory, request.Root);

        // The index covers the batch, but the user may be viewing only one model.
        var page = _displayedPage;
        var query = _appliedQuery;
        var selectedPaths = SelectedRecords().Where(record => !record.IsDirectory)
            .Select(record => record.Path).ToHashSet(StringComparer.OrdinalIgnoreCase);
        _location.DirectBookmark = null;
        return RefreshScopesAsync(scope.Path, request.Root, loadSelectedScope: () =>
        {
            if (!string.Equals(_selectedScope?.Path, scope.Path, StringComparison.OrdinalIgnoreCase))
                return RefreshSelectedScopeAsync();
            if (page is not { Source: "index" } || query is null)
                return LoadRecordsAsync(selectedPaths: selectedPaths);
            _appliedQuery = query;
            return LoadRecordsAsync(page.Offset, selectedPaths: selectedPaths);
        });
    }

    private async void OnCancelIndexClicked(object sender, RoutedEventArgs e)
    {
        var operationId = _activeIndexOperationId;
        var batchId = _activeIndexBatchId;
        var indexRequest = _loads.IndexRevision;
        if (!_indexBusy
            || (string.IsNullOrWhiteSpace(operationId) && string.IsNullOrWhiteSpace(batchId))
            || _cancelIndexRequested)
        {
            return;
        }

        _cancelIndexRequested = true;
        ResultStatusText.Text = "正在取消结果索引…";
        RefreshInteractionState();
        try
        {
            if (batchId is not null)
            {
                await App.Current.ControlPlane.CancelResultIndexBatchAsync(batchId);
                return;
            }
            var snapshot = await App.Current.ControlPlane.CancelResultIndexOperationAsync(
                operationId!);
            ApplyIndexSnapshot(snapshot, indexRequest);
        }
        catch (OperationCanceledException)
        {
            // Safe shutdown cancels the request.
        }
        catch (Exception exception)
        {
            if (_indexBusy && _loads.IsCurrentIndexRequest(indexRequest))
            {
                _cancelIndexRequested = false;
                ShowError(exception.Message, "无法取消结果索引");
                RefreshInteractionState();
            }
        }
    }

    private async void OnResultSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_recordsBusy || FileOperationBusy) return;
        await UpdateSelectionPreviewAsync();
    }

    private async Task UpdateSelectionPreviewAsync()
    {
        var primary = SelectedRecords().FirstOrDefault();
        if (primary is { Internal: false, IsDirectory: false })
        {
            RefreshInteractionState();
            await LoadPreviewAsync(primary);
        }
        else
        {
            ResetPreview();
            if (primary is { Internal: true } && _displayedPage is { Source: "index" } page)
            {
                string Field(string key) => page.IndexMetadata.TryGetValue(key, out var value)
                    && !string.IsNullOrWhiteSpace(value) ? value : "未记录";
                PreviewTitleText.Text = "预览 · 内部索引（只读）";
                PreviewTextBox.Text = string.Join(Environment.NewLine,
                    $"索引文件：{primary.Path}",
                    $"索引版本：{Field("schema_version")}",
                    $"绑定目录：{Field("canonical_path")}",
                    $"记录数量：{Field("record_count")}",
                    $"更新时间：{Field("updated_at")}",
                    $"目录身份摘要：{Field("identity_hash")}");
            }
            if (_direct is not null && primary is { IsDirectory: true }) PreviewTextBox.Text = "双击文件夹或点击“进入文件夹”继续浏览。";
            RefreshInteractionState();
        }
    }

    private async Task LoadPreviewAsync(ResultRecordItem record)
    {
        var request = ++_previewRequest;
        HideTablePreview();
        PreviewTitleText.Text = $"预览 · {record.Name}";
        PreviewImage.Source = null;
        PreviewImageScrollViewer.Visibility = Visibility.Collapsed;
        PreviewTextBox.Visibility = Visibility.Visible;
        PreviewTextBox.Text = "正在读取预览…";
        try
        {
            var preview = await ReadFilePreviewAsync(record);
            if (request != _previewRequest)
            {
                return;
            }

            switch (preview.Kind)
            {
                case "table":
                    PreviewTable.Show(preview);
                    SetWorksheetPicker(preview);
                    PreviewTextBox.Visibility = Visibility.Collapsed;
                    PreviewTable.Visibility = Visibility.Visible;
                    break;
                case "text":
                    PreviewTextBox.Text = preview.Truncated
                        ? preview.Text + Environment.NewLine + Environment.NewLine + "— 预览已按大小截断 —"
                        : preview.Text;
                    break;
                case "image":
                    await ShowImagePreviewAsync(preview.MediaPath, request);
                    break;
                default:
                    PreviewTextBox.Text = preview.Message;
                    break;
            }
        }
        catch (ControlPlaneException exception)
        {
            if (request == _previewRequest)
            {
                PreviewTextBox.Text = exception.ToDisplayMessage();
            }
        }
        catch (Exception exception)
        {
            if (request == _previewRequest)
            {
                PreviewTextBox.Text = exception.Message;
            }
        }
    }

    private Task<ResultPreviewResponse> ReadFilePreviewAsync(ResultRecordItem record, string? worksheet = null)
    {
        _direct?.ValidateFile(record.Path);
        return App.Current.ControlPlane.GetResultPreviewAsync(
            _appliedQuery?.Root ?? _location.RequireLoadedRoot(), record.Path, worksheet: worksheet);
    }

    private void SetWorksheetPicker(ResultPreviewResponse? preview)
    {
        _worksheetPending = false;
        _displayedWorkbook = preview?.SelectedWorksheet is null ? null : preview;
        _updatingWorksheets = true;
        try
        {
            WorksheetPanel.Visibility = _displayedWorkbook is null ? Visibility.Collapsed : Visibility.Visible;
            bool multiple = _displayedWorkbook?.Worksheets.Count > 1;
            WorksheetLabel.Text = multiple ? "工作表" : _displayedWorkbook?.SelectedWorksheet;
            WorksheetPicker.Visibility = multiple ? Visibility.Visible : Visibility.Collapsed;
            WorksheetPicker.ItemsSource = multiple ? _displayedWorkbook!.Worksheets : null;
            WorksheetPicker.SelectedItem = multiple ? _displayedWorkbook!.SelectedWorksheet : null;
        }
        finally { _updatingWorksheets = false; }
    }

    private void RestoreDisplayedWorksheet()
    {
        SetWorksheetPicker(_displayedWorkbook);
        PreviewTable.Visibility = Visibility.Visible;
        PreviewTextBox.Visibility = Visibility.Collapsed;
    }

    private void InvalidatePreview()
    {
        ++_previewRequest;
        if (_worksheetPending) RestoreDisplayedWorksheet();
    }

    private async void OnWorksheetChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_updatingWorksheets || WorksheetPicker.SelectedItem is not string worksheet
            || _displayedWorkbook is not { } displayed || SelectedRecords().FirstOrDefault() is not { } record
            || !string.Equals(displayed.Path, record.Path, StringComparison.OrdinalIgnoreCase)) return;
        if (!_worksheetPending && worksheet == displayed.SelectedWorksheet) return;
        var request = ++_previewRequest;
        if (worksheet == displayed.SelectedWorksheet) { RestoreDisplayedWorksheet(); return; }
        _worksheetPending = true;
        PreviewTable.Visibility = Visibility.Collapsed;
        PreviewTextBox.Visibility = Visibility.Visible;
        PreviewTextBox.Text = $"正在读取工作表“{worksheet}”…";
        try
        {
            var preview = await ReadFilePreviewAsync(record, worksheet);
            if (request != _previewRequest) return;
            PreviewTable.Show(preview);
            _displayedWorkbook = preview;
            RestoreDisplayedWorksheet();
        }
        catch (Exception error)
        {
            if (request != _previewRequest) return;
            RestoreDisplayedWorksheet();
            ShowWarning(error is ControlPlaneException problem ? problem.ToDisplayMessage() : error.Message, "无法切换工作表");
        }
    }

    private async Task ShowImagePreviewAsync(string path, long request)
    {
        var file = await StorageFile.GetFileFromPathAsync(path);
        using var stream = await file.OpenReadAsync();
        var bitmap = new BitmapImage();
        await bitmap.SetSourceAsync(stream);
        if (request != _previewRequest)
        {
            return;
        }

        PreviewImage.Source = bitmap;
        PreviewTextBox.Visibility = Visibility.Collapsed;
        PreviewImageScrollViewer.Visibility = Visibility.Visible;
    }

    private void HideTablePreview()
    {
        SetWorksheetPicker(null);
        PreviewTable.Visibility = Visibility.Collapsed;
        PreviewTable.Clear();
    }

    private async void OnOpenFileClicked(object sender, RoutedEventArgs e)
    {
        if (!OpenFileButton.IsEnabled || ResultList.SelectedItem is not ResultRecordItem { Internal: false } record
            || !_records.Contains(record)) return;
        if (record.IsDirectory)
        {
            await EnterDirectFolderAsync(record);
            return;
        }

        try
        {
            _direct?.ValidateFile(record.Path);
            var file = await StorageFile.GetFileFromPathAsync(record.Path);
            if (!await Launcher.LaunchFileAsync(file))
            {
                ShowWarning("系统没有可用于打开该文件的关联程序。", "未能打开文件");
            }
        }
        catch (Exception exception)
        {
            ShowError(exception.Message, "未能打开文件");
        }
    }

    private async void OnRevealFileClicked(object sender, RoutedEventArgs e)
    {
        if (!RevealFileButton.IsEnabled || ResultList.SelectedItem is not ResultRecordItem record || !_records.Contains(record))
        {
            return;
        }

        try
        {
            _direct?.ValidateFile(record.Path);
            var file = await StorageFile.GetFileFromPathAsync(record.Path);
            var folderPath = Path.GetDirectoryName(record.Path)
                ?? throw new InvalidOperationException("文件没有可定位的父目录。");
            var folder = await StorageFolder.GetFolderFromPathAsync(folderPath);
            var options = new FolderLauncherOptions();
            options.ItemsToSelect.Add(file);
            if (!await Launcher.LaunchFolderAsync(folder, options))
            {
                ShowWarning("系统未能打开文件所在目录。", "未能定位文件");
            }
        }
        catch (Exception exception)
        {
            ShowError(exception.Message, "未能定位文件");
        }
    }

    private void OnCopyPathClicked(object sender, RoutedEventArgs e)
    {
        if (!CopyPathButton.IsEnabled) return;
        var records = SelectedRecords();
        if (records.Count == 0)
        {
            return;
        }

        try
        {
            var package = new DataPackage();
            package.SetText(string.Join(Environment.NewLine, records.Select(record => record.Path)));
            Clipboard.SetContent(package);
            App.Current.MainWindow.ShowFeedback("路径已复制", $"{records.Count} 个文件路径已复制到剪贴板。", InfoBarSeverity.Success);
        }
        catch (Exception error) { ShowError(error.Message, "未能复制路径"); }
    }

    private async void OnRecycleClicked(object sender, RoutedEventArgs e)
    {
        if (_direct is not null || FileOperationBusy || _recordsBusy || _scopeBusy || _indexBusy || App.Current.Session.IsClosing
            || !App.Current.PendingResultFileOperation.IsCompleted) return;
        var records = SelectedRecords().ToArray();
        if (records.Length == 0 || records.Any(record => record.Internal || record.IsDirectory
            || !ResultFileRecycle.IsExport(record.Path))) return;
        var root = _location.LoadedRoot;
        if (root is null) return;
        var message = $"将所选 {records.Length} 个导出文件移到系统回收站。公共数据文件可能被多个对比组引用。\n\n"
            + string.Join("\n", records.Take(8).Select(record => record.Path));
        if (records.Length > 8) message += $"\n另有 {records.Length - 8} 个文件";
        var confirm = new ContentDialog
        {
            XamlRoot = XamlRoot, Title = "清理所选结果", Content = message,
            PrimaryButtonText = "移到回收站", CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        App.Current.PendingResultFileOperation = completion.Task;
        _recycleBusy = true;
        RefreshInteractionState();
        try
        {
            if (await confirm.ShowAsync() != ContentDialogResult.Primary || App.Current.Session.IsClosing) return;
            ResetPreview();
            var operation = RecycleSelectedAsync(root, records);
            await operation;
        }
        catch (Exception exception)
        {
            ShowError(exception.Message, "结果清理失败");
        }
        finally
        {
            completion.TrySetResult();
            if (ReferenceEquals(App.Current.PendingResultFileOperation, completion.Task))
                App.Current.PendingResultFileOperation = Task.CompletedTask;
            _recycleBusy = false;
            RefreshInteractionState();
        }
    }

    private async Task RecycleSelectedAsync(string root, ResultRecordItem[] records)
    {
        var completed = 0;
        string? failure = null;
        try
        {
            foreach (var record in records)
            {
                ResultStatusText.Text = $"正在清理 {completed + 1}/{records.Length} · {record.Name}";
                await Task.Run(() => ResultFileRecycle.Recycle(root, record.Path));
                completed++;
            }
        }
        catch (OperationCanceledException) { failure = "清理已取消"; }
        catch (Exception exception) { failure = exception.Message; }
        if (completed > 0)
        {
            // Rebuild even after a partial failure so removed files cannot remain selected.
            if (!string.IsNullOrWhiteSpace(_selectedScope?.TimeDirectory)) await BuildIndexAsync();
            else await RefreshSelectedScopeAsync();
        }
        ResultStatusText.Text = $"已清理 {completed}/{records.Length} 个文件";
        if (failure is not null) ShowWarning(failure, $"已清理 {completed} 个，剩余 {records.Length - completed} 个");
        else App.Current.MainWindow.ShowFeedback("结果已移到回收站", $"{completed} 个文件", InfoBarSeverity.Success);
    }

    private IReadOnlyList<ResultRecordItem> SelectedRecords()
    {
        return ResultList.SelectedItems.OfType<ResultRecordItem>().Where(_records.Contains).ToArray();
    }

    private void ResetPreview()
    {
        _previewRequest++;
        HideTablePreview();
        PreviewTitleText.Text = "预览";
        PreviewImage.Source = null;
        PreviewImageScrollViewer.Visibility = Visibility.Collapsed;
        PreviewTextBox.Visibility = Visibility.Visible;
        PreviewTextBox.Text = "选择一个文件后显示预览。";
        OpenFileButton.IsEnabled = false;
        RevealFileButton.IsEnabled = false;
        CopyPathButton.IsEnabled = false;
        ExportButton.IsEnabled = false;
        RecycleButton.IsEnabled = false;
    }

    private void ClearIndexBusyState(long indexRequest)
    {
        if (!_loads.IsCurrentIndexRequest(indexRequest))
        {
            return;
        }

        _loads.EndIndex();
        _cancelIndexRequested = false;
        _activeIndexOperationId = null;
        _activeIndexBatchId = null;
        IndexProgressBar.Visibility = Visibility.Collapsed;
        IndexProgressBar.IsIndeterminate = true;
        RefreshInteractionState();
    }

    private void RefreshInteractionState()
    {
        var idle = !_scopeBusy && !_recordsBusy && !_indexBusy && !FileOperationBusy;
        var canSort = !_scopeBusy && !_indexBusy && !FileOperationBusy && _displayedPage is not null;
        foreach (var button in SortHeaders.Children.OfType<Button>()) button.IsEnabled = canSort;
        SortPathMenuItem.IsEnabled = SortDescriptionMenuItem.IsEnabled = canSort;
        ResetSortMenuItem.IsEnabled = canSort && (_pendingSort ?? _sort).Key != "default";
        ResultList.IsEnabled = idle || (_indexBusy && !_scopeBusy && !_recordsBusy && !FileOperationBusy
            && _displayedPage?.Source == "index");
        var selected = SelectedRecords();
        var first = selected.FirstOrDefault();
        var enterFolder = _direct is not null && first is { IsDirectory: true } && selected.Count == 1;
        OpenFileButton.Content = enterFolder ? "进入文件夹" : "打开文件";
        OpenFileButton.IsEnabled = idle && (enterFolder || first is { Internal: false, IsDirectory: false });
        RevealFileButton.IsEnabled = idle && first is { IsDirectory: false };
        CopyPathButton.IsEnabled = idle && selected.Count > 0;
        ExportButton.IsEnabled = idle && selected.Any(record => !record.Internal && !record.IsDirectory);
        RecycleButton.IsEnabled = idle && _direct is null && selected.Count > 0 && selected.All(record =>
            !record.Internal && !record.IsDirectory && ResultFileRecycle.IsExport(record.Path));
        DirectBrowseButton.IsEnabled = idle && _selectedScope?.Kind is "batch" or "odb";
        DirectToolbar.Visibility = _direct is null ? Visibility.Collapsed : Visibility.Visible;
        FilterPanel.Visibility = _direct is null ? Visibility.Visible : Visibility.Collapsed;
        DirectRefreshButton.IsEnabled = DirectExitButton.IsEnabled = idle;
        DirectBuildIndexButton.IsEnabled = idle && _selectedScope?.CanRefreshIndex == true;
        DirectBuildIndexButton.Content = _selectedScope?.IndexState == "missing" ? "创建索引" : "刷新索引";
        DirectUpButton.IsEnabled = idle && _direct is { AtScope: false };
        DirectPathText.Text = _direct is null ? "" : "直接浏览 · "
            + (_direct.AtScope ? _selectedScope?.Name : Path.GetRelativePath(_direct.Scope, _direct.DirectoryPath));
        ToolTipService.SetToolTip(DirectPathText, _direct?.DirectoryPath);
        PreviousPageButton.IsEnabled = idle && _displayedPage is { Offset: > 0 };
        NextPageButton.IsEnabled = idle && _displayedPage is { HasMore: true };
        RootTextBox.IsEnabled = idle;
        BrowseButton.IsEnabled = idle;
        RefreshScopesButton.IsEnabled = idle;
        ScopeTree.IsEnabled = idle;
        ShowInternalCheckBox.IsEnabled = idle;
        SectionComboBox.IsEnabled = idle;
        UseCaseComboBox.IsEnabled = idle;
        SearchTextBox.IsEnabled = idle;
        BuildIndexButton.Content = _selectedScope?.CanBuildMissingIndexes == true ? "补建缺失索引" : "刷新索引";
        BuildIndexButton.IsEnabled = idle && _selectedScope is { } scope && (scope.CanBuildMissingIndexes || scope.CanRefreshIndex);
        CancelIndexButton.Content = _activeIndexBatchId is null ? "取消索引" : "取消补建";
        CancelIndexButton.IsEnabled = _indexBusy
            && !_cancelIndexRequested
            && (_activeIndexOperationId is not null || _activeIndexBatchId is not null);
    }

    private void ShowError(string message, string title = "操作失败")
    {
        App.Current.MainWindow.ShowFeedback(title, message, InfoBarSeverity.Error);
        ReportPageStatus(title);
    }

    private void ShowWarning(string message, string title)
    {
        App.Current.MainWindow.ShowFeedback(title, message, InfoBarSeverity.Warning);
    }

    private static string SourceDisplay(string source) => source switch
    {
        "direct" => "直接浏览",
        "index" => "正式索引",
        "shared_asset" => "ODB 公共数据",
        _ => source,
    };

    private static string IndexStatusDisplay(string status) => status switch
    {
        "queued" => "等待索引",
        "starting" => "正在准备",
        "running" => "正在索引",
        "cancelling" => "正在取消",
        "succeeded" => "索引完成",
        "cancelled" => "索引已取消",
        "failed" => "索引失败",
        _ => status,
    };

    private sealed record SectionOption(string Key, string Label)
    {
        public override string ToString() => Label;
    }
}
