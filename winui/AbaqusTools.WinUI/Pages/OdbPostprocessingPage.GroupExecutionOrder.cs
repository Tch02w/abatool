using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private async void OnGroupExecutionOrderClicked(object sender, RoutedEventArgs args)
    {
        if (!GroupExecutionOrderButton.IsEnabled) return;
        const string title = "对比组执行顺序";
        var root = _lastDiscoveryRoot;
        var catalog = KnownGroupNames();
        var selected = OdbList.SelectedItems.OfType<OdbFileRow>();
        var occurrences = selected.Concat(_odbItems).SelectMany(row => ParseGroupNames(row.ComparisonGroup));
        var defaultNames = OdbComparisonGroups.OrderGroupNames(occurrences.Concat(catalog), []);
        var draft = new ObservableCollection<string>(OdbComparisonGroups.OrderGroupNames(defaultNames, _groupExecutionOrder));
        var customized = _groupExecutionOrder.Count > 0;
        var list = new ListView { Name = "GroupExecutionOrderList", ItemsSource = draft, SelectedIndex = 0,
            SelectionMode = ListViewSelectionMode.Single, MaxHeight = 320 };
        AutomationProperties.SetName(list, title);
        var earlier = new Button { Name = "MoveGroupEarlierButton", Content = "上移" };
        var later = new Button { Name = "MoveGroupLaterButton", Content = "下移" };
        var reset = new Button { Content = "恢复默认顺序" };
        var mode = new TextBlock { TextWrapping = TextWrapping.Wrap };
        var error = new TextBlock { TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed };
        AutomationProperties.SetLiveSetting(error, Microsoft.UI.Xaml.Automation.Peers.AutomationLiveSetting.Polite);
        void RefreshButtons()
        {
            earlier.IsEnabled = list.SelectedIndex > 0;
            later.IsEnabled = list.SelectedIndex >= 0 && list.SelectedIndex < draft.Count - 1;
            reset.IsEnabled = customized;
            mode.Text = customized ? "自定义顺序。新增组按首次出现顺序排在末尾。"
                : "默认按组在所选模型中首次出现的顺序执行。";
        }
        void Move(int offset)
        {
            var from = list.SelectedIndex;
            var to = from + offset;
            if (from < 0 || to < 0 || to >= draft.Count) return;
            customized = true;
            draft.Move(from, to);
            list.SelectedIndex = to;
            list.ScrollIntoView(draft[to]);
            RefreshButtons();
        }
        void ReplaceDraft(IEnumerable<string> names, bool useCustomOrder)
        {
            var selection = list.SelectedItem as string;
            customized = useCustomOrder;
            draft.Clear();
            foreach (var name in names) draft.Add(name);
            list.SelectedItem = selection;
            if (list.SelectedIndex < 0) list.SelectedIndex = 0;
            RefreshButtons();
        }
        list.SelectionChanged += (_, _) => RefreshButtons();
        earlier.Click += (_, _) => Move(-1);
        later.Click += (_, _) => Move(1);
        reset.Click += (_, _) => ReplaceDraft(defaultNames, false);
        RefreshButtons();

        var buttons = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        buttons.Children.Add(earlier);
        buttons.Children.Add(later);
        buttons.Children.Add(reset);
        var panel = new StackPanel { Spacing = 8, MinWidth = 320 };
        panel.Children.Add(mode);
        panel.Children.Add(list);
        panel.Children.Add(buttons);
        panel.Children.Add(new TextBlock { TextWrapping = TextWrapping.Wrap,
            Text = "此设置用于新建和追加任务。已入队任务按队列中的顺序执行，独立模型保留原位置。" });
        panel.Children.Add(error);
        var dialog = new ContentDialog { XamlRoot = XamlRoot, Title = title, Content = panel,
            PrimaryButtonText = "保存顺序", CloseButtonText = "取消" };
        dialog.PrimaryButtonClick += (_, click) =>
        {
            click.Cancel = true;
            if (root != _lastDiscoveryRoot || !catalog.SequenceEqual(KnownGroupNames()))
                error.Text = "工作区或对比组已改变，请关闭后重新打开此窗口。";
            else
            {
                List<string> nextOrder = customized ? [.. draft] : [];
                if (TrySaveWorkspaceChange(next => next.GroupExecutionOrder = nextOrder, message => error.Text = message))
                {
                    _groupExecutionOrder = nextOrder;
                    click.Cancel = false;
                    return;
                }
            }
            error.Visibility = Visibility.Visible;
        };

        // Save indices against the stable catalog, independently of selection order.
        var indices = catalog.Select((name, index) => (name, index)).ToDictionary(item => item.name,
            item => item.index, StringComparer.OrdinalIgnoreCase);
        Dictionary<string, string> Capture()
        {
            var values = new Dictionary<string, string> { ["模式"] = customized ? "自定义" : "默认" };
            if (customized)
            {
                var part = 0;
                foreach (var chunk in draft.Select(name => indices[name]).Chunk(2048))
                    values[$"顺序 {++part}"] = string.Join(",", chunk);
            }
            return values;
        }
        void Restore(IReadOnlyDictionary<string, string> values)
        {
            if (values.GetValueOrDefault("模式") == "默认") { ReplaceDraft(defaultNames, false); return; }
            var names = new List<string>(catalog.Length);
            var seen = new HashSet<int>();
            for (var part = 1; values.TryGetValue($"顺序 {part}", out var chunk); part++)
                foreach (var token in chunk.Split(','))
                {
                    if (!int.TryParse(token, out var index) || index < 0 || index >= catalog.Length || !seen.Add(index))
                        throw new InvalidDataException("草稿中的对比组顺序无效。");
                    names.Add(catalog[index]);
                }
            if (values.GetValueOrDefault("模式") != "自定义" || names.Count != catalog.Length)
                throw new InvalidDataException("草稿缺少部分对比组。");
            ReplaceDraft(names, true);
        }
        var basis = new { Catalog = catalog, Order = _groupExecutionOrder.ToArray() };
        if (await ShowRecoverableDialogAsync(dialog, panel, title, "当前目录", basis, new(), Capture, Restore)
            != ContentDialogResult.Primary) return;
        RefreshInteractionState();
        if (await CompleteDialogDraftAsync(title, "当前目录"))
            ShowSuccess("下次创建和追加队列将使用已保存的顺序。", "对比组执行顺序已保存");
    }

    private async void OnRunOrderPreviewClicked(object sender, RoutedEventArgs args)
    {
        var plan = ResolveRunScope(OdbList.SelectedItems.OfType<OdbFileRow>());
        if (!plan.CanRun) { ShowWarning(plan.Summary, "本次执行顺序"); return; }
        var entries = plan.Groups.Select((group, index) => group.Standalone
            ? $"{index + 1}.  独立模型 · {group.Members[0].RelativePath}"
            : $"{index + 1}.  对比组 · {group.Name}").ToArray();
        var list = new ListView { SelectionMode = ListViewSelectionMode.None, ItemsSource = entries,
            IsItemClickEnabled = false, MinWidth = 260, MaxHeight = 380 };
        AutomationProperties.SetName(list, "本次执行顺序");
        var dialog = new ContentDialog { XamlRoot = XamlRoot, Content = list,
            Title = $"本次执行顺序（{entries.Length} 项）", CloseButtonText = "关闭" };
        await dialog.ShowAsync();
    }
}
