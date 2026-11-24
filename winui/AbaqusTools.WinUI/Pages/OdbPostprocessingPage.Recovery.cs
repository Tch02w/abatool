using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private readonly OdbPostprocessRecoveryState _postprocessTracking = new();
    private bool _postprocessRecoveryBusy;
    private bool _postprocessCancelInFlight;
    private CancellationTokenSource? _postprocessMonitoringSource;

    private void BeginPostprocessMonitoring(string requestId, string kind)
    {
        _postprocessTracking.Begin(requestId, kind);
        _resultLocations.Begin(requestId, kind, RootTextBox.Text);
        _postprocessMonitoringSource = new CancellationTokenSource();
    }

    private void EndPostprocessMonitoring()
    {
        _postprocessMonitoringSource?.Dispose();
        _postprocessMonitoringSource = null;
        ReleasePostprocessMonitoring();
    }

    private void HandlePostprocessInterruption(Exception error, string title)
    {
        var detail = error is ControlPlaneException controlPlaneError ? controlPlaneError.ToDisplayMessage() : error.Message;
        if (_postprocessTracking.RequiresVerification(error))
        {
            _postprocessTracking.MarkUnconfirmed();
            MarkPostprocessRowsIncomplete("状态待确认", "通信中断或等待超时，后台操作可能仍在执行。请查询原操作状态。");
            PostprocessPhaseText.Text = "原操作状态待确认，请查询后继续";
            AppendPostprocessLog($"待核实原请求：{_postprocessTracking.ClientRequestId}；操作：{_activePostprocessOperationId ?? "尚未收到编号"}");
            ShowWarning(detail + Environment.NewLine + "已保留原请求。查询确认后台终态前，暂停提交新的后处理操作。", "操作状态待确认");
        }
        else
        {
            MarkPostprocessRowsIncomplete("请求未受理", detail);
            ShowError(detail, title);
        }
    }

    private void ReleasePostprocessMonitoring()
    {
        if (_postprocessTracking.NeedsRecovery)
        {
            SetPostprocessBusy(true);
            return;
        }
        _postprocessTracking.Reset();
        _activePostprocessOperationId = null;
        _activePostprocessKind = null;
        _activePathKeys.Clear();
        SetPostprocessBusy(_postprocessCancelInFlight);
    }

    private async void OnRecoverPostprocessClicked(object sender, RoutedEventArgs e)
    {
        if (!_postprocessTracking.NeedsRecovery || _postprocessRecoveryBusy
            || _postprocessMonitoringSource is not null || _postprocessCancelInFlight) return;
        _postprocessRecoveryBusy = true;
        PostprocessPhaseText.Text = "正在查询原操作状态…";
        RefreshInteractionState();
        try
        {
            // One bounded read per click. Never recreate or resubmit an uncertain request.
            using var timeout = new CancellationTokenSource(TimeSpan.FromSeconds(15));
            var snapshot = _activePostprocessOperationId is { } operationId
                ? await App.Current.ControlPlane.GetOdbPostprocessOperationAsync(operationId, timeout.Token)
                : _postprocessTracking.FindExisting((await App.Current.ControlPlane.ListOdbPostprocessOperationsAsync(
                    activeOnly: false, cancellationToken: timeout.Token)).Operations);
            if (snapshot is null)
            {
                PostprocessPhaseText.Text = "尚未找到原请求，状态仍待确认";
                ShowWarning("当前控制面没有返回原请求记录。后台是否执行尚未确认，已保留请求编号，可稍后再次查询。", "原操作尚未确认");
                return;
            }
            ApplyPostprocessSnapshot(snapshot, recovered: true);
            if (snapshot.IsTerminal)
                CompletePostprocessOperation(snapshot);
            else
            {
                _postprocessTracking.MarkUnconfirmed();
                PostprocessPhaseText.Text = $"原操作{PostprocessStatusDisplay(snapshot.Status)} · 可稍后再次查询";
            }
        }
        catch (Exception error)
        {
            HandlePostprocessInterruption(error, "原操作查询失败");
        }
        finally
        {
            _postprocessRecoveryBusy = false;
            ReleasePostprocessMonitoring();
        }
    }
}
