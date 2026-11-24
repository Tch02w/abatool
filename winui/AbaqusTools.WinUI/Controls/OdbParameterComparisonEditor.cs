using System.Globalization;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Windows.UI;

namespace AbaqusTools.WinUI.Controls;

/// <summary>Shows a bounded set of model columns and one editor for the selected cell.</summary>
public sealed class OdbParameterComparisonEditor : UserControl
{
    private readonly IReadOnlyList<OdbFileRow> _rows;
    private readonly ComboBox _source = new() { Header = "当前模型", HorizontalAlignment = HorizontalAlignment.Stretch };
    private readonly Button _copy = new() { VerticalAlignment = VerticalAlignment.Bottom };
    private readonly Button _previous = new() { Content = "上一页" };
    private readonly Button _next = new() { Content = "下一页" };
    private readonly StackPanel _pager = new() { Orientation = Orientation.Horizontal, Spacing = 7 };
    private readonly TextBlock _position = new() { VerticalAlignment = VerticalAlignment.Center };
    private readonly Grid _table = new();
    private readonly ScrollViewer _viewport = new() { VerticalScrollBarVisibility = ScrollBarVisibility.Auto,
        HorizontalScrollMode = ScrollMode.Disabled, HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
        HorizontalContentAlignment = HorizontalAlignment.Stretch };
    private readonly ContentControl _input = new() { HorizontalContentAlignment = HorizontalAlignment.Stretch };
    private readonly Button _reset = new() { Content = "恢复原值" };
    private readonly TextBlock _target = new() { TextWrapping = TextWrapping.Wrap };
    private readonly TextBlock _notice = new() { TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed,
        IsTextSelectionEnabled = true };
    private readonly TextBox _details = new() { AcceptsReturn = true, IsReadOnly = true,
        TextWrapping = TextWrapping.Wrap, MaxHeight = 100 };
    private readonly Expander _summary = new() { HorizontalAlignment = HorizontalAlignment.Stretch,
        HorizontalContentAlignment = HorizontalAlignment.Stretch };
    private readonly HashSet<string> _checked = [];
    private readonly HashSet<(int Row, string Key)> _changes = [];
    private readonly int[] _changesPerModel;
    private readonly Dictionary<(int Row, string Key), Button> _cells = [];
    private readonly SolidColorBrush _line = new();
    private int _pageSize = 2;
    private int _first;
    private int _current;
    private int _changedModels;
    private string _field = "StartStep";
    private bool _switching;

    public OdbPostprocessParameterComparison Session { get; }

