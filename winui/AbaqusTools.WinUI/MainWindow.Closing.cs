using AbaqusTools.WinUI.Services;
using Microsoft.UI.Windowing;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Windows.Graphics;

namespace AbaqusTools.WinUI;

public sealed partial class MainWindow
{
    private WorkbenchWindowState? _restoredWindowBounds;
    private Task? _closeAttempt;

    private Task RequestCloseAsync()
    {
        if (_closeAttempt is { IsCompleted: false }) return _closeAttempt;
        _closeAttempt = CloseWorkbenchAsync();
        return _closeAttempt;
    }

    private void SetCloseInteractionEnabled(bool enabled)
    {
        WindowMenuBar.IsEnabled = enabled;
        ShellNavigation.IsEnabled = enabled;
    }

    private void RestoreWindowState()
    {
        var saved = App.Current.Session.State.Window;
        var area = DisplayArea.GetFromWindowId(AppWindow.Id, DisplayAreaFallback.Nearest)?.WorkArea;
        if (area is { } bounds)
        {
            var width = Math.Clamp(saved.Width, 1, bounds.Width);
            var height = Math.Clamp(saved.Height, 1, bounds.Height);
            AppWindow.MoveAndResize(new RectInt32(Math.Clamp(saved.X, bounds.X, bounds.X + bounds.Width - width),
                Math.Clamp(saved.Y, bounds.Y, bounds.Y + bounds.Height - height), width, height));
            UpdateWindowSizeLimits();
        }
        RememberRestoredWindowBounds();
        if (saved.Maximized && AppWindow.Presenter is OverlappedPresenter presenter) presenter.Maximize();
    }

    private void RememberRestoredWindowBounds()
    {
        if (AppWindow.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Restored }
            && AppWindow.Size.Width > 0 && AppWindow.Size.Height > 0)
            _restoredWindowBounds = new() { X = AppWindow.Position.X, Y = AppWindow.Position.Y,
                Width = AppWindow.Size.Width, Height = AppWindow.Size.Height, Maximized = false };
    }

    private WorkbenchWindowState CaptureWindowState()
    {
        RememberRestoredWindowBounds();
        var restored = _restoredWindowBounds ?? App.Current.Session.State.Window;
        return new() { X = restored.X, Y = restored.Y, Width = restored.Width, Height = restored.Height,
            Maximized = AppWindow.Presenter is OverlappedPresenter { State: OverlappedPresenterState.Maximized } };
    }

    private ContentDialog CloseDialog(string title, object content) => new()
    {
        XamlRoot = Content.XamlRoot, Title = title, Content = content,
        CloseButtonText = "取消关闭", DefaultButton = ContentDialogButton.Close,
    };

    private static TextBlock CloseText(string text) => new() { Text = text, TextWrapping = TextWrapping.Wrap, MaxWidth = 520 };

    private async Task<bool> ConfirmAndCommitCloseAsync()
    {
        ShutdownSnapshot state;
        try { state = await _controlPlane.PrepareCloseAsync(Guid.NewGuid()); }
        catch (Exception error)
        {
            if (_sessionEnd.IsEnding) return false;
            var unknown = CloseDialog("无法确认后台状态", CloseText(error.Message +
                "\n\n编辑内容已保存。可以保留后台并关闭窗口；现有任务不会因此被取消。"));
            unknown.PrimaryButtonText = "保留后台并关闭";
            return await unknown.ShowAsync() == ContentDialogResult.Primary;
        }
        if (_sessionEnd.IsEnding) return false;
        var deadline = DateTime.UtcNow.AddSeconds(20);
        while (state.PendingRequests > 0)
        {
            if (DateTime.UtcNow >= deadline) throw new TimeoutException("仍有提交或文件操作没有结束，请稍后关闭。");
            await Task.Delay(200);
            state = await _controlPlane.GetCloseStateAsync();
            if (_sessionEnd.IsEnding) return false;
        }
        var mode = "idle";
        if (!state.SafeToStop)
        {
            var names = string.Join("\n", state.Operations.Take(6).Select(item => "• " + item.DisplayName));
            var dialog = CloseDialog("还有后台工作正在进行", CloseText(
                names + "\n\n后台继续：关闭窗口，任务和队列继续运行。\n停止任务并关闭：停止调度，向运行任务请求停止，等待保存和清理完成。"));
            dialog.PrimaryButtonText = "后台继续";
            dialog.SecondaryButtonText = "停止任务并关闭";
            var choice = await ShowCloseChoiceWithHeartbeatAsync(dialog);
            if (_sessionEnd.IsEnding) return false;
            if (choice == ContentDialogResult.None)
            {
                ReportPageStatus("关闭已取消");
                return false;
            }
            mode = choice == ContentDialogResult.Primary ? "background" : "stop";
            if (mode == "stop")
            {
                await _controlPlane.StopForCloseAsync();
                if (!await WaitForCloseCleanupAsync())
                {
                    ReportPageStatus("关闭已取消 · 已发出的停止请求仍会继续执行");
                    return false;
                }
            }
        }
        if (_sessionEnd.IsEnding) return false;
        await _controlPlane.CommitCloseAsync(mode);
        return true;
    }

    private async Task<ContentDialogResult> ShowCloseChoiceWithHeartbeatAsync(ContentDialog dialog)
    {
        using var cancellation = new CancellationTokenSource();
        Exception? failure = null;
        async Task Renew()
        {
            try
            {
                while (true)
                {
                    await Task.Delay(TimeSpan.FromSeconds(10), cancellation.Token);
                    await _controlPlane.GetCloseStateAsync(cancellation.Token);
                }
            }
            catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
            catch (Exception error) { failure = error; dialog.Hide(); }
        }
        var renewal = Renew();
        ContentDialogResult result;
        try { result = await dialog.ShowAsync(); }
        finally { cancellation.Cancel(); await renewal; }
        if (failure is not null) throw new IOException("后台关闭准备无法保持，关闭已取消。", failure);
        return result;
    }

    private async Task<bool> WaitForCloseCleanupAsync()
    {
        var message = CloseText("正在等待后台保存和清理…\n可以取消关闭，已发出的停止请求不会撤回。");
        var dialog = CloseDialog("正在停止任务", message);
        using var cancellation = new CancellationTokenSource(TimeSpan.FromSeconds(60));
        async Task Wait()
        {
            while (true)
            {
                var state = await _controlPlane.GetCloseStateAsync(cancellation.Token);
                if (state.SafeToStop) return;
                message.Text = $"仍有 {state.Operations.Count} 项后台工作正在收尾。\n可以取消关闭，已发出的停止请求不会撤回。";
                await Task.Delay(250, cancellation.Token);
            }
        }
        var showing = dialog.ShowAsync().AsTask();
        var waiting = Wait();
        try
        {
            if (await Task.WhenAny(showing, waiting) == showing)
            {
                cancellation.Cancel();
                try { await waiting; } catch (OperationCanceledException) { }
                return false;
            }
            await waiting;
            return true;
        }
        finally
        {
            cancellation.Cancel();
            dialog.Hide();
            await showing;
        }
    }
}
