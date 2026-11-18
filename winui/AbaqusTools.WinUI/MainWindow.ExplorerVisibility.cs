using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;
using Microsoft.UI.Xaml.Media;

namespace AbaqusTools.WinUI;

public sealed partial class MainWindow
{
    private void OnExplorerToggleClicked(object sender, RoutedEventArgs args) =>
        SetExplorerVisibility(!App.Current.Session.State.ExplorerVisible);

    private void OnExplorerAcceleratorInvoked(
        KeyboardAccelerator sender, KeyboardAcceleratorInvokedEventArgs args)
    {
        SetExplorerVisibility(!App.Current.Session.State.ExplorerVisible);
        args.Handled = true;
    }

    private void SetExplorerVisibility(bool visible)
    {
        if (!_shutdownStarted && !App.Current.Session.IsClosing && !App.Current.Commands.Locked)
        {
            App.Current.Session.State.ExplorerVisible = visible;
        }
        ApplyExplorerVisibility();
    }

    private void ApplyExplorerVisibility()
    {
        var visible = App.Current.Session.State.ExplorerVisible;
        ExplorerToggleIcon.Glyph = visible ? "\uE76B" : "\uE76C";
        ExplorerToggleButton.Margin = new Thickness(0, 8, visible ? 8 : 5, 0);
        var action = visible ? "收起浏览侧栏" : "显示浏览侧栏";
        AutomationProperties.SetName(ExplorerToggleButton, action);
        ToolTipService.SetToolTip(ExplorerToggleButton, action + " (Ctrl+B)");
        if (!visible && Content.XamlRoot is { } root)
        {
            for (var element = FocusManager.GetFocusedElement(root) as DependencyObject;
                 element is not null; element = VisualTreeHelper.GetParent(element))
            {
                if (!ReferenceEquals(element, ExplorerHost)) continue;
                ExplorerToggleButton.Focus(FocusState.Programmatic);
                break;
            }
        }
        // Keep the same explorer and page instances, including selection and ongoing work.
        ExplorerHost.Visibility = visible ? Visibility.Visible : Visibility.Collapsed;
        ExplorerCollapsedRail.Visibility = visible ? Visibility.Collapsed : Visibility.Visible;
        ExplorerColumn.Width = new GridLength(visible
            ? WindowLayoutConstraints.ExplorerWidth : WindowLayoutConstraints.ExplorerRailWidth);
        UpdateWindowSizeLimits();
    }
}
