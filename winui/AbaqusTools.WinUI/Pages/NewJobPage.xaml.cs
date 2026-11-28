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
    private RemoteServerProfile? _displayedRemote;
    private int _lastExecutionIndex;
    // Unknown policy must not clamp a restored draft before the first resource response.
    private int _localCpuLimit = int.MaxValue;
    private int _cpuPolicyRequest;

    public NewJobPage()
    {
        InitializeComponent();
        _workspaceExplorerAdapter = new WorkspaceExplorerAdapter(
            () => PickFolderAsync("选择工作目录"),
            ActivateExplorerItemAsync);
        App.Current.Session.Register(this, "new-job",
            ["ExecutionLocationComboBox", "JobNameTextBox", "InputPathTextBox", "OldjobPathTextBox", "FortranPathTextBox",
             "UseSsdCheckBox", "CalculationRootTextBox", "ArchiveRootTextBox",
             "AbaqusCommandTextBox", "MemoryValueTextBox", "MemoryUnitComboBox", "CpuNumberBox",
             "ExecutionOptionsPanel", "PriorityComboBox", "InteractiveCheckBox", "DatacheckCheckBox", "NotifyCheckBox", "MaxParallelNumberBox"],
            () => WorkbenchSession.WaitForIdleAsync(() => _previewBusy || _submitBusy, "作业提交或检查"));
        Loaded += OnPageLoaded;
    }

    public IWorkbenchExplorerAdapter ExplorerAdapter => _workspaceExplorerAdapter;
    public bool IsDraftBusy => _previewBusy || _submitBusy;

    public JobPostprocessTarget PostprocessTarget => JobPostprocessTarget.Draft(
        InputPathTextBox.Text, JobNameTextBox.Text, IsRemote);

    public void ApplyNewJobReset()
    {
        // Change mode before paths: the mode handler clears incompatible paths.
        ExecutionLocationComboBox.SelectedIndex = 0;
        JobNameTextBox.Text = string.Empty;
        InputPathTextBox.Text = string.Empty;
        OldjobPathTextBox.Text = string.Empty;
        FortranPathTextBox.Text = string.Empty;
        CommandPreviewTextBox.Text = string.Empty;
        CommandPreviewExpander.IsExpanded = false;
        ApplyExecutionMode();
    }

    public void FocusNewJobInput()
    {
        if (IsLoaded) InputPathTextBox.Focus(FocusState.Programmatic);
        else Loaded += OnNewJobFocusLoaded;
    }

    private void OnNewJobFocusLoaded(object sender, RoutedEventArgs args)
    {
        Loaded -= OnNewJobFocusLoaded;
        InputPathTextBox.Focus(FocusState.Programmatic);
    }

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
        if (App.Current.Session.IsResettingNewJob) return;
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
        LoadRemoteSubmission();
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
            _localCpuLimit = int.MaxValue;
            if (!IsRemote)
            {
                CpuNumberBox.Maximum = int.MaxValue;
                ToolTipService.SetToolTip(CpuNumberBox, "未取得 CPU 上限，已保留填写值；请检查连接后重新进入页面。预览和提交时仍由后台校验。");
            }
        }
    }

    private async void OnChooseInputClicked(object sender, RoutedEventArgs e)
    {
        var path = await ChooseJobFileAsync([".inp"], "选择 Abaqus 输入文件", "选择服务器上的 Abaqus 输入文件");
        if (path is null)
        {
            return;
        }
        if (!string.Equals(Path.GetExtension(path), ".inp", StringComparison.OrdinalIgnoreCase))
        {
            App.Current.MainWindow.ShowFeedback("输入文件格式不符", "请选择 .inp 输入文件。", InfoBarSeverity.Warning);
            return;
        }

        ApplyInputPath(path);
    }

    private async void OnChooseOldjobClicked(object sender, RoutedEventArgs e)
    {
        var path = await ChooseJobFileAsync([".odb"], "选择重启动依赖 ODB", "选择服务器上的重启动依赖 ODB");
        if (path is not null)
        {
            OldjobPathTextBox.Text = path;
        }
    }

    private async void OnChooseFortranClicked(object sender, RoutedEventArgs e)
    {
        var path = await ChooseJobFileAsync([".for", ".f", ".f90", ".obj"],
            "选择 Fortran 用户子程序", "选择服务器上的用户子程序");
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
        if (IsDraftBusy || App.Current.Session.IsResettingNewJob)
        {
            return;
        }

        _previewBusy = true;
        PreviewButton.IsEnabled = false;
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
                App.Current.MainWindow.ShowFeedback("远端命令预览已生成", remotePreview.ProfileName, InfoBarSeverity.Success);
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
                ArchiveRootTextBox.Text, executionOptions: ExecutionOptionsPanel.ReadValue());
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
            App.Current.MainWindow.ShowFeedback(preview.Valid ? "命令预览已生成" : "草稿校验未通过",
                preview.Valid ? preview.EffectiveJobName : preview.ValidationMessage,
                preview.Valid ? InfoBarSeverity.Success : InfoBarSeverity.Warning);
        }
        catch (Exception exception)
        {
            ShowActionError("命令预览失败", exception);
        }
        finally
        {
            _previewBusy = false;
            PreviewButton.IsEnabled = true;
            if (IsLoaded) App.Current.MainWindow.ReportPageStatus("新建作业");
        }
    }

    private async void OnSubmitClicked(object sender, RoutedEventArgs e) => await SubmitAsync(false);
    private async void OnCheckRemoteSubmission(object sender, RoutedEventArgs e) => await SubmitAsync(true);

    private async Task SubmitAsync(bool checkRemote)
    {
        if (IsDraftBusy || App.Current.Session.IsResettingNewJob)
        {
            return;
        }

        _submitBusy = true;
        SubmitButton.IsEnabled = false;
        PreviewButton.IsEnabled = false;
        var status = checkRemote || (IsRemote && _pendingRemote is not null)
            ? "正在核对上次远端提交…" : IsRemote ? "正在提交远端作业…" : "正在加入本机正式队列…";
        App.Current.MainWindow.ReportPageStatus(status);
        try
        {
            if (IsRemote || checkRemote)
            {
                if (!checkRemote || _pendingRemote is not null) await SubmitOrRecoverRemoteAsync();
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
                ArchiveRootTextBox.Text, executionOptions: ExecutionOptionsPanel.ReadValue());
            App.Current.MainWindow.ShowFeedback("已加入正式队列", result.Message, InfoBarSeverity.Success);
            App.Current.MainWindow.NavigateToRoute("job-queue");
        }
        catch (Exception exception)
        {
            ShowActionError("作业提交失败", exception);
        }
        finally
        {
            _submitBusy = false;
            SubmitButton.IsEnabled = true;
            PreviewButton.IsEnabled = true;
            UpdateRemoteSubmissionControls();
            if (IsLoaded) App.Current.MainWindow.ReportPageStatus("新建作业");
        }
    }

    private static void ShowActionError(string title, Exception exception)
    {
        App.Current.MainWindow.ShowFeedback(title,
            exception is ControlPlaneException problem ? problem.ToDisplayMessage() : exception.Message,
            InfoBarSeverity.Error);
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
        if (App.Current.Session.IsResettingNewJob) return Task.CompletedTask;
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

    private RemoteJobRequest BuildRemoteJobRequest(RemoteServerProfile? target = null)
    {
        var memoryValue = MemoryValueTextBox.Text.Trim();
        var memory = string.IsNullOrWhiteSpace(memoryValue)
            ? string.Empty
            : memoryValue + ComboText(MemoryUnitComboBox, "%");
        var execution = ExecutionOptionsPanel.ReadValue();
        return new RemoteJobRequest
        {
            ExpectedProfile = target,
            ClientRequestId = Guid.NewGuid().ToString("N"),
            JobName = JobNameTextBox.Text.Trim(),
            InputMode = UsesRemoteExistingFiles ? "existing" : "upload",
            InputPath = InputPathTextBox.Text.Trim(),
            OldjobPath = OldjobPathTextBox.Text.Trim(),
            FortranPath = FortranPathTextBox.Text.Trim(),
            Cpus = NumberValue(CpuNumberBox, 0),
            GpuCount = execution.GpuCount,
            ExplicitPrecision = execution.ExplicitPrecision,
            OutputPrecision = execution.OutputPrecision,
            Memory = memory,
            Datacheck = DatacheckCheckBox.IsChecked is true,
            Notify = NotifyCheckBox.IsChecked is true,
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
        UpdateRemoteSubmissionControls();
        UpdatePathDecision();
    }

    private async Task RefreshRemoteStatusAsync()
    {
        try
        {
            var snapshot = await App.Current.ControlPlane.GetRemoteServersAsync();
            _displayedRemote = snapshot.Connection.Profile;
            RemoteServerStatusText.Text = snapshot.Connection.Status == "connected" && _displayedRemote is null
                ? "后台未提供已连接服务器的身份，请使用与工作台配套的后台后再提交。"
                : snapshot.Connection.Status == "connected"
                ? $"已连接：{snapshot.Connection.ProfileName}"
                : "尚未连接服务器，请先在计算资源中连接";
            RemoteServerStatusText.Foreground = _displayedRemote is not null
                ? (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[
                    "AbaqusSuccessBrush"]
                : (Microsoft.UI.Xaml.Media.Brush)Application.Current.Resources[
                    "TextFillColorSecondaryBrush"];
        }
        catch (Exception exception)
        {
            _displayedRemote = null;
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

    private async Task<string?> ChooseJobFileAsync(IReadOnlyList<string> extensions, string localTitle, string remoteTitle)
    {
        try
        {
            if (UsesRemoteExistingFiles)
                return (await new RemoteFileBrowserDialog(XamlRoot, RemoteSelectionMode.File, remoteTitle).ShowAsync())?.Path;
            var picker = new FileOpenPicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
                CommitButtonText = localTitle,
            };
            foreach (var extension in extensions)
                picker.FileTypeFilter.Add(extension);
            var windowHandle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
            WinRT.Interop.InitializeWithWindow.Initialize(picker, windowHandle);
            return (await picker.PickSingleFileAsync())?.Path;
        }
        catch (Exception exception)
        {
            ShowActionError("文件选择失败", exception);
            return null;
        }
    }

    private static async Task<string?> PickFolderAsync(string commitButtonText)
    {
        try
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
        catch (Exception exception)
        {
            ShowActionError("目录选择失败", exception);
            return null;
        }
    }
}
