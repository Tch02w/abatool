using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Navigation;
using Windows.Storage.Pickers;
using Windows.System;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage : Page
{
    private readonly ObservableCollection<OdbFileRow> _odbItems = [];
    private readonly Dictionary<string, OdbFileRow> _odbByPath =
        new(StringComparer.OrdinalIgnoreCase);
    private readonly HashSet<string> _activePathKeys =
        new(StringComparer.OrdinalIgnoreCase);
    private readonly Dictionary<string, IReadOnlyDictionary<string, OdbLegendOverride>> _legendOverridesByGroup =
        new(StringComparer.OrdinalIgnoreCase);
    private static readonly string[] LegendFieldNames =
    [
        "PILE_U_MAG",
        "PILE_CON_S_MISES",
        "PILE_STEEL_S_MISES",
        "PILE_CON_DAMAGET",
        "PILE_CON_DAMAGEC",
        "SOIL_PEEQ_XZ",
        "SOIL_PEMAG_XZ",
        "SOIL_S33_XZ",
        "SOIL_S_MISES_XZ",
        "REBAR_LONG_S_MISES_UNDEFORMED",
        "REBAR_LONG_S11_UNDEFORMED",
    ];

    private bool _discoveryBusy;
    private bool _compatibilityBusy;
    private bool _postprocessBusy;
    private bool _cancelRequested;
    private bool _recoveryAttempted;
    private string? _activeOperationId;
    private string? _activeAttemptId;
    private long _lastOperationVersion = -1;
    private string? _activePostprocessOperationId;
    private string? _activePostprocessKind;
    private long _lastPostprocessVersion = -1;
    private int _displayedLogCount;

    public OdbPostprocessingPage()
    {
        InitializeComponent();
        NavigationCacheMode = NavigationCacheMode.Required;
        OdbList.ItemsSource = _odbItems;
        Loaded += OnPageLoaded;
        RefreshInteractionState();
    }

    public async Task LoadOdbPathAsync(string path)
    {
        if (!string.Equals(Path.GetExtension(path), ".odb", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        var directory = Path.GetDirectoryName(path);
        if (string.IsNullOrWhiteSpace(directory))
        {
            return;
        }

        RootTextBox.Text = directory;
        await DiscoverAsync();
        if (_odbByPath.TryGetValue(PathKey(path), out var row))
        {
            OdbList.SelectedItem = row;
            OdbList.ScrollIntoView(row);
        }
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        if (_recoveryAttempted)
        {
            return;
        }

        _recoveryAttempted = true;
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
            var snapshot = operations.Operations.FirstOrDefault(operation => !operation.IsTerminal);
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

            _activePostprocessOperationId = snapshot.OperationId;
            _activePostprocessKind = snapshot.Kind;
            _lastPostprocessVersion = -1;
            _displayedLogCount = 0;
            ApplyPostprocessSnapshot(snapshot);
            App.Current.MainWindow.ReportPageStatus("已恢复未完成的 ODB 后处理操作");
            var progress = new Progress<OdbPostprocessOperationSnapshot>(ApplyPostprocessSnapshot);
            var final = await App.Current.ControlPlane.PollOdbPostprocessUntilTerminalAsync(
                snapshot,
                progress);
            ApplyPostprocessSnapshot(final);
            CompletePostprocessOperation(final);
            return true;
        }
        catch (OperationCanceledException)
        {
            PostprocessPhaseText.Text = "ODB 后处理操作已取消";
            return true;
        }
        catch (Exception exception)
        {
            ShowWarning(exception.Message, "未能恢复 ODB 后处理操作");
            return false;
        }
        finally
        {
            _activePostprocessOperationId = null;
            _activePostprocessKind = null;
            SetPostprocessBusy(false);
        }
    }

    private void RestoreRowsFromPostprocessRequest(OdbPostprocessOperationRequestSummary request)
    {
        OdbList.SelectedItems.Clear();
        _odbItems.Clear();
        _odbByPath.Clear();
        RootTextBox.Text = request.Root;
        ForceRescanCheckBox.IsChecked = request.ForceRescan;
        ParallelWorkersNumberBox.Value = Math.Clamp(request.ParallelWorkers, 1, 4);
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
        var root = RootTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(root))
        {
            ShowError("请选择或输入 ODB 根目录。", "无法发现 ODB");
            RootTextBox.Focus(FocusState.Programmatic);
            return;
        }

        SetDiscoveryBusy(true);
        ErrorInfoBar.IsOpen = false;
        WarningInfoBar.IsOpen = false;
        OdbList.SelectedItems.Clear();
        _odbItems.Clear();
        _odbByPath.Clear();
        ResetCompatibilityPresentation();
        ResultCountText.Text = "0 个";
        DiscoveryMetadataText.Text = "正在扫描";
        EmptyState.Visibility = Visibility.Visible;
        EmptyStateTitle.Text = "正在发现 ODB…";
        App.Current.MainWindow.ReportPageStatus("正在通过本地控制面发现 ODB…");
        try
        {
            var result = await App.Current.ControlPlane.DiscoverOdbsAsync(
                root,
                RecursiveCheckBox.IsChecked is not false);

            foreach (var odb in result.Odbs)
            {
                var row = new OdbFileRow(odb);
                _odbItems.Add(row);
                _odbByPath[PathKey(row.Path)] = row;
            }

            if (_odbItems.Count > 0)
            {
                OdbList.SelectAll();
            }

            RootTextBox.Text = result.Root;
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
        }
        catch (ControlPlaneException exception)
        {
            DiscoveryMetadataText.Text = "扫描失败";
            EmptyStateTitle.Text = "未能发现 ODB";
            ShowError(exception.ToDisplayMessage(), "ODB 发现失败");
        }
        catch (Exception exception)
        {
            DiscoveryMetadataText.Text = "扫描失败";
            EmptyStateTitle.Text = "未能发现 ODB";
            ShowError("ODB 发现失败。" + Environment.NewLine + exception.Message, "ODB 发现失败");
        }
        finally
        {
            SetDiscoveryBusy(false);
        }
    }

    private void OnOdbSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        RefreshInteractionState();
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
        OdbList.SelectedItems.Clear();
        foreach (var row in _odbItems.Where(row => !selected.Contains(row)))
        {
            OdbList.SelectedItems.Add(row);
        }

        RefreshInteractionState();
    }

    private async void OnCompatibilityCheckClicked(object sender, RoutedEventArgs e)
    {
        await StartCompatibilityCheckAsync();
    }

    private async void OnOpenResultsClicked(object sender, RoutedEventArgs e)
    {
        var root = RootTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(root))
        {
            ShowWarning("请先选择 ODB 根目录。", "无法打开结果浏览");
            return;
        }

        var resultRoot = Path.Combine(root, "AbaqusODBPostProcessor_Results");
        if (!Directory.Exists(resultRoot))
        {
            ShowWarning(
                $"尚未找到结果目录：{resultRoot}{Environment.NewLine}请先完成后处理提取。",
                "结果目录不存在");
            return;
        }

        await App.Current.MainWindow.OpenResultBrowserAsync(resultRoot);
    }

    private async void OnAnalyzeClicked(object sender, RoutedEventArgs e)
    {
        await AnalyzeSelectedAsync();
    }

    private async Task AnalyzeSelectedAsync()
    {
        if (_postprocessBusy || _compatibilityBusy || _discoveryBusy)
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
                Guid.NewGuid());
            ForceRescanCheckBox.IsChecked = false;
            _activePostprocessOperationId = initial.OperationId;
            ApplyPostprocessSnapshot(initial);
            var progress = new Progress<OdbPostprocessOperationSnapshot>(ApplyPostprocessSnapshot);
            var final = await App.Current.ControlPlane.PollOdbPostprocessUntilTerminalAsync(
                initial,
                progress);
            ApplyPostprocessSnapshot(final);
            CompletePostprocessOperation(final);
        }
        catch (OperationCanceledException)
        {
            MarkPostprocessRowsIncomplete("未完成", "ODB 结构读取已取消。");
            PostprocessPhaseText.Text = "ODB 结构读取已取消";
        }
        catch (ControlPlaneException exception)
        {
            MarkPostprocessRowsIncomplete("读取失败", exception.Message);
            ShowError(exception.ToDisplayMessage(), "ODB 结构读取失败");
        }
        catch (Exception exception)
        {
            MarkPostprocessRowsIncomplete("读取失败", exception.Message);
            ShowError(exception.Message, "ODB 结构读取失败");
        }
        finally
        {
            _activePostprocessOperationId = null;
            _activePostprocessKind = null;
            _activePathKeys.Clear();
            SetPostprocessBusy(false);
        }
    }

    private void OnApplyGroupClicked(object sender, RoutedEventArgs e)
    {
        var names = ParseGroupNames(GroupNameTextBox.Text);
        if (names.Length == 0)
        {
            ShowWarning("对比组名称不能为空。", "无法应用对比组");
            return;
        }

        var selected = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();
        foreach (var row in selected)
        {
            row.ComparisonGroup = string.Join("；", names);
        }
        SelectedPlanText.Text = $"已将 {selected.Length} 个 ODB 加入：{string.Join("、", names)}";
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
        var rows = new List<(string Field, CheckBox Manual, TextBox Minimum, TextBox Maximum)>();
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
        foreach (var field in LegendFieldNames)
        {
            grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            OdbLegendOverride? rule = null;
            var enabled = existing is not null && existing.TryGetValue(field, out rule);
            var label = new TextBlock { Text = field, VerticalAlignment = VerticalAlignment.Center };
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
            rows.Add((field, manual, minimum, maximum));
            rowIndex++;
        }

        var content = new StackPanel { Spacing = 10 };
        content.Children.Add(new TextBlock
        {
            Text = "自动模式按本组全部 ODB 汇总。仅在需要跨批次固定色标时启用手动范围。",
            TextWrapping = TextWrapping.Wrap,
            Opacity = 0.72,
        });
        content.Children.Add(grid);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"图例范围 · {groupName}",
            Content = new ScrollViewer
            {
                MaxHeight = 620,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Auto,
                VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
                Content = content,
            },
            PrimaryButtonText = "保存范围",
            SecondaryButtonText = "全部恢复自动",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Primary,
        };
        var result = await dialog.ShowAsync();
        if (result == ContentDialogResult.None)
        {
            return;
        }
        if (result == ContentDialogResult.Secondary)
        {
            _legendOverridesByGroup.Remove(groupName);
            ShowWarning($"“{groupName}”已恢复为自动图例范围。", "图例设置已更新");
            return;
        }

        var values = new Dictionary<string, OdbLegendOverride>(StringComparer.Ordinal);
        foreach (var row in rows.Where(row => row.Manual.IsChecked is true))
        {
            if (!double.TryParse(row.Minimum.Text, out var minimum)
                || !double.TryParse(row.Maximum.Text, out var maximum)
                || !double.IsFinite(minimum)
                || !double.IsFinite(maximum)
                || maximum <= minimum)
            {
                ShowWarning($"{row.Field} 的上下限必须是有效数字，且最大值大于最小值。", "图例范围无效");
                return;
            }
            values[row.Field] = new OdbLegendOverride
            {
                Minimum = minimum,
                Maximum = maximum,
            };
        }
        _legendOverridesByGroup[groupName] = values;
        ShowWarning($"已保存“{groupName}”的 {values.Count} 个手动图例范围。", "图例设置已更新");
    }

    private async void OnConfigureClicked(object sender, RoutedEventArgs e)
    {
        var selected = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();
        if (selected.Length != 1)
        {
            ShowWarning("请只选择一个 ODB，再编辑它的提取参数。", "需要单选");
            return;
        }
        var row = selected[0];
        if (row.ScanDetails is null || row.PostprocessJob is null)
        {
            ShowWarning("请先运行“读取结构与默认参数”。", "参数尚未就绪");
            return;
        }

        var draft = await ShowJobConfigurationDialogAsync(row);
        if (draft is not null)
        {
            row.UpdatePostprocessJob(draft);
            SelectedPlanText.Text = $"已更新 {row.Name} 的提取参数";
            RefreshInteractionState();
        }
    }

    private async Task<OdbPostprocessJobDraft?> ShowJobConfigurationDialogAsync(OdbFileRow row)
    {
        var scan = row.ScanDetails!;
        var current = row.PostprocessJob!.Clone();
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
        var steel = Choice(["", .. scan.AssemblyElementSets], current.PileSteelSet, "钢构件集合（RC 可留空）");
        var soil = Choice(scan.AssemblyElementSets, current.SoilSet, "土体截面集合");
        var rebar = Choice(scan.AssemblyElementSets, current.RebarSet, "纵筋集合");
        var material = new TextBox { Header = "纵筋材料", Text = current.LongitudinalMaterial };
        var diameter = new NumberBox
        {
            Header = "纵筋直径 mm",
            Minimum = 1,
            Maximum = 100,
            Value = current.RebarDiameterMm,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact,
        };
        var prefracture = new NumberBox
        {
            Header = "断裂前帧序号（-1=自动）",
            Minimum = -1,
            Maximum = 1_000_000,
            Value = current.PrefractureSequenceIndex,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Compact,
        };
        var fields = new StackPanel { Spacing = 10 };
        fields.Children.Add(new TextBlock
        {
            Text = scan.NameMetadata.Condition.Length > 0
                ? $"文件名识别：{scan.NameMetadata.SampleId} · {scan.NameMetadata.Condition}"
                : "文件名没有提供加载方向，请在下方手动选择。",
            TextWrapping = TextWrapping.Wrap,
            Opacity = 0.72,
        });
        foreach (var control in new Control[]
        {
            startStep, endStep, frameMode, manualFrames, direction, loadSet, pileType,
            pileDisplay, concrete, steel, soil, rebar, material, diameter, prefracture,
        })
        {
            fields.Children.Add(control);
        }

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
        if (await dialog.ShowAsync() != ContentDialogResult.Primary)
        {
            return null;
        }

        var mode = frameMode.SelectedItem?.ToString() switch
        {
            "全部帧" => "all",
            "手动帧序号" => "manual",
            _ => "auto",
        };
        if (mode == "manual" && string.IsNullOrWhiteSpace(manualFrames.Text))
        {
            ShowWarning("手动帧模式必须填写帧序号表达式。", "参数未保存");
            return null;
        }

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
            HorizontalAlignment = HorizontalAlignment.Stretch,
        };
        var index = Array.FindIndex(items, value => string.Equals(value, selected, StringComparison.OrdinalIgnoreCase));
        combo.SelectedIndex = index >= 0 ? index : (items.Length > 0 ? 0 : -1);
        return combo;
    }

    private static string SelectedText(ComboBox combo) => combo.SelectedItem?.ToString()?.Trim() ?? string.Empty;

    private async void OnRunPostprocessClicked(object sender, RoutedEventArgs e)
    {
        await RunPostprocessAsync();
    }

    private async Task RunPostprocessAsync()
    {
        if (_postprocessBusy || _compatibilityBusy || _discoveryBusy)
        {
            return;
        }
        var rows = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();
        if (rows.Length == 0 || rows.Any(row => row.PostprocessJob is null))
        {
            ShowWarning("请选择已完成结构读取的 ODB。", "处理计划不完整");
            return;
        }
        if (WhiteBackgroundCheckBox.IsChecked is not true
            && TransparentBackgroundCheckBox.IsChecked is not true)
        {
            ShowWarning("白底 PNG 与透明底 PNG 至少启用一项。", "输出设置无效");
            return;
        }

        var memberships = new Dictionary<string, List<OdbFileRow>>(StringComparer.OrdinalIgnoreCase);
        foreach (var row in rows)
        {
            var names = ParseGroupNames(row.ComparisonGroup);
            if (names.Length == 0)
            {
                names = [row.Name];
            }
            foreach (var name in names)
            {
                if (!memberships.TryGetValue(name, out var members))
                {
                    members = [];
                    memberships[name] = members;
                }
                if (!members.Contains(row))
                {
                    members.Add(row);
                }
            }
        }
        var groups = memberships
            .Select((group, index) => new OdbPostprocessGroupDraft
            {
                Id = $"group-{index + 1}",
                Name = group.Key,
                Members = group.Value.Select(row => row.Path).ToArray(),
                Standalone = group.Value.Count == 1
                    && ParseGroupNames(group.Value[0].ComparisonGroup).Length == 0,
                LegendOverrides = _legendOverridesByGroup.TryGetValue(group.Key, out var overrides)
                    ? overrides
                    : new Dictionary<string, OdbLegendOverride>(),
            })
            .ToArray();
        var request = new OdbPostprocessRunCreateRequest
        {
            ClientRequestId = Guid.NewGuid().ToString("D"),
            Root = RootTextBox.Text.Trim(),
            ParallelWorkers = ParallelWorkerCount(),
            ForceRescan = ForceRescanCheckBox.IsChecked is true,
            FullTimehistoryFreebody = FullTimehistoryCheckBox.IsChecked is true,
            RebarMethod = SelectedTag(RebarMethodComboBox, "element_cut"),
            ExpectedLongitudinalRebarCount = (int)Math.Round(ExpectedRebarCountNumberBox.Value),
            ImageSizeUnit = SelectedTag(ImageUnitComboBox, "px"),
            ImageWidth = (int)Math.Round(ImageWidthNumberBox.Value),
            ImageHeight = (int)Math.Round(ImageHeightNumberBox.Value),
            ExportWhiteBackgroundPng = WhiteBackgroundCheckBox.IsChecked is true,
            ExportTransparentBackgroundPng = TransparentBackgroundCheckBox.IsChecked is true,
            AnimationFps = (int)Math.Round(AnimationFpsNumberBox.Value),
            RebarCutToleranceMm = RebarToleranceNumberBox.Value,
            Jobs = rows.Select(row => row.PostprocessJob!.Clone()).ToArray(),
            Groups = groups,
        };

        _activePathKeys.Clear();
        foreach (var row in rows)
        {
            _activePathKeys.Add(PathKey(row.Path));
            row.MarkProcessing("排队中", "处理计划已提交，等待 Abaqus 后处理");
        }
        _activePostprocessOperationId = null;
        _activePostprocessKind = "odb.postprocess.run";
        _lastPostprocessVersion = -1;
        _displayedLogCount = 0;
        PostprocessLogTextBox.Text = string.Empty;
        SetPostprocessBusy(true);
        try
        {
            var initial = await App.Current.ControlPlane.StartOdbPostprocessAsync(request);
            ForceRescanCheckBox.IsChecked = false;
            _activePostprocessOperationId = initial.OperationId;
            ApplyPostprocessSnapshot(initial);
            var progress = new Progress<OdbPostprocessOperationSnapshot>(ApplyPostprocessSnapshot);
            var final = await App.Current.ControlPlane.PollOdbPostprocessUntilTerminalAsync(initial, progress);
            ApplyPostprocessSnapshot(final);
            CompletePostprocessOperation(final);
        }
        catch (OperationCanceledException)
        {
            MarkPostprocessRowsIncomplete("已取消", "ODB 后处理已取消，源 ODB 未被修改。");
        }
        catch (ControlPlaneException exception)
        {
            MarkPostprocessRowsIncomplete("处理失败", exception.Message);
            ShowError(exception.ToDisplayMessage(), "ODB 后处理失败");
        }
        catch (Exception exception)
        {
            MarkPostprocessRowsIncomplete("处理失败", exception.Message);
            ShowError(exception.Message, "ODB 后处理失败");
        }
        finally
        {
            _activePostprocessOperationId = null;
            _activePostprocessKind = null;
            _activePathKeys.Clear();
            SetPostprocessBusy(false);
        }
    }

    private async void OnCancelPostprocessClicked(object sender, RoutedEventArgs e)
    {
        if (string.IsNullOrWhiteSpace(_activePostprocessOperationId))
        {
            return;
        }
        CancelPostprocessButton.IsEnabled = false;
        PostprocessPhaseText.Text = "正在停止 Abaqus 子进程，请稍候…";
        try
        {
            var snapshot = await App.Current.ControlPlane.CancelOdbPostprocessOperationAsync(
                _activePostprocessOperationId);
            ApplyPostprocessSnapshot(snapshot);
        }
        catch (Exception exception)
        {
            ShowError(exception.Message, "无法停止 ODB 后处理");
            RefreshInteractionState();
        }
    }

    private void ApplyPostprocessSnapshot(OdbPostprocessOperationSnapshot snapshot)
    {
        if (_activePostprocessOperationId is not null
            && !string.Equals(_activePostprocessOperationId, snapshot.OperationId, StringComparison.Ordinal))
        {
            return;
        }
        if (snapshot.Version < _lastPostprocessVersion)
        {
            return;
        }
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
        if (snapshot.Status == "succeeded" && snapshot.Result is { } result)
        {
            if (snapshot.Kind == "odb.postprocess.scan")
            {
                foreach (var item in result.Items)
                {
                    FindRow(item.Path)?.ApplyPostprocessScan(item);
                }
                MarkPostprocessRowsWithoutConfiguration("没有返回 ODB 结构结果。");
                PostprocessPhaseText.Text = $"结构读取完成 · {result.Count} 个 ODB · 缓存命中 {result.CacheHits}";
            }
            else
            {
                foreach (var pathKey in _activePathKeys)
                {
                    if (_odbByPath.TryGetValue(pathKey, out var row))
                    {
                        row.MarkProcessing("已完成", $"本批次共生成 {result.OutputCount} 个结果目录");
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

    private void MarkPostprocessRowsWithoutConfiguration(string message)
    {
        foreach (var pathKey in _activePathKeys)
        {
            if (_odbByPath.TryGetValue(pathKey, out var row) && !row.HasPostprocessConfiguration)
            {
                row.MarkPostprocessIncomplete("无结构结果", message);
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

    private int ParallelWorkerCount() => Math.Clamp((int)Math.Round(ParallelWorkersNumberBox.Value), 1, 4);

    private static string SelectedTag(ComboBox comboBox, string fallback) =>
        (comboBox.SelectedItem as ComboBoxItem)?.Tag?.ToString() ?? fallback;

    private static string[] ParseGroupNames(string value) => value
        .Replace('；', ';')
        .Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Where(name => !string.IsNullOrWhiteSpace(name))
        .Distinct(StringComparer.OrdinalIgnoreCase)
        .ToArray();

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
        if (_discoveryBusy || _compatibilityBusy)
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
        var idle = !_discoveryBusy && !_compatibilityBusy && !_postprocessBusy;
        var hasItems = _odbItems.Count > 0;
        var selectedCount = OdbList.SelectedItems.Count;
        var selectedRows = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();

        BrowseButton.IsEnabled = idle;
        DiscoverButton.IsEnabled = idle;
        RootTextBox.IsEnabled = idle;
        RecursiveCheckBox.IsEnabled = idle;
        OdbList.IsEnabled = idle;
        SelectAllButton.IsEnabled = idle && hasItems && selectedCount < _odbItems.Count;
        SelectNoneButton.IsEnabled = idle && selectedCount > 0;
        InvertSelectionButton.IsEnabled = idle && hasItems;
        ForceRescanCheckBox.IsEnabled = idle && hasItems;
        CompatibilityCheckButton.IsEnabled = idle && selectedCount > 0;
        AnalyzeButton.IsEnabled = idle && selectedCount > 0;
        ApplyGroupButton.IsEnabled = idle && selectedCount > 0;
        LegendButton.IsEnabled = idle && selectedCount > 0;
        ConfigureButton.IsEnabled = idle
            && selectedRows.Length == 1
            && selectedRows[0].HasPostprocessConfiguration;
        RunPostprocessButton.IsEnabled = idle
            && selectedRows.Length > 0
            && selectedRows.All(row => row.HasPostprocessConfiguration);
        OpenResultsButton.IsEnabled = !_discoveryBusy && !string.IsNullOrWhiteSpace(RootTextBox.Text);
        ParallelWorkersNumberBox.IsEnabled = idle;
        GroupNameTextBox.IsEnabled = idle;
        FullTimehistoryCheckBox.IsEnabled = idle;
        RebarMethodComboBox.IsEnabled = idle;
        ExpectedRebarCountNumberBox.IsEnabled = idle;
        ImageUnitComboBox.IsEnabled = idle;
        ImageWidthNumberBox.IsEnabled = idle;
        ImageHeightNumberBox.IsEnabled = idle;
        AnimationFpsNumberBox.IsEnabled = idle;
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
        CancelPostprocessButton.IsEnabled = _postprocessBusy
            && !string.IsNullOrWhiteSpace(_activePostprocessOperationId);
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
