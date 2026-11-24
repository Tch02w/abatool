using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.Storage.Pickers;
using Line = Microsoft.UI.Xaml.Shapes.Line;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class RestartChainPage : Page, IWorkbenchExplorerPage
{
    private readonly ObservableCollection<RestartChainNode> _nodes = [];
    private bool _refreshBusy;
    private RestartChainNode? _selectedNode;
    private Button? _selectedGraphButton;
    private double _graphZoom = 1;
    private readonly RestartChainExplorerAdapter _explorerAdapter;

    public RestartChainPage()
    {
        InitializeComponent();
        _explorerAdapter = new RestartChainExplorerAdapter(RefreshAsync, SelectExplorerNode);
        App.Current.Session.Register(this, "restart-chain", []);
        Loaded += OnPageLoaded;
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _explorerAdapter;

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }

    private async void OnRefreshClicked(object sender, RoutedEventArgs e)
    {
        await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        if (_refreshBusy)
        {
            return;
        }

        _refreshBusy = true;
        RefreshButton.IsEnabled = false;
        try
        {
            var selectedItemId = _selectedNode?.ItemId;
            var snapshot = await App.Current.ControlPlane.GetRestartChainsAsync();
            _nodes.Clear();
            foreach (var node in snapshot.GraphNodes.Count > 0
                         ? snapshot.GraphNodes
                         : snapshot.Nodes)
            {
                _nodes.Add(node);
            }
            _selectedNode = _nodes.FirstOrDefault(node => string.Equals(
                node.ItemId,
                selectedItemId,
                StringComparison.Ordinal));
            RenderRestartGraph();
            UpdateExplorer(snapshot);

            EmptyChainPanel.Visibility = snapshot.NodeCount == 0
                ? Visibility.Visible
                : Visibility.Collapsed;
            ChainSummaryText.Text = $"{snapshot.ChainCount} 条链 · {_nodes.Count} 个节点 · {snapshot.NodeCount} 个重启动作业";
            CycleCheckText.Text = CheckText(snapshot.Checks.CycleCount);
            MissingCheckText.Text = CheckText(snapshot.Checks.MissingParentCount);
            PathCheckText.Text = CheckText(snapshot.Checks.IncompatiblePathCount);
            OrderCheckText.Text = snapshot.Checks.CycleCount == 0
                ? $"已生成 · {snapshot.Checks.ValidCount} 个有效节点"
                : "循环依赖阻止生成完整顺序";
            ChainInfoBar.Title = snapshot.NodeCount == 0
                ? "没有重启动依赖"
                : snapshot.HasIssues ? "依赖链存在问题" : "依赖链校验通过";
            ChainInfoBar.Message = snapshot.NodeCount == 0
                ? "正式队列中尚无包含 oldjob 的真实作业。"
                : $"循环 {snapshot.Checks.CycleCount} · 缺失 {snapshot.Checks.MissingParentCount} · 路径不兼容 {snapshot.Checks.IncompatiblePathCount}";
            ChainInfoBar.Severity = snapshot.NodeCount == 0
                ? InfoBarSeverity.Informational
                : snapshot.HasIssues ? InfoBarSeverity.Warning : InfoBarSeverity.Success;
            ChainInfoBar.IsOpen = true;
            App.Current.MainWindow.ReportPageStatus(
                snapshot.HasIssues ? "重启动依赖需要修正" : "重启动依赖校验完成");
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
            _refreshBusy = false;
            RefreshButton.IsEnabled = true;
        }
    }

    private void RenderRestartGraph()
    {
        RestartGraphCanvas.Children.Clear();
        _selectedGraphButton = null;
        if (_nodes.Count == 0)
        {
            ApplySelectedNode(null, null);
            return;
        }

        const double nodeWidth = 230;
        const double nodeHeight = 116;
        const double horizontalGap = 92;
        const double verticalGap = 28;
        var positions = new Dictionary<string, (double X, double Y)>();
        foreach (var stageGroup in _nodes.GroupBy(node => Math.Max(1, node.Stage)))
        {
            var stageNodes = stageGroup.OrderBy(node => node.JobName, StringComparer.OrdinalIgnoreCase).ToArray();
            for (var index = 0; index < stageNodes.Length; index++)
            {
                positions[stageNodes[index].JobId] = (
                    36 + (stageGroup.Key - 1) * (nodeWidth + horizontalGap),
                    36 + index * (nodeHeight + verticalGap));
            }
        }

        foreach (var node in _nodes)
        {
            if (string.IsNullOrWhiteSpace(node.ParentJobId)
                || !positions.TryGetValue(node.ParentJobId, out var parentPosition)
                || !positions.TryGetValue(node.JobId, out var childPosition))
            {
                continue;
            }
            RestartGraphCanvas.Children.Add(new Line
            {
                X1 = parentPosition.X + nodeWidth,
                Y1 = parentPosition.Y + nodeHeight / 2,
                X2 = childPosition.X,
                Y2 = childPosition.Y + nodeHeight / 2,
                Stroke = ResourceBrush("ControlStrokeColorDefaultBrush"),
                StrokeThickness = 2,
            });
        }

        foreach (var node in _nodes)
        {
            var button = CreateGraphNode(node, nodeWidth, nodeHeight);
            var position = positions[node.JobId];
            Canvas.SetLeft(button, position.X);
            Canvas.SetTop(button, position.Y);
            RestartGraphCanvas.Children.Add(button);
            if (_selectedNode is not null
                && string.Equals(_selectedNode.ItemId, node.ItemId, StringComparison.Ordinal))
            {
                ApplySelectedNode(node, button);
            }
        }

        var maxStage = _nodes.Max(node => Math.Max(1, node.Stage));
        var maxRows = _nodes.GroupBy(node => Math.Max(1, node.Stage)).Max(group => group.Count());
        RestartGraphCanvas.Width = Math.Max(860, 72 + maxStage * (nodeWidth + horizontalGap));
        RestartGraphCanvas.Height = Math.Max(520, 72 + maxRows * (nodeHeight + verticalGap));
        ApplyGraphZoom();
    }

    private void UpdateExplorer(RestartChainSnapshot snapshot)
    {
        var groups = _nodes
            .GroupBy(node => Math.Max(1, node.Stage))
            .OrderBy(group => group.Key)
            .Select(group => WorkbenchExplorerAdapterBase.Group(
                $"restart:stage:{group.Key}",
                $"阶段 {group.Key}",
                group.Select(node => new ExplorerItem
                {
                    StableId = $"restart:job:{node.JobId}",
                    Kind = ExplorerItemKind.RestartChain,
                    EntityId = node.ItemId,
                    Title = node.JobName,
                    Subtitle = node.IsRestart
                        ? $"前置：{node.ParentJobName} · {node.JobStatus}"
                        : $"基础计算 · {node.JobStatus}",
                    Path = node.OutputOdb,
                    Status = node.ValidationStatus,
                    Badge = node.ValidationStatusDisplay,
                    IconGlyph = node.IsRestart ? "\uE895" : "\uE9D5",
                }),
                group.Count().ToString()))
            .ToArray();
        _explorerAdapter.Update(
            "计算依赖与结果生成保持分离",
            $"{snapshot.ChainCount} 条链 · {_nodes.Count} 个图谱节点",
            groups);
    }

    private void SelectExplorerNode(ExplorerItem item)
    {
        var node = _nodes.FirstOrDefault(candidate => string.Equals(
            candidate.ItemId,
            item.EntityId,
            StringComparison.Ordinal));
        var button = RestartGraphCanvas.Children
            .OfType<Button>()
            .FirstOrDefault(candidate => candidate.Tag == node);
        ApplySelectedNode(node, button);
    }

    private Button CreateGraphNode(RestartChainNode node, double width, double height)
    {
        var panel = new StackPanel { Spacing = 5 };
        panel.Children.Add(new TextBlock
        {
            Text = node.JobName,
            FontWeight = Microsoft.UI.Text.FontWeights.SemiBold,
            TextTrimming = TextTrimming.CharacterEllipsis,
        });
        panel.Children.Add(new TextBlock
        {
            Text = node.IsRestart ? $"Restart · 阶段 {node.Stage}" : "基础计算",
            Foreground = ResourceBrush("TextFillColorSecondaryBrush"),
        });
        panel.Children.Add(new TextBlock
        {
            Text = string.IsNullOrWhiteSpace(node.JobStatus) ? "未运行" : node.JobStatus,
            Foreground = ResourceBrush("TextFillColorSecondaryBrush"),
        });
        panel.Children.Add(new TextBlock
        {
            Text = string.IsNullOrWhiteSpace(node.OutputOdb)
                ? Path.GetFileName(node.InpPath)
                : Path.GetFileName(node.OutputOdb),
            Foreground = ResourceBrush("TextFillColorSecondaryBrush"),
            TextTrimming = TextTrimming.CharacterEllipsis,
        });
        var button = new Button
        {
            Width = width,
            Height = height,
            Padding = new Thickness(14, 10, 14, 10),
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
            VerticalContentAlignment = VerticalAlignment.Center,
            Content = panel,
            Tag = node,
            BorderThickness = new Thickness(1),
            BorderBrush = NodeBorderBrush(node),
            Background = ResourceBrush("LayerFillColorDefaultBrush"),
        };
        button.Click += OnGraphNodeClicked;
        return button;
    }

    private void OnGraphNodeClicked(object sender, RoutedEventArgs e)
    {
        if (sender is Button { Tag: RestartChainNode node } button)
        {
            ApplySelectedNode(node, button);
        }
    }

    private void ApplySelectedNode(RestartChainNode? node, Button? button)
    {
        if (_selectedGraphButton is not null
            && _selectedGraphButton.Tag is RestartChainNode previous)
        {
            _selectedGraphButton.BorderThickness = new Thickness(1);
            _selectedGraphButton.BorderBrush = NodeBorderBrush(previous);
        }
        _selectedNode = node;
        _selectedGraphButton = button;
        if (node is null)
        {
            SelectedStageText.Text = "选择计算节点后显示作业、输入文件、预期 ODB 与重启动依赖。";
            GenerateFullResultButton.IsEnabled = false;
            EditDependencyButton.IsEnabled = false;
            LocateInQueueButton.IsEnabled = false;
            return;
        }
        if (button is not null)
        {
            button.BorderThickness = new Thickness(3);
            button.BorderBrush = ResourceBrush("AccentFillColorDefaultBrush");
        }

        GenerateFullResultButton.IsEnabled = node.IsRestart
            && string.Equals(node.ValidationStatus, "valid", StringComparison.Ordinal);
        EditDependencyButton.IsEnabled = node.IsRestart;
        LocateInQueueButton.IsEnabled = !string.IsNullOrWhiteSpace(node.ItemId);
        SelectedStageText.Text =
            $"作业：{node.JobName}\n前置作业：{node.ParentJobName}\n作业状态：{node.JobStatus}\n"
            + $"校验：{node.ValidationMessage}\n输入：{node.InpPath}\n依赖 ODB：{node.OldjobPath}\n"
            + $"阶段结果：{node.OutputOdb}";
    }

    private async void OnGenerateFullResultClicked(object sender, RoutedEventArgs e)
    {
        var node = _selectedNode;
        if (node is null || !node.IsRestart || string.IsNullOrWhiteSpace(node.ItemId))
        {
            return;
        }
        GenerateFullResultButton.IsEnabled = false;
        try
        {
            var plan = await App.Current.ControlPlane.CreateRestartResultPlanAsync(node.ItemId);
            if (!plan.Valid)
            {
                ShowError(plan.Issues.Count > 0
                    ? string.Join(Environment.NewLine, plan.Issues)
                    : "当前节点尚不能生成完整结果。");
                return;
            }
            App.Current.MainWindow.NavigateToOdbMergePlan(plan);
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
            GenerateFullResultButton.IsEnabled = node.IsRestart
                && string.Equals(node.ValidationStatus, "valid", StringComparison.Ordinal);
        }
    }

    private void OnZoomOutClicked(object sender, RoutedEventArgs e)
    {
        _graphZoom = Math.Max(0.65, _graphZoom - 0.1);
        ApplyGraphZoom();
    }

    private void OnZoomInClicked(object sender, RoutedEventArgs e)
    {
        _graphZoom = Math.Min(1.5, _graphZoom + 0.1);
        ApplyGraphZoom();
    }

    private void ApplyGraphZoom()
    {
        RestartGraphCanvas.RenderTransformOrigin = new Windows.Foundation.Point(0, 0);
        RestartGraphCanvas.RenderTransform = new ScaleTransform
        {
            ScaleX = _graphZoom,
            ScaleY = _graphZoom,
        };
    }

    private static Brush ResourceBrush(string key) =>
        (Brush)Application.Current.Resources[key];

    private static Brush NodeBorderBrush(RestartChainNode node) =>
        ResourceBrush(string.Equals(node.ValidationStatus, "valid", StringComparison.Ordinal)
            ? "ControlStrokeColorDefaultBrush"
            : "SystemFillColorCriticalBrush");

    private async void OnEditDependencyClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedNode is not RestartChainNode node
            || string.IsNullOrWhiteSpace(node.ItemId))
        {
            return;
        }

        try
        {
            var oldjobBox = new TextBox
            {
                Header = "前置作业 ODB",
                Text = node.OldjobPath,
                PlaceholderText = "输入或选择前置作业的 .odb 路径",
            };
            var chooseButton = new Button
            {
                Content = "选择 ODB…",
                HorizontalAlignment = HorizontalAlignment.Left,
            };
            chooseButton.Click += async (_, _) =>
            {
                var selectedPath = await PickOdbAsync();
                if (selectedPath is not null)
                {
                    oldjobBox.Text = selectedPath;
                }
            };
            var panel = new StackPanel { Spacing = 10, Width = 520 };
            panel.Children.Add(new TextBlock
            {
                Text = $"作业：{node.JobName}",
            });
            panel.Children.Add(oldjobBox);
            panel.Children.Add(chooseButton);
            panel.Children.Add(new TextBlock
            {
                Text = "保存前会检查循环和前置作业。前置作业尚在队列中时可填写预期 ODB 路径；留空后，含 Restart 指令的作业会等待指定前置。",
                Foreground = (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[
                    "TextFillColorSecondaryBrush"],
                TextWrapping = TextWrapping.Wrap,
            });
            var dialog = new ContentDialog
            {
                XamlRoot = XamlRoot,
                Title = "编辑重启动依赖",
                Content = panel,
                PrimaryButtonText = "保存并重新校验",
                CloseButtonText = "取消",
                DefaultButton = ContentDialogButton.Primary,
            };
            if (await dialog.ShowAsync() != ContentDialogResult.Primary)
            {
                return;
            }

            var oldjobPath = oldjobBox.Text.Trim();
            await App.Current.ControlPlane.UpdateRestartDependencyAsync(node.ItemId, oldjobPath);
            await RefreshAsync();
        }
        catch (ControlPlaneException exception)
        {
            ShowError(exception.ToDisplayMessage(), "重启动依赖未保存");
        }
        catch (Exception exception)
        {
            ShowError(exception.Message, "重启动依赖未保存");
        }
    }

    private void OnLocateInQueueClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedNode is RestartChainNode node
            && !string.IsNullOrWhiteSpace(node.ItemId))
        {
            App.Current.MainWindow.NavigateToQueueItem(node.ItemId);
        }
    }

    private static async Task<string?> PickOdbAsync()
    {
        var picker = new FileOpenPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = "设为前置作业",
        };
        picker.FileTypeFilter.Add(".odb");
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        return (await picker.PickSingleFileAsync())?.Path;
    }

    private void ShowError(string message, string title = "依赖链读取失败")
    {
        ChainInfoBar.Title = title;
        ChainInfoBar.Message = message;
        ChainInfoBar.Severity = InfoBarSeverity.Error;
        ChainInfoBar.IsOpen = true;
    }

    private static string CheckText(int count)
    {
        return count == 0 ? "通过" : $"发现 {count} 项";
    }
}
