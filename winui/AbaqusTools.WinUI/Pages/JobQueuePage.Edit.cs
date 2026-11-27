using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class JobQueuePage
{
    private void UpdateEditorButtons()
    {
        SetEnabledIfChanged(EditCandidateButton, !_busy && CandidateList.SelectedItems.Count == 1);
        SetEnabledIfChanged(CandidateDirectoriesButton, !_busy && _candidates.Any(item => item.Selected));
    }

    private async void OnEditCandidateClicked(object sender, RoutedEventArgs e) =>
        await EditSelectedItemAsync(candidate: true);

    private async Task EditSelectedItemAsync(bool candidate)
    {
        if (_busy) return;
        var rows = candidate ? CandidateList.SelectedItems.OfType<JobQueueItem>().ToArray() : SelectedFormalItems();
        if (rows.Length != 1)
        {
            ShowNotice("请选择一个作业", "请选中要编辑的一行作业。");
            return;
        }

        var item = rows[0];
        var jobName = new TextBox { Header = "作业名称", Text = item.JobName };
        var cores = new Controls.WorkbenchNumberBox
        {
            FrameAppearance = Controls.NumberBoxFrameAppearance.TextField,
            Header = "Core（0 表示未指定）", Minimum = 0, Maximum = 999, Value = item.Cores,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline,
        };
        var memory = new TextBox { Header = "内存", PlaceholderText = "例如 80%、4096MB 或 8GB", Text = item.Memory };
        var priority = new Controls.WorkbenchNumberBox
        {
            FrameAppearance = Controls.NumberBoxFrameAppearance.TextField,
            Header = "优先级", Minimum = -10000, Maximum = 10000, Value = item.Priority,
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline,
        };
        Controls.ParameterHelpButton.AddToHeader(cores, "cpu");
        Controls.ParameterHelpButton.AddToHeader(priority, "queue-priority");
        var oldjob = new TextBox { Header = "Restart 前置 ODB", Text = item.OldjobPath, PlaceholderText = "普通作业留空" };
        var fortran = new TextBox { Header = "Fortran 用户子程序", Text = item.FortranPath, PlaceholderText = "可选" };
        var execution = new Controls.ExecutionOptionsEditor();
        try
        {
            execution.SetValue(new ExecutionOptionsValues { GpuCount = item.GpuCount,
                ExplicitPrecision = item.ExplicitPrecision, OutputPrecision = item.OutputPrecision });
        }
        catch (ControlPlaneException error) { ShowNotice("作业参数无效", error.Message); return; }

        // Queue polling updates the bound item in place. Compare with the values shown
        // when the dialog opened so untouched directory settings stay untouched.
        var initialRoot = item.CalculationRootDir;
        var initialArchive = item.ArchiveDir;
        var initialCleanup = item.CleanupAfterArchive;
        var root = new TextBox { Text = initialRoot, PlaceholderText = "留空则使用原作业目录" };
        var archive = new TextBox { Text = initialArchive, PlaceholderText = "留空则关闭归档" };
        var cleanup = new CheckBox { Content = "归档成功后清理独立作业目录", IsChecked = initialCleanup };
        var directories = new StackPanel { Spacing = 8 };
        directories.Children.Add(DirectoryField("计算根目录（可用 SSD）", root));
        directories.Children.Add(DirectoryField("归档根目录", archive));
        directories.Children.Add(cleanup);
        var panel = new StackPanel { Spacing = 8 };
        panel.Children.Add(jobName);
        panel.Children.Add(cores);
        panel.Children.Add(memory);
        panel.Children.Add(priority);
        panel.Children.Add(oldjob);
        panel.Children.Add(fortran);
        panel.Children.Add(OptionsSection("计算与归档目录", directories));
        panel.Children.Add(OptionsSection("GPU 与精度（可选）", execution));
        await ShowQueueEditorAsync(candidate ? "编辑候选作业" : "编辑正式作业", panel,
            () => App.Current.ControlPlane.UpdateJobQueueItemAsync(
                item.ItemId, candidate, jobName.Text, NumberValue(cores), memory.Text, NumberValue(priority),
                oldjob.Text, fortran.Text, executionOptions: execution.ReadValue(),
                calculationRootDir: ChangedPath(root.Text, initialRoot),
                archiveDir: ChangedPath(archive.Text, initialArchive),
                cleanupAfterArchive: cleanup.IsChecked == initialCleanup ? null : cleanup.IsChecked));
    }

    private static Expander OptionsSection(string header, FrameworkElement content) => new()
    {
        Header = header, Content = content,
        HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch,
    };

    private static string? ChangedPath(string value, string original) =>
        string.Equals(value.Trim(), original.Trim(), StringComparison.OrdinalIgnoreCase) ? null : value.Trim();

    private static StackPanel DirectoryField(string label, TextBox field, bool showLabel = true)
    {
        AutomationProperties.SetName(field, label);
        var browse = new Button { Content = "浏览…" };
        AutomationProperties.SetName(browse, $"选择{label}");
        browse.Click += async (_, _) =>
        {
            if (await PickFolderAsync($"选择{label}") is { } selected) field.Text = selected;
        };
        var row = new Grid { ColumnSpacing = 6 };
        row.ColumnDefinitions.Add(new() { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        Grid.SetColumn(browse, 1);
        row.Children.Add(field);
        row.Children.Add(browse);
        var labeled = new StackPanel { Spacing = 4 };
        if (showLabel) labeled.Children.Add(new TextBlock { Text = label });
        labeled.Children.Add(row);
        return labeled;
    }

    private async void OnCandidateDirectoriesClicked(object sender, RoutedEventArgs e)
    {
        var ids = _candidates.Where(item => item.Selected).Select(item => item.ItemId).ToArray();
        if (_busy || ids.Length == 0) return;
        var panel = new StackPanel { Spacing = 10 };
        var root = AddBatchPath(panel, "计算根目录（可用 SSD）");
        var archive = AddBatchPath(panel, "归档根目录");
        var cleanup = new ComboBox { Header = "归档成功后清理独立作业目录",
            HorizontalAlignment = HorizontalAlignment.Stretch, ItemsSource = new[] { "保留各作业设置", "关闭", "开启" }, SelectedIndex = 0 };
        panel.Children.Add(cleanup);
        await ShowQueueEditorAsync($"设置 {ids.Length} 个已勾选候选的目录", panel, () =>
        {
            var workPath = root();
            var archivePath = archive();
            bool? cleanupValue = cleanup.SelectedIndex switch { 1 => false, 2 => true, _ => null };
            if (workPath is null && archivePath is null && cleanupValue is null)
                throw new InvalidOperationException("请选择要修改的目录或清理设置。");
            return App.Current.ControlPlane.SetCandidateDirectoriesAsync(ids, workPath, archivePath, cleanupValue);
        });
    }

    private static Func<string?> AddBatchPath(StackPanel panel, string label)
    {
        var mode = new ComboBox { Header = label, ItemsSource = new[] { "保留各作业设置", "设置目录", "清除目录" },
            SelectedIndex = 0, HorizontalAlignment = HorizontalAlignment.Stretch };
        var value = new TextBox { PlaceholderText = "输入或浏览已有文件夹" };
        var path = DirectoryField(label, value, showLabel: false);
        path.Visibility = Visibility.Collapsed;
        mode.SelectionChanged += (_, _) => path.Visibility = mode.SelectedIndex == 1 ? Visibility.Visible : Visibility.Collapsed;
        panel.Children.Add(mode);
        panel.Children.Add(path);
        return () => mode.SelectedIndex switch
        {
            1 when !string.IsNullOrWhiteSpace(value.Text) => value.Text.Trim(),
            1 => throw new InvalidOperationException($"请填写{label}，或选择清除目录。"),
            2 => string.Empty,
            _ => null,
        };
    }

    private async Task ShowQueueEditorAsync(string title, StackPanel panel, Func<Task<JobQueueCommandResponse>> save)
    {
        var error = new TextBlock { TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed };
        var content = new Grid { RowSpacing = 6 };
        content.RowDefinitions.Add(new() { Height = new GridLength(1, GridUnitType.Star) });
        content.RowDefinitions.Add(new() { Height = GridLength.Auto });
        content.Children.Add(Controls.ServerDialogLayout.Content(panel));
        Grid.SetRow(error, 1);
        content.Children.Add(error);
        var dialog = new ContentDialog { XamlRoot = XamlRoot, Title = title, Content = content,
            PrimaryButtonText = "保存", CloseButtonText = "取消", DefaultButton = ContentDialogButton.Primary };
        Controls.ServerDialogLayout.KeepExistingWidth(dialog);
        dialog.PrimaryButtonClick += async (_, args) =>
        {
            var deferral = args.GetDeferral();
            args.Cancel = true;
            try
            {
                if (_busy) { error.Text = "队列正在更新，请稍后保存。"; error.Visibility = Visibility.Visible; return; }
                SetBusy(true, "正在保存作业设置…");
                try
                {
                    var result = await save();
                    ApplySnapshot(result.Snapshot);
                    ShowSuccess("队列已更新", result.Message, result.Message);
                    args.Cancel = false;
                }
                finally { SetBusy(false); }
            }
            catch (Exception exception)
            {
                error.Text = exception is ControlPlaneException api ? api.ToDisplayMessage() : exception.Message;
                error.Visibility = Visibility.Visible;
                App.Current.MainWindow.ReportPageStatus("作业设置未保存");
            }
            finally { deferral.Complete(); }
        };
        await dialog.ShowAsync();
    }
}
