using System.Text;

namespace AbaqusTools.WinUI.Services;

// Keep original cell strings (including leading zeroes and embedded line breaks).
// Only a window of columns needs XAML elements, even for very wide spreadsheets.
internal sealed class ResultTablePreview(IReadOnlyList<string> headers, IReadOnlyList<IReadOnlyList<string>> rows)
{
    public const int ColumnsPerView = 8;
    public int ColumnCount { get; } = Math.Max(headers.Count, rows.Count == 0 ? 0 : rows.Max(row => row.Count));
    public int RowCount => rows.Count;
    public int FirstColumn { get; private set; }
    public int EndColumn => Math.Min(FirstColumn + ColumnsPerView, ColumnCount);
    public bool HasPrevious => FirstColumn > 0;
    public bool HasNext => EndColumn < ColumnCount;
    public void Next() { if (HasNext) FirstColumn = EndColumn; }
    public void Previous() => FirstColumn = Math.Max(FirstColumn - ColumnsPerView, 0);
    public string Header(int col) => col < headers.Count && headers[col].Length > 0 ? headers[col] : $"列 {col + 1}";
    public string Cell(int row, int col) => col < rows[row].Count ? rows[row][col] : "";

    public string ToClipboardText()
    {
        var text = new StringBuilder();
        void AddRow(Func<int, string> value)
        {
            for (var col = 0; col < ColumnCount; col++)
            {
                if (col > 0) text.Append('\t');
                var cell = value(col);
                if (cell.IndexOfAny(['\t', '\r', '\n', '"']) < 0) text.Append(cell);
                else text.Append('"').Append(cell.Replace("\"", "\"\"")).Append('"');
            }
        }
        AddRow(col => col < headers.Count ? headers[col] : "");
        for (int row = 0; row < RowCount; row++)
        {
            text.AppendLine();
            AddRow(col => Cell(row, col));
        }
        return text.ToString();
    }
}
