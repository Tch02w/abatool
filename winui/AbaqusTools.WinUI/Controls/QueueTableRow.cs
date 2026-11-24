using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Data;
using Microsoft.UI.Xaml.Media;
using Windows.UI;
using Microsoft.UI.Text;

namespace AbaqusTools.WinUI.Controls;

public enum QueueTableKind { Candidate, Formal }

/// <summary>Single source of column boundaries, alignment and separators for header and rows.</summary>
public sealed class QueueTableRow : Grid
{
    private sealed record Column(string Title, string? Field, double Width, bool Star = false,
        bool Center = false, bool Bold = false, string? Help = null);

    private static readonly Column[] CandidateColumns =
    [
        new("勾选", null, 44, Center: true), new("序号", "Index", 52, Center: true),
        new("作业名称", "JobName", 190, Bold: true), new("INP 文件路径", "InpPath", 3, Star: true),
        new("加入方式", "Source", 112), new("作业类型", "JobType", 100),
        new("重启动依赖", "OldjobName", 138), new("检查结果", "Message", 2, Star: true)
    ];
    private static readonly Column[] FormalColumns =
    [
        new("勾选", null, 44, Center: true), new("序号", "Index", 52, Center: true),
        new("作业名称", "JobName", 190, Bold: true), new("INP 文件路径", "InpPath", 3, Star: true),
        new("作业类型", "JobType", 100), new("重启动依赖", "OldjobName", 130),
        new("Core", "CoresDisplay", 64, Center: true),
        new("内存", "RuntimeMemoryDisplay", 96, Center: true, Help: "MemoryDetailsDisplay"),
        new("优先级", "PriorityDisplay", 76, Center: true), new("调度", "SchedulingDisplay", 90),
        new("状态", "Status", 100, Bold: true),
        new("备注", "ResultMessageDisplay", 2, Star: true, Help: "ArchiveDetailsDisplay")
    ];

    public static readonly DependencyProperty KindProperty = DependencyProperty.Register(
        nameof(Kind), typeof(QueueTableKind), typeof(QueueTableRow),
        new PropertyMetadata(QueueTableKind.Candidate, Rebuild));
    public static readonly DependencyProperty IsHeaderProperty = DependencyProperty.Register(
        nameof(IsHeader), typeof(bool), typeof(QueueTableRow), new PropertyMetadata(false, Rebuild));

    public QueueTableKind Kind
    {
        get => (QueueTableKind)GetValue(KindProperty);
        set => SetValue(KindProperty, value);
    }
    public bool IsHeader
    {
        get => (bool)GetValue(IsHeaderProperty);
        set => SetValue(IsHeaderProperty, value);
    }

    public event RoutedEventHandler? CandidateCheckClicked;
    private readonly SolidColorBrush _separator = new();

    public QueueTableRow()
    {
        ActualThemeChanged += (_, _) => UpdateSeparator();
        Loaded += (_, _) => UpdateSeparator();
        BuildCells();
    }

    private static void Rebuild(DependencyObject sender, DependencyPropertyChangedEventArgs args) =>
        ((QueueTableRow)sender).BuildCells();

    private void BuildCells()
    {
        Children.Clear();
        ColumnDefinitions.Clear();
        MinHeight = IsHeader ? 34 : 40;
        var columns = Kind == QueueTableKind.Candidate ? CandidateColumns : FormalColumns;
        for (var index = 0; index < columns.Length; index++)
        {
            var column = columns[index];
            ColumnDefinitions.Add(new ColumnDefinition
            {
                Width = new GridLength(column.Width, column.Star ? GridUnitType.Star : GridUnitType.Pixel)
            });
            FrameworkElement content;
            if (IsHeader || column.Field is not null)
            {
                var text = new TextBlock
                {
                    VerticalAlignment = VerticalAlignment.Center,
                    HorizontalAlignment = column.Center ? HorizontalAlignment.Center : HorizontalAlignment.Stretch,
                    TextAlignment = column.Center ? TextAlignment.Center : TextAlignment.Left,
                    TextTrimming = TextTrimming.CharacterEllipsis,
                    TextWrapping = TextWrapping.NoWrap,
                    FontWeight = !IsHeader && column.Bold ? FontWeights.SemiBold : FontWeights.Normal
                };
                if (IsHeader) text.Text = column.Title;
                else
                {
                    text.SetBinding(TextBlock.TextProperty, Field(column.Field!));
                    text.SetBinding(ToolTipService.ToolTipProperty,
                        Field(column.Help ?? column.Field!));
                }
                content = text;
            }
            else
            {
                var check = new CheckBox
                {
                    MinWidth = 20, MinHeight = 20, Padding = new Thickness(0),
                    HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center
                };
                AutomationProperties.SetName(check, Kind == QueueTableKind.Candidate ? "加入队列" : "选择作业");
                if (Kind == QueueTableKind.Candidate)
                {
                    check.SetBinding(CheckBox.IsCheckedProperty, Field("Selected"));
                    check.Click += (sender, args) => CandidateCheckClicked?.Invoke(sender, args);
                }
                else
                {
                    check.Loaded += (_, _) =>
                    {
                        DependencyObject? parent = this;
                        while (parent is not null && parent is not ListViewItem)
                            parent = VisualTreeHelper.GetParent(parent);
                        if (parent is ListViewItem item)
                            check.SetBinding(CheckBox.IsCheckedProperty, new Binding
                            { Source = item, Path = new PropertyPath("IsSelected"), Mode = BindingMode.TwoWay });
                    };
                }
                content = check;
            }
            var cell = new Border
            {
                Child = content, Padding = new Thickness(column.Field is null ? 0 : 8, 0,
                    column.Field is null ? 0 : 8, 0),
                BorderBrush = _separator, BorderThickness = new Thickness(0, 0, index < columns.Length - 1 ? 1 : 0, 1)
            };
            SetColumn(cell, index);
            Children.Add(cell);
        }
        UpdateSeparator();
    }

    private static Binding Field(string field) => new() { Path = new PropertyPath(field), Mode = BindingMode.OneWay };

    private void UpdateSeparator() => _separator.Color = ActualTheme == ElementTheme.Dark
        ? Color.FromArgb(28, 255, 255, 255) : Color.FromArgb(22, 0, 0, 0);
}
