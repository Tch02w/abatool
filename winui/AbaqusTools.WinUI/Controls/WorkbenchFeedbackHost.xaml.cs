using System.Diagnostics;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

namespace AbaqusTools.WinUI.Controls;

public sealed partial class WorkbenchFeedbackHost : UserControl
{
    private sealed record Notice(string Title, string Message, InfoBarSeverity Severity);

    private readonly List<Notice> _waiting = [];
    private readonly DispatcherQueueTimer _timer;
    private Notice? _current;
    private TimeSpan _remaining;
    private long _lastTick;
    private bool _paused;
    private bool _overCard;
    private bool _stopped;

    public WorkbenchFeedbackHost()
    {
        InitializeComponent();
        _timer = DispatcherQueue.CreateTimer();
        _timer.Interval = TimeSpan.FromMilliseconds(150);
        _timer.Tick += OnTick;
        Loaded += (_, _) => DisplayNext();
        Unloaded += (_, _) =>
        {
            _timer.Stop();
            _lastTick = 0;
            _overCard = false;
        };
        Card.PointerEntered += (_, _) => { _overCard = true; UpdateClock(); };
        Card.PointerExited += (_, _) => { _overCard = false; UpdateClock(); };
        Card.GotFocus += (_, _) => UpdateClock();
        Card.LostFocus += (_, _) => DispatcherQueue.TryEnqueue(UpdateClock);
    }

    public void Show(string title, string message, InfoBarSeverity severity)
    {
        if (_stopped || (string.IsNullOrWhiteSpace(title) && string.IsNullOrWhiteSpace(message))) return;
        var notice = new Notice(title.Trim(), message.Trim(), severity);
        if (notice == _current || _waiting.Contains(notice)) return;
        _waiting.Add(notice);
        UpdateCount();
        DisplayNext();
    }

    private void DisplayNext()
    {
        if (_stopped || !IsLoaded) return;
        if (_current is null && _waiting.Count > 0)
        {
            // ContentDialogs have their own popup layer. Announce the message once the dialog closes.
            if (HasModal()) { StartTimer(); return; }
            var index = _waiting.FindIndex(item => item.Severity == InfoBarSeverity.Error);
            if (index < 0) index = 0;
            var notice = _waiting[index];
            _waiting.RemoveAt(index);
            _current = notice;
            _remaining = notice.Severity == InfoBarSeverity.Warning ? TimeSpan.FromSeconds(8) : TimeSpan.FromSeconds(4);
            _lastTick = Stopwatch.GetTimestamp();
            _paused = _overCard || HasCardFocus();
            FeedbackBar.Severity = notice.Severity;
            FeedbackBar.Title = notice.Title;
            // Keep the close button reachable even for multi-line error details.
            bool longMessage = notice.Message.Length > 160 || notice.Message.Count(c => c == '\n') > 2;
            FeedbackBar.Message = longMessage ? "" : notice.Message;
            Details.Text = longMessage ? notice.Message : "";
            LongMessage.Visibility = longMessage ? Visibility.Visible : Visibility.Collapsed;
            LongMessage.ChangeView(null, 0, null, true);
            AutomationProperties.SetName(FeedbackBar, $"{notice.Title} {notice.Message}".Trim());
            UpdateCount();
            Card.Visibility = Visibility.Visible;
            FeedbackBar.IsOpen = true;
        }
        if (_current is null || _current.Severity == InfoBarSeverity.Error)
            _timer.Stop();
        else
            StartTimer();
    }

    private void StartTimer()
    {
        if (!_timer.IsRunning) _timer.Start();
    }

    private void UpdateCount()
    {
        PendingCount.Text = _waiting.Count == 0 ? "" : $"另有 {_waiting.Count} 条提示";
        PendingCount.Visibility = _waiting.Count == 0 ? Visibility.Collapsed : Visibility.Visible;
    }

    private void OnTick(DispatcherQueueTimer sender, object args)
    {
        if (_current is null) DisplayNext();
        else UpdateClock();
    }

    private void UpdateClock()
    {
        if (_stopped || !IsLoaded || _current is null || _current.Severity == InfoBarSeverity.Error) return;
        var now = Stopwatch.GetTimestamp();
        bool modal = HasModal();
        if (_lastTick != 0 && !_paused && !modal) _remaining -= Stopwatch.GetElapsedTime(_lastTick, now);
        _lastTick = now;
        _paused = _overCard || HasCardFocus() || modal;
        if (!_paused && _remaining <= TimeSpan.Zero) FeedbackBar.IsOpen = false;
    }

    private bool HasCardFocus()
    {
        if (XamlRoot is null) return false;
        var element = FocusManager.GetFocusedElement(XamlRoot) as DependencyObject;
        while (element is not null)
        {
            if (element == Card) return true;
            element = VisualTreeHelper.GetParent(element);
        }
        return false;
    }

    private bool HasModal() => XamlRoot is not null && VisualTreeHelper.GetOpenPopupsForXamlRoot(XamlRoot)
        .Any(popup => ContainsDialog(popup.Child));

    private static bool ContainsDialog(DependencyObject? element)
    {
        if (element is ContentDialog) return true;
        if (element is null || element is Control) return false;
        var count = VisualTreeHelper.GetChildrenCount(element);
        for (var index = 0; index < count; index++)
            if (ContainsDialog(VisualTreeHelper.GetChild(element, index))) return true;
        return false;
    }

    private void OnClosed(InfoBar sender, InfoBarClosedEventArgs args)
    {
        _timer.Stop();
        _current = null;
        Card.Visibility = Visibility.Collapsed;
        _overCard = false;
        if (!_stopped && _waiting.Count > 0) DispatcherQueue.TryEnqueue(DisplayNext);
    }

    public void Stop()
    {
        _stopped = true;
        _waiting.Clear();
        _timer.Stop();
        _timer.Tick -= OnTick;
        FeedbackBar.IsOpen = false;
    }
}
