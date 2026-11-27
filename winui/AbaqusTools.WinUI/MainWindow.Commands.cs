using AbaqusTools.WinUI.Pages;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI;

public sealed partial class MainWindow
{
    private bool _queueCommandRefreshBusy;
    private bool _remoteCommandRefreshBusy;
    private bool _menuCommandBusy;

    private void UpdateCommandMenus()
    {
        var commands = App.Current.Commands;
        ExplorerToggleButton.IsEnabled = !commands.Locked;
        ExplorerHost.SetCollapseEnabled(!commands.Locked);
        StartQueueMenuItem.IsEnabled = !_menuCommandBusy && commands.CanStartQueue;
        StopQueueMenuItem.IsEnabled = !_menuCommandBusy && commands.CanStopQueue;
        TerminateQueueMenuItem.IsEnabled = !_menuCommandBusy && commands.CanTerminateSelected;
        RefreshRemoteMenuItem.IsEnabled = !_menuCommandBusy && commands.CanUseRemote;
        DisconnectRemoteMenuItem.IsEnabled = !_menuCommandBusy && commands.CanUseRemote;
        CurrentJobPostprocessingMenuItem.IsEnabled = !_menuCommandBusy && !commands.Locked;
    }

    private Task RefreshCommandSnapshotsAsync() => Task.WhenAll(RefreshQueueCommandSnapshotAsync(), RefreshRemoteCommandSnapshotAsync());

    private async Task RefreshQueueCommandSnapshotAsync()
    {
        var commands = App.Current.Commands;
        if (_queueCommandRefreshBusy || commands.QueueBusy || commands.Locked || ContentFrame.Content is JobQueuePage) return;
        _queueCommandRefreshBusy = true;
        var revision = commands.QueueRevision;
        try
        {
            var snapshot = await _controlPlane.GetLocalQueueRuntimeAsync();
            if (!_windowClosed && commands.QueueObservationIsCurrent(revision)) commands.ApplyQueue(snapshot);
        }
        catch (Exception)
        {
            if (commands.QueueObservationIsCurrent(revision)) commands.InvalidateQueue();
        }
        finally { _queueCommandRefreshBusy = false; }
    }

    private async Task RefreshRemoteCommandSnapshotAsync()
    {
        var commands = App.Current.Commands;
        if (_remoteCommandRefreshBusy || commands.ResourceBusy || commands.RemoteRefreshBusy || commands.Locked) return;
        _remoteCommandRefreshBusy = true;
        var revision = commands.RemoteRevision;
        try
        {
            // Observe published state only; this poll never sends an SSH resource command.
            var snapshot = await _controlPlane.GetRemoteServersAsync();
            if (_windowClosed || !commands.RemoteObservationIsCurrent(revision)) return;
            if (App.Current.Session.GetRestoredPage("compute-resources") is ComputeResourcesPage page)
                page.ApplyRemoteSnapshot(snapshot);
            else ApplyRemoteServerSnapshot(snapshot);
        }
        catch (Exception)
        {
            if (commands.RemoteObservationIsCurrent(revision)) commands.InvalidateRemote();
        }
        finally { _remoteCommandRefreshBusy = false; }
    }

    private async Task RunQueueMenuAsync(Func<bool> canExecute, Func<JobQueuePage, Task> execute)
    {
        if (_menuCommandBusy || !canExecute()) return;
        _menuCommandBusy = true; UpdateCommandMenus();
        try
        {
            NavigateToRoute("job-queue");
            if (ContentFrame.Content is not JobQueuePage page) return;
            await page.WaitForMenuReadyAsync();
            if (ReferenceEquals(ContentFrame.Content, page) && canExecute()) await execute(page);
            else ShowFeedback("队列状态已变化", "请核对所选作业后重试。", InfoBarSeverity.Warning);
        }
        catch (Exception error) { ShowFeedback("队列菜单操作未完成", error.Message, InfoBarSeverity.Error); }
        finally { _menuCommandBusy = false; UpdateCommandMenus(); }
    }

    private async Task RunRemoteMenuAsync(bool disconnect)
    {
        var commands = App.Current.Commands;
        if (_menuCommandBusy || !commands.CanUseRemote) return;
        var expected = commands.ConnectedProfile!;
        var profile = expected.ProfileName;
        _menuCommandBusy = true; UpdateCommandMenus();
        try
        {
            NavigateToRoute("compute-resources");
            if (ContentFrame.Content is not ComputeResourcesPage page) return;
            await page.WaitForMenuReadyAsync();
            if (!ReferenceEquals(ContentFrame.Content, page) || !commands.CanUseSelectedRemote(profile))
            {
                ShowFeedback("连接状态已变化", "请核对服务器连接后重试。", InfoBarSeverity.Warning);
                return;
            }
            if (!page.SelectConnectedServer(profile))
            {
                ShowFeedback("未找到已连接服务器的配置", "请在计算资源页核对当前连接。", InfoBarSeverity.Warning);
                return;
            }
            if (disconnect) await page.DisconnectAsync(expected);
            else await page.RefreshConnectedServerAsync(expected);
        }
        catch (Exception error) { ShowFeedback("服务器菜单操作未完成", error.Message, InfoBarSeverity.Error); }
        finally { _menuCommandBusy = false; UpdateCommandMenus(); }
    }
}
