using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Controls;

/// <summary>A fixed header and virtualized rows share one horizontal viewport and column schema.</summary>
public sealed partial class QueueTableView : UserControl
{
    public QueueTableView()
    {
        InitializeComponent();
        ApplyKind();
    }

    public static readonly DependencyProperty KindProperty = DependencyProperty.Register(
        nameof(Kind), typeof(QueueTableKind), typeof(QueueTableView),
        new PropertyMetadata(QueueTableKind.Candidate, (sender, _) => ((QueueTableView)sender).ApplyKind()));

    public QueueTableKind Kind
    {
        get => (QueueTableKind)GetValue(KindProperty);
        set => SetValue(KindProperty, value);
    }

    public ListView List => Rows;
    public event RoutedEventHandler? CandidateCheckClicked;

    private void ApplyKind()
    {
        if (Rows is null) return;
        ColumnHeader.Kind = Kind;
        Rows.ItemTemplate = (DataTemplate)Resources[Kind == QueueTableKind.Candidate
            ? "CandidateRowTemplate" : "FormalRowTemplate"];
        UpdateWidth();
    }

    private void OnCandidateCheckClicked(object sender, RoutedEventArgs args) =>
        CandidateCheckClicked?.Invoke(sender, args);

    private void OnViewportSizeChanged(object sender, SizeChangedEventArgs args) => UpdateWidth();

    private void UpdateWidth()
    {
        // Reserve the same scrollbar gutter in the header and list, including when it is hidden.
        var minimum = Kind == QueueTableKind.Candidate ? 1120 : 1360;
        TableContent.Width = Math.Max(minimum, HorizontalViewport.ActualWidth);
    }
}
