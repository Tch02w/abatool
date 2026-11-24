using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;
using Windows.Storage.Pickers;
using Windows.System;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage : Page, IWorkbenchExplorerPage
{
    private readonly ObservableCollection<OdbFileRow> _odbItems = [];
    private readonly Dictionary<string, OdbFileRow> _odbByPath =
        new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _activePathKeys =
        new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, IReadOnlyDictionary<string, OdbLegendOverride>> _legendOverridesByGroup =
        new(StringComparer.OrdinalIgnoreCase);
    private static readonly (string Field, string Label)[] LegendFields =
    [
        ("PILE_U_MAG", "桩身位移大小"),
        ("PILE_CON_S_MISES", "桩身混凝土 Mises 应力"),
        ("PILE_STEEL_S_MISES", "钢管 / 型钢 Mises 应力"),
        ("PILE_CON_DAMAGET", "桩身混凝土拉伸损伤"),
        ("PILE_CON_DAMAGEC", "桩身混凝土压缩损伤"),
        ("SOIL_PEEQ_XZ", "土体等效塑性应变（XZ 切片）"),
        ("SOIL_PEMAG_XZ", "土体塑性应变大小（XZ 切片）"),
        ("SOIL_S33_XZ", "土体竖向应力 S33（XZ 切片）"),
        ("SOIL_S_MISES_XZ", "土体 Mises 应力（XZ 切片）"),
        ("REBAR_LONG_S_MISES_UNDEFORMED", "纵筋 Mises 应力（未变形）"),
        ("REBAR_LONG_S11_UNDEFORMED", "纵筋轴向应力 S11（未变形）"),
    ];

    private bool _discoveryBusy;
    private bool _updatingSelection;
    private string? _lastDiscoveryRoot;
    private bool _updatingRunScopes;
    private string? _scopeCatalogRoot;
    private List<OdbRunScope>? _runScopeChoices;
    private readonly OdbPostprocessResultLocations _resultLocations = new();
    private readonly Dictionary<string, List<string>> _groupMemberOrder = new(StringComparer.OrdinalIgnoreCase);
    private readonly OdbPostprocessWorkspaceStore _workspaceStore = new(Path.Combine(
        WorkbenchProfile.Current.StateDirectory, "postprocess-workspaces"));
    private readonly HashSet<string> _unreadableWorkspaces = new(StringComparer.OrdinalIgnoreCase);
    private bool _compatibilityBusy;
    private bool _postprocessBusy;
    private bool _cancelRequested;
    private bool _recoveryAttempted;
    private Task? _initialLoadTask;
    private string? _activeOperationId;
    private string? _activeAttemptId;
    private long _lastOperationVersion = -1;
    private string? _activePostprocessOperationId;
    private string? _activePostprocessKind;
    private long _lastPostprocessVersion = -1;
    private int _displayedLogCount;
    private readonly PostprocessingExplorerAdapter _explorerAdapter;

    public OdbPostprocessingPage()
    {
        InitializeComponent();
        ParallelWorkersNumberBox.Maximum = Math.Max(1, Environment.ProcessorCount);
        RebarToleranceNumberBox.NumberFormatter = new Controls.PlainDecimalFormatter();
        RebarToleranceNumberBox.Value = 0.0001d;
        RebarToleranceNumberBox.SmallChange = 0.0001d;
        Controls.ParameterHelpButton.AddToHeader(ExpectedRebarCountNumberBox, "rebar-count");
        Controls.ParameterHelpButton.AddToHeader(AnimationFpsNumberBox, "animation-fps");
        AnimationDurationNumberBox.NumberFormatter = new Controls.PlainDecimalFormatter();
        Controls.ParameterHelpButton.AddToHeader(AnimationDurationNumberBox, "animation-duration");
        Controls.ParameterHelpButton.AddToHeader(ImageWidthNumberBox, "image-size");
        Controls.ParameterHelpButton.AddToHeader(ImageHeightNumberBox, "image-size");
        Controls.ParameterHelpButton.AddToHeader(RebarToleranceNumberBox, "rebar-tolerance");
        _explorerAdapter = new PostprocessingExplorerAdapter(
            () => string.IsNullOrWhiteSpace(RootTextBox.Text) ? Task.CompletedTask : DiscoverAsync(),
            SelectExplorerOdb,
            ActivateExplorerOdbAsync);
        NavigationCacheMode = NavigationCacheMode.Required;
        OdbList.ItemsSource = _odbItems;
        UpdateRunScopeChoices();
        RootTextBox.TextChanged += (_, _) => RefreshInteractionState();
        App.Current.Session.Register(this, "odb-postprocessing", ["RootTextBox", "RecursiveCheckBox", "GroupNameTextBox", "GroupOperationComboBox"], async () =>
        {
            await WorkbenchSession.WaitForIdleAsync(() => _discoveryBusy || _postprocessRecoveryBusy, "后处理目录读取或恢复");
            if (!SaveWorkspace(forClose: true)) throw new IOException("后处理配置未能保存，关闭已取消。");
        });
        App.Current.Session.RegisterCheckpoint("postprocess-workspace", SavePostprocessDraftAsync);
        _groupQueueTimer.Tick += OnGroupQueueTick;
        Loaded += OnPageLoaded;
        Unloaded += (_, _) => { _groupQueueTimer.Stop(); SaveWorkspace(); };
        RefreshInteractionState();
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _explorerAdapter;

    public async Task<bool> LoadOdbPathAsync(string path, Func<bool>? canApply = null)
    {
        var deadline = DateTime.UtcNow.AddSeconds(30);
        try
        {
            // Session restoration and operation recovery must finish before applying a route.
            // Observe the existing load; do not start a second recovery after a timeout.
            while (_initialLoadTask is null || !_initialLoadTask.IsCompleted)
            {
                if (canApply?.Invoke() is false || App.Current.Session.IsClosing) return false;
                if (DateTime.UtcNow >= deadline)
                    throw new InvalidOperationException("后处理页面仍在加载或恢复原操作，请稍后重试；原操作没有重新启动。");
                await Task.Delay(50);
            }
            await _initialLoadTask;
        }
        catch (Exception error)
        {
            if (canApply?.Invoke() is not false) ShowWarning(error.Message, "不能切换 ODB");
            return false;
        }
        if (!IsLoaded || canApply?.Invoke() is false || App.Current.Session.IsClosing) return false;
        if (GroupQueueBlocksOtherOperations) { ShowWarning("请先结束当前工作区的提取队列。", "不能切换 ODB"); return false; }
        if (_discoveryBusy || _postprocessBusy || _compatibilityBusy || UpgradeBlocksEditing
            || _postprocessRecoveryBusy || DraftPending || _draftActionBusy)
        {
            ShowWarning("请先完成当前读取、检查、后处理或升级操作，并处理待恢复的草稿，再切换 ODB。", "不能切换 ODB");
            return false;
        }
        if (!Path.IsPathFullyQualified(path) || !string.Equals(Path.GetExtension(path), ".odb", StringComparison.OrdinalIgnoreCase))
        {
            ShowWarning("请选择完整的本地 ODB 文件路径。", "不能切换 ODB");
            return false;
        }
        var directory = Path.GetDirectoryName(path)!;
        if (!await DiscoverCoreAsync(directory, canApply)) return false;
        if (DraftPending)
        {
            ShowWarning("该目录存在待恢复草稿，请先选择恢复或保留当前配置，再选择要处理的作业。", "已读取目录，尚未切换选择");
            return false;
        }
        if (_odbByPath.TryGetValue(PathKey(path), out var row))
        {
            OdbList.SelectedItems.Clear();
            OdbList.SelectedItem = row;
            OdbList.ScrollIntoView(row);
            return true;
        }
        ShowWarning($"目录已读取，但未找到请求的 ODB：{path}。请核对文件是否已移动或被扫描规则排除。", "未能定位作业 ODB");
        return false;
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        if (_initialLoadTask?.IsCompleted == true && _groupQueue is { IsActive: true }) StartGroupQueuePolling();
        _initialLoadTask ??= InitializePageAsync();
        try { await _initialLoadTask; }
        catch (Exception error) { ShowWarning(error.Message, "后处理页面恢复未完成"); }
    }

    private async Task InitializePageAsync()
    {
        try
        {
            var resource = await App.Current.ControlPlane.GetLocalResourceAsync();
            ParallelWorkersNumberBox.Maximum = resource.LogicalCpus;
            ToolTipService.SetToolTip(ParallelWorkersNumberBox, $"同时运行的 Abaqus 进程数，上限为本机 {resource.LogicalCpus} 个逻辑线程。每个进程另占内存及许可证。");
        }
        catch (Exception)
        {
            // Keep the local runtime topology fallback; the API validates again.
        }
        if (_recoveryAttempted)
        {
            return;
        }

        _recoveryAttempted = true;
        if (await RecoverUpgradeAsync(showHistory: false)) return;
        if (await RestoreGroupQueueAsync()) return;
        if (!await RecoverActivePostprocessOperationAsync())
        {
            await RecoverActiveCompatibilityOperationAsync();
        }
    }

    private async Task<bool> RecoverActivePostprocessOperationAsync()
    {
        SetPostprocessBusy(true);
        try
        {
            var operations = await App.Current.ControlPlane.ListOdbPostprocessOperationsAsync(activeOnly: true);
            var snapshot = operations.Operations.FirstOrDefault(operation => !operation.IsTerminal
                && !operation.Request.ClientRequestId.StartsWith("pgq:", StringComparison.OrdinalIgnoreCase));
            if (snapshot is null)
            {
                return false;
            }

            if (snapshot.Kind == "odb.postprocess.scan" && snapshot.Request.Paths.Count > 0)
            {
                RestoreRowsFromPostprocessRequest(snapshot.Request);
            }
            else if (!string.IsNullOrWhiteSpace(snapshot.Request.Root))
            {
                RootTextBox.Text = snapshot.Request.Root;
            }

            BeginPostprocessMonitoring(snapshot.Request.ClientRequestId, snapshot.Kind);
            _activePostprocessOperationId = snapshot.OperationId;
            _activePostprocessKind = snapshot.Kind;
            _lastPostprocessVersion = -1;
            _displayedLogCount = 0;
            ApplyPostprocessSnapshot(snapshot);
            App.Current.MainWindow.ReportPageStatus("已恢复未完成的 ODB 后处理操作");
            var progress = new Progress<OdbPostprocessOperationSnapshot>(ApplyPostprocessProgressSnapshot);
            var final = await App.Current.ControlPlane.PollOdbPostprocessUntilTerminalAsync(
                snapshot,
                progress, _postprocessMonitoringSource!.Token);
            ApplyPostprocessSnapshot(final);
            CompletePostprocessOperation(final);
            return true;
        }
        catch (Exception exception)
        {
            if (_postprocessTracking.Active)
            {
                HandlePostprocessInterruption(exception, "原操作恢复失败");
                return true;
            }
            ShowWarning(exception.Message, "未能恢复 ODB 后处理操作");
            return false;
        }
        finally
        {
            EndPostprocessMonitoring();
        }
    }

    private void RestoreRowsFromPostprocessRequest(OdbPostprocessOperationRequestSummary request)
    {
        OdbList.SelectedItems.Clear();
        _odbItems.Clear();
        _odbByPath.Clear();
        RootTextBox.Text = request.Root;
        // An operation request contains only selected paths, not a complete workspace.
        // Do not persist this partial view; the next discovery must reload saved drafts.
        _lastDiscoveryRoot = null;
        ForceRescanCheckBox.IsChecked = request.ForceRescan;
        ParallelWorkersNumberBox.Value = Math.Clamp(request.ParallelWorkers, 1, (int)ParallelWorkersNumberBox.Maximum);
        foreach (var path in request.Paths)
        {
            var row = new OdbFileRow(CreateRecoveryDiscoveryItem(request.Root, path));
            row.MarkStructureAnalysisPending();
            _odbItems.Add(row);
            _odbByPath[PathKey(path)] = row;
        }

        if (_odbItems.Count > 0)
        {
            OdbList.SelectAll();
        }
        ResultCountText.Text = $"{_odbItems.Count} 个";
        DiscoveryMetadataText.Text = "从未完成的结构读取恢复";
        EmptyState.Visibility = _odbItems.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        UpdateExplorer();
    }

    private async Task RecoverActiveCompatibilityOperationAsync()
    {
        SetCompatibilityBusy(true);
        try
        {
            var operationList = await App.Current.ControlPlane.ListOperationsAsync(activeOnly: true);
            var snapshot = operationList.Operations.FirstOrDefault(
                operation => string.Equals(
                        operation.Kind,
                        "odb.compatibility.check",
                        StringComparison.Ordinal)
                    && !operation.IsTerminal
                    && operation.Request is { Paths.Count: > 0 });
            if (snapshot?.Request is not { } request)
            {
                return;
            }

            RestoreRowsFromOperationRequest(request);
            _activeOperationId = snapshot.OperationId;
            _activeAttemptId = snapshot.AttemptId;
            _lastOperationVersion = -1;
            _cancelRequested = string.Equals(snapshot.Status, "cancelling", StringComparison.Ordinal);
            ApplyOperationSnapshot(snapshot);
            App.Current.MainWindow.ReportPageStatus(
                $"已恢复兼容性检查 · {snapshot.Progress.Completed} / {snapshot.Progress.Total}");

            var progress = new Progress<OdbCompatibilityOperationSnapshot>(ApplyOperationSnapshot);
            var finalSnapshot = await App.Current.ControlPlane.PollOperationUntilTerminalAsync(
                snapshot,
                progress);
            ApplyOperationSnapshot(finalSnapshot);
            CompleteCompatibilityOperation(finalSnapshot);
        }
        catch (OperationCanceledException)
        {
            CompatibilityStatusText.Text = "兼容性检查已取消";
            MarkUnfinishedRows("未完成", "兼容性检查在完成前已取消。");
        }
        catch (ControlPlaneException exception)
        {
            ShowWarning(exception.ToDisplayMessage(), "未能恢复兼容性检查");
        }
        catch (Exception exception)
        {
            ShowWarning(exception.Message, "未能恢复兼容性检查");
        }
        finally
        {
            _activeOperationId = null;
            _activeAttemptId = null;
            _cancelRequested = false;
            _activePathKeys.Clear();
            CompatibilityProgress.IsIndeterminate = false;
            SetCompatibilityBusy(false);
        }
    }

    private void RestoreRowsFromOperationRequest(OdbCompatibilityOperationRequest request)
    {
        ErrorInfoBar.IsOpen = false;
        WarningInfoBar.IsOpen = false;
        OdbList.SelectedItems.Clear();
        _odbItems.Clear();
        _odbByPath.Clear();
        _activePathKeys.Clear();
        RootTextBox.Text = request.Root;
        // Compatibility recovery is also a partial view, not an editable workspace snapshot.
        _lastDiscoveryRoot = null;
        ForceRescanCheckBox.IsChecked = request.ForceRescan;

        foreach (var path in request.Paths)
        {
            var item = CreateRecoveryDiscoveryItem(request.Root, path);
            var row = new OdbFileRow(item);
            row.MarkPending();
            _odbItems.Add(row);
            var key = PathKey(row.Path);
            _odbByPath[key] = row;
            _activePathKeys.Add(key);
        }

        OdbList.SelectAll();
        ResultCountText.Text = $"{_odbItems.Count} 个";
        DiscoveryMetadataText.Text = "从未完成操作恢复";
        EmptyState.Visibility = _odbItems.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
        EmptyStateTitle.Text = _odbItems.Count == 0 ? "未能恢复 ODB 列表" : "尚未发现 ODB";
        UpdateExplorer();
    }

    private static OdbDiscoveryItem CreateRecoveryDiscoveryItem(string root, string path)
    {
        var info = new FileInfo(path);
        string relativePath;
        try
        {
            relativePath = Path.GetRelativePath(root, path);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException)
        {
            relativePath = Path.GetFileName(path);
        }

        return new OdbDiscoveryItem
        {
            Path = path,
            RelativePath = relativePath,
            Name = Path.GetFileName(path),
            SizeBytes = info.Exists ? info.Length : 0,
            ModifiedAt = info.Exists
                ? new DateTimeOffset(info.LastWriteTimeUtc)
                : DateTimeOffset.MinValue,
        };
    }

    private async void OnBrowseClicked(object sender, RoutedEventArgs e)
    {
        if (GroupQueueBlocksOtherOperations) return;
        ErrorInfoBar.IsOpen = false;
        try
        {
            var picker = new FolderPicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
                CommitButtonText = "选择此目录",
            };
            picker.FileTypeFilter.Add("*");

            var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
            var folder = await picker.PickSingleFolderAsync();
            if (folder is not null)
            {
                RootTextBox.Text = folder.Path;
                App.Current.MainWindow.ReportPageStatus($"已选择目录 · {folder.Path}");
            }
        }
        catch (Exception exception)
        {
            ShowError("无法打开文件夹选择器。" + Environment.NewLine + exception.Message);
        }
    }

    private async void OnDiscoverClicked(object sender, RoutedEventArgs e)
    {
        await DiscoverAsync();
    }

    private async void OnRootTextBoxKeyDown(object sender, KeyRoutedEventArgs e)
    {
        if (e.Key == VirtualKey.Enter && !_compatibilityBusy && !_postprocessBusy)
        {
            e.Handled = true;
            await DiscoverAsync();
        }
    }

    private async Task DiscoverAsync()
    {
        if (!GroupQueueBlocksOtherOperations) await DiscoverCoreAsync();
    }

    private async Task<bool> DiscoverCoreAsync(string? requestedRoot = null, Func<bool>? canApply = null)
    {
        if (_discoveryBusy || _compatibilityBusy || _postprocessBusy || UpgradeBlocksEditing || DraftPending || _draftActionBusy) return false;
        var root = (requestedRoot ?? RootTextBox.Text).Trim();
        if (string.IsNullOrWhiteSpace(root))
        {
            ShowError("请选择或输入 ODB 根目录。", "无法发现 ODB");
            RootTextBox.Focus(FocusState.Programmatic);
            return false;
        }

        if (!SaveWorkspace()) return false;
        Task draftSave;
        try { draftSave = SavePostprocessDraftAsync(); }
        catch (Exception error) { ShowWarning(error.Message, "草稿未能保存，未切换目录"); return false; }
        SetDiscoveryBusy(true);
        ErrorInfoBar.IsOpen = false;
        WarningInfoBar.IsOpen = false;
        var previousRows = _odbItems.ToArray();
        var selectedPaths = OdbList.SelectedItems.OfType<OdbFileRow>().Select(row => row.Path).ToArray();
        DiscoveryMetadataText.Text = "正在扫描";
        EmptyState.Visibility = previousRows.Length == 0 ? Visibility.Visible : Visibility.Collapsed;
        EmptyStateTitle.Text = "正在发现 ODB…";
        App.Current.MainWindow.ReportPageStatus("正在通过本地控制面发现 ODB…");
        try
        {
            // Lock discovery before the first await, then finish the old root's snapshot.
            await draftSave;
            if (canApply?.Invoke() is false || App.Current.Session.IsClosing) return false;
            var result = await App.Current.ControlPlane.DiscoverOdbsAsync(
                root,
                RecursiveCheckBox.IsChecked is not false);
            if (canApply?.Invoke() is false || App.Current.Session.IsClosing) return false;

            var sameRoot = _lastDiscoveryRoot is not null
                && string.Equals(PathKey(_lastDiscoveryRoot), PathKey(result.Root), StringComparison.OrdinalIgnoreCase)
                && !_unreadableWorkspaces.Contains(PathKey(result.Root));
            var refreshed = OdbDiscoveryReconciler.Reconcile(result.Odbs, previousRows, selectedPaths, sameRoot);
            OdbPostprocessWorkspace? saved = null;
            if (!sameRoot)
            {
                try
                {
                    saved = _workspaceStore.Load(result.Root);
                    _unreadableWorkspaces.Remove(PathKey(result.Root));
                }
                catch (Exception exception)
                {
                    _unreadableWorkspaces.Add(PathKey(result.Root));
                    ShowWarning($"已保留原配置文件，未覆盖：{exception.Message}", "无法恢复后处理配置");
                }
            }
            OdbList.SelectedItems.Clear();
            _odbItems.Clear();
            _odbByPath.Clear();
            ResetCompatibilityPresentation();
            if (!sameRoot) _legendOverridesByGroup.Clear();
            if (!sameRoot)
            {
                _groupMemberOrder.Clear();
                if (saved is not null)
                    foreach (var pair in saved.GroupMemberOrder) _groupMemberOrder[pair.Key] = pair.Value;
            }
            if (!sameRoot) RestoreOutputOptions(saved?.Output ?? new OdbPostprocessOutputOptions());
            if (saved is not null)
                foreach (var pair in saved.Legends) _legendOverridesByGroup[pair.Key] = pair.Value;
            var savedRows = saved?.Rows.ToDictionary(item => PathKey(item.Path), StringComparer.OrdinalIgnoreCase);
            foreach (var row in refreshed.Rows)
            {
                if (savedRows is not null && savedRows.TryGetValue(PathKey(row.Path), out var previous))
                {
                    row.ComparisonGroup = previous.Group;
                    if (previous.Draft is not null) row.UpdatePostprocessJob(previous.Draft);
                    row.MarkStructureAnalysisIncomplete("已恢复参数草稿，请重新读取 ODB 结构。");
                }
                _odbItems.Add(row);
                _odbByPath[PathKey(row.Path)] = row;
            }

            // Old workspaces sometimes kept a group only on its members. Keep
            // its name available if a refresh no longer finds the last member.
            var previousGroups = sameRoot ? previousRows.Select(row => row.ComparisonGroup)
                : saved?.Rows.Select(row => row.Group) ?? [];
            var memberGroups = _odbItems.SelectMany(row => ParseGroupNames(row.ComparisonGroup));
            foreach (var name in previousGroups.SelectMany(ParseGroupNames).Except(memberGroups, StringComparer.OrdinalIgnoreCase))
                _groupMemberOrder.TryAdd(name, []);

            var restoredSelection = savedRows is null ? refreshed.SelectedRows : refreshed.Rows.Where(row =>
                savedRows.TryGetValue(PathKey(row.Path), out var previous) && previous.Selected).ToArray();
            foreach (var row in restoredSelection)
            {
                OdbList.SelectedItems.Add(row);
            }

            RootTextBox.Text = result.Root;
            _lastDiscoveryRoot = result.Root;
            _resultLocations.DiscoveryAccepted(result.Root);
            if (!sameRoot) await LoadWorkspaceRecoveryAsync(result.Root, saved);
            ResultCountText.Text = $"{result.Count} 个";
            DiscoveryMetadataText.Text = $"游标 {result.EventCursor} · {FormatDiscoveryId(result.DiscoveryId)}";
            EmptyState.Visibility = result.Count == 0 ? Visibility.Visible : Visibility.Collapsed;
            EmptyStateTitle.Text = result.Count == 0 ? "目录中没有 ODB" : "尚未发现 ODB";

            if (result.Warnings.Count > 0)
            {
                ShowWarning(
                    string.Join(Environment.NewLine, result.Warnings),
                    "扫描完成，但有警告");
            }

            App.Current.MainWindow.ReportPageStatus(
                result.Count == 0 ? "扫描完成 · 未发现 ODB" : $"扫描完成 · 发现 {result.Count} 个 ODB");
            UpdateExplorer();
            return canApply?.Invoke() is not false && !App.Current.Session.IsClosing;
        }
        catch (ControlPlaneException exception)
        {
            if (_lastDiscoveryRoot is not null) RootTextBox.Text = _lastDiscoveryRoot;
            DiscoveryMetadataText.Text = "扫描失败";
            EmptyStateTitle.Text = "未能发现 ODB";
            ShowError(exception.ToDisplayMessage(), "ODB 发现失败");
        }
        catch (Exception exception)
        {
            if (_lastDiscoveryRoot is not null) RootTextBox.Text = _lastDiscoveryRoot;
            DiscoveryMetadataText.Text = "扫描失败";
            EmptyStateTitle.Text = "未能发现 ODB";
            ShowError("ODB 发现失败。" + Environment.NewLine + exception.Message, "ODB 发现失败");
        }
        finally
        {
            SetDiscoveryBusy(false);
            SaveWorkspace();
        }
        return false;
    }

    private void UpdateExplorer()
    {
        UpdateRunScopeChoices();
        var groups = OdbComparisonGroups.ForBrowser(_odbItems, SavedGroupNames())
            .Select(group => WorkbenchExplorerAdapterBase.Group(
                group.Unassigned ? "postprocess:ungrouped" : $"postprocess:group:{group.Name}",
                group.Name,
                group.Members.Select(row => new ExplorerItem
                {
                    StableId = $"postprocess:odb:{(group.Unassigned ? "" : Uri.EscapeDataString(group.Name.ToUpperInvariant()))}:{row.Path.ToUpperInvariant()}",
                    Kind = ExplorerItemKind.OdbFile,
                    Title = row.Name,
                    Subtitle = $"{row.CompatibilityStatusDisplay} · {row.PostprocessStatusDisplay}",
                    Path = row.Path,
                    Status = row.CompatibilityStatus,
                    Badge = row.CompatibilityStatusDisplay,
                    IconGlyph = "\uE8A5",
                }),
                group.Members.Count.ToString()))
            .ToList();
        _explorerAdapter.Update(
            RootTextBox.Text.Trim(),
            $"ODB {_odbItems.Count} · 分组 {groups.Count}",
            groups);
    }

    private void SelectExplorerOdb(ExplorerItem item)
    {
        if (DraftPending || _draftActionBusy || _discoveryBusy) return;
        if (item.Kind == ExplorerItemKind.Group)
        {
            if (item.StableId.StartsWith("postprocess:group:", StringComparison.Ordinal))
                GroupNameTextBox.Text = item.Title;
            return;
        }
        if (_odbByPath.TryGetValue(PathKey(item.Path), out var row))
        {
            OdbList.SelectedItems.Clear();
            OdbList.SelectedItem = row;
            OdbList.ScrollIntoView(row);
            RefreshInteractionState();
        }
    }

    private Task ActivateExplorerOdbAsync(ExplorerItem item)
    {
        SelectExplorerOdb(item);
        return Task.CompletedTask;
    }

    private void OnOdbSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_updatingSelection || _discoveryBusy || _draftActionBusy) return;
        RefreshInteractionState();
        SaveWorkspace();
    }

    private bool SaveWorkspace(bool forClose = false)
    {
        if (DraftPending || _draftActionBusy) return true;
        if (forClose && _lastDiscoveryRoot is not null && _unreadableWorkspaces.Contains(PathKey(_lastDiscoveryRoot)))
            throw new IOException("原后处理配置无法读取，未覆盖它；请先检查配置后再关闭。");
        if (_lastDiscoveryRoot is null || _discoveryBusy || (!forClose && (_postprocessBusy || _compatibilityBusy || UpgradeBlocksEditing))
            || _unreadableWorkspaces.Contains(PathKey(_lastDiscoveryRoot))) return true;
        try
        {
            CommitWorkspace(_lastDiscoveryRoot, CaptureEditableWorkspace(CaptureOutputOptions()));
            return true;
        }
        catch (Exception exception)
        {
            ShowWarning(exception.Message, "后处理配置未能保存");
            return false;
        }
    }

    private bool TrySaveWorkspaceChange(Action<OdbPostprocessWorkspace> change)
    {
        try
        {
            if (_lastDiscoveryRoot is null || _unreadableWorkspaces.Contains(PathKey(_lastDiscoveryRoot))
                || _discoveryBusy || _postprocessBusy || _compatibilityBusy || UpgradeBlocksEditing
                || DraftPending || _draftActionBusy || App.Current.Session.IsClosing
                || !string.Equals(PathKey(RootTextBox.Text), PathKey(_lastDiscoveryRoot), StringComparison.OrdinalIgnoreCase))
                throw new InvalidOperationException("请先回到已读取的工作区，处理待恢复草稿或等待当前操作结束。");
            var next = CaptureEditableWorkspace(CaptureOutputOptions());
            change(next);
            CommitWorkspace(_lastDiscoveryRoot, next);
            return true;
        }
        catch (Exception error)
        {
            ShowWarning(error.Message, "工作区修改未能保存");
            return false;
        }
    }

    private void CommitWorkspace(string root, OdbPostprocessWorkspace workspace)
    {
        var basis = OdbPostprocessDraftRecovery.Fingerprint(workspace);
        _workspaceStore.Save(root, workspace);
        _workspaceBasis = basis;
        _lastSavedOutput = workspace.Output;
    }

    private OdbPostprocessOutputOptions CaptureOutputOptions() => new()
    {
        ParallelWorkers = ParallelWorkerCount(),
        FullTimehistory = FullTimehistoryCheckBox.IsChecked is true,
        RebarMethod = SelectedTag(RebarMethodComboBox, "element_cut"),
        ExpectedRebarCount = (int)Math.Round(ExpectedRebarCountNumberBox.Value),
        ImageUnit = SelectedTag(ImageUnitComboBox, "px"),
        ImageWidth = (int)Math.Round(ImageWidthNumberBox.Value),
        ImageHeight = (int)Math.Round(ImageHeightNumberBox.Value),
        AnimationFps = DurationMode && double.IsNaN(AnimationFpsNumberBox.Value) ? 25 : (int)Math.Round(AnimationFpsNumberBox.Value),
        AnimationTimingMode = DurationMode ? "duration" : "fps",
        AnimationDurationSeconds = !DurationMode && double.IsNaN(AnimationDurationNumberBox.Value) ? 4 : AnimationDurationNumberBox.Value,
        RebarTolerance = RebarToleranceNumberBox.Value,
        WhiteBackground = WhiteBackgroundCheckBox.IsChecked is true,
        TransparentBackground = TransparentBackgroundCheckBox.IsChecked is true,
    };

    private void RestoreOutputOptions(OdbPostprocessOutputOptions options)
    {
        ParallelWorkersNumberBox.Value = Math.Clamp(options.ParallelWorkers, 1, (int)ParallelWorkersNumberBox.Maximum);
        FullTimehistoryCheckBox.IsChecked = options.FullTimehistory;
        RebarMethodComboBox.SelectedIndex = options.RebarMethod == "element_cut" ? 0 : 1;
        ExpectedRebarCountNumberBox.Value = options.ExpectedRebarCount;
        // Apply units first: the selection handler changes bounds and converts dimensions.
        ImageUnitComboBox.SelectedIndex = options.ImageUnit == "px" ? 0 : 1;
        ImageWidthNumberBox.Value = options.ImageWidth;
        ImageHeightNumberBox.Value = options.ImageHeight;
        AnimationFpsNumberBox.Value = options.AnimationFps;
        AnimationDurationNumberBox.Value = options.AnimationDurationSeconds;
        AnimationTimingModeComboBox.SelectedIndex = options.AnimationTimingMode == "duration" ? 1 : 0;
        RebarToleranceNumberBox.Value = Math.Round(options.RebarTolerance, 10);
        WhiteBackgroundCheckBox.IsChecked = options.WhiteBackground;
        TransparentBackgroundCheckBox.IsChecked = options.TransparentBackground;
    }

    private void OnSelectAllClicked(object sender, RoutedEventArgs e)
    {
        OdbList.SelectAll();
        RefreshInteractionState();
    }

    private void OnSelectNoneClicked(object sender, RoutedEventArgs e)
    {
        OdbList.SelectedItems.Clear();
        RefreshInteractionState();
    }

    private void OnInvertSelectionClicked(object sender, RoutedEventArgs e)
    {
        var selected = OdbList.SelectedItems
            .OfType<OdbFileRow>()
            .ToHashSet();
        _updatingSelection = true;
        try
        {
            OdbList.SelectedItems.Clear();
            foreach (var row in _odbItems.Where(row => !selected.Contains(row)))
                OdbList.SelectedItems.Add(row);
        }
        finally { _updatingSelection = false; }
        RefreshInteractionState();
        SaveWorkspace();
    }

    private async void OnCompatibilityCheckClicked(object sender, RoutedEventArgs e)
    {
        await StartCompatibilityCheckAsync();
    }

    private async void OnOpenResultsClicked(object sender, RoutedEventArgs e)
    {
        try
        {
            var roots = _resultLocations.Resolve(RootTextBox.Text, _lastDiscoveryRoot,
                OdbList.SelectedItems.OfType<OdbFileRow>().Select(row => row.Path), _odbItems.Select(row => row.Path));
            var resultRoot = roots[0];
            if (roots.Count > 1)
            {
                var choices = new ListView { MaxHeight = 320, SelectionMode = ListViewSelectionMode.Single };
                foreach (var path in roots) choices.Items.Add(new TextBlock { Text = path, TextWrapping = TextWrapping.Wrap });
                var dialog = new ContentDialog
                {
                    XamlRoot = XamlRoot, Title = "选择要浏览的结果目录", Content = choices,
                    PrimaryButtonText = "打开", CloseButtonText = "取消", IsPrimaryButtonEnabled = false
                };
                choices.SelectionChanged += (_, _) => dialog.IsPrimaryButtonEnabled = choices.SelectedIndex >= 0;
                if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
                resultRoot = roots[choices.SelectedIndex];
            }
            await App.Current.MainWindow.OpenResultBrowserAsync(resultRoot);
        }
        catch (Exception error) { ShowWarning(error.Message, "无法打开结果浏览"); }
    }

    private async void OnAnalyzeClicked(object sender, RoutedEventArgs e)
    {
        await AnalyzeSelectedAsync();
    }

    private async Task AnalyzeSelectedAsync()
    {
        if (GroupQueueBlocksOtherOperations || _postprocessBusy || _compatibilityBusy || _discoveryBusy || UpgradeBlocksEditing)
        {
            return;
        }

        var selected = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();
        if (selected.Length == 0)
        {
            ShowWarning("请至少选择一个 ODB。", "无法读取 ODB 结构");
            return;
        }

        var root = RootTextBox.Text.Trim();
        foreach (var row in selected)
        {
            row.MarkStructureAnalysisPending();
        }
        _activePathKeys.Clear();
        foreach (var row in selected)
        {
            _activePathKeys.Add(PathKey(row.Path));
        }

        var requestId = Guid.NewGuid();
        BeginPostprocessMonitoring(requestId.ToString("D"), "odb.postprocess.scan");
        _activePostprocessOperationId = null;
        _activePostprocessKind = "odb.postprocess.scan";
        _lastPostprocessVersion = -1;
        _displayedLogCount = 0;
        PostprocessLogTextBox.Text = string.Empty;
        SetPostprocessBusy(true);
        try
        {
            var initial = await App.Current.ControlPlane.StartOdbPostprocessScanAsync(
                root,
                selected.Select(row => row.Path).ToArray(),
                ParallelWorkerCount(),
                ForceRescanCheckBox.IsChecked is true,
                requestId);
            ForceRescanCheckBox.IsChecked = false;
            _activePostprocessOperationId = initial.OperationId;
            ApplyPostprocessSnapshot(initial);
            var progress = new Progress<OdbPostprocessOperationSnapshot>(ApplyPostprocessProgressSnapshot);
            var final = await App.Current.ControlPlane.PollOdbPostprocessUntilTerminalAsync(
                initial,
                progress, _postprocessMonitoringSource!.Token);
            ApplyPostprocessSnapshot(final);
            CompletePostprocessOperation(final);
        }
        catch (Exception exception)
        {
            HandlePostprocessInterruption(exception, "ODB 结构读取失败");
        }
        finally
        {
            EndPostprocessMonitoring();
        }
    }

    private void OnApplyGroupClicked(object sender, RoutedEventArgs e)
    {
        var operation = SelectedTag(GroupOperationComboBox, "replace");
        var names = ParseGroupNames(GroupNameTextBox.Text);
        if (names.Length == 0 && operation != "clear")
        {
            ShowWarning("对比组名称不能为空。", "无法应用对比组");
            return;
        }

        var selected = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();
        var memberships = selected.Select(row => (Row: row, NewValue: OdbComparisonGroups.UpdateMembership(
            row.ComparisonGroup, GroupNameTextBox.Text, operation))).ToArray();
        foreach (var (row, value) in memberships)
        {
            var priorNames = ParseGroupNames(row.ComparisonGroup);
            var nextNames = ParseGroupNames(value);
            var removedNames = priorNames.Except(nextNames, StringComparer.OrdinalIgnoreCase).ToHashSet(StringComparer.OrdinalIgnoreCase);
            var affected = UnfinishedGroups.FirstOrDefault(entry => entry.Members.Contains(row.Path, StringComparer.OrdinalIgnoreCase)
                && (entry.Standalone ? priorNames.Length == 0 && nextNames.Length > 0 : removedNames.Contains(entry.Name)));
            if (!CanRemoveGroupMembership(affected)) return;
        }
        var changes = memberships.ToDictionary(pair => PathKey(pair.Row.Path), pair => pair.NewValue, StringComparer.OrdinalIgnoreCase);
        var retainedNames = memberships.SelectMany(pair => ParseGroupNames(pair.Row.ComparisonGroup)
            .Concat(ParseGroupNames(pair.NewValue))).Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        if (!TrySaveWorkspaceChange(next =>
            {
                foreach (var name in retainedNames) next.GroupMemberOrder.TryAdd(name, []);
                foreach (var saved in next.Rows)
                    if (changes.TryGetValue(PathKey(saved.Path), out var value)) saved.Group = value;
            })) return;
        foreach (var name in retainedNames) _groupMemberOrder.TryAdd(name, []);
        foreach (var (row, value) in memberships) row.ComparisonGroup = value;
        SelectedPlanText.Text = $"已更新 {selected.Length} 个 ODB 的分组；原始文件未修改。";
        UpdateExplorer();
        RefreshInteractionState();
    }

    private async void OnLegendClicked(object sender, RoutedEventArgs e)
    {
        var typedGroups = ParseGroupNames(GroupNameTextBox.Text);
        var selectedGroups = OdbList.SelectedItems
                .OfType<OdbFileRow>()
                .SelectMany(row => ParseGroupNames(row.ComparisonGroup))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .Take(2)
                .ToArray();
        var groupName = typedGroups.Length == 1
            ? typedGroups[0]
            : selectedGroups.Length == 1 ? selectedGroups[0] : null;
        if (string.IsNullOrWhiteSpace(groupName))
        {
            ShowWarning("请在组名框中只填写一个对比组，再编辑图例范围。", "无法确定对比组");
            return;
        }

        _legendOverridesByGroup.TryGetValue(groupName, out var existing);
        var rows = new List<(string Field, string Label, CheckBox Manual, TextBox Minimum, TextBox Maximum)>();
        var grid = new Grid { ColumnSpacing = 8, RowSpacing = 6 };
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(2, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        var headers = new[] { "变量", "手动", "最小值", "最大值" };
        for (var column = 0; column < headers.Length; column++)
        {
            var text = new TextBlock { Text = headers[column] };
            Grid.SetColumn(text, column);
            grid.Children.Add(text);
        }
        var rowIndex = 1;
        foreach (var (field, displayName) in LegendFields)
        {
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            OdbLegendOverride? rule = null;
            var enabled = existing is not null && existing.TryGetValue(field, out rule);
            var label = new StackPanel { VerticalAlignment = VerticalAlignment.Center };
            label.Children.Add(new TextBlock { Text = displayName, TextWrapping = TextWrapping.Wrap });
            label.Children.Add(new TextBlock { Text = field, FontSize = 11, Opacity = 0.72, TextWrapping = TextWrapping.Wrap });
            var manual = new CheckBox { IsChecked = enabled, VerticalAlignment = VerticalAlignment.Center };
            var minimum = new TextBox
            {
                Text = enabled ? rule!.Minimum.ToString("G17") : string.Empty,
                PlaceholderText = "自动",
                IsEnabled = enabled,
            };
            var maximum = new TextBox
            {
                Text = enabled ? rule!.Maximum.ToString("G17") : string.Empty,
                PlaceholderText = "自动",
                IsEnabled = enabled,
            };
            manual.Checked += (_, _) => minimum.IsEnabled = maximum.IsEnabled = true;
            manual.Unchecked += (_, _) => minimum.IsEnabled = maximum.IsEnabled = false;
            Grid.SetRow(label, rowIndex);
            Grid.SetRow(manual, rowIndex);
            Grid.SetRow(minimum, rowIndex);
            Grid.SetRow(maximum, rowIndex);
            Grid.SetColumn(manual, 1);
            Grid.SetColumn(minimum, 2);
            Grid.SetColumn(maximum, 3);
            grid.Children.Add(label);
            grid.Children.Add(manual);
            grid.Children.Add(minimum);
            grid.Children.Add(maximum);
            rows.Add((field, displayName, manual, minimum, maximum));
            rowIndex++;
        }

        var content = new StackPanel { Spacing = 10 };
        content.Children.Add(new TextBlock
        {
            Text = "静态云图按组内选定帧统一色标，动画按完整时程统一。手动上下限同时用于两者。",
            TextWrapping = TextWrapping.Wrap,
            Opacity = 0.72,
        });
        var validation = new TextBlock { TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed };
        content.Children.Add(grid);
        var editor = new Grid { MaxHeight = 620, RowSpacing = 6 };
        editor.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        editor.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        editor.Children.Add(validation);
        var scroller = new ScrollViewer { Content = content, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        Grid.SetRow(scroller, 1);
        editor.Children.Add(scroller);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"图例范围 · {groupName}",
            Content = editor,
            PrimaryButtonText = "保存范围",
            SecondaryButtonText = "全部恢复自动",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Primary,
        };
        var values = new Dictionary<string, OdbLegendOverride>(StringComparer.Ordinal);
        bool PersistLegend(bool reset)
        {
            if (TrySaveWorkspaceChange(next =>
                {
                    next.GroupMemberOrder.TryAdd(groupName, []);
                    if (reset) next.Legends.Remove(groupName);
                    else next.Legends[groupName] = values;
                })) return true;
            validation.Text = "未能保存该组的图例设置。请检查工作区后重试。";
            validation.Visibility = Visibility.Visible;
            return false;
        }
        dialog.PrimaryButtonClick += (_, args) =>
        {
            values.Clear();
            foreach (var row in rows.Where(row => row.Manual.IsChecked is true))
            {
                var validMin = OdbComparisonGroups.TryParseLegendBound(row.Minimum.Text, out var minimum);
                var validMax = OdbComparisonGroups.TryParseLegendBound(row.Maximum.Text, out var maximum);
                if (!validMin || !validMax || maximum <= minimum)
                {
                    args.Cancel = true;
                    var input = !validMin ? row.Minimum : row.Maximum;
                    validation.Text = !validMin || !validMax
                        ? $"{row.Label}的{(!validMin ? "最小值" : "最大值")}须为 −1×10³⁰ 至 1×10³⁰ 之间的有限数。"
                        : $"{row.Label}的最大值必须大于最小值。";
                    validation.Visibility = Visibility.Visible;
                    input.Focus(FocusState.Programmatic);
                    input.SelectAll();
                    return;
                }
                values[row.Field] = new OdbLegendOverride { Minimum = minimum, Maximum = maximum };
            }
            args.Cancel = !PersistLegend(false);
        };
        dialog.SecondaryButtonClick += (_, args) => args.Cancel = !PersistLegend(true);
        var legendInputs = new Dictionary<string, Control>();
        foreach (var row in rows)
        {
            legendInputs[row.Label + " 手动"] = row.Manual;
            legendInputs[row.Label + " 最小值"] = row.Minimum;
            legendInputs[row.Label + " 最大值"] = row.Maximum;
        }
        var result = await ShowRecoverableDialogAsync(dialog, content, "图例范围", groupName,
            new { groupName, existing }, legendInputs);
        if (result == ContentDialogResult.None) return;
        _groupMemberOrder.TryAdd(groupName, []);
        if (result == ContentDialogResult.Secondary) _legendOverridesByGroup.Remove(groupName);
        else _legendOverridesByGroup[groupName] = values;
        UpdateExplorer();
        RefreshInteractionState();
        await CompleteDialogDraftAsync("图例范围", groupName);
        ShowWarning(result == ContentDialogResult.Secondary
            ? $"“{groupName}”已恢复为自动图例范围。"
            : $"已保存“{groupName}”的 {values.Count} 个手动图例范围。", "图例设置已更新");
    }

    private async void OnManageGroupsClicked(object sender, RoutedEventArgs e)
    {
        if (_discoveryBusy || _postprocessBusy || _compatibilityBusy || UpgradeBlocksEditing) return;
        var names = KnownGroupNames();
        if (names.Length == 0) return;
        var selector = Choice(names, names[0], "对比组");
        var nameBox = new TextBox { Header = "新名称（重命名时使用）", Text = names[0] };
        selector.SelectionChanged += (_, _) => nameBox.Text = SelectedText(selector);
        var panel = new StackPanel { Spacing = 10, MinWidth = 380 };
        panel.Children.Add(selector);
        panel.Children.Add(nameBox);
        panel.Children.Add(new TextBlock { Text = "删除仅解除该组的成员关系和分组设置，不删除 ODB 或已有结果。", TextWrapping = TextWrapping.Wrap });
        var dialog = new ContentDialog { XamlRoot = XamlRoot, Title = "管理对比组", Content = panel,
            PrimaryButtonText = "重命名", SecondaryButtonText = "删除分组", CloseButtonText = "取消" };
        var result = await ShowRecoverableDialogAsync(dialog, panel, "管理分组", "当前目录", names,
            new() { ["原组名"] = selector, ["新名称"] = nameBox });
        if (result == ContentDialogResult.None) return;
        var oldName = SelectedText(selector);
        var affected = UnfinishedGroups.FirstOrDefault(entry => !entry.Standalone && entry.Name.Equals(oldName, StringComparison.OrdinalIgnoreCase));
        if (!CanRemoveGroupMembership(affected)) return;
        if (result == ContentDialogResult.Secondary)
        {
            var confirmation = new ContentDialog { XamlRoot = XamlRoot, Title = "删除对比组？",
                Content = $"解除“{oldName}”的分组关系；原始 ODB 和已生成结果保持不变。",
                PrimaryButtonText = "删除分组", CloseButtonText = "取消" };
            if (await confirmation.ShowAsync() != ContentDialogResult.Primary)
            {
                await CompleteDialogDraftAsync("管理分组", "当前目录");
                return;
            }
        }
        try
        {
            var replacement = result == ContentDialogResult.Secondary ? null : nameBox.Text;
            if (!TrySaveWorkspaceChange(next => OdbComparisonGroups.ChangeGroup(next, oldName, replacement))) return;
            OdbComparisonGroups.ChangeGroup(_odbItems, oldName, replacement, _legendOverridesByGroup, _groupMemberOrder);
            GroupNameTextBox.Text = result == ContentDialogResult.Secondary ? "" : nameBox.Text.Trim();
            UpdateExplorer();
            RefreshInteractionState();
            await CompleteDialogDraftAsync("管理分组", "当前目录");
        }
        catch (ArgumentException exception) { ShowWarning(exception.Message, "无法更新对比组"); }
    }

    private async void OnGroupOrderClicked(object sender, RoutedEventArgs e)
    {
        if (_discoveryBusy || _postprocessBusy || _compatibilityBusy || UpgradeBlocksEditing) return;
        var groups = OdbComparisonGroups.ForExecution(_odbItems).Where(group => !group.Standalone).ToArray();
        if (groups.Length == 0) return;
        var drafts = groups.ToDictionary(group => group.Name, group =>
            new ObservableCollection<OdbFileRow>(OdbComparisonGroups.OrderMembers(group.Members,
                _groupMemberOrder.TryGetValue(group.Name, out var order) ? order : [])), StringComparer.OrdinalIgnoreCase);
        var selector = Choice(groups.Select(group => group.Name).ToArray(), groups[0].Name, "选择对比组");
        var list = new ListView { Height = 300, SelectionMode = ListViewSelectionMode.Single,
            DisplayMemberPath = "RelativePath", ItemsSource = drafts[groups[0].Name] };
        selector.SelectionChanged += (_, _) => list.ItemsSource = drafts[SelectedText(selector)];
        var up = new Button { Content = "上移", Width = 100 };
        var down = new Button { Content = "下移", Width = 100 };
        void Move(int delta)
        {
            var items = drafts[SelectedText(selector)];
            var index = list.SelectedIndex;
            if (index < 0 || index + delta < 0 || index + delta >= items.Count) return;
            items.Move(index, index + delta);
            list.SelectedIndex = index + delta;
        }
        up.Click += (_, _) => Move(-1);
        down.Click += (_, _) => Move(1);
        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 8 };
        buttons.Children.Add(up);
        buttons.Children.Add(down);
        var panel = new StackPanel { Spacing = 10, MinWidth = 420 };
        panel.Children.Add(new TextBlock { Text = "各组独立排序；未勾选的成员仍保留顺序，新增成员排在末尾。", TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(selector);
        panel.Children.Add(list);
        panel.Children.Add(buttons);
        var dialog = new ContentDialog { XamlRoot = XamlRoot, Title = "组内成员顺序",
            Content = panel, PrimaryButtonText = "保存", CloseButtonText = "取消" };
        Dictionary<string, string> CaptureOrders() => drafts.ToDictionary(p => "顺序：" + p.Key,
            p => string.Join("\n", p.Value.Select(row => row.Path)));
        var initialOrders = CaptureOrders();
        void RestoreOrders(IReadOnlyDictionary<string, string> stored)
        {
            var restored = new Dictionary<string, string[]>();
            foreach (var pair in drafts)
            {
                if (!stored.TryGetValue("顺序：" + pair.Key, out var value)) throw new InvalidDataException("草稿缺少组内顺序，未套用旧输入。");
                var paths = value.Split('\n', StringSplitOptions.RemoveEmptyEntries);
                var known = pair.Value.Select(row => PathKey(row.Path)).ToHashSet(StringComparer.OrdinalIgnoreCase);
                if (paths.Length != known.Count || paths.Select(PathKey).Distinct(StringComparer.OrdinalIgnoreCase).Count() != known.Count
                    || paths.Any(path => !known.Contains(PathKey(path)))) throw new InvalidDataException("组内成员已变化，未套用旧顺序。");
                restored[pair.Key] = paths;
            }
            foreach (var pair in restored)
            {
                var items = drafts[pair.Key];
                var byPath = items.ToDictionary(row => PathKey(row.Path), StringComparer.OrdinalIgnoreCase);
                items.Clear();
                foreach (var path in pair.Value) items.Add(byPath[PathKey(path)]);
            }
        }
        if (await ShowRecoverableDialogAsync(dialog, panel, "组内顺序", "当前目录", initialOrders,
            new() { ["对比组"] = selector }, CaptureOrders, RestoreOrders) != ContentDialogResult.Primary) return;
        foreach (var pair in drafts) _groupMemberOrder[pair.Key] = pair.Value.Select(row => row.Path).ToList();
        SaveWorkspace();
        await CompleteDialogDraftAsync("组内顺序", "当前目录");
    }

    private async void OnConfigureClicked(object sender, RoutedEventArgs e)
    {
        var selected = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();
        if (selected.Length == 0)
        {
            ShowWarning("请选择要编辑的 ODB。", "尚未选择模型");
            return;
        }
        if (selected.Any(row => row.ScanDetails is not { Error.Length: 0 } || row.PostprocessJob is null))
        {
            ShowWarning("请为每个所选模型运行“读取结构与默认参数”。", "参数尚未就绪");
            return;
        }
        if (selected.Length > 1)
        {
            try { await ShowParameterComparisonAsync(selected); }
            catch (Exception error) { ShowWarning(error.Message, "模型参数对照未完成"); }
            return;
        }
        var row = selected[0];

        var draft = await ShowJobConfigurationDialogAsync(row);
        if (draft is not null)
        {
            row.UpdatePostprocessJob(draft);
            SaveWorkspace();
            await CompleteDialogDraftAsync("提取参数", PathKey(row.Path));
            SelectedPlanText.Text = $"已更新 {row.Name} 的提取参数";
            RefreshInteractionState();
        }
    }

    private async Task<OdbPostprocessJobDraft?> ShowJobConfigurationDialogAsync(OdbFileRow row, OdbPostprocessJobDraft? queued = null)
    {
        var current = (queued ?? row.PostprocessJob!).Clone();
        var scan = row.ScanDetails ?? new OdbPostprocessScanItem
        {
            Steps = [current.StartStep, current.EndStep], AssemblyNodeSets = [current.LoadSet],
            AssemblyElementSets = [current.PileDisplaySet, current.PileConcreteSet, current.PileSteelSet, current.SoilSet, current.RebarSet]
        };
        var startStep = Choice(scan.Steps, current.StartStep, "起始分析步");
        var endStep = Choice(scan.Steps, current.EndStep, "结束分析步");
        var frameMode = Choice(
            ["关键帧（自动）", "全部帧", "手动帧序号"],
            current.FrameMode switch { "all" => "全部帧", "manual" => "手动帧序号", _ => "关键帧（自动）" },
            "高开销数值提取帧");
        var manualFrames = new TextBox
        {
            Header = "手动帧序号表达式",
            PlaceholderText = "例如 0,10,20-25",
            Text = current.ManualSequenceExpression,
        };
        var direction = Choice(["1", "3", "1+3"], current.LoadDirection, "加载方向");
        var loadSet = Choice(scan.AssemblyNodeSets, current.LoadSet, "加载节点集");
        var pileType = Choice(["RC", "CFST"], current.PileType, "桩体类型");
        var pileDisplay = Choice(scan.AssemblyElementSets, current.PileDisplaySet, "桩体显示集合");
        var concrete = Choice(scan.AssemblyElementSets, current.PileConcreteSet, "混凝土集合");
        var steel = Choice(["", .. scan.AssemblyElementSets], current.PileSteelSet, "钢构件集合（可留空，与旧版一致）");
        var soil = Choice(scan.AssemblyElementSets, current.SoilSet, "土体截面集合");
        var rebar = Choice(scan.AssemblyElementSets, current.RebarSet, "纵筋集合");
        var reinforcement = Choice(["有纵筋", "无纵筋（素混凝土主体）"],
            current.ReinforcementMode == "none" ? "无纵筋（素混凝土主体）" : "有纵筋", "主体配筋");
        var material = new TextBox { Header = "纵筋材料", Text = current.LongitudinalMaterial };
        var diameter = new Controls.WorkbenchNumberBox
        {
            Header = "纵筋直径 mm",
            Minimum = 1,
            Maximum = 100,
            Value = current.RebarDiameterMm,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline,
        };
        var prefracture = new Controls.WorkbenchNumberBox
        {
            Header = "断裂前帧序号（-1=自动）",
            Minimum = -1,
            Maximum = 1_000_000,
            Value = current.PrefractureSequenceIndex,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline,
        };
        Controls.ParameterHelpButton.AddToHeader(diameter, "rebar-diameter");
        Controls.ParameterHelpButton.AddToHeader(prefracture, "prefracture-frame");
        void UpdateRebarFields()
        {
            var enabled = SelectedText(reinforcement) == "有纵筋";
            rebar.IsEnabled = material.IsEnabled = diameter.IsEnabled = enabled;
        }
        reinforcement.SelectionChanged += (_, _) => UpdateRebarFields();
        UpdateRebarFields();
        if (queued is not null && row.ScanDetails is null)
            foreach (var choice in new[] { startStep, endStep, loadSet, pileDisplay, concrete, steel, soil, rebar })
                choice.IsEditable = true;
        var fields = new StackPanel { Spacing = 10 };
        fields.Children.Add(new TextBlock
        {
            Text = row.ScanDetails is null ? "显示排队时保存的集合与分析步。可直接输入其他已核对的名称。" : scan.NameMetadata.Condition.Length > 0
                ? $"文件名识别：{scan.NameMetadata.SampleId} · {scan.NameMetadata.Condition}"
                : "文件名没有提供加载方向，请在下方手动选择。",
            TextWrapping = TextWrapping.Wrap,
            Opacity = 0.72,
        });
        foreach (var control in new Control[]
        {
            startStep, endStep, frameMode, manualFrames, direction, loadSet, pileType,
            pileDisplay, concrete, steel, soil, reinforcement, rebar, material, diameter, prefracture,
        })
        {
            fields.Children.Add(control);
        }

        var validationMessage = new TextBlock
        {
            TextWrapping = TextWrapping.Wrap,
            Visibility = Visibility.Collapsed,
        };
        fields.Children.Add(validationMessage);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"提取参数 · {row.Name}",
            Content = new ScrollViewer
            {
                MaxHeight = 620,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Content = fields,
            },
            PrimaryButtonText = "保存参数",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Primary,
        };
        dialog.PrimaryButtonClick += (_, args) =>
        {
            var error = frameMode.SelectedItem?.ToString() == "手动帧序号"
                && string.IsNullOrWhiteSpace(manualFrames.Text)
                ? "手动帧模式必须填写帧序号表达式。"
                : !double.IsFinite(diameter.Value) || diameter.Value < 1 || diameter.Value > 100
                    ? "请填写 1–100 mm 的纵筋直径。"
                    : !double.IsFinite(prefracture.Value) || prefracture.Value < -1
                        || prefracture.Value > 1_000_000 || prefracture.Value != Math.Truncate(prefracture.Value)
                        ? "断裂前帧序号应为 -1（自动）或非负整数。"
                        : string.Empty;
            validationMessage.Text = error;
            validationMessage.Visibility = error.Length > 0 ? Visibility.Visible : Visibility.Collapsed;
            args.Cancel = error.Length > 0;
        };
        var inputControls = new Dictionary<string, Control>
        {
            ["起始分析步"] = startStep, ["结束分析步"] = endStep, ["帧方式"] = frameMode,
            ["手动帧序号"] = manualFrames, ["加载方向"] = direction, ["加载节点集"] = loadSet,
            ["桩体类型"] = pileType, ["桩体集合"] = pileDisplay, ["混凝土集合"] = concrete,
            ["钢构件集合"] = steel, ["土体集合"] = soil, ["配筋"] = reinforcement,
            ["纵筋集合"] = rebar, ["纵筋材料"] = material, ["纵筋直径"] = diameter, ["断裂前帧"] = prefracture,
        };
        var response = queued is null
            ? await ShowRecoverableDialogAsync(dialog, fields, "提取参数", PathKey(row.Path),
                new { current, scan.Steps, scan.AssemblyNodeSets, scan.AssemblyElementSets }, inputControls)
            : await dialog.ShowAsync();
        if (response != ContentDialogResult.Primary)
        {
            return null;
        }

        var mode = frameMode.SelectedItem?.ToString() switch
        {
            "全部帧" => "all",
            "手动帧序号" => "manual",
            _ => "auto",
        };
        current.StartStep = SelectedText(startStep);
        current.EndStep = SelectedText(endStep);
        current.FrameMode = mode;
        current.ManualSequenceExpression = manualFrames.Text.Trim();
        current.LoadDirection = SelectedText(direction);
        current.LoadSet = SelectedText(loadSet);
        current.PileType = SelectedText(pileType);
        current.PileDisplaySet = SelectedText(pileDisplay);
        current.PileConcreteSet = SelectedText(concrete);
        current.PileSteelSet = SelectedText(steel);
        current.SoilSet = SelectedText(soil);
        current.RebarSet = SelectedText(rebar);
        current.ReinforcementMode = SelectedText(reinforcement) == "有纵筋" ? "required" : "none";
        current.LongitudinalMaterial = material.Text.Trim();
        current.RebarDiameterMm = diameter.Value;
        current.PrefractureSequenceIndex = (int)Math.Round(prefracture.Value);
        return current;
    }

    private static ComboBox Choice(IEnumerable<string> values, string selected, string header)
    {
        var items = values.Distinct(StringComparer.OrdinalIgnoreCase).ToArray();
        var combo = new ComboBox
        {
            Header = header,
            ItemsSource = items,
            PlaceholderText = "请选择（未自动识别）",
            HorizontalAlignment = HorizontalAlignment.Stretch,
        };
        var index = Array.FindIndex(items, value => string.Equals(value, selected, StringComparison.OrdinalIgnoreCase));
        combo.SelectedIndex = index;
        return combo;
    }

    private static string SelectedText(ComboBox combo) => (combo.IsEditable ? combo.Text : combo.SelectedItem?.ToString())?.Trim() ?? string.Empty;

    private async void OnRunPostprocessClicked(object sender, RoutedEventArgs e)
    {
        await RunPostprocessAsync();
    }

    private async Task RunPostprocessAsync()
    {
        if (!RunPostprocessButton.IsEnabled)
        {
            return;
        }
        var submission = BuildScopedQueueRequest();
        if (submission is not null && SaveWorkspace()) await SubmitGroupQueueAsync(submission);
    }

    private void UpdateRunScopeChoices()
    {
        var previous = RunScopeComboBox.SelectedItem as OdbRunScope;
        var choices = new List<OdbRunScope> { new(OdbRunScopeKind.Selection), new(OdbRunScopeKind.SingleModel) };
        choices.AddRange(KnownGroupNames().Select(name => new OdbRunScope(OdbRunScopeKind.NamedGroup, name)));
        var sameRoot = string.Equals(_scopeCatalogRoot, _lastDiscoveryRoot, StringComparison.OrdinalIgnoreCase);
        if (sameRoot && _runScopeChoices is not null && _runScopeChoices.SequenceEqual(choices)) return;
        var selectedIndex = -1;
        if (_runScopeChoices is null) selectedIndex = 0;
        else if (previous is not null && (sameRoot || previous.Kind != OdbRunScopeKind.NamedGroup))
            selectedIndex = choices.FindIndex(item => item.Kind == previous.Kind
                && string.Equals(item.GroupName, previous.GroupName, StringComparison.OrdinalIgnoreCase));
        _updatingRunScopes = true;
        try
        {
            _runScopeChoices = choices;
            RunScopeComboBox.ItemsSource = choices;
            // A deleted group or a new workspace must not silently widen the request.
            RunScopeComboBox.SelectedIndex = selectedIndex;
            _scopeCatalogRoot = _lastDiscoveryRoot;
        }
        finally { _updatingRunScopes = false; }
    }

    private void OnRunScopeChanged(object sender, SelectionChangedEventArgs args)
    {
        if (!_updatingRunScopes && RunPostprocessButton is not null) RefreshInteractionState();
    }

    private OdbScopedRunPlan ResolveRunScope(IEnumerable<OdbFileRow> selectedRows) => OdbScopedRunPlan.Resolve(
        RunScopeComboBox.SelectedItem as OdbRunScope, selectedRows, _odbItems, RootTextBox.Text, _lastDiscoveryRoot,
        _groupQueue is { IsTerminal: false } queue ? queue.Root : null, _groupQueue?.Groups,
        _lastDiscoveryRoot is null || !_unreadableWorkspaces.Contains(PathKey(_lastDiscoveryRoot)));

    private OdbPostprocessRunCreateRequest? BuildScopedQueueRequest()
    {
        var plan = ResolveRunScope(OdbList.SelectedItems.OfType<OdbFileRow>());
        if (plan.CanRun) return BuildQueueRequest(plan.Rows, plan.Groups);
        ShowWarning(plan.Summary, "请核对运行范围");
        return null;
    }

    private OdbPostprocessRunCreateRequest? BuildQueueRequest(OdbFileRow[] rows, IReadOnlyList<OdbExecutionGroup> selectedGroups)
    {
        if (rows.Length == 0 || rows.Any(row => row.PostprocessJob is null || !row.HasPostprocessConfiguration))
        {
            ShowWarning("请选择已完成结构读取的 ODB。", "处理计划不完整");
            return null;
        }
        if (WhiteBackgroundCheckBox.IsChecked is not true
            && TransparentBackgroundCheckBox.IsChecked is not true)
        {
            ShowWarning("白底 PNG 与透明底 PNG 至少启用一项。", "输出设置无效");
            return null;
        }

        if (DurationMode && (!double.IsFinite(AnimationDurationNumberBox.Value) || AnimationDurationNumberBox.Value < 0.01))
        {
            ShowWarning("请填写至少 0.01 秒的 GIF 单轮时长。", "输出设置无效");
            return null;
        }
        if (!DurationMode && (!double.IsFinite(AnimationFpsNumberBox.Value)
            || AnimationFpsNumberBox.Value != Math.Round(AnimationFpsNumberBox.Value)))
        {
            ShowWarning("请填写 1 至 60 之间的整数帧率。", "输出设置无效");
            return null;
        }
        return OdbScopedRunPlan.BuildRequest(RootTextBox.Text, rows, selectedGroups, CaptureOutputOptions(),
            ForceRescanCheckBox.IsChecked is true, _groupMemberOrder, _legendOverridesByGroup);
    }

    private async void OnCancelPostprocessClicked(object sender, RoutedEventArgs e)
    {
        if (_groupQueue is { IsActive: true } queue && !_postprocessBusy)
        {
            await ChangeGroupQueueAsync(queue, PostprocessGroupQueueAction.CancelCurrent, groupId: queue.CurrentGroupId);
            return;
        }
        if (_postprocessCancelInFlight || !_postprocessTracking.RequestCancel())
        {
            return;
        }
        var operationId = _activePostprocessOperationId!;
        var wasRecovering = _postprocessTracking.NeedsRecovery && _postprocessMonitoringSource is null;
        _postprocessCancelInFlight = true;
        CancelPostprocessButton.IsEnabled = false;
        PostprocessPhaseText.Text = "正在停止 Abaqus 子进程，请稍候…";
        try
        {
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            var snapshot = await App.Current.ControlPlane.CancelOdbPostprocessOperationAsync(
                operationId, timeout.Token);
            if (_activePostprocessOperationId != operationId) return;
            ApplyPostprocessSnapshot(snapshot);
            if (wasRecovering && snapshot.IsTerminal)
            {
                CompletePostprocessOperation(snapshot);
                ReleasePostprocessMonitoring();
            }
        }
        catch (Exception exception)
        {
            if (_activePostprocessOperationId != operationId) return;
            HandlePostprocessInterruption(exception, "停止请求状态待确认");
            _postprocessMonitoringSource?.Cancel();
        }
        finally
        {
            _postprocessCancelInFlight = false;
            if (_postprocessMonitoringSource is null) ReleasePostprocessMonitoring();
            else RefreshInteractionState();
        }
    }

    private void ApplyPostprocessProgressSnapshot(OdbPostprocessOperationSnapshot snapshot)
    {
        // Progress callbacks can arrive after an older request has already finished.
        if (_postprocessTracking.MatchesProgress(snapshot)) ApplyPostprocessSnapshot(snapshot);
    }

    private void ApplyPostprocessSnapshot(OdbPostprocessOperationSnapshot snapshot) => ApplyPostprocessSnapshot(snapshot, false);

    private void ApplyPostprocessSnapshot(OdbPostprocessOperationSnapshot snapshot, bool recovered)
    {
        if (!_postprocessBusy && !_postprocessTracking.Active) return;
        if (_activePostprocessOperationId is not null
            && !string.Equals(_activePostprocessOperationId, snapshot.OperationId, StringComparison.Ordinal))
        {
            return;
        }
        if (snapshot.Version < _lastPostprocessVersion)
        {
            return;
        }
        _postprocessTracking.Observe(snapshot, recovered);
        if (snapshot.IsTerminal) WarningInfoBar.IsOpen = false;
        _activePostprocessOperationId ??= snapshot.OperationId;
        _activePostprocessKind ??= snapshot.Kind;
        _lastPostprocessVersion = snapshot.Version;
        PostprocessProgress.Value = Math.Clamp(snapshot.Progress.Percent, 0, 100);
        PostprocessPercentText.Text = $"{snapshot.Progress.Percent}%";
        PostprocessPhaseText.Text = string.IsNullOrWhiteSpace(snapshot.Progress.Phase)
            ? PostprocessStatusDisplay(snapshot.Status)
            : snapshot.Progress.Phase;
        if (snapshot.Logs.Count < _displayedLogCount)
        {
            _displayedLogCount = 0;
            PostprocessLogTextBox.Text = string.Empty;
        }
        foreach (var line in snapshot.Logs.Skip(_displayedLogCount))
        {
            AppendPostprocessLog(line);
        }
        _displayedLogCount = snapshot.Logs.Count;
        if (!snapshot.IsTerminal && snapshot.Kind == "odb.postprocess.scan")
        {
            foreach (var pathKey in _activePathKeys)
            {
                if (_odbByPath.TryGetValue(pathKey, out var row))
                {
                    row.MarkStructureAnalysisRunning();
                }
            }
        }
        App.Current.MainWindow.ReportPageStatus($"ODB 后处理 · {snapshot.Progress.Percent}% · {PostprocessStatusDisplay(snapshot.Status)}");
        RefreshInteractionState();
    }

    private void CompletePostprocessOperation(OdbPostprocessOperationSnapshot snapshot)
    {
        if (_activePostprocessOperationId != snapshot.OperationId) return;
        _resultLocations.Complete(snapshot);
        if (snapshot.Status == "succeeded" && snapshot.Result is { } result)
        {
            if (snapshot.Kind == "odb.postprocess.scan")
            {
                foreach (var item in result.Items)
                {
                    FindRow(item.Path)?.ApplyPostprocessScan(item);
                }
                MarkPostprocessRowsWithoutConfiguration("没有返回 ODB 结构结果。", result.Items.Select(item => item.Path));
                PostprocessPhaseText.Text = $"结构读取完成 · {result.Count} 个 ODB · 缓存命中 {result.CacheHits}";
            }
            else if (!OdbPostprocessResultLocations.HasPublishedOutputs(result))
            {
                MarkPostprocessRowsIncomplete("未发布结果", "回执缺少已发布的结果目录。");
                PostprocessPhaseText.Text = "后处理结束 · 未收到完整的结果目录";
                ShowWarning("请查看运行日志核对输出。", "没有可打开的已发布结果");
            }
            else
            {
                foreach (var pathKey in _activePathKeys)
                {
                    if (_odbByPath.TryGetValue(pathKey, out var row))
                    {
                        row.MarkProcessing(snapshot.Kind == "odb.postprocess.region" ? "对象提取完成" : "已完成",
                            $"本批次共生成 {result.OutputCount} 个结果目录");
                    }
                }
                PostprocessPhaseText.Text = $"后处理完成 · {result.OutputCount} 个结果";
                AppendPostprocessLog($"结果根目录：{string.Join("；", result.ResultRoots)}");
            }
        }
        else if (snapshot.Status == "cancelled")
        {
            MarkPostprocessRowsIncomplete("已取消", "操作已取消，已完成的缓存与结果会保留。 ");
            PostprocessPhaseText.Text = "ODB 后处理操作已取消";
        }
        else if (snapshot.Status == "failed")
        {
            var message = snapshot.Error?.Message ?? "控制面未返回详细原因。";
            MarkPostprocessRowsIncomplete("处理失败", message);
            ShowError(message, snapshot.Kind == "odb.postprocess.scan" ? "ODB 结构读取失败" : "ODB 后处理失败");
        }
        RefreshInteractionState();
    }

    private void MarkPostprocessRowsWithoutConfiguration(string message, IEnumerable<string> returnedPaths)
    {
        var returned = returnedPaths.Select(PathKey).ToHashSet(StringComparer.OrdinalIgnoreCase);
        foreach (var pathKey in _activePathKeys)
        {
            if (!returned.Contains(pathKey) && _odbByPath.TryGetValue(pathKey, out var row))
            {
                row.MarkStructureAnalysisIncomplete(message);
            }
        }
    }

    private void MarkPostprocessRowsIncomplete(string status, string message)
    {
        foreach (var pathKey in _activePathKeys)
        {
            if (_odbByPath.TryGetValue(pathKey, out var row))
            {
                row.MarkPostprocessIncomplete(status, message);
            }
        }
    }

    private void AppendPostprocessLog(string message)
    {
        if (string.IsNullOrWhiteSpace(message))
        {
            return;
        }
        var timestamp = DateTimeOffset.Now.ToString("HH:mm:ss");
        PostprocessLogTextBox.Text += $"[{timestamp}] {message.Trim()}{Environment.NewLine}";
    }

    private int ParallelWorkerCount() => Math.Clamp(
        double.IsFinite(ParallelWorkersNumberBox.Value) ? (int)Math.Round(ParallelWorkersNumberBox.Value) : 1,
        1, (int)ParallelWorkersNumberBox.Maximum);

    private static string SelectedTag(ComboBox comboBox, string fallback) =>
        (comboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? fallback;

    private static string[] ParseGroupNames(string value) => OdbComparisonGroups.ParseNames(value);

    private bool DurationMode => AnimationTimingModeComboBox.SelectedIndex == 1;

    private void OnAnimationTimingModeChanged(object sender, SelectionChangedEventArgs e)
    {
        if (AnimationFpsNumberBox is null || AnimationDurationNumberBox is null) return;
        AnimationFpsNumberBox.Visibility = DurationMode ? Visibility.Collapsed : Visibility.Visible;
        AnimationDurationNumberBox.Visibility = DurationMode ? Visibility.Visible : Visibility.Collapsed;
    }

    private void OnImageUnitChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ImageWidthNumberBox is null || ImageHeightNumberBox is null)
        {
            return;
        }
        var millimetres = SelectedTag(ImageUnitComboBox, "px") == "mm";
        var oldWidth = ImageWidthNumberBox.Value;
        var oldHeight = ImageHeightNumberBox.Value;
        ImageWidthNumberBox.Minimum = millimetres ? 30 : 320;
        ImageWidthNumberBox.Maximum = millimetres ? 500 : 4096;
        ImageHeightNumberBox.Minimum = millimetres ? 30 : 320;
        ImageHeightNumberBox.Maximum = millimetres ? 500 : 4096;
        if (millimetres && oldWidth > 500)
        {
            ImageWidthNumberBox.Value = Math.Clamp(Math.Round(oldWidth * 25.4 / 96), 30, 500);
            ImageHeightNumberBox.Value = Math.Clamp(Math.Round(oldHeight * 25.4 / 96), 30, 500);
        }
        else if (!millimetres && oldWidth <= 500)
        {
            ImageWidthNumberBox.Value = Math.Clamp(Math.Round(oldWidth * 96 / 25.4), 320, 4096);
            ImageHeightNumberBox.Value = Math.Clamp(Math.Round(oldHeight * 96 / 25.4), 320, 4096);
        }
    }

    private static string PostprocessStatusDisplay(string status) => status switch
    {
        "queued" => "排队中",
        "starting" => "正在启动 Abaqus",
        "running" => "正在运行",
        "cancelling" => "正在停止",
        "succeeded" => "已完成",
        "cancelled" => "已取消",
        "failed" => "失败",
        _ => status,
    };

    private async Task StartCompatibilityCheckAsync()
    {
        if (GroupQueueBlocksOtherOperations || _discoveryBusy || _compatibilityBusy || _postprocessBusy || UpgradeBlocksEditing)
        {
            return;
        }

        var selectedRows = OdbList.SelectedItems
            .OfType<OdbFileRow>()
            .ToArray();
        if (selectedRows.Length == 0)
        {
            ShowError("请至少选择一个要检查的 ODB。", "无法开始兼容性检查");
            return;
        }

        var root = RootTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(root))
        {
            ShowError("ODB 根目录为空，请重新运行发现。", "无法开始兼容性检查");
            return;
        }

        ErrorInfoBar.IsOpen = false;
        WarningInfoBar.IsOpen = false;
        _activeOperationId = null;
        _activeAttemptId = null;
        _lastOperationVersion = -1;
        _cancelRequested = false;
        _activePathKeys.Clear();
        foreach (var row in selectedRows)
        {
            _activePathKeys.Add(PathKey(row.Path));
            row.MarkPending();
        }

        CompatibilityProgress.IsIndeterminate = true;
        CompatibilityProgress.Minimum = 0;
        CompatibilityProgress.Maximum = Math.Max(1, selectedRows.Length);
        CompatibilityProgress.Value = 0;
        CompatibilityProgressText.Text = $"0 / {selectedRows.Length}";
        CompatibilityStatusText.Text = "正在创建兼容性检查…";
        SetCompatibilityBusy(true);
        App.Current.MainWindow.ReportPageStatus(
            $"正在创建兼容性检查 · {selectedRows.Length} 个 ODB");

        try
        {
            var initialSnapshot = await App.Current.ControlPlane.StartOdbCompatibilityCheckAsync(
                root,
                selectedRows.Select(row => row.Path).ToArray(),
                ForceRescanCheckBox.IsChecked is true,
                Guid.NewGuid());
            _activeOperationId = initialSnapshot.OperationId;
            ApplyOperationSnapshot(initialSnapshot);

            var progress = new Progress<OdbCompatibilityOperationSnapshot>(ApplyOperationSnapshot);
            var finalSnapshot = await App.Current.ControlPlane.PollOperationUntilTerminalAsync(
                initialSnapshot,
                progress);
            ApplyOperationSnapshot(finalSnapshot);
            CompleteCompatibilityOperation(finalSnapshot);
        }
        catch (OperationCanceledException)
        {
            CompatibilityStatusText.Text = "兼容性检查已取消";
            MarkUnfinishedRows("未完成", "兼容性检查在完成前已取消。");
            App.Current.MainWindow.ReportPageStatus("兼容性检查已取消");
        }
        catch (ControlPlaneException exception)
        {
            CompatibilityStatusText.Text = "兼容性检查失败";
            MarkUnfinishedRows("检查失败", exception.Message);
            ShowError(exception.ToDisplayMessage(), "兼容性检查失败");
        }
        catch (Exception exception)
        {
            CompatibilityStatusText.Text = "兼容性检查失败";
            MarkUnfinishedRows("检查失败", exception.Message);
            ShowError(
                "ODB 兼容性检查失败。" + Environment.NewLine + exception.Message,
                "兼容性检查失败");
        }
        finally
        {
            _activeOperationId = null;
            _activeAttemptId = null;
            _cancelRequested = false;
            _activePathKeys.Clear();
            CompatibilityProgress.IsIndeterminate = false;
            SetCompatibilityBusy(false);
        }
    }

    private async void OnCancelCompatibilityClicked(object sender, RoutedEventArgs e)
    {
        var operationId = _activeOperationId;
        if (!_compatibilityBusy || string.IsNullOrWhiteSpace(operationId) || _cancelRequested)
        {
            return;
        }

        _cancelRequested = true;
        CompatibilityStatusText.Text = "正在请求取消，请稍候…";
        App.Current.MainWindow.ReportPageStatus("正在取消兼容性检查…");
        RefreshInteractionState();
        try
        {
            var snapshot = await App.Current.ControlPlane.CancelOperationAsync(operationId);
            ApplyOperationSnapshot(snapshot);
        }
        catch (OperationCanceledException)
        {
            // Host disposal cancels outstanding requests during safe shutdown.
        }
        catch (ControlPlaneException exception)
        {
            _cancelRequested = false;
            ShowError(exception.ToDisplayMessage(), "无法取消兼容性检查");
            RefreshInteractionState();
        }
        catch (Exception exception)
        {
            _cancelRequested = false;
            ShowError(exception.Message, "无法取消兼容性检查");
            RefreshInteractionState();
        }
    }

    private void ApplyOperationSnapshot(OdbCompatibilityOperationSnapshot snapshot)
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

        if (!string.IsNullOrWhiteSpace(_activeAttemptId)
            && !string.IsNullOrWhiteSpace(snapshot.AttemptId)
            && !string.Equals(_activeAttemptId, snapshot.AttemptId, StringComparison.Ordinal))
        {
            return;
        }

        _activeOperationId ??= snapshot.OperationId;
        if (string.IsNullOrWhiteSpace(_activeAttemptId)
            && !string.IsNullOrWhiteSpace(snapshot.AttemptId))
        {
            _activeAttemptId = snapshot.AttemptId;
        }

        _lastOperationVersion = snapshot.Version;
        foreach (var result in snapshot.Results)
        {
            if (FindRow(result.Path) is { } row)
            {
                row.ApplyCompatibilityResult(result);
            }
        }

        if (!snapshot.IsTerminal
            && !string.IsNullOrWhiteSpace(snapshot.Progress.CurrentItem)
            && FindRow(snapshot.Progress.CurrentItem) is { } currentRow
            && currentRow.CompatibilityStatus is "pending" or "running")
        {
            currentRow.MarkRunning();
        }

        var maximum = Math.Max(1, snapshot.Progress.Total);
        CompatibilityProgress.IsIndeterminate = snapshot.Progress.Total == 0 && !snapshot.IsTerminal;
        CompatibilityProgress.Maximum = maximum;
        CompatibilityProgress.Value = Math.Clamp(snapshot.Progress.Completed, 0, maximum);
        CompatibilityProgressText.Text = $"{snapshot.Progress.Completed} / {snapshot.Progress.Total}";

        var currentItem = string.IsNullOrWhiteSpace(snapshot.Progress.CurrentItem)
            ? string.Empty
            : $" · {Path.GetFileName(snapshot.Progress.CurrentItem)}";
        CompatibilityStatusText.Text =
            $"{OperationStatusDisplay(snapshot.Status)}{currentItem} · {FormatOperationId(snapshot.OperationId)}";
        App.Current.MainWindow.ReportPageStatus(
            $"兼容性检查 · {snapshot.Progress.Completed} / {snapshot.Progress.Total} · {OperationStatusDisplay(snapshot.Status)}");
        RefreshInteractionState();
    }

    private void CompleteCompatibilityOperation(OdbCompatibilityOperationSnapshot snapshot)
    {
        switch (snapshot.Status)
        {
            case "succeeded":
                MarkUnfinishedRows("无结果", "控制面未返回此 ODB 的兼容性结果。");
                CompatibilityStatusText.Text =
                    $"兼容性检查完成 · {snapshot.Results.Count} 个结果 · {FormatOperationId(snapshot.OperationId)}";
                App.Current.MainWindow.ReportPageStatus(
                    $"兼容性检查完成 · {snapshot.Progress.Completed} / {snapshot.Progress.Total}");
                break;
            case "cancelled":
                MarkUnfinishedRows("未完成", "兼容性检查已取消。");
                CompatibilityStatusText.Text = $"兼容性检查已取消 · {FormatOperationId(snapshot.OperationId)}";
                ShowWarning("已保留取消前返回的兼容性结果。", "兼容性检查已取消");
                App.Current.MainWindow.ReportPageStatus("兼容性检查已取消");
                break;
            case "failed":
                var errorMessage = FormatOperationError(snapshot.Error);
                MarkUnfinishedRows("检查失败", errorMessage);
                CompatibilityStatusText.Text = $"兼容性检查失败 · {FormatOperationId(snapshot.OperationId)}";
                ShowError(errorMessage, "兼容性检查失败");
                break;
        }
    }

    private OdbFileRow? FindRow(string path)
    {
        if (_odbByPath.TryGetValue(PathKey(path), out var row))
        {
            return row;
        }

        if (!Path.IsPathFullyQualified(path)
            && !string.IsNullOrWhiteSpace(RootTextBox.Text))
        {
            var rootedPath = Path.Combine(RootTextBox.Text.Trim(), path);
            if (_odbByPath.TryGetValue(PathKey(rootedPath), out row))
            {
                return row;
            }
        }

        var fileName = Path.GetFileName(path);
        var matchingRows = _odbItems
            .Where(candidate => string.Equals(candidate.Name, fileName, StringComparison.OrdinalIgnoreCase))
            .Take(2)
            .ToArray();
        if (matchingRows.Length == 1)
        {
            return matchingRows[0];
        }

        return null;
    }

    private void MarkUnfinishedRows(string statusDisplay, string message)
    {
        foreach (var pathKey in _activePathKeys)
        {
            if (_odbByPath.TryGetValue(pathKey, out var row)
                && row.CompatibilityStatus is "pending" or "running")
            {
                row.MarkIncomplete(statusDisplay, message);
            }
        }
    }

    private void SetDiscoveryBusy(bool busy)
    {
        _discoveryBusy = busy;
        DiscoveryProgress.IsActive = busy;
        DiscoveryProgress.Visibility = busy ? Visibility.Visible : Visibility.Collapsed;
        DiscoverButtonText.Text = busy ? "正在发现" : "发现 ODB";
        RefreshInteractionState();
    }

    private void SetCompatibilityBusy(bool busy)
    {
        _compatibilityBusy = busy;
        RefreshInteractionState();
    }

    private void SetPostprocessBusy(bool busy)
    {
        _postprocessBusy = busy;
        RefreshInteractionState();
    }

    private void RefreshInteractionState()
    {
        var idle = !_discoveryBusy && !_compatibilityBusy && !_postprocessBusy && !UpgradeBlocksEditing && !DraftPending && !_draftActionBusy && !_groupQueueCommandBusy;
        var canStartOtherOperation = idle && !GroupQueueBlocksOtherOperations;
        RefreshDraftActions();
        var hasItems = _odbItems.Count > 0;
        var selectedCount = OdbList.SelectedItems.Count;
        var selectedRows = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();

        BrowseButton.IsEnabled = canStartOtherOperation;
        GroupOrderButton.IsEnabled = idle && _odbItems.Any(row => ParseGroupNames(row.ComparisonGroup).Length > 0);
        CreateGroupsButton.IsEnabled = idle && _lastDiscoveryRoot is not null
            && !_unreadableWorkspaces.Contains(PathKey(_lastDiscoveryRoot));
        ManageGroupsButton.IsEnabled = CreateGroupsButton.IsEnabled
            && (GroupOrderButton.IsEnabled || _groupMemberOrder.Count != 0 || _legendOverridesByGroup.Count != 0);
        DiscoverButton.IsEnabled = canStartOtherOperation;
        RootTextBox.IsEnabled = canStartOtherOperation;
        RecursiveCheckBox.IsEnabled = canStartOtherOperation;
        OdbList.IsEnabled = idle;
        SelectAllButton.IsEnabled = idle && hasItems && selectedCount < _odbItems.Count;
        SelectNoneButton.IsEnabled = idle && selectedCount > 0;
        InvertSelectionButton.IsEnabled = idle && hasItems;
        ForceRescanCheckBox.IsEnabled = idle && hasItems;
        CompatibilityCheckButton.IsEnabled = canStartOtherOperation && selectedCount > 0;
        UpgradeButton.IsEnabled = canStartOtherOperation && selectedCount > 0
            && selectedRows.All(row => row.CompatibilityStatus == "upgrade_required");
        RecoverUpgradeButton.IsEnabled = !GroupQueueBlocksOtherOperations && !_discoveryBusy && !_compatibilityBusy && !_postprocessBusy && !_upgradeBusy;
        CancelUpgradeButton.Visibility = UpgradeBlocksEditing ? Visibility.Visible : Visibility.Collapsed;
        CancelUpgradeButton.IsEnabled = !string.IsNullOrWhiteSpace(_upgradeOperationId)
            && !_upgradeCancelRequested;
        AnalyzeButton.IsEnabled = canStartOtherOperation && selectedCount > 0;
        StructureBrowserButton.IsEnabled = canStartOtherOperation && selectedRows.Length == 1
            && selectedRows[0].ScanDetails is { Error.Length: 0 };
        ApplyGroupButton.IsEnabled = idle && selectedCount > 0;
        LegendButton.IsEnabled = CreateGroupsButton.IsEnabled
            && (selectedCount > 0 || _groupMemberOrder.Count != 0 || _legendOverridesByGroup.Count != 0);
        ConfigureButton.Content = selectedCount > 1 ? "对照提取参数…" : "编辑提取参数";
        ConfigureButton.IsEnabled = idle && selectedRows.Length > 0
            && selectedRows.All(row => row.ScanDetails is { Error.Length: 0 } && row.PostprocessJob is not null);
        var runScope = ResolveRunScope(selectedRows);
        RunScopePreviewText.Text = runScope.Summary;
        RunScopeComboBox.IsEnabled = idle;
        RunPostprocessButton.IsEnabled = idle && runScope.CanRun;
        OpenResultsButton.IsEnabled = !_discoveryBusy && !_postprocessBusy && !string.IsNullOrWhiteSpace(RootTextBox.Text);
        ParallelWorkersNumberBox.IsEnabled = idle;
        GroupNameTextBox.IsEnabled = idle;
        GroupOperationComboBox.IsEnabled = idle;
        FullTimehistoryCheckBox.IsEnabled = idle;
        RebarMethodComboBox.IsEnabled = idle;
        ExpectedRebarCountNumberBox.IsEnabled = idle;
        ImageUnitComboBox.IsEnabled = idle;
        ImageWidthNumberBox.IsEnabled = idle;
        ImageHeightNumberBox.IsEnabled = idle;
        AnimationFpsNumberBox.IsEnabled = idle;
        AnimationTimingModeComboBox.IsEnabled = idle;
        AnimationDurationNumberBox.IsEnabled = idle;
        RebarToleranceNumberBox.IsEnabled = idle;
        WhiteBackgroundCheckBox.IsEnabled = idle;
        TransparentBackgroundCheckBox.IsEnabled = idle;
        CancelCompatibilityButton.IsEnabled =
            _compatibilityBusy
            && !_cancelRequested
            && !string.IsNullOrWhiteSpace(_activeOperationId);
        CancelCompatibilityButton.Visibility = _compatibilityBusy
            ? Visibility.Visible
            : Visibility.Collapsed;
        CancelPostprocessButton.IsEnabled = _postprocessBusy && !_postprocessRecoveryBusy && !_postprocessCancelInFlight
            && _postprocessTracking.CanCancel;
        RecoverPostprocessButton.Visibility = _postprocessTracking.NeedsRecovery ? Visibility.Visible : Visibility.Collapsed;
        RecoverPostprocessButton.IsEnabled = _postprocessTracking.NeedsRecovery && !_postprocessRecoveryBusy
            && _postprocessMonitoringSource is null && !_postprocessCancelInFlight;
        UpdateGroupQueueControls();
        SelectionCountText.Text = $"已选择 {selectedCount} / {_odbItems.Count}";
        SelectedPlanText.Text = selectedRows.Length switch
        {
            0 => "选择 ODB 后可编辑参数",
            1 when selectedRows[0].HasPostprocessConfiguration =>
                $"{selectedRows[0].Name}{Environment.NewLine}{selectedRows[0].PostprocessSummary}",
            1 => $"{selectedRows[0].Name}{Environment.NewLine}请先读取 ODB 结构",
            _ => $"已选择 {selectedRows.Length} 个 ODB · 已就绪 {selectedRows.Count(row => row.HasPostprocessConfiguration)} 个",
        };
    }

    private void ResetCompatibilityPresentation()
    {
        _activeOperationId = null;
        _activeAttemptId = null;
        _lastOperationVersion = -1;
        _activePathKeys.Clear();
        _cancelRequested = false;
        CompatibilityProgress.IsIndeterminate = false;
        CompatibilityProgress.Maximum = 1;
        CompatibilityProgress.Value = 0;
        CompatibilityProgressText.Text = "0 / 0";
        CompatibilityStatusText.Text = "尚未运行兼容性检查";
    }

    private void ShowError(string message, string title = "操作失败")
    {
        ErrorInfoBar.Title = title;
        ErrorInfoBar.Message = message;
        ErrorInfoBar.IsOpen = true;
        App.Current.MainWindow.ReportPageStatus(title);
    }

    private void ShowWarning(string message, string title)
    {
        WarningInfoBar.Title = title;
        WarningInfoBar.Message = message;
        WarningInfoBar.IsOpen = true;
    }

    private static string PathKey(string path)
    {
        try
        {
            return Path.GetFullPath(path.Trim()).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        }
        catch (Exception exception) when (exception is ArgumentException or NotSupportedException or PathTooLongException)
        {
            return path.Trim().Replace(Path.AltDirectorySeparatorChar, Path.DirectorySeparatorChar);
        }
    }

    private static string OperationStatusDisplay(string status)
    {
        return status switch
        {
            "queued" => "排队中",
            "starting" => "正在启动 Abaqus",
            "running" => "正在检查",
            "cancelling" => "正在取消",
            "succeeded" => "已完成",
            "cancelled" => "已取消",
            "failed" => "失败",
            _ => status,
        };
    }

    private static string FormatOperationError(OdbCompatibilityOperationError? error)
    {
        if (error is null || string.IsNullOrWhiteSpace(error.Message))
        {
            return "兼容性检查未能完成，控制面没有返回详细原因。";
        }

        return string.IsNullOrWhiteSpace(error.TraceId)
            ? error.Message
            : $"{error.Message}（跟踪 ID：{error.TraceId}）";
    }

    private static string FormatDiscoveryId(string discoveryId)
    {
        if (string.IsNullOrWhiteSpace(discoveryId))
        {
            return "发现记录不可用";
        }

        return discoveryId.Length <= 12 ? discoveryId : $"发现 {discoveryId[..8]}";
    }

    private static string FormatOperationId(string operationId)
    {
        if (string.IsNullOrWhiteSpace(operationId))
        {
            return "操作记录不可用";
        }

        return operationId.Length <= 12 ? operationId : $"操作 {operationId[..8]}";
    }
}
