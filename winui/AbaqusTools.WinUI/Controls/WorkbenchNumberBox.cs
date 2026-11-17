using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Controls;

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
}
