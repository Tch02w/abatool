using System.Text.Json;
using AbaqusTools.WinUI.Controls;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;

namespace NumberBoxControlChecks;

public sealed partial class TestApp : Application
{
    private readonly string _receipt;
    private readonly List<string> _checks = [];
    private readonly bool _nativeTeardown;
    private readonly bool _templateClose;
    private Window? _host;
    private readonly StackPanel _fields = new();

    public TestApp(string receipt, bool nativeTeardown = false, bool templateClose = false)
    {
        _receipt = receipt;
        _nativeTeardown = nativeTeardown;
        _templateClose = templateClose;
        InitializeComponent();
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        try
        {
            _host = new Window { Content = _fields };
            _host.AppWindow.MoveAndResize(new Windows.Graphics.RectInt32(-32000, -32000, 400, 800));
            var loaded = new TaskCompletionSource();
            _fields.Loaded += (_, _) => loaded.TrySetResult();
            _host.Activate();
            await loaded.Task.WaitAsync(TimeSpan.FromSeconds(10));
            if (_templateClose) CheckTemplateClose();
            else if (_nativeTeardown) await CheckNativeTeardownAsync();
            else await RunChecksAsync();
            File.WriteAllText(_receipt, JsonSerializer.Serialize(new { status = "passed", checks = _checks }, new JsonSerializerOptions { WriteIndented = true }));
        }
        catch (Exception error)
        {
            Environment.ExitCode = 1;
            File.WriteAllText(_receipt, JsonSerializer.Serialize(new { status = "failed", checks = _checks, error = error.ToString() }, new JsonSerializerOptions { WriteIndented = true }));
        }
        finally
        {
            if (_templateClose)
            {
                _host?.Close();
            }
            else
            {
                // Let queued native focus/UIA work finish while its XAML owner is alive.
                _fields.Children.Clear();
                await DispatchAsync();
                if (_host is not null) _host.Content = null;
                await DispatchAsync();
                Exit();
            }
        }
    }

    private void Check(bool condition, string description)
    {
        if (!condition) throw new InvalidOperationException(description);
        _checks.Add(description);
    }

