using System.Text.Json;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Controls;

/// <summary>One editor for new jobs and queue edits; defaults never override Abaqus.</summary>
public sealed class ExecutionOptionsEditor : StackPanel
{
    private readonly CheckBox _overrideGpu = new() { Content = "指定", VerticalAlignment = VerticalAlignment.Center };
    private readonly WorkbenchNumberBox _gpu = new() { Minimum = 0, Maximum = 1024, Value = 0,
        SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline, IsEnabled = false };
    private readonly ComboBox _explicit = CreateChoices([
        ("default", "遵循环境配置"), ("off", "单精度"), ("explicit", "分析双精度"),
        ("both", "预处理和分析双精度"), ("constraint", "仅约束双精度")]);
    private readonly ComboBox _output = CreateChoices([
        ("default", "遵循环境配置"), ("single", "单精度场输出"), ("full", "全精度场输出")]);
    private readonly TextBlock _error = new() { TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed };
    private readonly Button _resetDraft = new() { Content = "恢复默认设置", Visibility = Visibility.Collapsed };
    private string? _unrestoredDraft;

    public ExecutionOptionsEditor()
    {
        Spacing = 12;
        var gpuInput = new Grid { ColumnSpacing = 10 };
        gpuInput.ColumnDefinitions.Add(new() { Width = GridLength.Auto });
        gpuInput.ColumnDefinitions.Add(new() { Width = new(1, GridUnitType.Star) });
        Grid.SetColumn(_gpu, 1);
        gpuInput.Children.Add(_overrideGpu); gpuInput.Children.Add(_gpu);
        _overrideGpu.Checked += (_, _) => _gpu.IsEnabled = true;
        _overrideGpu.Unchecked += (_, _) => _gpu.IsEnabled = false;
        Children.Add(Row("GPU 数量", "gpu-count", gpuInput));
        Children.Add(Row("Explicit 计算精度", "explicit-precision", _explicit));
        Children.Add(Row("ODB 场输出精度", "output-precision", _output));
        Children.Add(_error);
        Children.Add(_resetDraft);
        _resetDraft.Click += (_, _) => {
            SetValue(new()); _unrestoredDraft = null;
            _error.Visibility = _resetDraft.Visibility = Visibility.Collapsed;
        };
    }

    public ExecutionOptionsValues ReadValue()
    {
        if (_unrestoredDraft is not null)
            throw new ControlPlaneException("GPU 与精度草稿未能恢复，请展开设置并选择恢复默认设置后重新填写。");
        // NumberBox validates on focus loss; do not round a fractional GPU count.
        int? count = null;
        if (_overrideGpu.IsChecked is true)
        {
            if (!double.IsFinite(_gpu.Value) || _gpu.Value != Math.Truncate(_gpu.Value))
                throw new ControlPlaneException("GPU 数量必须填写整数；0 表示关闭 GPU。");
            count = checked((int)_gpu.Value);
        }
        var value = new ExecutionOptionsValues { GpuCount = count,
            ExplicitPrecision = Choice(_explicit), OutputPrecision = Choice(_output) };
        if (!value.IsValid) throw new ControlPlaneException("GPU 或精度选项无效，请重新选择。");
        return value;
    }

    public void SetValue(ExecutionOptionsValues value)
    {
        if (!value.IsValid) throw new ControlPlaneException("队列中的 GPU 或精度选项无效，未覆盖原记录。");
        _overrideGpu.IsChecked = value.GpuCount is not null;
        _gpu.Value = value.GpuCount ?? 0;
        Select(_explicit, value.ExplicitPrecision); Select(_output, value.OutputPrecision);
    }

    public string CaptureDraft() => _unrestoredDraft ?? JsonSerializer.Serialize(new ExecutionOptionsDraft {
        OverrideGpu = _overrideGpu.IsChecked is true, GpuText = _gpu.Text,
        ExplicitPrecision = Choice(_explicit), OutputPrecision = Choice(_output) });

    public void RestoreDraft(string value)
    {
        try
        {
            var draft = ExecutionOptionsDraft.Parse(value);
            _overrideGpu.IsChecked = draft.OverrideGpu; _gpu.Text = draft.GpuText;
            Select(_explicit, draft.ExplicitPrecision); Select(_output, draft.OutputPrecision);
        }
        catch (Exception error) when (error is JsonException or InvalidDataException)
        {
            _unrestoredDraft = value;
            _error.Text = "GPU 与精度草稿未能恢复，请重新设置。";
            _error.Visibility = _resetDraft.Visibility = Visibility.Visible;
        }
    }

    private static string Choice(ComboBox box) => (box.SelectedItem as ComboBoxItem)?.Tag as string ?? "default";
    private static void Select(ComboBox box, string value) => box.SelectedItem = box.Items.Cast<ComboBoxItem>().First(item => (string)item.Tag == value);
    private static ComboBox CreateChoices((string Key, string Label)[] values)
    {
        var box = new ComboBox { HorizontalAlignment = HorizontalAlignment.Stretch, MinHeight = 40,
            VerticalContentAlignment = VerticalAlignment.Center };
        foreach (var (key, label) in values) box.Items.Add(new ComboBoxItem { Tag = key, Content = label });
        box.SelectedIndex = 0; return box;
    }
    private static Grid Row(string title, string topic, FrameworkElement input)
    {
        var grid = new Grid { ColumnSpacing = 10 };
        grid.ColumnDefinitions.Add(new() { Width = new(150) });
        grid.ColumnDefinitions.Add(new() { Width = new(1, GridUnitType.Star) });
        var label = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 4, VerticalAlignment = VerticalAlignment.Center };
        label.Children.Add(new TextBlock { Text = title, VerticalAlignment = VerticalAlignment.Center });
        label.Children.Add(new ParameterHelpButton { Title = title, Topic = topic });
        Grid.SetColumn(input, 1); grid.Children.Add(label); grid.Children.Add(input); return grid;
    }
}
