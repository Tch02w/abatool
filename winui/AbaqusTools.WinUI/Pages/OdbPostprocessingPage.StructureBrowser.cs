using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using System.Globalization;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private async void OnStructureBrowserClicked(object sender, RoutedEventArgs e)
    {
        var rows = OdbList.SelectedItems.OfType<OdbFileRow>().ToArray();
        if (rows.Length != 1 || rows[0].ScanDetails is not { } scan) return;
        var catalog = scan.StructureCatalog;
        if (catalog.SchemaVersion != 1)
        {
            await new ContentDialog
            {
                XamlRoot = XamlRoot, Title = "需要重新读取结构",
                Content = "这份结构记录尚未包含实例和集合目录。请勾选“本次强制重扫”，再读取结构与默认参数。",
                CloseButtonText = "知道了",
            }.ShowAsync();
            return;
        }

        var panel = new StackPanel { Spacing = 10, MinWidth = 360 };
        panel.Children.Add(new TextBlock
        {
            Text = "只读查看 ODB。这里的部件对应装配实例；节点集与单元集分开列出。单位沿用原模型。",
            TextWrapping = TextWrapping.Wrap,
        });
        var search = new TextBox { PlaceholderText = "搜索实例或集合名称" };
        var regions = new ComboBox { Header = $"对象（{catalog.Regions.Count}）", HorizontalAlignment = HorizontalAlignment.Stretch,
            DisplayMemberPath = nameof(OdbRegionDescriptor.DisplayName), ItemsSource = catalog.Regions };
        var regionDetails = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        regions.SelectionChanged += (_, _) =>
        {
            regionDetails.Text = regions.SelectedItem is OdbRegionDescriptor region
                ? (region.Kind == "node_set" ? $"节点数：{region.NodeCount}" : $"单元数：{region.ElementCount}")
                    + "\n" + string.Join("；", region.ElementTypes.Select(pair => $"{pair.Key}：{pair.Value}"))
                : "请选择一个对象。";
        };
        search.TextChanged += (_, _) =>
        {
            var selectedId = (regions.SelectedItem as OdbRegionDescriptor)?.Id;
            var filtered = catalog.Regions.Where(region => region.DisplayName.Contains(search.Text.Trim(), StringComparison.OrdinalIgnoreCase)).ToArray();
            regions.ItemsSource = filtered;
            regions.SelectedItem = filtered.FirstOrDefault(region => region.Id == selectedId);
        };
        panel.Children.Add(search);
        panel.Children.Add(regions);
        panel.Children.Add(regionDetails);

        var steps = new ComboBox { Header = "分析步", ItemsSource = catalog.Steps,
            DisplayMemberPath = nameof(OdbStepDescriptor.Name), HorizontalAlignment = HorizontalAlignment.Stretch };
        var frames = new ComboBox { Header = "帧", DisplayMemberPath = nameof(OdbFrameDescriptor.DisplayName), HorizontalAlignment = HorizontalAlignment.Stretch };
        var outputs = new TextBlock { TextWrapping = TextWrapping.Wrap, IsTextSelectionEnabled = true };
        frames.SelectionChanged += (_, _) => outputs.Text = frames.SelectedItem is OdbFrameDescriptor frame
            ? (frame.Fields.Count == 0 ? "这一帧没有场输出。" : string.Join("\n", frame.Fields.Select(field =>
                $"{field.Name} · {string.Join(", ", field.Components)} · {string.Join(", ", field.Positions)}")))
            : "请选择分析步和帧。";
        steps.SelectionChanged += (_, _) =>
        {
            frames.ItemsSource = (steps.SelectedItem as OdbStepDescriptor)?.Frames;
            frames.SelectedIndex = (steps.SelectedItem as OdbStepDescriptor)?.Frames.Count > 0 ? 0 : -1;
        };
        panel.Children.Add(steps);
        panel.Children.Add(frames);
        var allFrames = new CheckBox { Content = "提取所选分析步的全部帧（缺失输出将报错）" };
        panel.Children.Add(allFrames);
        var method = new ComboBox { Header = "提取方法（按实际单元类型）", HorizontalAlignment = HorizontalAlignment.Stretch,
            DisplayMemberPath = nameof(OdbRegionExtractionMethod.DisplayName), IsEnabled = false };
        var methodDetails = new TextBlock { TextWrapping = TextWrapping.Wrap };
        var area = new Controls.WorkbenchNumberBox { Header = "统一参考截面积（模型长度单位²，留空则读取截面属性）",
            SpinButtonPlacementMode = NumberBoxSpinButtonPlacementMode.Inline, Minimum = 0,
            PlaceholderText = "留空读取 ODB", HorizontalAlignment = HorizontalAlignment.Stretch, IsEnabled = false, Visibility = Visibility.Collapsed };
        Controls.ParameterHelpButton.AddToHeader(area, "reference-area");
        var acknowledge = new CheckBox { Content = "确认参考面积法不等于有限变形下的当前截面轴力", IsEnabled = false, Visibility = Visibility.Collapsed };
        var sectionFields = new StackPanel { Spacing = 8, Visibility = Visibility.Collapsed };
        var origin = new TextBox { Header = "切面基准点 X, Y, Z（模型长度单位）", Text = "0, 0, 0" };
        var normal = new TextBox { Header = "切面法向量（自动归一化）", Text = "0, 0, 1" };
        var offsets = new TextBox { Header = "沿法向量的切面距离，逗号分隔", PlaceholderText = "例如 100, 200, 300；按模型实际坐标填写" };
        var momentPoint = new TextBox { Header = "弯矩参考点 X, Y, Z（留空使用各切面形心）", PlaceholderText = "固定参考点，或留空" };
        sectionFields.Children.Add(origin);
        sectionFields.Children.Add(normal);
        sectionFields.Children.Add(offsets);
        sectionFields.Children.Add(momentPoint);
        sectionFields.Children.Add(new TextBlock { Text = "沿用旧版：在未变形几何上积分应力。切面位置＝基准点＋距离×单位法向量。仅计算所选实体，不自动补加钢筋。", TextWrapping = TextWrapping.Wrap });
        method.SelectionChanged += (_, _) =>
        {
            var methodKey = (method.SelectedItem as OdbRegionExtractionMethod)?.Key;
            area.IsEnabled = methodKey == "truss_reference_area";
            acknowledge.IsEnabled = area.IsEnabled;
            area.Visibility = area.IsEnabled ? Visibility.Visible : Visibility.Collapsed;
            acknowledge.Visibility = area.Visibility;
            sectionFields.Visibility = methodKey == "solid_section" ? Visibility.Visible : Visibility.Collapsed;
        };
        panel.Children.Add(method);
        panel.Children.Add(methodDetails);
        panel.Children.Add(area);
        panel.Children.Add(acknowledge);
        panel.Children.Add(sectionFields);
        panel.Children.Add(new TextBlock { Text = "梁/钢筋保留单元积分点，不沿构件求和。实体输出截面合力/合矩和参考点；分量按全局坐标，并给出法向轴力、扭矩和弯矩大小。", TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new Expander { Header = "整帧可用输出（不保证所选集合有数据）", Content = outputs,
            HorizontalAlignment = HorizontalAlignment.Stretch, HorizontalContentAlignment = HorizontalAlignment.Stretch });
        var validation = new TextBlock { TextWrapping = TextWrapping.Wrap };
        panel.Children.Add(validation);
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot, Title = "结构与集合 · " + scan.Name, CloseButtonText = "关闭",
            PrimaryButtonText = "提取所选对象", DefaultButton = ContentDialogButton.Close,
            Content = new ScrollViewer { MaxHeight = 560, VerticalScrollBarVisibility = ScrollBarVisibility.Auto, Content = panel },
        };
        regions.SelectionChanged += (_, _) =>
        {
            var eligibility = OdbRegionExtractionMethods.Evaluate(regions.SelectedItem as OdbRegionDescriptor);
            method.ItemsSource = eligibility.Method is { } available
                ? new[] { available } : Array.Empty<OdbRegionExtractionMethod>();
            method.SelectedIndex = eligibility.CanExtract ? 0 : -1;
            method.IsEnabled = eligibility.CanExtract;
            methodDetails.Text = eligibility.Message;
            dialog.IsPrimaryButtonEnabled = eligibility.CanExtract;
            validation.Text = string.Empty;
        };
        dialog.IsPrimaryButtonEnabled = false;
        regions.SelectedIndex = catalog.Regions.Count > 0 ? 0 : -1;
        steps.SelectedIndex = catalog.Steps.Count > 0 ? 0 : -1;
        OdbRegionSectionDefinition? selectedSection = null;
        dialog.PrimaryButtonClick += (dialogSender, args) =>
        {
            var selectedMethodKey = (method.SelectedItem as OdbRegionExtractionMethod)?.Key;
            var eligibility = OdbRegionExtractionMethods.Evaluate(regions.SelectedItem as OdbRegionDescriptor);
            validation.Text = !eligibility.CanExtract ? eligibility.Message
                : !OdbRegionExtractionMethods.IsAllowed(regions.SelectedItem as OdbRegionDescriptor, selectedMethodKey)
                    ? "提取方法与所选对象的实际单元类型不一致，请重新选择对象。"
                : steps.SelectedItem is not OdbStepDescriptor || frames.SelectedItem is not OdbFrameDescriptor
                    ? "请选择分析步和帧。"
                    : selectedMethodKey == "truss_reference_area" && acknowledge.IsChecked is not true
                        ? "请先确认参考面积法的适用限制。"
                        : selectedMethodKey == "truss_reference_area" && !double.IsNaN(area.Value) && (!double.IsFinite(area.Value) || area.Value <= 0)
                            ? "截面积应为正数，或留空读取 ODB。" : string.Empty;
            if (validation.Text.Length == 0 && selectedMethodKey == "solid_section")
            {
                if (!TrySectionNumbers(origin.Text, 3, 3, out var originValues)
                    || !TrySectionNumbers(normal.Text, 3, 3, out var normalValues)
                    || !double.IsFinite(Math.Sqrt(normalValues.Sum(value => value * value)))
                    || Math.Sqrt(normalValues.Sum(value => value * value)) < 1e-12
                    || !TrySectionNumbers(offsets.Text, 1, 1000, out var offsetValues)
                    || offsetValues.Distinct().Count() != offsetValues.Length)
                    validation.Text = "请填写有效的三个坐标、非零法向量和不重复的切面距离。";
                else if (!string.IsNullOrWhiteSpace(momentPoint.Text) && !TrySectionNumbers(momentPoint.Text, 3, 3, out _))
                    validation.Text = "弯矩参考点必须为三个有限数值，或留空使用形心。";
                else
                {
                    TrySectionNumbers(momentPoint.Text, 3, 3, out var point);
                    selectedSection = new OdbRegionSectionDefinition { Origin = originValues, Normal = normalValues,
                        Offsets = offsetValues, MomentReference = point.Length == 3 ? "point" : "centroid",
                        MomentPoint = point.Length == 3 ? point : null };
                }
            }
            args.Cancel = validation.Text.Length > 0;
        };
        if (await dialog.ShowAsync() != ContentDialogResult.Primary) return;
        var selectedRegion = (OdbRegionDescriptor)regions.SelectedItem;
        var selectedMethod = (OdbRegionExtractionMethod)method.SelectedItem;
        var selectedStep = (OdbStepDescriptor)steps.SelectedItem;
        var selectedFrames = allFrames.IsChecked is true ? selectedStep.Frames : new[] { (OdbFrameDescriptor)frames.SelectedItem };
        await RunRegionExtractionAsync(new OdbRegionExtractionRequest
        {
            Root = RootTextBox.Text.Trim(), Path = scan.Path,
            Region = new() { ["scope"] = selectedRegion.Scope, ["instance"] = selectedRegion.Instance,
                ["kind"] = selectedRegion.Kind, ["name"] = selectedRegion.Name },
            Method = selectedMethod.Key,
            Frames = selectedFrames.Select(frame => new OdbRegionFrameSelection { Step = selectedStep.Name, Index = frame.Index }).ToArray(),
            AcknowledgeReferenceArea = selectedMethod.Key == "truss_reference_area" && acknowledge.IsChecked is true,
            ReferenceAreaOverride = selectedMethod.Key == "truss_reference_area" && double.IsFinite(area.Value) ? area.Value : null,
            Section = selectedMethod.Key == "solid_section" ? selectedSection : null,
        }, rows[0]);
    }

    private static bool TrySectionNumbers(string text, int minimum, int maximum, out double[] values)
    {
        values = [];
        var pieces = text.Trim().Replace('，', ',').Split(',', StringSplitOptions.TrimEntries);
        if (pieces.Length < minimum || pieces.Length > maximum) return false;
        var parsed = new double[pieces.Length];
        for (var index = 0; index < pieces.Length; index++)
            if (!double.TryParse(pieces[index], NumberStyles.Float, CultureInfo.InvariantCulture, out parsed[index])
                || !double.IsFinite(parsed[index])) return false;
        values = parsed;
        return true;
    }

    private async Task RunRegionExtractionAsync(OdbRegionExtractionRequest request, OdbFileRow row)
    {
        if (_postprocessBusy || _compatibilityBusy || _discoveryBusy || UpgradeBlocksEditing) return;
        _activePathKeys.Clear();
        _activePathKeys.Add(PathKey(row.Path));
        row.MarkProcessing("排队中", "正在提取所选对象");
        BeginPostprocessMonitoring(request.ClientRequestId, "odb.postprocess.region");
        _activePostprocessOperationId = null;
        _activePostprocessKind = "odb.postprocess.region";
        _lastPostprocessVersion = -1;
        _displayedLogCount = 0;
        PostprocessLogTextBox.Text = string.Empty;
        SetPostprocessBusy(true);
        try
        {
            var initial = await App.Current.ControlPlane.StartOdbRegionExtractionAsync(request);
            _activePostprocessOperationId = initial.OperationId;
            ApplyPostprocessSnapshot(initial);
            var final = await App.Current.ControlPlane.PollOdbPostprocessUntilTerminalAsync(initial,
                new Progress<OdbPostprocessOperationSnapshot>(ApplyPostprocessProgressSnapshot), _postprocessMonitoringSource!.Token);
            ApplyPostprocessSnapshot(final);
            CompletePostprocessOperation(final);
            if (final.Status == "succeeded" && final.Result is { } result)
                foreach (var path in result.Outputs) AppendPostprocessLog("结果目录：" + path);
        }
        catch (Exception exception)
        {
            HandlePostprocessInterruption(exception, "所选对象提取失败");
        }
        finally
        {
            EndPostprocessMonitoring();
        }
    }
}
