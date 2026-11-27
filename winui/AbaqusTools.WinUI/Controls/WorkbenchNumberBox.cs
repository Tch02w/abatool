using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;
using Windows.Globalization.NumberFormatting;

namespace AbaqusTools.WinUI.Controls;

public enum NumberBoxFrameAppearance { Standard, TextField, ComboBox }

/// <summary>
/// Native NumberBox with always-visible decrement/increment buttons, in that order.
/// Value, parsing, stepping, limits, blank values, and enabled states stay with NumberBox.
/// The visual template keeps the native NumberBox parts and enabled states while
/// matching the approved input preview. No value/validation/step handlers are replaced.
/// </summary>
public sealed class WorkbenchNumberBox : NumberBox
{
    public WorkbenchNumberBox()
    {
        DefaultStyleKey = typeof(NumberBox);
        SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline;
        MinWidth = 160;
        var appearance = CreateAppearanceResources();
        Resources.MergedDictionaries.Add(appearance);
        Template = (ControlTemplate)appearance["WorkbenchNumberBoxTemplate"];
    }

    internal static ResourceDictionary CreateAppearanceResources() => new()
    {
        Source = new Uri("ms-appx:///Controls/WorkbenchNumberBoxResources.xaml")
    };

    // NumberBox.Text reflects the last committed value while the inner editor has focus.
    internal string EditingText => (GetTemplateChild("InputBox") as TextBox)?.Text ?? Text;

    internal double? ParseEditingValue(string text)
    {
        var parsed = (NumberFormatter as INumberParser)?.ParseDouble(text);
        return parsed is double value && double.IsFinite(value) && value >= Minimum && value <= Maximum
            ? value : null;
    }

    internal void RestoreEditingText(string text)
    {
        ApplyTemplate();
        if (GetTemplateChild("InputBox") is not TextBox input)
            throw new InvalidOperationException("未能打开数字编辑框。");
        if (ParseEditingValue(text) is double value && Value != value) Value = value;
        input.Text = text;
    }

    public static readonly DependencyProperty FrameAppearanceProperty = DependencyProperty.Register(
        nameof(FrameAppearance), typeof(NumberBoxFrameAppearance), typeof(WorkbenchNumberBox),
        new PropertyMetadata(NumberBoxFrameAppearance.Standard,
            (sender, _) => ((WorkbenchNumberBox)sender).ApplyFrameAppearance()));

    public NumberBoxFrameAppearance FrameAppearance
    {
        get => (NumberBoxFrameAppearance)GetValue(FrameAppearanceProperty);
        set => SetValue(FrameAppearanceProperty, value);
    }

    protected override void OnApplyTemplate()
    {
        base.OnApplyTemplate();
        ApplyFrameAppearance();
    }

    private void ApplyFrameAppearance()
    {
        if (GetTemplateChild("NumberFrame") is not Grid frame) return;

        var styleKey = FrameAppearance switch
        {
            NumberBoxFrameAppearance.TextField => "WorkbenchNumberFormFrameStyle",
            NumberBoxFrameAppearance.ComboBox => "WorkbenchNumberComboFrameStyle",
            _ => "WorkbenchNumberFrameStyle",
        };
        frame.Style = (Style)Resources[styleKey];
        if (GetTemplateChild("BottomOutline") is Border outline)
            outline.Visibility = FrameAppearance == NumberBoxFrameAppearance.Standard ? Visibility.Visible : Visibility.Collapsed;
        foreach (var name in new[] { "DownSpinButton", "UpSpinButton" })
            if (GetTemplateChild(name) is RepeatButton button)
                button.Width = frame.Height;
    }
}
