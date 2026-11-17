using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;
using AbaqusTools.WinUI.Services;

namespace AbaqusTools.WinUI.Controls;

/// <summary>Hover explanations keep both the trigger and flyout readable; clicks and keys also work.</summary>
public sealed class ParameterHelpButton : Button
{
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _showTimer;
    private readonly Microsoft.UI.Dispatching.DispatcherQueueTimer _hideTimer;
    private bool _overTrigger;
    private bool _overPopup;
    private bool _isOpen;
    private bool _hoverDriven;
    private bool _closingOnPointerLeave;
    private bool _reopenAfterClose;
    private FrameworkElement? _presenter;

    public static readonly DependencyProperty TopicProperty = DependencyProperty.Register(
        nameof(Topic), typeof(string), typeof(ParameterHelpButton),
        new PropertyMetadata(string.Empty, OnExplanationChanged));

    public static readonly DependencyProperty TitleProperty = DependencyProperty.Register(
        nameof(Title), typeof(string), typeof(ParameterHelpButton),
        new PropertyMetadata("参数说明", OnExplanationChanged));

    public static readonly DependencyProperty DescriptionProperty = DependencyProperty.Register(
        nameof(Description), typeof(string), typeof(ParameterHelpButton),
        new PropertyMetadata(string.Empty, OnExplanationChanged));

    public string Title
    {
        get => (string)GetValue(TitleProperty);
        set => SetValue(TitleProperty, value);
    }

    public string Topic
    {
        get => (string)GetValue(TopicProperty);
        set => SetValue(TopicProperty, value);
    }

    public string Description
    {
        get => (string)GetValue(DescriptionProperty);
        set => SetValue(DescriptionProperty, value);
    }