    private static T Part<T>(DependencyObject root, string name) where T : FrameworkElement
    {
        if (root is T element && element.Name == name) return element;
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(root); index++)
        {
            var found = TryPart<T>(VisualTreeHelper.GetChild(root, index), name);
            if (found is not null) return found;
        }
        throw new InvalidOperationException("Missing native template part: " + name);
    }

    private static T? TryPart<T>(DependencyObject root, string name) where T : FrameworkElement
    {
        if (root is T element && element.Name == name) return element;
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(root); index++)
            if (TryPart<T>(VisualTreeHelper.GetChild(root, index), name) is { } found) return found;
        return null;
    }

    private static async Task InvokeAsync(RepeatButton button)
    {
        var peer = FrameworkElementAutomationPeer.CreatePeerForElement(button)
            ?? throw new InvalidOperationException("Native spin button has no automation peer");
        var invoke = (IInvokeProvider)peer.GetPattern(PatternInterface.Invoke);
        invoke.Invoke();
        var dispatched = new TaskCompletionSource();
        DispatcherQueue.GetForCurrentThread().TryEnqueue(DispatcherQueuePriority.Low, () => dispatched.SetResult());
        await dispatched.Task.WaitAsync(TimeSpan.FromSeconds(5));
    }

    private async Task RunChecksAsync()
    {
        var cpu = new WorkbenchNumberBox { Minimum = 0, Maximum = 8, Value = 1 };
        Attach(cpu);
        var down = Part<RepeatButton>(cpu, "DownSpinButton");
        var up = Part<RepeatButton>(cpu, "UpSpinButton");
        var input = Part<TextBox>(cpu, "InputBox");
        Check(cpu.SpinButtonPlacementMode == NumberBoxSpinButtonPlacementMode.Inline
            && down.Visibility == Visibility.Visible && up.Visibility == Visibility.Visible,
            "Both native step buttons remain visible without focus or a popup");
        Check(Grid.GetColumn(down) < Grid.GetColumn(up), "Decrement is left of increment");
        Check(down.Content is Polyline downGlyph && downGlyph.Points[1].Y > downGlyph.Points[0].Y
            && up.Content is Polyline upGlyph && upGlyph.Points[1].Y < upGlyph.Points[0].Y,
            "Buttons use down/up chevrons in decrement/increment order");
        Check(input.TextAlignment == TextAlignment.Center && up.ActualHeight >= 32 && down.ActualWidth >= 32,
            "Numbers are centered and buttons have usable hit areas");
        await CheckAppearanceAsync(cpu, input, down, up);
        await InvokeAsync(up);
        Check(cpu.Value == 2, "Native increment changes the value exactly once");
        await InvokeAsync(down);
        Check(cpu.Value == 1, "Native decrement changes the value exactly once");
        input.Text = "3";
        await InvokeAsync(up);
        Check(cpu.Value == 4, "Stepping first commits the edited number");
        cpu.Maximum = 2;
        Check(cpu.Value == 2 && !up.IsEnabled && down.IsEnabled,
            "A changed hardware limit clamps the value and disables increment");
        cpu.Value = 0;
        Check(!down.IsEnabled && up.IsEnabled, "Zero remains a valid sentinel and cannot decrement below the minimum");
        cpu.IsEnabled = false;
        Check(!up.IsEnabled && !down.IsEnabled, "Busy-state disabling reaches both native buttons");
        await DispatchAsync();
        Check(Math.Abs(Part<ContentPresenter>(up, "GlyphContent").Opacity - 0.35) < 0.001,
            "A disabled step button visibly dims its chevron");

        var frame = new WorkbenchNumberBox { Minimum = -1, Maximum = 1_000_000, Value = -1 };
        Attach(frame);
        await InvokeAsync(Part<RepeatButton>(frame, "UpSpinButton"));
        Check(frame.Value == 0, "Frame sentinel minus one increments to frame zero");
        await InvokeAsync(Part<RepeatButton>(frame, "DownSpinButton"));
        Check(frame.Value == -1 && !Part<RepeatButton>(frame, "DownSpinButton").IsEnabled,
            "Frame zero decrements to the automatic sentinel without crossing it");

        var area = new WorkbenchNumberBox { Minimum = 0, PlaceholderText = "留空读取 ODB" };
        Attach(area);
        Check(double.IsNaN(area.Value) && Part<TextBox>(area, "InputBox").Text.Length == 0,
            "An optional reference area stays blank and NaN after templating");
        Check(Part<TextBlock>(area, "PlaceholderTextContentPresenter").Visibility == Visibility.Visible,
            "A blank area displays the read-from-ODB placeholder");
        Check(!Part<RepeatButton>(area, "DownSpinButton").IsEnabled && !Part<RepeatButton>(area, "UpSpinButton").IsEnabled,
            "Native stepping does not invent a reference area for a blank field");
        area.Value = 1.5;
        await InvokeAsync(Part<RepeatButton>(area, "UpSpinButton"));
        Check(area.Value == 2.5, "A supplied reference area retains its fractional value during native stepping");
        Check(Part<TextBlock>(area, "PlaceholderTextContentPresenter").Visibility == Visibility.Collapsed,
            "An entered area hides the placeholder instead of overlapping the value");

        var tolerance = new WorkbenchNumberBox { Minimum = 0, Maximum = 100,
            NumberFormatter = new PlainDecimalFormatter(), SmallChange = 0.0001, Value = 0.0001 };
        Attach(tolerance);
        await InvokeAsync(Part<RepeatButton>(tolerance, "UpSpinButton"));
        Check(Math.Abs(tolerance.Value - 0.0002) < 1e-12, "Tolerance increment preserves the 0.0001 step");
        Check(Part<TextBox>(tolerance, "InputBox").Text == new PlainDecimalFormatter().FormatDouble(0.0002),
            "Tolerance still uses the configured plain decimal formatter");
        await InvokeAsync(Part<RepeatButton>(tolerance, "DownSpinButton"));
        Check(Math.Abs(tolerance.Value - 0.0001) < 1e-12, "Tolerance decrement restores its default value");
        cpu.IsEnabled = true;
        cpu.Maximum = 32;
        cpu.Value = 8;
        var helpHeader = new Grid();
        helpHeader.ColumnDefinitions.Add(new ColumnDefinition());
        helpHeader.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        helpHeader.Children.Add(new TextBlock { Text = "CPU 核数" });
        var helpButton = new Button { Content = "?", Width = 28, Height = 28 };
        Grid.SetColumn(helpButton, 1);
        helpHeader.Children.Add(helpButton);
        cpu.Header = helpHeader;
        _fields.UpdateLayout();
        Check(Part<ContentPresenter>(cpu, "HeaderContentPresenter").Visibility == Visibility.Visible
            && helpHeader.ActualHeight >= 28 && Part<Grid>(cpu, "NumberFrame").ActualHeight == 40,
            "A composite help header stays visible above the unchanged 40 DIP input row");
        AutomationProperties.SetName(cpu, "CPU 核数");
        var numberPeer = FrameworkElementAutomationPeer.CreatePeerForElement(cpu)!;
        var range = (IRangeValueProvider)numberPeer.GetPattern(PatternInterface.RangeValue);
        Check(range.Value == 8 && range.Minimum == 0 && range.Maximum == 32,
            "Native NumberBox automation still exposes the value and hardware bounds");
        Check(FrameworkElementAutomationPeer.CreatePeerForElement(input)!.GetName().Contains("CPU 核数"),
            "The accessible field name still reaches the editable text box");
        Check(input.Focus(FocusState.Programmatic), "The native editable field accepts keyboard focus");
        await DispatchAsync();
        Check(Part<Border>(input, "FocusLine").Opacity == 1,
            "Keyboard focus has a visible accent indicator without moving the value");
        cpu.IsEnabled = false;
        await DispatchAsync();
        Check(Part<Border>(input, "FocusLine").Opacity == 0,
            "Disabling a focused field removes its active focus indicator");
    }

    private async Task CheckAppearanceAsync(WorkbenchNumberBox field, TextBox input, RepeatButton down, RepeatButton up)
    {
        var frame = Part<Grid>(field, "NumberFrame");
        var downLeft = down.TransformToVisual(frame).TransformPoint(new Windows.Foundation.Point());
        var upLeft = up.TransformToVisual(frame).TransformPoint(new Windows.Foundation.Point());
        Check(frame.ActualHeight == 40 && frame.CornerRadius == new CornerRadius(5),
            "The approved shared frame is 40 DIPs high with a 5 DIP corner radius");
        Check(down.ActualWidth == 40 && up.ActualWidth == 40
            && Math.Abs(downLeft.X + down.ActualWidth - upLeft.X) < 0.01
            && Math.Abs(frame.ActualWidth - upLeft.X - up.ActualWidth - 1) < 0.01,
            "Two 40 DIP buttons meet without a gap and end at the shared outer border");
        Check(Part<Border>(down, "ButtonChrome").BorderThickness == new Thickness(1, 0, 0, 0)
            && Part<Border>(up, "ButtonChrome").BorderThickness == new Thickness(1, 0, 0, 0),
            "Both buttons use only a one DIP vertical separator inside the shared frame");
        Check(Math.Abs(input.ActualWidth - downLeft.X + 1) < 0.01
            && Math.Abs(Part<ScrollViewer>(input, "ContentElement").ActualWidth - input.ActualWidth) < 0.01,
            "The centered text uses exactly the space before the buttons with no hidden popup gutter");
        field.RequestedTheme = ElementTheme.Light;
        await DispatchAsync();
        Check(ColorOf(frame.Background) == "#FFFFFFFF" && ColorOf(frame.BorderBrush) == "#FFD2D2D2",
            "Light appearance uses the approved white frame and light gray border");
        VisualStateManager.GoToState(up, "PointerOver", false);
        Check(Part<Border>(up, "HoverFill").Opacity == 1
            && ColorOf(Part<Border>(up, "HoverFill").Background) == "#FFEEEEEE",
            "Light hover highlights the full increment button");
        field.RequestedTheme = ElementTheme.Dark;
        await DispatchAsync();
        Check(ColorOf(frame.Background) == "#FF323232" && ColorOf(frame.BorderBrush) == "#FF595959"
            && ColorOf(Part<Border>(up, "HoverFill").Background) == "#FF454545",
            "Changing to dark theme updates the frame, border and active hover state");
        VisualStateManager.GoToState(up, "Normal", false);
        field.RequestedTheme = ElementTheme.Light;
        await DispatchAsync();
        field.Width = 160;
        _fields.UpdateLayout();
        Check(frame.ActualWidth == 160 && input.ActualWidth >= 78,
            "At the minimum field width the value retains 78 DIPs without clipping the buttons");
        field.ClearValue(FrameworkElement.WidthProperty);
        _fields.UpdateLayout();
    }

    private static string ColorOf(Brush brush) => ((SolidColorBrush)brush).Color.ToString();

    private static async Task DispatchAsync()
    {
        var completion = new TaskCompletionSource();
        DispatcherQueue.GetForCurrentThread().TryEnqueue(DispatcherQueuePriority.Low, () => completion.SetResult());
        await completion.Task.WaitAsync(TimeSpan.FromSeconds(5));
    }

    private async Task CheckNativeTeardownAsync()
    {
        var field = new NumberBox { Minimum = 0, Maximum = 32, Value = 8,
            Header = "CPU 核数", SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline };
        Attach(field);
        var peer = FrameworkElementAutomationPeer.CreatePeerForElement(field)!;
        var range = (IRangeValueProvider)peer.GetPattern(PatternInterface.RangeValue);
        Check(range.Value == 8, "Stock NumberBox exposes its native RangeValue");
        Check(Part<TextBox>(field, "InputBox").Focus(FocusState.Programmatic), "Stock NumberBox accepts focus");
        await DispatchAsync();
        field.IsEnabled = false;
        await DispatchAsync();
        Check(!Part<TextBox>(field, "InputBox").IsEnabled, "Stock NumberBox disables its focused input");
    }

    private void CheckTemplateClose()
    {
        var blank = new WorkbenchNumberBox { Minimum = 0, PlaceholderText = "留空读取 ODB" };
        var filled = new WorkbenchNumberBox { Minimum = 0, Maximum = 32, Value = 8, Header = "CPU 核数" };
        Attach(blank);
        Attach(filled);
        Check(double.IsNaN(blank.Value) && Part<TextBox>(blank, "InputBox").Text.Length == 0,
            "Blank preview-template field loads before a normal window close");
        Check(filled.Value == 8 && Part<TextBox>(filled, "InputBox").Text == "8",
            "Filled preview-template field loads before a normal window close");
    }

    private void Attach(NumberBox field)
    {
        _fields.Children.Add(field);
        _fields.Measure(new Windows.Foundation.Size(400, 1000));
        _fields.Arrange(new Windows.Foundation.Rect(0, 0, 400, 1000));
        field.ApplyTemplate();
        _fields.UpdateLayout();
    }
}
