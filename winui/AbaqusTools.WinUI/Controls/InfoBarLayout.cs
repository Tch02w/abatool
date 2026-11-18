using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Controls;

/// <summary>Closed InfoBars must release their margins as well as their content.</summary>
public static class InfoBarLayout
{
    public static void Track(FrameworkElement? container, params InfoBar[] bars)
    {
        void Update(DependencyObject? sender, DependencyProperty? property)
        {
            foreach (var bar in bars)
            {
                bar.Visibility = bar.IsOpen ? Visibility.Visible : Visibility.Collapsed;
            }
            if (container is not null)
            {
                container.Visibility = bars.Any(bar => bar.IsOpen)
                    ? Visibility.Visible : Visibility.Collapsed;
            }
        }

        foreach (var bar in bars)
        {
            bar.RegisterPropertyChangedCallback(InfoBar.IsOpenProperty, Update);
        }
        Update(null, null);
    }
}
