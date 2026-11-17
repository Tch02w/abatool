using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Windows.ApplicationModel.DataTransfer;

namespace AbaqusTools.WinUI.Controls;

public sealed partial class ResultPreviewTable : UserControl
{
    private ResultTablePreview? _table;
    private bool _truncated;

    public ResultPreviewTable() => InitializeComponent();

    public void Show(ResultPreviewResponse preview)
    {
        _table = new(preview.Headers, preview.Rows);
        _truncated = preview.Truncated;
        Draw(resetRows: true);
    }

    public void Clear()
    {
        _table = null;
        foreach (var grid in new[] { HeaderGrid, CellsGrid })
        {
            grid.Children.Clear();
            grid.ColumnDefinitions.Clear();
            grid.RowDefinitions.Clear();
        }
    }

    private void OnPrevious(object sender, RoutedEventArgs e) { _table?.Previous(); Draw(false); }
    private void OnNext(object sender, RoutedEventArgs e) { _table?.Next(); Draw(false); }

    private void OnCopy(object sender, RoutedEventArgs e)
    {
        if (_table is null) return;
        try
        {
            var data = new DataPackage();
            data.SetText(_table.ToClipboardText());
            Clipboard.SetContent(data);
            Summary.Text = $"已复制预览（{_table.RowCount} 行数据，{_table.ColumnCount} 列）";
        }
        catch (Exception) { Summary.Text = "无法写入剪贴板，请重试。"; }
    }

    private void Draw(bool resetRows)
    {
        if (_table is not { } table) return;
        foreach (var grid in new[] { HeaderGrid, CellsGrid })
        {
            grid.Children.Clear();
            grid.ColumnDefinitions.Clear();
            grid.RowDefinitions.Clear();
        }
        var paged = table.ColumnCount > ResultTablePreview.ColumnsPerView;
        PreviousColumns.Visibility = NextColumns.Visibility = paged ? Visibility.Visible : Visibility.Collapsed;
        PreviousColumns.IsEnabled = table.HasPrevious;
        NextColumns.IsEnabled = table.HasNext;
        CopyTable.IsEnabled = table.ColumnCount > 0;
        Summary.Text = table.ColumnCount == 0 ? "表格为空。" :
            $"预览{(_truncated ? "前 " : " ")}{table.RowCount} 行数据 · {table.ColumnCount} 列"
            + (paged ? $"（当前第 {table.FirstColumn + 1}–{table.EndColumn} 列）" : "");
        for (var r = 0; r < table.RowCount; r++)
            CellsGrid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        for (var c = table.FirstColumn; c < table.EndColumn; c++)
        {
            var column = c - table.FirstColumn;
            var chars = Math.Max(table.Header(c).Length,
                Enumerable.Range(0, table.RowCount).Select(r => table.Cell(r, c).Length).DefaultIfEmpty().Max());
            var width = new GridLength(Math.Clamp(chars * 9d + 24, 96, 260));
            HeaderGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = width });
            CellsGrid.ColumnDefinitions.Add(new ColumnDefinition { Width = width });
            AddCell(HeaderGrid, 0, column, table.Header(c), table.Header(c), true);
            for (var r = 0; r < table.RowCount; r++)
                AddCell(CellsGrid, r, column, table.Cell(r, c), table.Header(c), false);
        }
        ColumnsScroll.ChangeView(0, null, null, true);
        if (resetRows) RowsScroll.ChangeView(null, 0, null, true);
    }

    private static void AddCell(Grid grid, int row, int column, string value, string header, bool isHeader)
    {
        var text = new TextBlock
        {
            Text = value, Margin = new Thickness(8, 4, 8, 4), IsTextSelectionEnabled = true,
            TextTrimming = TextTrimming.CharacterEllipsis, MaxLines = 2, TextWrapping = TextWrapping.Wrap,
        };
        if (isHeader) text.FontWeight = Microsoft.UI.Text.FontWeights.SemiBold;
        else AutomationProperties.SetName(text, $"第 {row + 1} 行，{header}：{value}");
        if (value.Length > 0) ToolTipService.SetToolTip(text, value);
        Grid.SetRow(text, row);
        Grid.SetColumn(text, column);
        grid.Children.Add(text);
    }
}
