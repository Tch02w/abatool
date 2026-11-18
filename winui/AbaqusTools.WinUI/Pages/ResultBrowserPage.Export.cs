using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Windows.Storage.Pickers;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class ResultBrowserPage
{
    private bool _exportBusy;
    private CancellationTokenSource? _exportCancellation;
    private bool FileOperationBusy => _recycleBusy || _exportBusy;

    private async void OnExportClicked(object sender, RoutedEventArgs e)
    {
        if (FileOperationBusy || _scopeBusy || _recordsBusy || _indexBusy || App.Current.Session.IsClosing
            || !App.Current.PendingResultFileOperation.IsCompleted) return;
        var records = SelectedRecords().Where(record => !record.Internal && !record.IsDirectory)
            .Select(record => new ResultExportFile(record.Path, record.RelativePath)).ToArray();
        if (records.Length == 0) return;
        var root = RootTextBox.Text;
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        App.Current.PendingResultFileOperation = completion.Task; // Includes the destination picker.
        _exportBusy = true;
        RefreshInteractionState();
        try
        {
            var picker = new FolderPicker { SuggestedStartLocation = PickerLocationId.DocumentsLibrary, CommitButtonText = "导出到此目录" };
            picker.FileTypeFilter.Add("*");
            WinRT.Interop.InitializeWithWindow.Initialize(picker,
                WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow));
            var destination = await picker.PickSingleFolderAsync();
            if (destination is null || App.Current.Session.IsClosing) return;
            ErrorInfoBar.IsOpen = WarningInfoBar.IsOpen = false;
            ExportDetailsExpander.Visibility = Visibility.Collapsed;
            using var cancellation = new CancellationTokenSource();
            _exportCancellation = cancellation;
            ExportProgressBar.Visibility = Visibility.Visible;
            CancelExportButton.Visibility = Visibility.Visible;
            CancelExportButton.IsEnabled = true;
            var progress = new Progress<ResultExportProgress>(value =>
            {
                if (!ReferenceEquals(_exportCancellation, cancellation)) return;
                ExportProgressBar.Value = value.Length > 0 ? 100.0 * value.Bytes / value.Length : 0;
                ResultStatusText.Text = $"已导出 {value.Completed}/{value.Total} · {value.Name}";
            });
            var outcome = await ResultFileExport.CopyAsync(root, destination.Path, records, progress, cancellation.Token);
            _exportCancellation = null; // Ignore progress callbacks already queued on the UI thread.
            var summary = outcome.Succeeded ? $"导出完成 · {outcome.Completed.Count} 个文件"
                : $"导出{(outcome.Cancelled ? "已取消" : "未完成")} · 已完成 {outcome.Completed.Count}/{records.Length}";
            ResultStatusText.Text = summary;
            App.Current.MainWindow.ReportPageStatus(summary);
            var detail = $"目标：{destination.Path}\n\n已完成：\n"
                + string.Join("\n", outcome.Completed.Select(file => file.Destination))
                + "\n\n未完成：\n" + string.Join("\n", outcome.Remaining.Select(file => file.Path))
                + (outcome.Error is null ? "" : "\n\n" + outcome.Error)
                + (outcome.RetainedPartial is null ? "" : "\n未完成临时副本：" + outcome.RetainedPartial);
            ExportDetailsText.Text = detail;
            ExportDetailsExpander.Visibility = Visibility.Visible;
            ExportDetailsExpander.IsExpanded = !outcome.Succeeded;
            if (!outcome.Succeeded) ShowWarning("已完成的文件保留；未完成文件未发布。详细路径见导出记录。", summary);
        }
        catch (Exception error) { ShowError(error.Message, "结果导出未完成"); }
        finally
        {
            _exportCancellation = null;
            _exportBusy = false;
            ExportProgressBar.Visibility = CancelExportButton.Visibility = Visibility.Collapsed;
            completion.TrySetResult();
            if (ReferenceEquals(App.Current.PendingResultFileOperation, completion.Task))
                App.Current.PendingResultFileOperation = Task.CompletedTask;
            RefreshInteractionState();
        }
    }

    private void OnCancelExportClicked(object sender, RoutedEventArgs e)
    {
        _exportCancellation?.Cancel();
        CancelExportButton.IsEnabled = false;
        ResultStatusText.Text = "正在取消导出，保留已完成文件…";
    }
}