    public OdbParameterComparisonEditor(IReadOnlyList<OdbFileRow> rows)
    {
        _rows = rows;
        Session = new(rows);
        _changesPerModel = new int[rows.Count];
        HorizontalContentAlignment = HorizontalAlignment.Stretch;
        var layout = new StackPanel { Spacing = 6 };
        var toolbar = new Grid { ColumnSpacing = 8 };
        toolbar.ColumnDefinitions.Add(new() { Width = new(1, GridUnitType.Star) });
        toolbar.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        _source.ItemsSource = rows.Select(ModelLabel).ToArray();
        _source.SelectedIndex = 0;
        _source.SelectionChanged += (_, _) =>
        {
            if (!_switching && _source.SelectedIndex >= 0) FocusCell(_rows[_source.SelectedIndex].Path, _field);
        };
        toolbar.Children.Add(_source);
        _copy.Content = $"将勾选字段应用到其余 {rows.Count - 1} 个模型";
        _copy.Click += (_, _) => CopyCheckedFields();
        Grid.SetColumn(_copy, 1);
        toolbar.Children.Add(_copy);
        layout.Children.Add(toolbar);

        _previous.Click += (_, _) => FocusCell(_rows[Math.Max(0, _first - _pageSize)].Path, _field);
        _next.Click += (_, _) => FocusCell(_rows[Math.Min(rows.Count - 1, _first + _pageSize)].Path, _field);
        _pager.Children.Add(_previous);
        _pager.Children.Add(_next);
        _pager.Children.Add(_position);
        layout.Children.Add(_pager);
        _viewport.Content = _table;
        _viewport.MaxHeight = 350;
        layout.Children.Add(_viewport);
        layout.Children.Add(_target);
        var editing = new Grid { ColumnSpacing = 6 };
        editing.ColumnDefinitions.Add(new() { Width = new(1, GridUnitType.Star) });
        editing.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        editing.Children.Add(_input);
        Grid.SetColumn(_reset, 1);
        _reset.Click += (_, _) =>
        {
            Edit(_current, Field(_field), Session.GetOriginalValue(_rows[_current].Path, _field));
            ShowEditor();
        };
        editing.Children.Add(_reset);
        layout.Children.Add(editing);
        _summary.Content = _details;
        _summary.Expanding += (_, _) => UpdateDetails();
        layout.Children.Add(_summary);
        layout.Children.Add(_notice);
        Content = layout;

        AutomationProperties.SetAutomationId(_source, "ComparisonSource");
        AutomationProperties.SetAutomationId(_copy, "ComparisonApplyFields");
        AutomationProperties.SetAutomationId(_previous, "ComparisonPrevious");
        AutomationProperties.SetAutomationId(_next, "ComparisonNext");
        AutomationProperties.SetAutomationId(_summary, "ComparisonChanges");
        AutomationProperties.SetAutomationId(_reset, "ComparisonResetValue");
        AutomationProperties.SetLiveSetting(_notice, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        ActualThemeChanged += (_, _) => UpdateTheme();
        SizeChanged += (_, e) =>
        {
            var size = e.NewSize.Width >= 730 ? 3 : 2;
            if (_pageSize == size) return;
            _pageSize = size;
            ShowPage(_current / size * size);
        };
        UpdateTheme();
        ShowPage(0);
        ShowEditor();
        UpdateSummary();
    }

    public void FitHeight(double windowHeight) =>
        _viewport.MaxHeight = Math.Clamp(windowHeight - 405, 120, 520);

    private static string ModelLabel(OdbFileRow row) => string.IsNullOrEmpty(row.RelativePath) ? row.Name : row.RelativePath;

    private void UpdateTheme() => _line.Color = ActualTheme == ElementTheme.Dark
        ? Color.FromArgb(35, 255, 255, 255) : Color.FromArgb(28, 0, 0, 0);

    private void ShowPage(int start)
    {
        _first = Math.Clamp(start, 0, (_rows.Count - 1) / _pageSize * _pageSize);
        var end = Math.Min(_rows.Count, _first + _pageSize);
        _position.Text = $"模型 {_first + 1}–{end} / {_rows.Count}";
        _pager.Visibility = _rows.Count > _pageSize ? Visibility.Visible : Visibility.Collapsed;
        _previous.IsEnabled = _first > 0;
        _next.IsEnabled = end < _rows.Count;
        _table.Children.Clear();
        _table.RowDefinitions.Clear();
        _table.ColumnDefinitions.Clear();
        _cells.Clear();
        _table.ColumnDefinitions.Add(new() { Width = new(145) });
        for (var i = _first; i < end; i++) _table.ColumnDefinitions.Add(new() { Width = new(1, GridUnitType.Star) });
        _table.RowDefinitions.Add(new() { Height = GridLength.Auto });
        AddCell(new TextBlock { Text = "应用字段", FontWeight = FontWeights.SemiBold, Margin = new(7, 4, 4, 4) }, 0, 0);
        for (var i = _first; i < end; i++)
        {
            var title = new TextBlock { Text = ModelLabel(_rows[i]), FontWeight = FontWeights.SemiBold,
                TextTrimming = TextTrimming.CharacterEllipsis, Margin = new(7, 4, 4, 4) };
            ToolTipService.SetToolTip(title, _rows[i].Path);
            AddCell(title, 0, i - _first + 1);
        }
        var r = 1;
        foreach (var field in OdbPostprocessParameterComparison.Fields)
        {
            _table.RowDefinitions.Add(new() { Height = GridLength.Auto });
            var heading = new CheckBox { Content = field.Label, IsChecked = _checked.Contains(field.Key),
                MinWidth = 0, Padding = new(3, 0, 2, 0) };
            AutomationProperties.SetAutomationId(heading, "ComparisonField_" + field.Key);
            AutomationProperties.SetName(heading, "批量应用 " + field.Label);
            heading.Checked += (_, _) => { _checked.Add(field.Key); _copy.IsEnabled = true; };
            heading.Unchecked += (_, _) => { _checked.Remove(field.Key); _copy.IsEnabled = _checked.Count > 0; };
            AddCell(heading, r, 0);
            for (var i = _first; i < end; i++)
            {
                var rowIndex = i;
                var cell = new Button { MinWidth = 0, Padding = new(7, 1, 4, 1), BorderThickness = new(0),
                    Background = new SolidColorBrush(Microsoft.UI.Colors.Transparent),
                    HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Left,
                    Content = new TextBlock { TextTrimming = TextTrimming.CharacterEllipsis } };
                cell.Click += (_, _) => FocusCell(_rows[rowIndex].Path, field.Key);
                AutomationProperties.SetAutomationId(cell, $"ComparisonCell_{rowIndex}_{field.Key}");
                _cells[(rowIndex, field.Key)] = cell;
                AddCell(cell, r, i - _first + 1);
                UpdateCell(rowIndex, field);
            }
            r++;
        }
        _copy.IsEnabled = _checked.Count > 0;
        if (_summary.IsExpanded) UpdateDetails();
    }

    private void AddCell(FrameworkElement element, int row, int column)
    {
        var border = new Border { Child = element, BorderBrush = _line, BorderThickness = new(0, 0, 1, 1) };
        Grid.SetRow(border, row);
        Grid.SetColumn(border, column);
        _table.Children.Add(border);
    }

    private static string Display(string field, string value) => (field, value) switch
    {
        ("FrameMode", "auto") => "关键帧（自动）", ("FrameMode", "all") => "全部帧",
        ("FrameMode", "manual") => "手动帧序号", ("ReinforcementMode", "none") => "无纵筋",
        ("ReinforcementMode", "required") => "有纵筋", (_, "") => "（空）", _ => value
    };

    private void UpdateCell(int index, OdbComparisonField field)
    {
        if (!_cells.TryGetValue((index, field.Key), out var cell)) return;
        var path = _rows[index].Path;
        var text = (TextBlock)cell.Content;
        text.Text = Display(field.Key, Session.GetValue(path, field.Key));
        var changed = _changes.Contains((index, field.Key));
        text.FontWeight = changed || index == _current && field.Key == _field ? FontWeights.SemiBold : FontWeights.Normal;
        var name = $"{ModelLabel(_rows[index])} · {field.Label} · {text.Text}";
        AutomationProperties.SetName(cell, name);
        ToolTipService.SetToolTip(cell, changed ? name + "（原值 " + Display(field.Key, Session.GetOriginalValue(path, field.Key)) + "）" : name);
    }

    public void FocusCell(string path, string key)
    {
        int index = -1;
        for (var i = 0; i < _rows.Count; i++)
            if (string.Equals(_rows[i].Path, path, StringComparison.OrdinalIgnoreCase)) { index = i; break; }
        if (index < 0) throw new InvalidOperationException("模型已离开当前对照范围。");
        var previous = (_current, _field);
        _current = index;
        _field = key;
        _switching = true;
        try { _source.SelectedIndex = index; }
        finally { _switching = false; }
        if (index < _first || index >= _first + _pageSize) ShowPage(index / _pageSize * _pageSize);
        UpdateCell(previous.Item1, Field(previous.Item2));
        UpdateCell(index, Field(key));
        ShowEditor();
        if (_input.Content is Control control) control.Focus(FocusState.Programmatic);
    }

    private static OdbComparisonField Field(string key) =>
        OdbPostprocessParameterComparison.Fields.First(field => field.Key == key);

    private void ShowEditor()
    {
        var index = _current;
        var row = _rows[index];
        var field = Field(_field);
        var raw = Session.GetValue(row.Path, field.Key);
        var choices = Session.GetChoices(row.Path, field.Key);
        _target.Text = $"编辑 {ModelLabel(row)} · {field.Label}";
        if (field.Key is "RebarSet" or "LongitudinalMaterial" or "RebarDiameterMm"
            && Session.GetValue(row.Path, "ReinforcementMode") == "none")
            _target.Text += "（当前模型无纵筋）";
        _reset.IsEnabled = _changes.Contains((index, field.Key));
        Control input;
        if (field.Key is "RebarDiameterMm" or "PrefractureSequenceIndex")
        {
            var number = new WorkbenchNumberBox { Minimum = field.Key == "RebarDiameterMm" ? 1 : -1,
                Maximum = field.Key == "RebarDiameterMm" ? 100 : 1_000_000,
                HorizontalAlignment = HorizontalAlignment.Left, Width = 200,
                ValidationMode = NumberBoxValidationMode.Disabled };
            number.Text = double.TryParse(raw, NumberStyles.Float, CultureInfo.InvariantCulture, out var val)
                ? val.ToString(CultureInfo.CurrentCulture) : raw;
            number.RegisterPropertyChangedCallback(NumberBox.TextProperty, (_, _) =>
            {
                var value = double.TryParse(number.Text, NumberStyles.Float, CultureInfo.CurrentCulture, out var parsed)
                    ? parsed.ToString("R", CultureInfo.InvariantCulture) : number.Text;
                Edit(index, field, value);
            });
            input = number;
        }
        else if (choices.Count > 0)
        {
            var options = choices.Contains(raw, StringComparer.Ordinal) ? choices.ToList() : choices.Append(raw).ToList();
            var combo = new ComboBox { HorizontalAlignment = HorizontalAlignment.Stretch,
                ItemsSource = options.Select(value => Display(field.Key, value)).ToArray(), SelectedIndex = options.IndexOf(raw) };
            combo.SelectionChanged += (_, _) => { if (combo.SelectedIndex >= 0) Edit(index, field, options[combo.SelectedIndex]); };
            input = combo;
        }
        else
        {
            var box = new TextBox { Text = raw, HorizontalAlignment = HorizontalAlignment.Stretch };
            box.TextChanged += (_, _) => Edit(index, field, box.Text);
            input = box;
        }
        AutomationProperties.SetName(input, _target.Text);
        AutomationProperties.SetAutomationId(input, "ComparisonValue_" + field.Key);
        _input.Content = input;
    }

    private void Edit(int index, OdbComparisonField field, string value)
    {
        Session.SetValue(_rows[index].Path, field.Key, value);
        TrackChange(index, field);
        _notice.Visibility = Visibility.Collapsed;
        UpdateSummary();
    }

    private void TrackChange(int index, OdbComparisonField field)
    {
        var path = _rows[index].Path;
        var key = (index, field.Key);
        var changed = Session.GetOriginalValue(path, field.Key) != Session.GetValue(path, field.Key);
        if (changed && _changes.Add(key))
        {
            _changesPerModel[index]++;
            if (_changesPerModel[index] == 1) _changedModels++;
        }
        else if (!changed && _changes.Remove(key))
        {
            _changesPerModel[index]--;
            if (_changesPerModel[index] == 0) _changedModels--;
        }
        if (index == _current && field.Key == _field) _reset.IsEnabled = _changes.Contains(key);
        UpdateCell(index, field);
    }

    private void CopyCheckedFields()
    {
        if (_checked.Count == 0) return;
        var targets = _rows.Where((_, index) => index != _current).Select(row => row.Path).ToArray();
        Session.CopyFields(_rows[_current].Path, targets, _checked);
        foreach (var field in OdbPostprocessParameterComparison.Fields.Where(field => _checked.Contains(field.Key)))
            for (var i = 0; i < _rows.Count; i++) if (i != _current) TrackChange(i, field);
        _notice.Visibility = Visibility.Collapsed;
        UpdateSummary();
        _summary.IsExpanded = _changes.Count > 0;
    }

    private void UpdateSummary()
    {
        _summary.Header = _changes.Count == 0 ? "暂无修改" : $"待保存 · {_changedModels} 个模型 · {_changes.Count} 项修改";
        if (_summary.IsExpanded) UpdateDetails();
    }

    private void UpdateDetails()
    {
        var lines = new List<string>();
        for (var i = _first; i < Math.Min(_rows.Count, _first + _pageSize); i++)
        {
            var row = _rows[i];
            foreach (var field in OdbPostprocessParameterComparison.Fields)
                if (_changes.Contains((i, field.Key)))
                    lines.Add($"{ModelLabel(row)} · {field.Label}　{Display(field.Key, Session.GetOriginalValue(row.Path, field.Key))} → {Display(field.Key, Session.GetValue(row.Path, field.Key))}");
        }
        if (_rows.Count > _pageSize) lines.Insert(0, $"当前页的修改（模型 {_first + 1}–{Math.Min(_first + _pageSize, _rows.Count)}）");
        _details.Text = string.Join(Environment.NewLine, lines);
    }

    public Dictionary<string, string> CaptureDraft() => _changes.OrderBy(c => c.Row).ThenBy(c => c.Key)
        .ToDictionary(c => c.Row.ToString(CultureInfo.InvariantCulture) + "/" + c.Key,
            c => Session.GetValue(_rows[c.Row].Path, c.Key));

    public void RestoreDraft(IReadOnlyDictionary<string, string> values)
    {
        foreach (var c in _changes.ToArray())
        {
            var path = _rows[c.Row].Path;
            Session.SetValue(path, c.Key, Session.GetOriginalValue(path, c.Key));
            TrackChange(c.Row, Field(c.Key));
        }
        foreach (var (key, value) in values)
        {
            var parts = key.Split('/', 2);
            if (parts.Length != 2 || !int.TryParse(parts[0], out var index) || index < 0 || index >= _rows.Count)
                throw new InvalidDataException("对照草稿的模型位置无效。");
            Session.SetValue(_rows[index].Path, parts[1], value);
            TrackChange(index, Field(parts[1]));
        }
        ShowEditor();
        UpdateSummary();
    }

    public void ShowError(string message)
    {
        _notice.Text = message;
        _notice.Visibility = Visibility.Visible;
    }
}
