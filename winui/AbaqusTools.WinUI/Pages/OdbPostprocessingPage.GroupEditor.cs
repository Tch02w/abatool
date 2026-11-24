using AbaqusTools.WinUI.Models;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private async void OnEditQueuedGroupClicked(object sender, RoutedEventArgs e)
    {
        if (_groupQueue is not { } queue || !AcceptsPendingChanges(queue)
            || SelectedQueueGroup is not { Status: "queued", Run: { } initial } entry) return;
        try { await EditQueuedGroupAsync(queue, entry, initial); }
        catch (Exception error) { ShowWarning(QueueError(error), "等待组设置未保存"); }
    }

    private async Task EditQueuedGroupAsync(OdbPostprocessGroupQueueSnapshot queue, OdbPostprocessGroupQueueItem entry,
        OdbPostprocessRunCreateRequest initial)
    {
        var plan = initial;
        var group = plan.Groups.Single();
        var members = group.Members.ToList();
        var enabled = members.ToHashSet(StringComparer.OrdinalIgnoreCase);
        var jobs = plan.Jobs.ToDictionary(job => job.Path, job => job.Clone(), StringComparer.OrdinalIgnoreCase);
        var sameRoot = _lastDiscoveryRoot is not null && string.Equals(PathKey(queue.Root), PathKey(_lastDiscoveryRoot),
            StringComparison.OrdinalIgnoreCase);
        OdbExecutionGroup? local = null;
        if (sameRoot && !DraftPending)
        {
            if (entry.Standalone)
            {
                if (entry.Members.Count == 1 && FindRow(entry.Members[0]) is { } row)
                    local = new(row.Name, [row], true);
            }
            else local = OdbComparisonGroups.ForExecution(_odbItems).FirstOrDefault(candidate =>
                !candidate.Standalone && string.Equals(candidate.Name, entry.Name, StringComparison.OrdinalIgnoreCase));
        }
        if (local is not null)
            foreach (var row in local.Members.Where(row => row.HasPostprocessConfiguration && row.PostprocessJob is not null))
                if (jobs.TryAdd(row.Path, row.PostprocessJob!.Clone())) members.Add(row.Path);

        string? selected = members.FirstOrDefault();
        while (true)
        {
            var panel = new StackPanel { Spacing = 8, MinWidth = 350 };
            var description = new TextBlock { TextWrapping = TextWrapping.Wrap,
                Text = "只修改本次队列中的这个组。取消全部成员可跳过该组。" };
            panel.Children.Add(description);
            var list = new ListView { MaxHeight = 230, SelectionMode = ListViewSelectionMode.Single };
            foreach (var path in members)
            {
                var check = new CheckBox { Content = Path.GetFileName(path), Tag = path, IsChecked = enabled.Contains(path) };
                ToolTipService.SetToolTip(check, path);
                check.Checked += (_, _) => { enabled.Add(path); list.SelectedItem = check; };
                check.Unchecked += (_, _) => { enabled.Remove(path); list.SelectedItem = check; };
                list.Items.Add(check);
                if (string.Equals(selected, path, StringComparison.OrdinalIgnoreCase)) list.SelectedItem = check;
            }
            panel.Children.Add(list);
            var sync = new Button { Content = "同步本页的成员、顺序、参数及图例", IsEnabled = sameRoot && !DraftPending };
            panel.Children.Add(sync);
            var summary = new TextBlock { TextWrapping = TextWrapping.Wrap,
                Text = $"{group.LegendOverrides.Count} 项手动图例 · {plan.ImageWidth} × {plan.ImageHeight} {plan.ImageSizeUnit}" };
            panel.Children.Add(summary);
            var dialog = new ContentDialog { XamlRoot = XamlRoot, Title = $"编辑等待组 · {entry.Name}",
                Content = panel, PrimaryButtonText = "保存到等待组", SecondaryButtonText = "编辑选中成员参数…",
                CloseButtonText = "取消", IsSecondaryButtonEnabled = list.SelectedItem is not null };
            bool syncPage = false;
            sync.Click += (_, _) => { syncPage = true; dialog.Hide(); };
            list.SelectionChanged += (_, _) => dialog.IsSecondaryButtonEnabled = list.SelectedItem is not null;
            var result = await dialog.ShowAsync();
            selected = (list.SelectedItem as CheckBox)?.Tag as string;
            if (syncPage)
            {
                if (local is null)
                {
                    members.Clear();
                    enabled.Clear();
                    selected = null;
                    continue;
                }
                var updated = BuildQueueRequest(local.Members.ToArray(), [local]);
                if (updated is null) return;
                plan = updated;
                group = updated.Groups.Single() with { Id = initial.Groups.Single().Id };
                members = group.Members.ToList();
                enabled = members.ToHashSet(StringComparer.OrdinalIgnoreCase);
                jobs = updated.Jobs.ToDictionary(job => job.Path, StringComparer.OrdinalIgnoreCase);
                selected = members.FirstOrDefault();
                continue;
            }
            if (result == ContentDialogResult.Secondary && selected is not null)
            {
                var row = (sameRoot ? FindRow(selected) : null)
                    ?? new OdbFileRow(CreateRecoveryDiscoveryItem(queue.Root, selected));
                var draft = await ShowJobConfigurationDialogAsync(row, jobs[selected]);
                if (draft is not null) jobs[selected] = draft;
                continue;
            }
            if (result != ContentDialogResult.Primary) return;
            var paths = members.Where(enabled.Contains).ToArray();
            if (paths.Length == 0)
            {
                var skip = new ContentDialog { XamlRoot = XamlRoot, Title = $"跳过等待组 · {entry.Name}？",
                    Content = "该组没有启用成员。其他等待组将继续按队列顺序执行。", PrimaryButtonText = "跳过此组", CloseButtonText = "返回编辑" };
                if (await skip.ShowAsync() != ContentDialogResult.Primary) continue;
                await ChangeGroupQueueAsync(queue, PostprocessGroupQueueAction.SkipPending, groupId: entry.GroupId);
            }
            else
            {
                var revised = plan with { ClientRequestId = Guid.NewGuid().ToString("D"), Root = queue.Root,
                    Jobs = paths.Select(path => jobs[path]).ToArray(), Groups = [group with { Members = paths }] };
                await ChangeGroupQueueAsync(queue, PostprocessGroupQueueAction.UpdatePending, revised);
            }
            return;
        }
    }
}
