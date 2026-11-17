using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Storage.Pickers;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class NewJobPage : Page, IWorkbenchExplorerPage
{
    private readonly WorkspaceExplorerAdapter _workspaceExplorerAdapter;
    private bool _previewBusy;
    private bool _submitBusy;
    private int _lastExecutionIndex;
    private int _localCpuLimit = 1;
    private int _cpuPolicyRequest;

    public NewJobPage()
    {
        InitializeComponent();
        _workspaceExplorerAdapter = new WorkspaceExplorerAdapter(
            () => PickFolderAsync("选择工作目录"),
            ActivateExplorerItemAsync);
        App.Current.Session.Register(this, "new-job",
            ["JobNameTextBox", "InputPathTextBox", "OldjobPathTextBox", "FortranPathTextBox",
             "ExecutionLocationComboBox", "UseSsdCheckBox", "CalculationRootTextBox", "ArchiveRootTextBox",
             "AbaqusCommandTextBox", "MemoryValueTextBox", "MemoryUnitComboBox", "CpuNumberBox",
             "PriorityComboBox", "InteractiveCheckBox", "DatacheckCheckBox", "NotifyCheckBox", "MaxParallelNumberBox"],
            () => WorkbenchSession.WaitForIdleAsync(() => _previewBusy || _submitBusy, "作业提交或检查"));
        Loaded += OnPageLoaded;
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _workspaceExplorerAdapter;

    private bool IsRemote => ExecutionLocationComboBox.SelectedIndex is 1 or 2;

    private bool UsesRemoteExistingFiles => ExecutionLocationComboBox.SelectedIndex == 2;

    private void OnResourceGridSizeChanged(object sender, SizeChangedEventArgs args)
    {
        if (ResourceSecondaryFields is null) return;
        // Two equal field columns at normal widths; stack before labels squeeze the inputs.
        var stacked = args.NewSize.Width < 720;
        ResourceSecondColumn.Width = stacked ? new GridLength(0) : new GridLength(1, GridUnitType.Star);
        ResourceGrid.ColumnSpacing = stacked ? 0 : 28;
        ResourceGrid.RowSpacing = stacked ? 12 : 0;
        Grid.SetColumn(ResourceSecondaryFields, stacked ? 0 : 1);
        Grid.SetRow(ResourceSecondaryFields, stacked ? 1 : 0);
    }

    public void LoadInputPath(string path)
    {
        if (!string.Equals(Path.GetExtension(path), ".inp", StringComparison.OrdinalIgnoreCase))
        {
            return;
        }

        if (UsesRemoteExistingFiles && Path.IsPathFullyQualified(path))
        {
            ExecutionLocationComboBox.SelectedIndex = 0;
        }
        ApplyInputPath(path);
    }

    private async void OnPageLoaded(object sender, RoutedEventArgs e)
    {
        await RefreshCpuLimitAsync();
        await RefreshRemoteStatusAsync();
        ApplyExecutionMode();
    }

    private async void OnAbaqusCommandLostFocus(object sender, RoutedEventArgs e)
        => await RefreshCpuLimitAsync();

    private async Task RefreshCpuLimitAsync()
    {
        var request = ++_cpuPolicyRequest;
        try
        {
            var resource = await App.Current.ControlPlane.GetLocalResourceAsync(
                abaqusCommand: AbaqusCommandTextBox.Text.Trim());
            if (request != _cpuPolicyRequest) return;
            _localCpuLimit = Math.Max(1, resource.JobCpuLimit);
            if (!IsRemote)
            {
                CpuNumberBox.Maximum = _localCpuLimit;
                ToolTipService.SetToolTip(CpuNumberBox,
                    $"CPU 上限：{_localCpuLimit}；{resource.JobCpuPolicyNote}。0 表示使用 Abaqus 默认值。");
            }
        }
        catch (Exception)
        {
            if (request != _cpuPolicyRequest) return;
            _localCpuLimit = 1;
            if (!IsRemote)
            {
                CpuNumberBox.Maximum = 1;
                ToolTipService.SetToolTip(CpuNumberBox, "未取得 CPU 上限，暂按 1；请检查控制面连接或重新进入页面。");
            }
        }
    }

    private async void OnChooseInputClicked(object sender, RoutedEventArgs e)
    {
        var path = UsesRemoteExistingFiles
            ? (await new RemoteFileBrowserDialog(
                XamlRoot,
                RemoteSelectionMode.File,
                "选择服务器上的 Abaqus 输入文件").ShowAsync())?.Path
            : await PickFileAsync([".inp"], "选择 Abaqus 输入文件");
        if (path is null)
        {
            return;
        }
        if (!string.Equals(Path.GetExtension(path), ".inp", StringComparison.OrdinalIgnoreCase))
        {
            ShowPreviewError("请选择 .inp 输入文件。");
            return;
        }

        ApplyInputPath(path);
    }

    private async void OnChooseOldjobClicked(object sender, RoutedEventArgs e)
    {
        var path = UsesRemoteExistingFiles
            ? (await new RemoteFileBrowserDialog(
                XamlRoot,
                RemoteSelectionMode.File,
                "选择服务器上的重启动依赖 ODB").ShowAsync())?.Path
            : await PickFileAsync([".odb"], "选择重启动依赖 ODB");
        if (path is not null)
        {
            OldjobPathTextBox.Text = path;
        }
    }

    private async void OnChooseFortranClicked(object sender, RoutedEventArgs e)
    {
        var path = UsesRemoteExistingFiles
            ? (await new RemoteFileBrowserDialog(
                XamlRoot,
                RemoteSelectionMode.File,
                "选择服务器上的用户子程序").ShowAsync())?.Path
            : await PickFileAsync(
                [".for", ".f", ".f90", ".obj"],
                "选择 Fortran 用户子程序");
        if (path is not null)
        {
            FortranPathTextBox.Text = path;
        }
    }

    private void OnUseSsdChanged(object sender, RoutedEventArgs e)
    {
        var enabled = UseSsdCheckBox.IsChecked is true;
        CalculationRootTextBox.IsEnabled = enabled;
        ArchiveRootTextBox.IsEnabled = enabled;
        ChooseCalculationRootButton.IsEnabled = enabled;
        ChooseArchiveRootButton.IsEnabled = enabled;
        UpdatePathDecision();
    }

    private async void OnExecutionLocationChanged(
        object sender,
        SelectionChangedEventArgs e)
    {
        if (RemoteServerStatusText is null)
        {
            return;
        }
        var current = ExecutionLocationComboBox.SelectedIndex;
        if ((_lastExecutionIndex == 2) != (current == 2))
        {
            InputPathTextBox.Text = string.Empty;
            OldjobPathTextBox.Text = string.Empty;
            FortranPathTextBox.Text = string.Empty;
            App.Current.MainWindow.UpdateSelectedInputPath(string.Empty);
        }
        _lastExecutionIndex = current;
        ApplyExecutionMode();
        if (IsRemote)
        {
            await RefreshRemoteStatusAsync();
        }
    }

    private void OnOpenResourcesClicked(object sender, RoutedEventArgs e)
    {
        App.Current.MainWindow.NavigateToRoute("compute-resources");
    }

    private async void OnChooseCalculationRootClicked(object sender, RoutedEventArgs e)
    {
        var path = await PickFolderAsync("选择 SSD 工作目录");
        if (path is not null)
        {
            CalculationRootTextBox.Text = path;
            UpdatePathDecision();
        }
    }

    private async void OnChooseArchiveRootClicked(object sender, RoutedEventArgs e)
    {
        var path = await PickFolderAsync("选择结果归档目录");
        if (path is not null)
        {
            ArchiveRootTextBox.Text = path;
            UpdatePathDecision();
        }
    }

    private async void OnPreviewClicked(object sender, RoutedEventArgs e)
    {
        if (_previewBusy)
        {
            return;
        }

        _previewBusy = true;
        PreviewButton.IsEnabled = false;
        DraftInfoBar.IsOpen = false;
        App.Current.MainWindow.ReportPageStatus("正在校验作业草稿…");
        try
        {
            if (IsRemote)
            {
                var remotePreview = await App.Current.ControlPlane.PreviewRemoteJobAsync(
                    BuildRemoteJobRequest());
                PathDecisionText.Text =
                    $"服务器：{remotePreview.ProfileName}　计算根目录：{remotePreview.ComputeRoot}";
                CommandPreviewTextBox.Text = remotePreview.Command;
                CommandPreviewExpander.IsExpanded = true;
                DraftInfoBar.Title = "远端命令预览已生成";
                DraftInfoBar.Message = remotePreview.Command;
                DraftInfoBar.Severity = InfoBarSeverity.Success;
                DraftInfoBar.IsOpen = true;
                App.Current.MainWindow.ReportPageStatus("远端作业草稿校验通过");
                return;
            }
            var preview = await App.Current.ControlPlane.PreviewLocalJobDraftAsync(
                InputPathTextBox.Text,
                JobNameTextBox.Text,
                NumberValue(CpuNumberBox, 0),
                MemoryValueTextBox.Text,
                ComboText(MemoryUnitComboBox, "%"),
                OldjobPathTextBox.Text,
                FortranPathTextBox.Text,
                InteractiveCheckBox.IsChecked is true,
                DatacheckCheckBox.IsChecked is true,
                NotifyCheckBox.IsChecked is true,
                AbaqusCommandTextBox.Text,
                PriorityComboBox.SelectedIndex switch { 1 => 10, 2 => -10, _ => 0 },
                NumberValue(MaxParallelNumberBox, 1),
                UseSsdCheckBox.IsChecked is true,
                CalculationRootTextBox.Text,
                ArchiveRootTextBox.Text);
            if (!string.IsNullOrWhiteSpace(preview.EffectiveJobName)
                && string.IsNullOrWhiteSpace(JobNameTextBox.Text))
            {
                JobNameTextBox.Text = preview.EffectiveJobName;
            }

            PathDecisionText.Text = preview.Valid
                ? $"工作目录：{preview.WorkDirectory}　完成归档路径：{preview.ArchivePath}"
                : preview.ValidationMessage;
            CommandPreviewTextBox.Text = preview.Valid
                ? preview.Command
                : "草稿未通过校验，未生成命令。";
            CommandPreviewExpander.IsExpanded = true;
            DraftInfoBar.Title = preview.Valid ? "命令预览已生成" : "草稿校验未通过";
            DraftInfoBar.Message = preview.Valid ? preview.Command : preview.ValidationMessage;
            DraftInfoBar.Severity = preview.Valid
                ? InfoBarSeverity.Success
                : InfoBarSeverity.Warning;
            DraftInfoBar.IsOpen = true;
            App.Current.MainWindow.ReportPageStatus(
                preview.Valid ? "作业草稿校验通过" : "作业草稿需要修正");
        }
        catch (ControlPlaneException exception)
        {
            ShowPreviewError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowPreviewError(exception.Message);
        }
        finally
        {
            _previewBusy = false;
            PreviewButton.IsEnabled = true;
        }
    }

    private async void OnSubmitClicked(object sender, RoutedEventArgs e)
    {
        if (_submitBusy)
        {
            return;
        }

        _submitBusy = true;
        SubmitButton.IsEnabled = false;
        PreviewButton.IsEnabled = false;
        DraftInfoBar.IsOpen = false;
        App.Current.MainWindow.ReportPageStatus("正在加入本机正式队列…");
        try
        {
            if (IsRemote)
            {
                App.Current.MainWindow.ReportPageStatus("正在提交远端作业…");
                var operation = await App.Current.ControlPlane.StartRemoteJobAsync(
                    BuildRemoteJobRequest());
                DraftInfoBar.Title = "远端作业已提交";
                DraftInfoBar.Message = $"{operation.Request.JobName} · {operation.Phase}";
                DraftInfoBar.Severity = InfoBarSeverity.Success;
                DraftInfoBar.IsOpen = true;
                App.Current.MainWindow.ReportPageStatus(
                    $"远端作业已提交 · {operation.Request.JobName}");
                App.Current.MainWindow.NavigateToRoute("job-overview");
                return;
            }
            var result = await App.Current.ControlPlane.EnqueueLocalJobDraftAsync(
                InputPathTextBox.Text,
                JobNameTextBox.Text,
                NumberValue(CpuNumberBox, 0),
                MemoryValueTextBox.Text,
                ComboText(MemoryUnitComboBox, "%"),
                OldjobPathTextBox.Text,
                FortranPathTextBox.Text,
                InteractiveCheckBox.IsChecked is true,
                DatacheckCheckBox.IsChecked is true,
                NotifyCheckBox.IsChecked is true,
                AbaqusCommandTextBox.Text,
                PriorityComboBox.SelectedIndex switch { 1 => 10, 2 => -10, _ => 0 },
                NumberValue(MaxParallelNumberBox, 1),
                UseSsdCheckBox.IsChecked is true,
                CalculationRootTextBox.Text,
                ArchiveRootTextBox.Text);
            DraftInfoBar.Title = "已加入正式队列";
            DraftInfoBar.Message = result.Message;
            DraftInfoBar.Severity = InfoBarSeverity.Success;
            DraftInfoBar.IsOpen = true;
            App.Current.MainWindow.ReportPageStatus(result.Message);
            App.Current.MainWindow.NavigateToRoute("job-queue");
        }
        catch (ControlPlaneException exception)
        {
            ShowPreviewError(exception.ToDisplayMessage());
        }
        catch (Exception exception)
        {
            ShowPreviewError(exception.Message);
        }
        finally
        {
            _submitBusy = false;
            SubmitButton.IsEnabled = true;
            PreviewButton.IsEnabled = true;
        }
    }

    private void ShowPreviewError(string message)
    {
        DraftInfoBar.Title = "命令预览失败";
        DraftInfoBar.Message = message;
        DraftInfoBar.Severity = InfoBarSeverity.Error;
        DraftInfoBar.IsOpen = true;
        App.Current.MainWindow.ReportPageStatus("命令预览失败");
    }

    private void ApplyInputPath(string path)
    {
        var previous = InputPathTextBox.Text.Trim();
        var previousName = string.IsNullOrWhiteSpace(previous)
            ? string.Empty
            : Path.GetFileNameWithoutExtension(previous);
        InputPathTextBox.Text = path;
        if (string.IsNullOrWhiteSpace(JobNameTextBox.Text)
            || string.Equals(JobNameTextBox.Text.Trim(), previousName, StringComparison.Ordinal))
        {
            JobNameTextBox.Text = Path.GetFileNameWithoutExtension(path);
        }

        App.Current.MainWindow.UpdateSelectedInputPath(path);
        _workspaceExplorerAdapter.UsePath(path);
        UpdatePathDecision();
    }

    private Task ActivateExplorerItemAsync(ExplorerItem item)
    {
        if (item.Kind == ExplorerItemKind.InputFile)
        {
            LoadInputPath(item.Path);
        }
        else if (item.Kind == ExplorerItemKind.OdbFile)
        {
            OldjobPathTextBox.Text = item.Path;
        }
        else if (item.Kind == ExplorerItemKind.UserSubroutine)
        {
            FortranPathTextBox.Text = item.Path;
        }
        return Task.CompletedTask;
    }

    private void UpdatePathDecision()
    {
        var input = InputPathTextBox.Text.Trim();
        if (string.IsNullOrWhiteSpace(input))
        {
            PathDecisionText.Text = "尚未选择 INP，无法判定工作目录与完成归档路径。";
            return;
        }

        if (IsRemote)
        {
            PathDecisionText.Text = UsesRemoteExistingFiles
                ? $"服务器现有输入：{input}；将复制到已验证的计算根目录后执行。"
                : $"本机输入：{input}；提交后上传到已验证的服务器计算根目录。";
            return;
        }

        var jobName = JobNameTextBox.Text.Trim();
        var workDirectory = UseSsdCheckBox.IsChecked is true
            && !string.IsNullOrWhiteSpace(CalculationRootTextBox.Text)
            && !string.IsNullOrWhiteSpace(jobName)
                ? Path.Combine(CalculationRootTextBox.Text.Trim(), jobName)
                : Path.GetDirectoryName(input) ?? string.Empty;
        PathDecisionText.Text = $"预期工作目录：{workDirectory}";
    }

    private RemoteJobRequest BuildRemoteJobRequest()
    {
        var memoryValue = MemoryValueTextBox.Text.Trim();
        var memory = string.IsNullOrWhiteSpace(memoryValue)
            ? string.Empty
            : memoryValue + ComboText(MemoryUnitComboBox, "%");
        return new RemoteJobRequest
        {
            ClientRequestId = Guid.NewGuid().ToString("N"),
            JobName = JobNameTextBox.Text.Trim(),
            InputMode = UsesRemoteExistingFiles ? "existing" : "upload",
            InputPath = InputPathTextBox.Text.Trim(),
            OldjobPath = OldjobPathTextBox.Text.Trim(),
            FortranPath = FortranPathTextBox.Text.Trim(),
            Cpus = NumberValue(CpuNumberBox, 0),
            Memory = memory,
            Datacheck = DatacheckCheckBox.IsChecked is true,
        };
    }

    private void ApplyExecutionMode()
    {
        var remote = IsRemote;
        // Remote submissions are validated against the server, not this PC.
        CpuNumberBox.Maximum = remote ? int.MaxValue : _localCpuLimit;
        var existing = UsesRemoteExistingFiles;
        InputPathTextBox.PlaceholderText = existing
            ? "选择服务器允许目录中的 INP 文件"
            : "选择本机 INP 文件";
        ChooseInputButton.Content = existing ? "浏览服务器…" : "选择 INP…";
        ChooseOldjobButton.Content = existing ? "浏览服务器…" : "选择 ODB…";
        ChooseFortranButton.Content = existing ? "浏览服务器…" : "选择 FOR…";
        UseSsdCheckBox.IsEnabled = !remote;
        CalculationRootTextBox.IsEnabled = !remote && UseSsdCheckBox.IsChecked is true;
        ArchiveRootTextBox.IsEnabled = !remote && UseSsdCheckBox.IsChecked is true;
        ChooseCalculationRootButton.IsEnabled = !remote && UseSsdCheckBox.IsChecked is true;
        ChooseArchiveRootButton.IsEnabled = !remote && UseSsdCheckBox.IsChecked is true;
        AbaqusCommandTextBox.IsEnabled = !remote;
        PriorityComboBox.IsEnabled = !remote;
        MaxParallelNumberBox.IsEnabled = !remote;
        InteractiveCheckBox.IsEnabled = !remote;
        SubmitButton.Content = remote ? "提交远端作业" : "提交作业（加入队列）";
        UpdatePathDecision();
    }

    private async Task RefreshRemoteStatusAsync()
    {
        try
        {
            var snapshot = await App.Current.ControlPlane.GetRemoteServersAsync();
            RemoteServerStatusText.Text = snapshot.Connection.Status == "connected"
                ? $"已连接：{snapshot.Connection.ProfileName}"
                : "尚未连接服务器，请先在计算资源中连接";
            RemoteServerStatusText.Foreground = snapshot.Connection.Status == "connected"
                ? (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[
                    "AbaqusSuccessBrush"]
                : (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[
                    "TextFillColorSecondaryBrush"];
        }
        catch (Exception exception)
        {
            RemoteServerStatusText.Text = "服务器状态读取失败：" + exception.Message;
        }
    }

    private static int NumberValue(NumberBox numberBox, int fallback)
    {
        return double.IsNaN(numberBox.Value)
            ? fallback
            : Convert.ToInt32(numberBox.Value);
    }

    private static string ComboText(ComboBox comboBox, string fallback)
    {
        return (comboBox.SelectedItem as ComboBoxItem)?.Content?.ToString() ?? fallback;
    }

    private static async Task<string?> PickFileAsync(
        IReadOnlyList<string> extensions,
        string commitButtonText)
    {
        var picker = new FileOpenPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = commitButtonText,
        };
        foreach (var extension in extensions)
        {
            picker.FileTypeFilter.Add(extension);
        }

        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        return (await picker.PickSingleFileAsync())?.Path;
    }

    private static async Task<string?> PickFolderAsync(string commitButtonText)
    {
        var picker = new FolderPicker
        {
            SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
            CommitButtonText = commitButtonText,
        };
        picker.FileTypeFilter.Add("*");
        var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
        return (await picker.PickSingleFolderAsync())?.Path;
    }
}
