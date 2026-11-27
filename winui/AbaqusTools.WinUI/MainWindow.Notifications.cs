using System.Runtime.InteropServices;
using AbaqusTools.WinUI.Pages;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI;

public sealed partial class MainWindow
{
    private readonly JobNotificationPresentation _notificationState = new();
    private bool _notificationBusy;
    private bool _notificationActionBusy;
    private bool _notificationOpenBusy;
    private long _notificationRevision;
    private bool _notificationPollError;
    private string? _previousPersistenceWarning;
    private bool _notificationFlyoutOpen;
    private IReadOnlyList<JobNotification> _notificationsInView = [];
    private string _notificationListSignature = "";

    private async Task RefreshJobNotificationsAsync()
    {
        if (_notificationBusy || _notificationActionBusy || _shutdownStarted || App.Current.Session.IsClosing) return;
        _notificationBusy = true;
        var revision = _notificationRevision;
        try
        {
            var snapshot = await _controlPlane.GetJobNotificationsAsync();
            if (_shutdownStarted || _windowClosed || revision != _notificationRevision) return;
            ApplyJobNotifications(snapshot);
        }
        catch (Exception error) when (error is ControlPlaneException or OperationCanceledException)
        {
            if (_shutdownStarted || _windowClosed || revision != _notificationRevision) return;
            if (!_notificationPollError)
                ShowFeedback("结束提醒暂不可用", "已有作业仍继续运行，稍后将自动重试。", InfoBarSeverity.Warning);
            NotificationMessageText.Text = error.Message;
            _notificationPollError = true;
            JobNotificationsMenuItem.Text = "结束提醒（暂不可用）";
        }
        finally { _notificationBusy = false; }
    }

    private void ApplyJobNotifications(JobNotificationSnapshot snapshot, bool refreshList = false)
    {
        var newItems = _notificationState.Apply(snapshot);
        if (_notificationPollError)
        {
            NotificationMessageText.Text = "";
            _notificationPollError = false;
        }
        JobNotificationsMenuItem.Text = $"结束提醒（{snapshot.UnreadCount} 条未读）";
        if (newItems && snapshot.Items.FirstOrDefault() is { } latest)
        {
            var severity = snapshot.Items.Any(item => item.Status != "succeeded") ? InfoBarSeverity.Warning : InfoBarSeverity.Success;
            ShowFeedback($"作业结束提醒 · {snapshot.UnreadCount} 条未读", latest.Heading + "。可在「作业 → 结束提醒」查看。", severity);
        }
        if (_previousPersistenceWarning != snapshot.PersistenceWarning && !string.IsNullOrWhiteSpace(snapshot.PersistenceWarning))
            ShowFeedback("结束提醒保存异常", snapshot.PersistenceWarning, InfoBarSeverity.Error);
        _previousPersistenceWarning = snapshot.PersistenceWarning;
        var signature = string.Join("|", snapshot.Items.Select(item => item.Id));
        // Identical polls must not rebuild the list and discard selection or scroll.
        if (signature != _notificationListSignature && (!_notificationFlyoutOpen || refreshList))
        {
            _notificationListSignature = signature;
            _notificationsInView = snapshot.Items;
            JobNotificationList.ItemsSource = snapshot.Items;
        }
        NotificationListTitle.Text = snapshot.UnreadCount != _notificationsInView.Count
            ? $"未读 {snapshot.UnreadCount} 条 · 当前显示 {_notificationsInView.Count} 条，重新打开或标为已读后更新列表" : $"未读 {snapshot.UnreadCount} 条";
        ReadNotificationPageButton.IsEnabled = !_notificationActionBusy && _notificationsInView.Count > 0;
        if (newItems) RequestTaskbarAttention();
    }

    private async Task<bool> AcknowledgeNotificationsAsync(IReadOnlyList<string> ids)
    {
        if (_notificationActionBusy || ids.Count == 0 || App.Current.Session.IsClosing) return false;
        _notificationActionBusy = true;
        _notificationRevision++;
        JobNotificationList.IsEnabled = false;
        ReadNotificationPageButton.IsEnabled = false;
        try
        {
            var result = await _controlPlane.AcknowledgeJobNotificationsAsync(ids);
            if (_shutdownStarted || _windowClosed) return false;
            ApplyJobNotifications(result, refreshList: true);
            NotificationMessageText.Text = "";
            return true;
        }
        catch (Exception error) when (error is ControlPlaneException or OperationCanceledException)
        {
            if (!_windowClosed) NotificationMessageText.Text = "已读状态未确认，请重试。" + error.Message;
            return false;
        }
        finally
        {
            _notificationActionBusy = false;
            if (!_windowClosed)
            {
                JobNotificationList.IsEnabled = true;
                ReadNotificationPageButton.IsEnabled = _notificationsInView.Count > 0;
            }
        }
    }

    private async void OnReadNotificationClicked(object sender, RoutedEventArgs args)
    {
        if (sender is Button { Tag: JobNotification item }) await AcknowledgeNotificationsAsync([item.Id]);
    }

    private void OnNotificationFlyoutOpened(object? sender, object args)
    {
        ApplyJobNotifications(_notificationState.Current, refreshList: true);
        _notificationFlyoutOpen = true;
    }

    private void OnNotificationFlyoutClosed(object? sender, object args) => _notificationFlyoutOpen = false;

    private void OnOpenNotificationCenter(object sender, RoutedEventArgs args)
    {
        if (!App.Current.Session.IsClosing)
            DispatcherQueue.TryEnqueue(() => { if (!_windowClosed) JobNotificationFlyout.ShowAt(WindowMenuBar); });
    }

    private async void OnReadNotificationPageClicked(object sender, RoutedEventArgs args) =>
        await AcknowledgeNotificationsAsync(_notificationsInView.Select(item => item.Id).ToArray());

    private async void OnOpenNotifiedJobClicked(object sender, RoutedEventArgs args)
    {
        if (sender is not Button { Tag: JobNotification item } || _notificationOpenBusy || App.Current.Session.IsClosing) return;
        _notificationOpenBusy = true;
        try
        {
            SelectRoute("job-overview");
            if (ContentFrame.Content is JobOverviewPage page && await page.SelectNotificationJobAsync(item))
            {
                if (await AcknowledgeNotificationsAsync([item.Id]) && !_windowClosed) JobNotificationFlyout.Hide();
            }
            else if (!_windowClosed) NotificationMessageText.Text = "这次执行已不在当前作业列表中。提醒和原目录仍保留，可复制目录核对。";
        }
        finally { _notificationOpenBusy = false; }
    }

    private void RequestTaskbarAttention()
    {
        var window = WinRT.Interop.WindowNative.GetWindowHandle(this);
        if (window == IntPtr.Zero || GetForegroundWindow() == window) return;
        var request = new FlashWindowInfo { Size = (uint)Marshal.SizeOf<FlashWindowInfo>(), Window = window,
            Flags = 2 | 12, Count = 3, Timeout = 0 };
        FlashWindowEx(ref request);
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct FlashWindowInfo { public uint Size; public IntPtr Window; public uint Flags; public uint Count; public uint Timeout; }
    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] [return: MarshalAs(UnmanagedType.Bool)]
    private static extern bool FlashWindowEx(ref FlashWindowInfo request);
}
