using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private IEnumerable<string> SavedGroupNames() => _groupMemberOrder.Keys.Concat(_legendOverridesByGroup.Keys);
    private string[] KnownGroupNames() => OdbComparisonGroups.CatalogNames(_odbItems, SavedGroupNames());

    private async void OnCreateGroupsClicked(object sender, RoutedEventArgs args)
    {
        if (!CreateGroupsButton.IsEnabled) return;
        var names = KnownGroupNames();
        var input = new TextBox { Header = "组名（每行一个）", AcceptsReturn = true, MinHeight = 96,
            MaxHeight = 220, TextWrapping = TextWrapping.Wrap };
        var detail = new TextBlock { TextWrapping = TextWrapping.Wrap };
        var panel = new StackPanel { MinWidth = 300, Spacing = 8 };
        panel.Children.Add(input);
        panel.Children.Add(detail);
        var dialog = new ContentDialog { XamlRoot = XamlRoot, Title = "新建对比组", Content = panel,
            PrimaryButtonText = "创建", CloseButtonText = "取消" };
        string[] added = [];

        void Preview()
        {
            try
            {
                var plan = OdbComparisonGroups.PlanNewGroups(input.Text, names);
                detail.Text = plan.DuplicateNames.Length > 0
                    ? $"将创建 {plan.NewNames.Length} 个组，跳过重复名称：{string.Join("、", plan.DuplicateNames)}"
                    : plan.NewNames.Length == 0 ? "" : $"将创建 {plan.NewNames.Length} 个空组";
            }
            catch (ArgumentException error) { detail.Text = error.Message; }
        }
        input.TextChanged += (_, _) => Preview();
        dialog.PrimaryButtonClick += (_, click) =>
        {
            click.Cancel = true;
            try
            {
                var plan = OdbComparisonGroups.PlanNewGroups(input.Text, KnownGroupNames());
                if (plan.NewNames.Length == 0)
                {
                    detail.Text = "请至少填写一个未使用的组名。";
                    input.Focus(FocusState.Programmatic);
                    return;
                }
                if (!TrySaveWorkspaceChange(next =>
                    {
                        foreach (var name in plan.NewNames) next.GroupMemberOrder.Add(name, []);
                    }))
                {
                    detail.Text = "工作区未能保存，请检查当前目录和配置文件后重试。";
                    return;
                }
                added = plan.NewNames;
                foreach (var name in added) _groupMemberOrder.Add(name, []);
                click.Cancel = false;
            }
            catch (ArgumentException error) { detail.Text = error.Message; }
        };
        if (await ShowRecoverableDialogAsync(dialog, panel, "新建对比组", "当前目录", names,
            new() { ["组名"] = input }) != ContentDialogResult.Primary) return;
        GroupNameTextBox.Text = added[0];
        UpdateExplorer();
        RefreshInteractionState();
        await CompleteDialogDraftAsync("新建对比组", "当前目录");
        ShowWarning($"已创建 {added.Length} 个组。", "对比组已保存");
    }
}
