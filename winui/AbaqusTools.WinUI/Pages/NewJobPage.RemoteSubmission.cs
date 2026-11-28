using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class NewJobPage
{
    private readonly RecoveryDraftFile<RemoteJobRequest> _remoteCheckpoint = new(
        Path.Combine(WorkbenchProfile.Current.StateDirectory, "pending-remote-job.json"), request =>
        {
            if (!Guid.TryParseExact(request.ClientRequestId, "N", out _) || request.ExpectedProfile is not { } profile
                || string.IsNullOrWhiteSpace(profile.HostFingerprint) || string.IsNullOrWhiteSpace(profile.ComputeRoot))
                throw new InvalidDataException("远端提交记录缺少请求编号或服务器身份。");
        });
    private RemoteJobRequest? _pendingRemote;
    private string? _checkpointError;

    private void LoadRemoteSubmission()
    {
        if (_submitBusy) return;
        try
        {
            _pendingRemote = _remoteCheckpoint.Load();
            _checkpointError = null;
        }
        catch (Exception error) { _checkpointError = "上次远端提交记录无法读取，请检查 " + _remoteCheckpoint.FilePath + "。" + error.Message; }
        UpdateRemoteSubmissionControls();
    }

    private void UpdateRemoteSubmissionControls()
    {
        PendingRemotePanel.Visibility = _pendingRemote is not null || _checkpointError is not null
            ? Visibility.Visible : Visibility.Collapsed;
        PendingRemoteText.Text = _checkpointError ?? (_pendingRemote is null ? string.Empty :
            $"待核对远端提交 · {_pendingRemote.JobName} · {_pendingRemote.ExpectedProfile?.ProfileName}");
        CheckPendingRemoteButton.Visibility = !IsRemote && _pendingRemote is not null ? Visibility.Visible : Visibility.Collapsed;
        CheckPendingRemoteButton.IsEnabled = !_submitBusy;
        SubmitButton.IsEnabled = !_submitBusy && (!IsRemote || _checkpointError is null);
        SubmitButton.Content = !IsRemote ? "提交作业（加入队列）" : _pendingRemote is null ? "提交远端作业" : "核对上次远端提交";
    }

    private async Task SubmitOrRecoverRemoteAsync()
    {
        if (_checkpointError is not null) throw new IOException(_checkpointError);
        var host = App.Current.ControlPlane;
        var request = _pendingRemote;
        var first = request is null;
        var withdraw = false;
        RemoteJobOperationSnapshot? operation = null;
        if (request is null)
        {
            if (_displayedRemote is null) throw new InvalidOperationException(RemoteServerStatusText.Text);
            request = BuildRemoteJobRequest(_displayedRemote);
            // Wait for durable storage before the first POST. Saving can itself fail.
            try { await _remoteCheckpoint.SaveAsync(request); }
            catch (Exception error) { throw new IOException("远端提交记录未能保存，本次未发送作业。" + error.Message, error); }
            _pendingRemote = request;
        }
        try
        {
            if (!first)
            {
                operation = await host.FindRemoteSubmissionAsync(request);
                if (operation is null)
                {
                    if (!IsLoaded) return;
                    var dialog = new ContentDialog
                    {
                        XamlRoot = XamlRoot, Title = "尚未查到上次提交",
                        Content = $"{request.ExpectedProfile!.ProfileName} · {request.JobName}\n{request.InputPath}\n"
                            + "重试会使用上次保存的服务器和参数。放弃只对未登记的请求生效；若后台已受理，将显示已有作业。",
                        PrimaryButtonText = "按原参数重试", SecondaryButtonText = "放弃未登记请求", CloseButtonText = "返回",
                        DefaultButton = ContentDialogButton.Close,
                    };
                    var choice = await dialog.ShowAsync();
                    if (choice == ContentDialogResult.None) return;
                    withdraw = choice == ContentDialogResult.Secondary;
                }
            }
            operation ??= await host.StartRemoteJobAsync(request, withdrawUnregistered: withdraw);
        }
        catch (ControlPlaneException error) when (error.StatusCode is 400 or 401 or 403 or 404 or 409
            && error.Code is not null and not "IDEMPOTENCY_CONFLICT"
            && (first || error.Code is "MISSING_REMOTE_JOB_FIELD" or "INVALID_REMOTE_JOB_FIELD" or "INVALID_REMOTE_JOB_NAME" or "INVALID_REMOTE_JOB_MEMORY"
                or "INVALID_REMOTE_JOB_CPUS" or "INVALID_EXECUTION_OPTIONS" or "MISSING_FIELDS"))
        {
            await ClearRemoteSubmissionAsync();
            throw;
        }
        catch (Exception error)
        {
            App.Current.MainWindow.ShowFeedback("远端提交待核对", $"{request.JobName} · {error.Message}\n请点击“核对上次远端提交”。", InfoBarSeverity.Warning);
            return;
        }
        try { await ClearRemoteSubmissionAsync(); }
        catch (Exception error)
        {
            App.Current.MainWindow.ShowFeedback("远端回执已确认，本机记录未清除",
                $"{operation.Request.JobName} · {operation.Phase}\n请修复本机写入后再次核对。{error.Message}", InfoBarSeverity.Warning);
            return;
        }
        var title = operation.Status switch
        {
            _ when operation.TrackingState == "withdrawn" => "已放弃未登记请求",
            "failed" => "远端作业失败", "cancelled" => "远端作业已取消", "succeeded" => "远端作业已完成", _ => "远端作业已提交",
        };
        App.Current.MainWindow.ShowFeedback(title, $"{operation.Request.JobName} · {operation.Error?.Message ?? operation.Phase}",
            operation.Status == "failed" ? InfoBarSeverity.Error : operation.Status == "cancelled" ? InfoBarSeverity.Informational : InfoBarSeverity.Success);
        if (IsLoaded && operation.TrackingState != "withdrawn") App.Current.MainWindow.NavigateToRoute("job-overview");
    }

    private async Task ClearRemoteSubmissionAsync()
    {
        await _remoteCheckpoint.SaveAsync(null);
        _pendingRemote = null;
    }
}
