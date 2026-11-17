using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private bool _upgradeBusy;
    private bool _upgradeUncertain;
    private bool _upgradeCancelRequested;
    private string? _upgradeOperationId;
    private long _upgradeVersion = -1;
    private OdbUpgradePreview? _pendingUpgradePreview;
    private Guid _pendingUpgradeRequestId;
    private bool UpgradeBlocksEditing => _upgradeBusy || _upgradeUncertain;

    private async void OnUpgradeClicked(object sender, RoutedEventArgs e)
    {
        if (_discoveryBusy || _compatibilityBusy || _postprocessBusy || UpgradeBlocksEditing) return;
        var rows = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();
        if (rows.Length == 0 || rows.Any(row => row.CompatibilityStatus != "upgrade_required"))
        {
            ShowWarning("请先检查兼容性，并仅选择标记为“需要升级”的 ODB。", "不能开始升级");
            return;
        }
        if (!SaveWorkspace()) return;
        _upgradeBusy = true;
        RefreshInteractionState();
        try
        {
            var existing = await App.Current.ControlPlane.ListOdbUpgradeOperationsAsync(activeOnly: true);
            if (existing.Operations.Count > 0)
            {
                ShowWarning("已有升级任务正在执行，请使用“恢复／查看升级”接管原任务。", "不能重复开始升级");
                return;
            }
            var preview = await App.Current.ControlPlane.PreviewOdbUpgradeAsync(
                RootTextBox.Text.Trim(), rows.Select(row => row.Path).ToArray());
            if (!await ConfirmUpgradeAsync(preview)) return;
            _pendingUpgradePreview = preview;
            _pendingUpgradeRequestId = Guid.NewGuid();
            _upgradeUncertain = true; // Submission may succeed even if its response is lost.
            var initial = await App.Current.ControlPlane.StartOdbUpgradeAsync(preview, _pendingUpgradeRequestId);
            await MonitorUpgradeAsync(initial);
        }
        catch (Exception exception) { ReportUpgradeFailure(exception); }
        finally
        {
            _upgradeBusy = false;
            UpgradeProgress.IsIndeterminate = false;
            RefreshInteractionState();
            SaveWorkspace();
        }
    }

    private async Task<bool> ConfirmUpgradeAsync(OdbUpgradePreview preview)
    {
        var description = $"升级到 Abaqus {preview.TargetRelease}。每个旧文件先保留为下列备份，升级验证成功后新文件使用原路径。"
            + "\n此操作会替换源路径内容，不是只读检查。请关闭使用这些 ODB 的其他程序，并预留原文件、临时文件与备份所需空间。"
            + "\n停止时等待当前文件安全完成；关闭窗口不会强杀升级进程。\n\n"
            + string.Join("\n\n", preview.Entries.Select(entry =>
                $"源文件：{entry.SourcePath}\n备份：{entry.BackupPath}\n临时：{entry.TemporaryPath}\n结果：{entry.UpgradedPath}"));
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = $"确认备份并升级 {preview.Entries.Count} 个 ODB",
            PrimaryButtonText = "确认备份并升级",
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
            Content = new ScrollViewer { MaxHeight = 420, Content = new TextBlock
                { Text = description, TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true } },
        };
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    private async void OnRecoverUpgradeClicked(object sender, RoutedEventArgs e) =>
        await RecoverUpgradeAsync(showHistory: true);

    private async Task<bool> RecoverUpgradeAsync(bool showHistory)
    {
        if (_upgradeBusy || _discoveryBusy || _compatibilityBusy || _postprocessBusy) return false;
        _upgradeBusy = true;
        RefreshInteractionState();
        try
        {
            var list = await App.Current.ControlPlane.ListOdbUpgradeOperationsAsync();
            var snapshot = _upgradeOperationId is not null
                ? list.Operations.FirstOrDefault(item => item.OperationId == _upgradeOperationId)
                : _pendingUpgradePreview is not null
                    ? list.Operations.FirstOrDefault(item => item.ClientRequestId == _pendingUpgradeRequestId.ToString("D"))
                    : list.Operations.FirstOrDefault(item => item.Status is "running" or "cancelling")
                        ?? list.Operations.FirstOrDefault(item => !item.IsTerminal)
                        ?? (showHistory ? null : list.Operations.FirstOrDefault(item => item.Error?.Code == "UPGRADE_INTERRUPTED"));
            if (snapshot is null && _pendingUpgradePreview is not null && showHistory)
            {
                // Only an explicit retry reuses the original idempotency key.
                // Loading the page never submits a previously unknown operation.
                if (!await ConfirmUpgradeAsync(_pendingUpgradePreview)) return _upgradeUncertain;
                snapshot = await App.Current.ControlPlane.StartOdbUpgradeAsync(
                    _pendingUpgradePreview, _pendingUpgradeRequestId);
            }
            if (snapshot is null && _upgradeUncertain)
            {
                ShowWarning("未找到原升级任务。后台可能已重启，不能据此认定文件未被改动。请保留备份并检查文件。", "升级状态仍未确认");
                return true;
            }
            snapshot ??= showHistory ? await ChooseUpgradeHistoryAsync(list.Operations) : null;
            if (snapshot is null)
            {
                if (showHistory) UpgradeStatusText.Text = "当前后台没有升级任务记录。";
                return false;
            }
            if (_odbItems.Count == 0)
                RestoreUpgradeRows(snapshot.Preview);
            var wasActive = !snapshot.IsTerminal;
            await MonitorUpgradeAsync(snapshot);
            // A historical interruption must not hide another postprocess task.
            return showHistory || wasActive;
        }
        catch (Exception exception)
        {
            ReportUpgradeFailure(exception);
            return _upgradeUncertain;
        }
        finally
        {
            _upgradeBusy = false;
            UpgradeProgress.IsIndeterminate = false;
            RefreshInteractionState();
            SaveWorkspace();
        }
    }

    private async Task<OdbUpgradeOperationSnapshot?> ChooseUpgradeHistoryAsync(
        IReadOnlyList<OdbUpgradeOperationSnapshot> operations)
    {
        if (operations.Count == 0) return null;
        var choice = new ComboBox { HorizontalAlignment = HorizontalAlignment.Stretch, SelectedIndex = 0 };
        foreach (var item in operations)
            choice.Items.Add($"{item.Status} · {item.Preview.Entries.Count} 个文件 · {Path.GetFileName(item.Preview.Entries[0].SourcePath)} · {item.OperationId[..Math.Min(8, item.OperationId.Length)]}");
        choice.SelectedIndex = 0;
        var dialog = new ContentDialog { XamlRoot = XamlRoot, Title = "查看升级历史",
            Content = choice, PrimaryButtonText = "查看回执", CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close };
        return await dialog.ShowAsync() == ContentDialogResult.Primary ? operations[choice.SelectedIndex] : null;
    }

    private void RestoreUpgradeRows(OdbUpgradePreview preview)
    {
        RootTextBox.Text = preview.Root;
        _lastDiscoveryRoot = null; // A selected subset must not overwrite the full saved workspace.
        foreach (var entry in preview.Entries)
        {
            var row = new OdbFileRow(CreateRecoveryDiscoveryItem(preview.Root, entry.SourcePath));
            row.MarkIncomplete("需重新检查", "已恢复升级记录，请核查回执并重新读取结构。");
            _odbItems.Add(row);
            _odbByPath[PathKey(row.Path)] = row;
        }
        OdbList.SelectAll();
        EmptyState.Visibility = Visibility.Collapsed;
        ResultCountText.Text = $"{_odbItems.Count} 个";
        DiscoveryMetadataText.Text = "从升级任务恢复";
        UpdateExplorer();
    }

    private async Task MonitorUpgradeAsync(OdbUpgradeOperationSnapshot initial)
    {
        _upgradeOperationId = initial.OperationId;
        _upgradeVersion = -1;
        _upgradeUncertain = !initial.IsTerminal;
        _upgradeCancelRequested = initial.Status == "cancelling";
        ApplyUpgradeSnapshot(initial);
        var final = await App.Current.ControlPlane.PollOdbUpgradeUntilTerminalAsync(initial,
            new Progress<OdbUpgradeOperationSnapshot>(ApplyUpgradeSnapshot));
        ApplyUpgradeSnapshot(final);
        _upgradeUncertain = false;
        _pendingUpgradePreview = null;
        _upgradeOperationId = null;
        _upgradeCancelRequested = false;
        foreach (var entry in final.Preview.Entries)
        {
            var row = FindRow(entry.SourcePath);
            if (row is null) continue;
            row.MarkStructureAnalysisIncomplete("升级操作已结束，请重新检查兼容性并读取结构；编辑参数保留。");
            row.MarkIncomplete("请重新检查", "以逐文件升级回执为准，请重新检查当前 ODB。");
        }
        UpdateExplorer();
        if (final.Status == "failed") ShowError(final.Error?.Message ?? "部分文件未升级成功，请查看逐文件结果。", "升级失败");
        App.Current.MainWindow.ReportPageStatus(UpgradeStatusText.Text);
        // Other queued upgrades may still own files. Do not unlock editing merely
        // because the one currently displayed has finished.
        _upgradeUncertain = true;
        var remaining = await App.Current.ControlPlane.ListOdbUpgradeOperationsAsync(activeOnly: true);
        var next = remaining.Operations.FirstOrDefault(item => item.Status is "running" or "cancelling")
            ?? remaining.Operations.FirstOrDefault(item => !item.IsTerminal);
        if (next is not null)
            await MonitorUpgradeAsync(next);
        else
            _upgradeUncertain = false;
    }

    private void ApplyUpgradeSnapshot(OdbUpgradeOperationSnapshot snapshot)
    {
        if (snapshot.OperationId != _upgradeOperationId || snapshot.Version <= _upgradeVersion) return;
        _upgradeVersion = snapshot.Version;
        var status = snapshot.Status switch
        {
            "queued" => "等待升级", "running" => "正在检查／升级",
            "cancelling" => "等待当前文件安全完成", "succeeded" => "升级完成",
            "cancelled" => "升级已停止（已完成文件不会回滚）", _ => "升级失败",
        };
        if (snapshot.Error?.Code == "UPGRADE_INTERRUPTED") status = "升级中断，需核查文件";
        UpgradeStatusText.Text = $"{status} · 已返回 {snapshot.Progress.Completed} / {snapshot.Progress.Total} · {snapshot.Progress.CurrentFile}"
            + (snapshot.IsTerminal ? $" · 成功升级 {snapshot.Results.Count(result => result.Status == "upgraded")} 个" : "");
        UpgradeProgress.Visibility = Visibility.Visible;
        UpgradeProgress.IsIndeterminate = !snapshot.IsTerminal && snapshot.Progress.Completed == 0;
        UpgradeProgress.Maximum = snapshot.Preview.Entries.Count;
        UpgradeProgress.Value = snapshot.Progress.Completed;
        UpgradeDetailsExpander.Visibility = Visibility.Visible;
        UpgradeDetailsTextBox.Text = string.Join(Environment.NewLine, snapshot.Preview.Entries.Select(entry =>
                $"源文件：{entry.SourcePath}\n备份：{entry.BackupPath}\n临时文件：{entry.TemporaryPath}"))
            + Environment.NewLine + string.Join(Environment.NewLine, snapshot.Logs)
            + Environment.NewLine + string.Join(Environment.NewLine + Environment.NewLine, snapshot.Results.Select(result =>
                $"{result.SourcePath}\n状态：{result.Status} · {result.Message}\n备份：{result.BackupPath}\n结果：{result.UpgradedPath}"
                + (string.IsNullOrWhiteSpace(result.CacheWarning) ? "" : $"\n缓存提示：{result.CacheWarning}")))
            + (snapshot.Error is null ? "" : $"\n错误：{snapshot.Error.Message}")
            + (string.IsNullOrWhiteSpace(snapshot.PersistenceWarning) ? "" : $"\n记录保存警告：{snapshot.PersistenceWarning}");
        if (snapshot.IsTerminal) UpgradeDetailsExpander.IsExpanded = true;
        _upgradeCancelRequested = snapshot.Status == "cancelling";
        RefreshInteractionState();
    }

    private async void OnCancelUpgradeClicked(object sender, RoutedEventArgs e)
    {
        if (_upgradeOperationId is not { } operationId || _upgradeCancelRequested) return;
        _upgradeCancelRequested = true;
        RefreshInteractionState();
        try { ApplyUpgradeSnapshot(await App.Current.ControlPlane.CancelOdbUpgradeOperationAsync(operationId)); }
        catch (Exception exception)
        {
            _upgradeCancelRequested = false;
            ShowWarning(exception.Message + "\n停止状态未确认，请恢复查看原任务；不要重复提交升级。", "停止请求未确认");
        }
        finally { RefreshInteractionState(); }
    }

    private void ReportUpgradeFailure(Exception exception)
    {
        if (exception is ControlPlaneException { Code: "UPGRADE_HISTORY_UNAVAILABLE" })
            _upgradeUncertain = true;
        if (exception is ControlPlaneException { Code: "INVALID_UPGRADE_REQUEST" or "INVALID_UPGRADE_PREVIEW"
            or "UPGRADE_CONFIRMATION_REQUIRED" or "UNSUPPORTED_SCHEMA_VERSION" or "CONTROL_PLANE_SHUTTING_DOWN"
            or "UPGRADE_CAPABILITY_REQUIRED" })
        {
            _pendingUpgradePreview = null;
            _upgradeUncertain = false;
        }
        UpgradeStatusText.Text = _upgradeUncertain ? "升级状态未确认，请使用“恢复／查看升级”；不要重复创建任务。" : "升级操作未开始。";
        ShowWarning(exception.Message, "升级操作提示");
    }
}
