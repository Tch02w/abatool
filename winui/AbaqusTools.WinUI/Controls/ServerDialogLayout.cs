using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

namespace AbaqusTools.WinUI.Controls;

/// <summary>Shared geometry for add, edit, and connect server dialogs.</summary>
public static class ServerDialogLayout
{
    public const double DialogWidth = 548;
    public const double InputHeight = 32;

    public static Grid EndpointRow(TextBox host, TextBox port)
    {
        host.Header = null;
        port.Header = null;
        foreach (var field in new[] { host, port })
        {
            field.Height = InputHeight;
            field.MinHeight = InputHeight;
            field.VerticalContentAlignment = VerticalAlignment.Center;
            field.VerticalAlignment = VerticalAlignment.Top;
        }
        port.TextAlignment = TextAlignment.Center;
        var scope = new InputScope();
        scope.Names.Add(new InputScopeName { NameValue = InputScopeNameValue.Number });
        port.InputScope = scope;
        AutomationProperties.SetName(host, "主机名或 IP");
        AutomationProperties.SetName(port, "SSH 端口");

        var row = new Grid { ColumnSpacing = 10, RowSpacing = 4 };
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        row.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(104) });
        row.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        row.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        row.Children.Add(new TextBlock { Text = "主机名或 IP", VerticalAlignment = VerticalAlignment.Center });
        var portHeader = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4 };
        portHeader.Children.Add(new TextBlock { Text = "SSH 端口", VerticalAlignment = VerticalAlignment.Center });
        portHeader.Children.Add(new ParameterHelpButton { Topic = "ssh-port", Title = "SSH 端口" });
        Grid.SetColumn(portHeader, 1);
        row.Children.Add(portHeader);
        Grid.SetRow(host, 1);
        Grid.SetRow(port, 1);
        Grid.SetColumn(port, 1);
        row.Children.Add(host);
        row.Children.Add(port);
        return row;
    }

    public static ScrollViewer Content(StackPanel panel)
    {
        // The stock 548 DIP dialog has about 500 DIP inside its padding. An
        // explicit 560 DIP child overflows that viewport and clips every field.
        panel.Width = double.NaN;
        panel.HorizontalAlignment = HorizontalAlignment.Stretch;
        return new ScrollViewer
        {
            Content = panel,
            MaxHeight = 620,
            Padding = new Thickness(0, 0, 12, 0),
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
            HorizontalScrollMode = ScrollMode.Disabled,
            HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        };
    }

    public static void KeepExistingWidth(ContentDialog dialog)
    {
        dialog.Resources["ContentDialogMinWidth"] = DialogWidth;
        dialog.Resources["ContentDialogMaxWidth"] = DialogWidth;
    }
}
