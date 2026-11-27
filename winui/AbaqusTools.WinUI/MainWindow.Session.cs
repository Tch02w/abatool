using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;

namespace AbaqusTools.WinUI;

public sealed partial class MainWindow
{
    private readonly SystemSessionEndState _sessionEnd;
    private readonly DispatcherTimer _draftTimer;
    private SystemSessionEndHook? _sessionEndHook;
    private bool _draftSaveBusy;
    private string? _sessionHookError;
    private string? _lastDraftError;

    public bool IsSystemSessionEnding => _sessionEnd.IsEnding;

    private void InitializeSessionSaving()
    {
        try
        {
            _sessionEndHook = new SystemSessionEndHook(WinRT.Interop.WindowNative.GetWindowHandle(this), _sessionEnd);
        }
        catch (Exception error)
        {
            _sessionHookError = error.Message;
            ShowDraftSaveError(_sessionHookError);
        }
        _draftTimer.Tick += OnDraftTimerTick;
        _draftTimer.Start();
    }

    private async void OnDraftTimerTick(object? sender, object args)
    {
        if (_draftSaveBusy || _shutdownStarted || _windowClosed || _sessionEnd.IsEnding) return;
        _draftSaveBusy = true;
        try
        {
            await App.Current.Session.SaveDraftAsync(CaptureWindowState());
            if (!_windowClosed && !_sessionEnd.IsEnding && _sessionHookError is null)
                _lastDraftError = null;
        }
        catch (Exception error)
        {
            if (!_windowClosed && !_sessionEnd.IsEnding) ShowDraftSaveError(error.Message);
        }
        finally { _draftSaveBusy = false; }
    }

    private void ShowDraftSaveError(string message)
    {
        if (message == _lastDraftError) return;
        _lastDraftError = message;
        ShowFeedback("工作台草稿未能保存", message + " 当前输入仍保留在窗口中，请处理后再关闭。",
            Microsoft.UI.Xaml.Controls.InfoBarSeverity.Error);
    }

    private Task SaveForSystemSessionEnd()
    {
        App.Current.Commands.SetLocked(true);
        _shutdownStarted = true;
        _draftTimer.Stop();
        _resourceTimer.Stop();
        // Capture only the UI allowlist. Never wait for HTTP or ask to stop a solver here.
        return App.Current.Session.SaveDraftAsync(CaptureWindowState());
    }

    private void DisposeSessionSaving()
    {
        _draftTimer.Stop();
        _draftTimer.Tick -= OnDraftTimerTick;
        _sessionEndHook?.Dispose();
    }
}
