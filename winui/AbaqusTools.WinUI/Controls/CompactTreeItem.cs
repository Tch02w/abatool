using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Media;

namespace AbaqusTools.WinUI.Controls;

// Keep WinUI's selection, focus and expansion template; only adjust its spacing.
public sealed class CompactTreeItem : DependencyObject
{
    public static readonly DependencyProperty EnabledProperty = DependencyProperty.RegisterAttached(
        "Enabled", typeof(bool), typeof(CompactTreeItem), new PropertyMetadata(false, OnEnabledChanged));

    public static bool GetEnabled(DependencyObject target) => (bool)target.GetValue(EnabledProperty);
    public static void SetEnabled(DependencyObject target, bool value) => target.SetValue(EnabledProperty, value);

    private static void OnEnabledChanged(DependencyObject target, DependencyPropertyChangedEventArgs args)
    {
        if (target is not TreeViewItem item) return;
        item.Loaded -= OnLoaded;
        item.ActualThemeChanged -= OnThemeChanged;
        if (!(bool)args.NewValue) return;
        item.Loaded += OnLoaded;
        item.ActualThemeChanged += OnThemeChanged;
        if (item.IsLoaded) Apply(item);
    }

    private static void OnLoaded(object sender, RoutedEventArgs args) => Apply((TreeViewItem)sender);
    private static void OnThemeChanged(FrameworkElement sender, object args) => Apply((TreeViewItem)sender);

    private static void Apply(TreeViewItem item)
    {
        item.ApplyTemplate();
        if (Find<Grid>(item, "MultiSelectGrid") is { } content)
        {
            content.SetBinding(Grid.PaddingProperty, new Binding
            {
                Source = item,
                Path = new PropertyPath("TreeViewItemTemplateSettings.Indentation"),
                Converter = new IndentationConverter(),
            });
        }
        if (Find<Grid>(item, "ExpandCollapseChevron") is { } chevron)
            chevron.Padding = new Thickness(8, 0, 8, 0);
    }

    private static T? Find<T>(DependencyObject parent, string name) where T : FrameworkElement
    {
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(parent); index++)
        {
            var child = VisualTreeHelper.GetChild(parent, index);
            if (child is T element && element.Name == name) return element;
            if (Find<T>(child, name) is { } found) return found;
        }
        return null;
    }

    private sealed class IndentationConverter : IValueConverter
    {
        public object Convert(object value, Type targetType, object parameter, string language) =>
            value is Thickness spacing
                ? new Thickness(spacing.Left * (10.0 / 16), spacing.Top, spacing.Right, spacing.Bottom)
                : new Thickness(0);
        public object ConvertBack(object value, Type targetType, object parameter, string language) =>
            throw new NotSupportedException();
    }
}
