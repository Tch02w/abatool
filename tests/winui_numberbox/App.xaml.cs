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
using ShapePath = Microsoft.UI.Xaml.Shapes.Path;

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
        Check(Grid.GetColumn(down) < Grid.GetColumn(input) && Grid.GetColumn(input) < Grid.GetColumn(up),
            "Decrement and increment flank the native editable text");
        Check(Part<ShapePath>(down, "StepSign").Data is LineGeometry minus && minus.StartPoint.Y == minus.EndPoint.Y
            && minus.EndPoint.X > minus.StartPoint.X && Part<ShapePath>(up, "StepSign").Data is GeometryGroup plus
            && plus.Children.Count == 2 && plus.Children[0] is LineGeometry horizontal && plus.Children[1] is LineGeometry vertical
            && horizontal.StartPoint == minus.StartPoint && horizontal.EndPoint == minus.EndPoint
            && vertical.StartPoint.X == vertical.EndPoint.X && vertical.EndPoint.Y > vertical.StartPoint.Y,
            "Native buttons render horizontal minus and crossed plus strokes");
        Check(input.TextAlignment == TextAlignment.Center && up.ActualHeight >= 32 && down.ActualWidth >= 32,
            "Numbers are centered and buttons have usable hit areas");
        await CheckAppearanceAsync(cpu, input, down, up);
        await CheckTextFieldAppearanceAsync();
        await CheckQueueToolbarAppearanceAsync();
        input.Text = "-";
        Check(cpu.EditingText == "-" && cpu.Value == 1,
            "An unfinished number is available to the recovery checkpoint before native commit");
        var valueChanges = 0;
        cpu.ValueChanged += (_, _) => valueChanges++;
        cpu.RestoreEditingText("1e");
        Check(input.Text == "1e" && cpu.ParseEditingValue(cpu.EditingText) is null
            && cpu.Value == 1 && valueChanges == 0,
            "Restoring an incomplete number preserves its raw text and leaves the numeric value untouched");
        cpu.RestoreEditingText("2");
        Check(cpu.Value == 2 && cpu.ParseEditingValue(cpu.EditingText) == 2,
            "A complete restored number supplies the value for an explicit save");
        cpu.RestoreEditingText("1");
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
        Check(Math.Abs(Part<ShapePath>(up, "StepSign").Opacity - 0.35) < 0.001,
            "A disabled step button visibly dims its sign");

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
        var helpButton = new ParameterHelpButton { Title = "CPU 核数", Topic = "cpu" };
        Grid.SetColumn(helpButton, 1);
        helpHeader.Children.Add(helpButton);
        cpu.Header = helpHeader;
        _fields.UpdateLayout();
        foreach (var theme in new[] { ElementTheme.Light, ElementTheme.Dark })
        {
            helpButton.RequestedTheme = theme;
            await DispatchAsync();
            var icon = (ShapePath)helpButton.Content;
            Check(helpButton.ActualWidth == 28 && helpButton.ActualHeight == 28
                && icon.ActualWidth == 16 && icon.ActualHeight == 16 && icon.Opacity == 1,
                $"{theme}: a solid sixteen DIP icon sits inside the original 28 DIP help target");
            Check(icon.Data is GeometryGroup { FillRule: FillRule.EvenOdd } info && info.Children.Count == 3
                && info.Children[0] is EllipseGeometry { RadiusX: 8, RadiusY: 8 }
                && info.Children[1] is EllipseGeometry && info.Children[2] is RectangleGeometry
                && ColorOf(icon.Fill) == (theme == ElementTheme.Light ? "#FF555555" : "#FFD0D0D0"),
                $"{theme}: the neutral help disc cuts out the dot and stem of a lowercase i");
        }
        Check(AutomationProperties.GetName(helpButton).Contains("CPU 核数") && helpButton.Flyout is Flyout,
            "The help control retains its accessible name and explanatory flyout");
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
        Check(down.ActualWidth == 40 && up.ActualWidth == 40 && Math.Abs(downLeft.X - 1) < .01
            && Math.Abs(frame.ActualWidth - upLeft.X - up.ActualWidth - 1) < .01,
            "Both full-width hit targets start at the opposite outer frame edges");
        Check(Part<Grid>(down, "ButtonChrome").BorderThickness == new Thickness(0)
            && Part<Grid>(up, "ButtonChrome").BorderThickness == new Thickness(0),
            "The edge buttons have no internal hard separator");
        var inputLeft = input.TransformToVisual(frame).TransformPoint(default).X;
        Check(Math.Abs(inputLeft + input.ActualWidth / 2 - frame.ActualWidth / 2) < .01
            && Math.Abs(Part<ScrollViewer>(input, "ContentElement").ActualWidth - input.ActualWidth) < 0.01,
            "The editable text is centered on the complete frame without a hidden popup gutter");
        foreach (var theme in new[] { ElementTheme.Light, ElementTheme.Dark })
        {
            field.RequestedTheme = theme;
            await DispatchAsync();
            bool light = theme == ElementTheme.Light;
            Check(ColorOf(frame.Background) == (light ? "#FFFFFFFF" : "#FF323232")
                && ColorOf(frame.BorderBrush) == (light ? "#FFD2D2D2" : "#FF595959"),
                $"{theme}: the outer fill and border match the existing frame");
            foreach (var key in new[] { down, up })
            {
                var face = Part<Border>(key, "KeyFace");
                var sign = Part<ShapePath>(key, "StepSign");
                var bounds = face.TransformToVisual(key).TransformBounds(new Windows.Foundation.Rect(0, 0, face.ActualWidth, face.ActualHeight));
                Check(Math.Abs(bounds.Width - bounds.Height) < .01 && Math.Abs(bounds.Top - 3) < .01
                    && bounds.Left >= 3 && face.CornerRadius == new CornerRadius(3) && sign.StrokeThickness >= 1.5,
                    $"{theme}: the rounded key is inset in both directions inside its full hit area");
                Check(ColorOf(face.Background) == (light ? "#FFEEEEEE" : "#FF434343") && face.Opacity == 1,
                    $"{theme}: an enabled resting key has its own neutral fill");
                VisualStateManager.GoToState(key, "PointerOver", false);
                Check(ColorOf(face.Background) == (light ? "#FFEAF3FB" : "#FF263F50")
                    && ColorOf(sign.Stroke) == (light ? "#FF005A9E" : "#FF9FD9FF"),
                    $"{theme}: hovering tints the whole key face and its sign");
                VisualStateManager.GoToState(key, "Pressed", false);
                Check(ColorOf(face.Background) == (light ? "#FFD5E7F5" : "#FF335468"),
                    $"{theme}: pressing has a distinct key fill");
                VisualStateManager.GoToState(key, "Normal", false);
            }
            field.Value = field.Minimum;
            await DispatchAsync();
            Check(!down.IsEnabled && up.IsEnabled && Math.Abs(Part<ShapePath>(down, "StepSign").Opacity - .35) < .001
                && Math.Abs(Part<Border>(down, "KeyFace").Opacity - .45) < .001 && Part<Border>(up, "KeyFace").Opacity == 1,
                $"{theme}: the minimum dims just the decrement target");
            field.Value = field.Maximum;
            await DispatchAsync();
            Check(!up.IsEnabled && down.IsEnabled && Math.Abs(Part<ShapePath>(up, "StepSign").Opacity - .35) < .001
                && Math.Abs(Part<Border>(up, "KeyFace").Opacity - .45) < .001 && Part<Border>(down, "KeyFace").Opacity == 1,
                $"{theme}: the maximum dims just the increment target");
            field.Value = 1;
        }
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

    private async Task CheckTextFieldAppearanceAsync()
    {
        var text = new TextBox { Header = "内存", Text = "80%" };
        var number = new WorkbenchNumberBox { FrameAppearance = NumberBoxFrameAppearance.TextField, Header = "优先级", Value = 0 };
        _fields.Children.Add(text);
        Attach(number);
        var border = Part<Border>(text, "BorderElement");
        var frame = Part<Grid>(number, "NumberFrame");
        foreach (var theme in new[] { ElementTheme.Light, ElementTheme.Dark })
        {
            text.RequestedTheme = number.RequestedTheme = theme;
            await DispatchAsync();
            _fields.UpdateLayout();
            Check(frame.ActualHeight == 32 && frame.ActualHeight == border.ActualHeight
                && frame.ActualWidth == border.ActualWidth && frame.CornerRadius == border.CornerRadius
                && frame.BorderThickness == border.BorderThickness,
                $"{theme}: the form number field matches the native text field height, width, corners and border thickness");
            Check(ColorOf(frame.Background) == ColorOf(border.Background)
                && frame.BorderBrush == border.BorderBrush
                && Part<Border>(number, "BottomOutline").Visibility == Visibility.Collapsed,
                $"{theme}: form fields share the native fill and border brush with a single bottom edge");
        }
        var down = Part<RepeatButton>(number, "DownSpinButton");
        var up = Part<RepeatButton>(number, "UpSpinButton");
        var right = up.TransformToVisual(frame).TransformPoint(new Windows.Foundation.Point()).X + up.ActualWidth;
        Check(down.ActualWidth == 32 && up.ActualWidth == 32 && Math.Abs(right + frame.BorderThickness.Right - frame.ActualWidth) < 0.01
            && Part<TextBox>(number, "InputBox").TextAlignment == TextAlignment.Center,
            "The form field centers its value and keeps both full 32 DIP edge hit targets");
        await InvokeAsync(down);
        Check(number.Value == -1, "The form field decrements a signed queue priority");
        await InvokeAsync(up);
        Check(number.Value == 0, "The form field increments back to zero");
        _fields.Children.Remove(number);
        _fields.Children.Remove(text);
    }

    private async Task CheckQueueToolbarAppearanceAsync()
    {
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        var policy = new ComboBox { Width = 126, Height = 40, VerticalAlignment = VerticalAlignment.Center };
        policy.Items.Add("备份旧结果");
        policy.SelectedIndex = 0;
        var limit = new WorkbenchNumberBox { FrameAppearance = NumberBoxFrameAppearance.ComboBox,
            Width = 160, VerticalAlignment = VerticalAlignment.Center, Minimum = 1, Value = 1 };
        row.Children.Add(policy);
        row.Children.Add(limit);
        _fields.Children.Add(row);
        foreach (var theme in new[] { ElementTheme.Light, ElementTheme.Dark })
        {
            row.RequestedTheme = theme;
            await DispatchAsync();
            _fields.UpdateLayout();
            var frame = Part<Grid>(limit, "NumberFrame");
            var border = Part<Border>(policy, "Background");
            var origin = new Windows.Foundation.Point();
            Check(frame.ActualHeight == 40 && frame.ActualHeight == border.ActualHeight
                && frame.TransformToVisual(row).TransformPoint(origin).Y == border.TransformToVisual(row).TransformPoint(origin).Y,
                $"{theme}: the queue dropdown and stepper have identical top and bottom edges");
            Check(frame.Background == border.Background && frame.BorderBrush == border.BorderBrush
                && frame.CornerRadius == border.CornerRadius && frame.BorderThickness == border.BorderThickness
                && Part<Border>(limit, "BottomOutline").Visibility == Visibility.Collapsed,
                $"{theme}: both toolbar controls draw the same fill, corners and single outer border");
        }
        await InvokeAsync(Part<RepeatButton>(limit, "UpSpinButton"));
        Check(limit.Value == 2, "The toolbar still steps the parallel limit with its permanent increment button");
        _fields.Children.Remove(row);
    }

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