    public ParameterHelpButton()
    {
        _showTimer = DispatcherQueue.CreateTimer();
        _showTimer.IsRepeating = false;
        _showTimer.Interval = TimeSpan.FromMilliseconds(180);
        _showTimer.Tick += (_, _) =>
        {
            if (!_overTrigger || !IsLoaded || !IsEnabled || _isOpen) return;
            _hoverDriven = true;
            Flyout?.ShowAt(this, new FlyoutShowOptions { ShowMode = FlyoutShowMode.Transient });
        };
        _hideTimer = DispatcherQueue.CreateTimer();
        _hideTimer.IsRepeating = false;
        _hideTimer.Interval = TimeSpan.FromMilliseconds(240);
        _hideTimer.Tick += (_, _) =>
        {
            if (_hoverDriven && !_overTrigger && !_overPopup)
            {
                _closingOnPointerLeave = true;
                Flyout?.Hide();
            }
        };
        var helpGlyph = new Border
        {
            Width = 14,
            Height = 14,
            CornerRadius = new CornerRadius(7),
            BorderThickness = new Thickness(1),
            Opacity = 0.75,
            Child = new FontIcon { Glyph = ((char)Symbol.Help).ToString(), FontSize = 10 },
        };
        helpGlyph.SetBinding(Border.BorderBrushProperty, new Binding
        {
            Source = this,
            Path = new PropertyPath(nameof(Foreground)),
        });
        Content = helpGlyph;
        Padding = new Thickness(3);
        MinWidth = 28;
        MinHeight = 28;
        BorderThickness = new Thickness(0);
        Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent);
        VerticalAlignment = VerticalAlignment.Center;
        PointerEntered += (_, _) =>
        {
            _overTrigger = true;
            _hideTimer.Stop();
            if (_closingOnPointerLeave) _reopenAfterClose = true;
            if (!_isOpen) _showTimer.Start();
        };
        PointerExited += (_, _) =>
        {
            _overTrigger = false;
            _showTimer.Stop();
            ScheduleHide();
        };
        Click += (_, _) =>
        {
            _showTimer.Stop();
            _hideTimer.Stop();
            _closingOnPointerLeave = _reopenAfterClose = false;
            _hoverDriven = _overTrigger || FocusState != Microsoft.UI.Xaml.FocusState.Keyboard;
        };
        Unloaded += (_, _) =>
        {
            _showTimer.Stop();
            _hideTimer.Stop();
            _overTrigger = _overPopup = false;
            _closingOnPointerLeave = _reopenAfterClose = false;
            Flyout?.Hide();
        };
        UpdateExplanation();
    }

    private void ScheduleHide()
    {
        if (_isOpen && _hoverDriven && !_overTrigger && !_overPopup) _hideTimer.Start();
    }

    private void OnPopupEntered(object sender, PointerRoutedEventArgs args)
    {
        _overPopup = true;
        _hoverDriven = true;
        if (_closingOnPointerLeave) _reopenAfterClose = true;
        _hideTimer.Stop();
    }

    private void OnPopupExited(object sender, PointerRoutedEventArgs args)
    {
        _overPopup = false;
        ScheduleHide();
    }

    private void DetachPresenter()
    {
        if (_presenter is null) return;
        _presenter.PointerEntered -= OnPopupEntered;
        _presenter.PointerExited -= OnPopupExited;
        _presenter = null;
    }

    private static void OnExplanationChanged(DependencyObject sender, DependencyPropertyChangedEventArgs args) =>
        ((ParameterHelpButton)sender).UpdateExplanation();

    private void UpdateExplanation()
    {
        AutomationProperties.SetName(this, $"{Title}：查看说明");
        AutomationProperties.SetHelpText(this, "悬停或点击查看说明；移出按钮和提示区后自动关闭。键盘可用 Enter 打开、Escape 关闭。");
        _showTimer.Stop();
        _hideTimer.Stop();
        _isOpen = _overPopup = _hoverDriven = false;
        _closingOnPointerLeave = _reopenAfterClose = false;
        Flyout?.Hide();
        DetachPresenter();
        var content = new StackPanel { Spacing = 8, MaxWidth = 320 };
        content.Children.Add(new TextBlock { Text = Title, FontSize = 16, TextWrapping = TextWrapping.Wrap });
        content.Children.Add(new TextBlock
        {
            Text = string.IsNullOrWhiteSpace(Description) ? ParameterHelpText.ForTopic(Topic) : Description,
            TextWrapping = TextWrapping.Wrap,
            IsTextSelectionEnabled = true,
        });
        var explanation = new Flyout { Content = content, OverlayInputPassThroughElement = this };
        explanation.Opened += (_, _) =>
        {
            if (!ReferenceEquals(Flyout, explanation)) return;
            _isOpen = true;
            // Observe the whole presenter, including padding around the selectable text.
            DependencyObject? parent = content;
            while (parent is not null && parent is not FlyoutPresenter)
                parent = VisualTreeHelper.GetParent(parent);
            _presenter = parent as FrameworkElement ?? content;
            _presenter.PointerEntered += OnPopupEntered;
            _presenter.PointerExited += OnPopupExited;
            ScheduleHide();
        };
        explanation.Closed += (_, _) =>
        {
            if (!ReferenceEquals(Flyout, explanation)) return;
            var reopen = _closingOnPointerLeave && _reopenAfterClose
                && (_overTrigger || _overPopup) && IsLoaded;
            _isOpen = _overPopup = _hoverDriven = false;
            _closingOnPointerLeave = _reopenAfterClose = false;
            _showTimer.Stop();
            _hideTimer.Stop();
            DetachPresenter();
            if (reopen)
            {
                DispatcherQueue.TryEnqueue(() =>
                {
                    if (!IsLoaded || !IsEnabled || !ReferenceEquals(Flyout, explanation) || _isOpen) return;
                    _hoverDriven = true;
                    explanation.ShowAt(this, new FlyoutShowOptions { ShowMode = FlyoutShowMode.Transient });
                });
            }
        };
        Flyout = explanation;
        if (_overTrigger && IsLoaded) _showTimer.Start();
    }

    public static void AddToHeader(NumberBox field, string topic)
    {
        var title = field.Header as string ?? "参数";
        var description = ParameterHelpText.ForTopic(topic);
        var header = new Grid { ColumnSpacing = 4 };
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        header.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        header.Children.Add(new TextBlock
        {
            Text = title,
            TextWrapping = TextWrapping.Wrap,
            VerticalAlignment = VerticalAlignment.Center,
        });
        var help = new ParameterHelpButton { Title = title, Description = description };
        Grid.SetColumn(help, 1);
        header.Children.Add(help);
        field.Header = header;
        AutomationProperties.SetName(field, title);
        AutomationProperties.SetHelpText(field, description);
    }
}
