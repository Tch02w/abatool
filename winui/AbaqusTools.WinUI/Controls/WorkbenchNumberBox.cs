using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Controls.Primitives;

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
        var appearance = new ResourceDictionary
        {
            Source = new Uri("ms-appx:///Controls/WorkbenchNumberBoxResources.xaml")
        };
        Resources.MergedDictionaries.Add(appearance);
        Template = (ControlTemplate)appearance["WorkbenchNumberBoxTemplate"];
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
