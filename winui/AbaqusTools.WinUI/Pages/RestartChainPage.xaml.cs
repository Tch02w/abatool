using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class RestartChainPage : Page
{
    private readonly ObservableCollection<RestartChainNode> _nodes = [];
    private bool _refreshBusy;

    public RestartChainPage()
    {
        InitializeComponent();
        ChainList.ItemsSource = _nodes;
        Loaded += OnPageLoaded;
    }

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
            var selectedItemId = (ChainList.SelectedItem as RestartChainNode)?.ItemId;
            var snapshot = await App.Current.ControlPlane.GetRestartChainsAsync();
            _nodes.Clear();
            foreach (var node in snapshot.Nodes)
            {
                _nodes.Add(node);
            }
            if (!string.IsNullOrWhiteSpace(selectedItemId))
            {
                ChainList.SelectedItem = _nodes.FirstOrDefault(node => string.Equals(
                    node.ItemId,
                    selectedItemId,
                    StringComparison.Ordinal));
            }

            EmptyChainPanel.Visibility = snapshot.NodeCount == 0
                ? Visibility.Visible
                : Visibility.Collapsed;
            ChainSummaryText.Text = $"{snapshot.ChainCount} 条链 · {snapshot.NodeCount} 个作业";
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

    private void OnChainSelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (ChainList.SelectedItem is not RestartChainNode node)
        {
            SelectedStageText.Text = "选择依赖节点后显示作业名、前置作业、输入文件、预期 ODB 与状态传播。";
            EditDependencyButton.IsEnabled = false;
            LocateInQueueButton.IsEnabled = false;
            return;
        }

        EditDependencyButton.IsEnabled = true;
        LocateInQueueButton.IsEnabled = !string.IsNullOrWhiteSpace(node.ItemId);
        SelectedStageText.Text =
            $"作业：{node.JobName}\n前置作业：{node.ParentJobName}\n作业状态：{node.JobStatus}\n"
            + $"校验：{node.ValidationMessage}\n输入：{node.InpPath}\n依赖 ODB：{node.OldjobPath}";
    }

    private async void OnEditDependencyClicked(object sender, RoutedEventArgs e)
    {
        if (ChainList.SelectedItem is not RestartChainNode node
            || string.IsNullOrWhiteSpace(node.ItemId))
        {
            return;
        }

        try
        {
            var queue = await App.Current.ControlPlane.GetJobQueuesAsync();
            var item = queue.QueueItems.FirstOrDefault(candidate => string.Equals(
                candidate.ItemId,
                node.ItemId,
                StringComparison.Ordinal));
            if (item is null)
            {
                ShowError("正式队列中的作业已不存在，请刷新依赖链。");
                return;
            }

            var oldjobBox = new TextBox
            {
                Header = "前置作业 ODB",
                Text = item.OldjobPath,
                PlaceholderText = "留空可移除 Restart 依赖",
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
                Text = $"作业：{item.JobName}",
            });
            panel.Children.Add(oldjobBox);
            panel.Children.Add(chooseButton);
            panel.Children.Add(new TextBlock
            {
                Text = "保存后会重新计算依赖关系、提交阶段和循环校验。不会移动或删除任何文件。",
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
            if (!string.IsNullOrWhiteSpace(oldjobPath)
                && (!File.Exists(oldjobPath)
                    || !string.Equals(Path.GetExtension(oldjobPath), ".odb", StringComparison.OrdinalIgnoreCase)))
            {
                ShowError("前置作业必须是当前可访问的 .odb 文件，也可以留空以移除依赖。");
                return;
            }

            await App.Current.ControlPlane.UpdateJobQueueItemAsync(
                item.ItemId,
                candidate: false,
                item.JobName,
                item.Cores,
                item.Memory,
                item.Priority,
                oldjobPath,
                item.FortranPath);
            await RefreshAsync();
            App.Current.MainWindow.ReportPageStatus($"已更新 {item.JobName} 的重启动依赖");
        }
        catch (ControlPlaneException exception)
        {
            ShowError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowError(exception.Message);
        }
    }

    private void OnLocateInQueueClicked(object sender, RoutedEventArgs e)
    {
        if (ChainList.SelectedItem is RestartChainNode node
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

    private void ShowError(string message)
    {
        ChainInfoBar.Title = "依赖链读取失败";
        ChainInfoBar.Message = message;
        ChainInfoBar.Severity = InfoBarSeverity.Error;
        ChainInfoBar.IsOpen = true;
    }

    private static string CheckText(int count)
    {
        return count == 0 ? "通过" : $"发现 {count} 项";
    }
}
