using System.Text.Json;
using AbaqusTools.WinUI.Controls;
using AbaqusTools.WinUI.Explorer;
using AbaqusTools.WinUI.Services;
using System.Collections.ObjectModel;
using System.Collections.Specialized;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;

namespace ExplorerControlChecks;

public sealed partial class TestApp : Application
{
    private readonly string _receipt;
    private readonly List<string> _checks = [];
    private readonly List<string> _selectionEvents = [];
    private Window? _window;
    private readonly Grid _root = new();

    public TestApp(string receipt)
    {
        _receipt = receipt;
        InitializeComponent();
    }

    protected override async void OnLaunched(LaunchActivatedEventArgs args)
    {
        try
        {
            Write(new { status = "running", checks = _checks });
            _window = new Window { Content = _root };
            _window.AppWindow.MoveAndResize(new Windows.Graphics.RectInt32(-32000, -32000, 400, 800));
            var loaded = new TaskCompletionSource();
            _root.Loaded += (_, _) => loaded.TrySetResult();
            _window.Activate();
            await loaded.Task.WaitAsync(TimeSpan.FromSeconds(10));
            await CheckInfoBarLayoutAsync();
            await CheckHeaderAlignmentAsync();
            await CheckCompactTreeAsync();
            await CheckSelectionsAsync();
            await CheckServerDialogLayoutAsync();
            await CheckQueueUpdatesAsync();
            Write(new { status = "passed", checks = _checks });
        }
        catch (Exception error)
        {
            Environment.ExitCode = 1;
            Write(new { status = "failed", checks = _checks, selectionEvents = _selectionEvents.TakeLast(12), error = error.ToString() });
        }
        finally
        {
            _root.Children.Clear();
            await DispatchAsync();
            if (_window is not null) _window.Content = null;
            await DispatchAsync();
            Exit();
        }
    }

    private async Task CheckQueueUpdatesAsync()
    {
        var rows = new ObservableCollection<JobQueueItem>();
        var list = new ListView { ItemsSource = rows, SelectionMode = ListViewSelectionMode.Multiple, Height = 240 };
        list.ItemTemplate = (DataTemplate)Microsoft.UI.Xaml.Markup.XamlReader.Load("""
            <DataTemplate xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation">
              <StackPanel Orientation="Horizontal"><CheckBox IsChecked="{Binding Selected, Mode=OneWay}"/><TextBlock Text="{Binding Status}"/><TextBlock Text="{Binding RuntimeMemoryDisplay}"/></StackPanel>
            </DataTemplate>
            """);
        _root.Children.Add(list);
        JobQueueItem Row(int index, string status = "等待", bool selected = true) => new()
        {
            ItemId = $"queue-{index}", Index = index, JobName = $"GJA-8+2_{index}",
            Status = status, Selected = selected, DependencyJobIds = ["parent"],
            RuntimeMemoryBytes = status == "运行中" ? 2147483648 : 0
        };
        var initial = Enumerable.Range(0, 50).Select(index => Row(index)).ToArray();
        QueueListUpdates.Apply(list, rows, initial);
        await DispatchAsync(); _root.UpdateLayout();
        list.SelectedItems.Add(rows[1]); list.SelectedItems.Add(rows[3]);
        var row1 = rows[1];
        var container = list.ContainerFromItem(row1);
        Check(container is not null, "Queue native list realizes its selected row");
        var changes = new List<NotifyCollectionChangedAction>();
        rows.CollectionChanged += (_, args) => changes.Add(args.Action);
        var fields = new List<string?>();
        row1.PropertyChanged += (_, args) => fields.Add(args.PropertyName);
        for (var cycle = 0; cycle < 100; cycle++)
            QueueListUpdates.Apply(list, rows, Enumerable.Range(0, 50).Select(index => Row(index)).ToArray());
        await DispatchAsync(); _root.UpdateLayout();
        Check(changes.Count == 0 && fields.Count == 0, "100 identical polls cause no collection or field notifications");
        Check(ReferenceEquals(list.ContainerFromItem(row1), container) && list.SelectedItems.Count == 2,
            "Identical polls retain native row container and candidate multi-selection");
        var updated = Enumerable.Range(0, 50).Select(index => Row(index, index == 1 ? "运行中" : "等待", index != 1)).ToArray();
        QueueListUpdates.Apply(list, rows, updated);
        await DispatchAsync(); _root.UpdateLayout();
        Check(ReferenceEquals(rows[1], row1) && ReferenceEquals(list.ContainerFromItem(row1), container)
            && list.SelectedItems.Contains(row1) && row1.Status == "运行中", "Changed status updates the existing selected row in place");
        Check(fields.Contains("Status") && fields.Contains("RuntimeMemoryDisplay") && !fields.Contains("JobName")
            && changes.Count == 0, "Only changed values and dependent displays notify bindings");
        Check(Descendants(container!).OfType<CheckBox>().Single().IsChecked is false
            && Descendants(container!).OfType<TextBlock>().Any(text => text.Text == "运行中")
            && Descendants(container!).OfType<TextBlock>().Any(text => text.Text == "2.0 GB"),
            "Native checkbox, status and memory bindings receive new values without rebuilding the row");
        var scroller = Descendants(list).OfType<ScrollViewer>().First();
        scroller.ChangeView(null, 400, null, true);
        await DispatchAsync(); _root.UpdateLayout();
        var offset = scroller.VerticalOffset;
        QueueListUpdates.Apply(list, rows, updated);
        await DispatchAsync(); _root.UpdateLayout();
        Check(offset > 0 && Math.Abs(offset - scroller.VerticalOffset) < .1, "Unchanged refresh preserves native scroll position");
        QueueListUpdates.Apply(list, rows, updated.Reverse().ToArray());
        await DispatchAsync(); _root.UpdateLayout();
        Check(list.SelectedItems.Count == 2 && list.SelectedItems.Contains(row1)
            && rows[48] == row1, "Reordering preserves selected job identities");
        QueueListUpdates.Apply(list, rows, updated.Where(row => row.ItemId != "queue-3").ToArray());
        Check(list.SelectedItems.Count == 1 && list.SelectedItems.Contains(row1), "Removing one selected job preserves the surviving selection");
        Check(!changes.Contains(NotifyCollectionChangedAction.Reset), "Structural changes never reset the whole list");
        var original = new JobQueueSnapshot { QueueCount = 1, QueueItems = [Row(1)] };
        var memoryOnly = Row(1); memoryOnly.RuntimeMemoryBytes = 1234;
        Check(original.HasSameExplorerContent(new() { QueueCount = 1, QueueItems = [memoryOnly] }),
            "Memory-only changes do not rebuild a sidebar that does not display memory");
        Check(!original.HasSameExplorerContent(new() { QueueCount = 1, QueueItems = [Row(1, "运行中")] }),
            "A changed queue status still refreshes the sidebar badge");
        Check(!new JobQueueSnapshot { CandidateCount = 1, Candidates = [Row(1)] }.HasSameExplorerContent(
            new() { CandidateCount = 1, Candidates = [Row(1, selected: false)] }),
            "A changed candidate check still refreshes the sidebar selection badge");
        _root.Children.Clear(); await DispatchAsync();
    }

    private async Task CheckServerDialogLayoutAsync()
    {
        _window!.AppWindow.Resize(new Windows.Graphics.SizeInt32(1000, 900));
        foreach (var theme in new[] { ElementTheme.Light, ElementTheme.Dark })
        foreach (var title in new[] { "添加服务器", "编辑服务器", "连接 计算节点01" })
        {
            var host = new TextBox { Header = "主机名或 IP", Text = "192.168.1.202" };
            var port = new TextBox { Header = "SSH 端口", Text = "65535", MaxLength = 5 };
            var username = new TextBox { Header = "用户名", Text = "Administrator" };
            var password = new PasswordBox { Header = "密码" };
            var panel = new StackPanel { Spacing = 10 };
            panel.Children.Add(new TextBox { Header = "配置名称", Text = "计算节点01" });
            panel.Children.Add(ServerDialogLayout.EndpointRow(host, port));
            panel.Children.Add(username);
            panel.Children.Add(new ComboBox { Header = "认证方式", ItemsSource = new[] { "用户名/密码" },
                SelectedIndex = 0, HorizontalAlignment = HorizontalAlignment.Stretch });
            panel.Children.Add(password);
            panel.Children.Add(new TextBox { Header = "服务器计算目录", Text = @"D:\Abaqus_Cal\中文 路径" });
            panel.Children.Add(new TextBox { Header = "允许访问的服务器根目录（每行一个）", AcceptsReturn = true, MinHeight = 70 });
            panel.Children.Add(new TextBox { Header = "Abaqus 命令", Text = "abaqus.bat" });
            panel.Children.Add(new TextBox { Header = "已验证主机指纹", Text = new string('x', 60) });
            var scroller = ServerDialogLayout.Content(panel);
            var dialog = new ContentDialog { XamlRoot = _root.XamlRoot, Title = title, Content = scroller,
                RequestedTheme = theme, PrimaryButtonText = title.StartsWith("连接") ? "连接" : "保存并连接",
                SecondaryButtonText = title.StartsWith("连接") ? "" : "仅保存", CloseButtonText = "取消" };
            ServerDialogLayout.KeepExistingWidth(dialog);
            var opened = new TaskCompletionSource();
            dialog.Opened += (_, _) => opened.SetResult();
            var showing = dialog.ShowAsync();
            try
            {
                await opened.Task.WaitAsync(TimeSpan.FromSeconds(10));
                await DispatchAsync();
                dialog.UpdateLayout();
                var hostTop = host.TransformToVisual(panel).TransformPoint(default).Y;
                var portTop = port.TransformToVisual(panel).TransformPoint(default).Y;
                var userBody = Descendants(username).OfType<FrameworkElement>().First(e => e.Name == "BorderElement");
                var passwordBody = Descendants(password).OfType<FrameworkElement>().First(e => e.Name == "BorderElement");
                Check(host.ActualHeight == 32 && port.ActualHeight == 32
                    && userBody.ActualHeight == 32 && passwordBody.ActualHeight == 32
                    && Math.Abs(hostTop - portTop) < .01,
                    $"{theme}/{title}: body heights={host.ActualHeight}/{port.ActualHeight}/{userBody.ActualHeight}/{passwordBody.ActualHeight}; endpoint tops={hostTop}/{portTop}");
                Check(scroller.ScrollableWidth == 0 && panel.ActualWidth <= scroller.ViewportWidth + .1
                    && panel.Children.OfType<FrameworkElement>().All(field => field.ActualWidth <= panel.ActualWidth + .1)
                    && port.TransformToVisual(panel).TransformPoint(default).X + port.ActualWidth <= panel.ActualWidth + .1,
                    $"{theme}/{title}: all field right edges remain inside the fixed-width dialog viewport");
                Check(!Descendants(panel).Any(e => e is NumberBox or Microsoft.UI.Xaml.Controls.Primitives.RepeatButton)
                    && host.VerticalContentAlignment == VerticalAlignment.Center && port.VerticalContentAlignment == VerticalAlignment.Center,
                    $"{theme}/{title}: direct port input has no steppers and endpoint content is centered vertically");
            }
            finally
            {
                dialog.Hide();
                await showing;
                dialog.Content = null;
                await DispatchAsync();
            }
        }
    }

    private static IEnumerable<DependencyObject> Descendants(DependencyObject root)
    {
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(root); index++)
        {
            var child = VisualTreeHelper.GetChild(root, index);
            yield return child;
            foreach (var descendant in Descendants(child)) yield return descendant;
        }
    }

    private async Task CheckInfoBarLayoutAsync()
    {
        var panel = new StackPanel { VerticalAlignment = VerticalAlignment.Top };
        var bars = Enumerable.Range(0, 3).Select(_ => new InfoBar
        {
            IsOpen = false, Margin = new Thickness(12, 8, 12, 0), Title = "Layout check"
        }).ToArray();
        foreach (var bar in bars) panel.Children.Add(bar);
        _root.Children.Add(panel);
        await DispatchAsync();
        _root.UpdateLayout();
        Check(Math.Abs(panel.ActualHeight - 24) < .1,
            "Three closed stock InfoBars reproduce the 24 DIP blank band");
        InfoBarLayout.Track(panel, bars);
        _root.UpdateLayout();
        Check(panel.Visibility == Visibility.Collapsed && panel.DesiredSize.Height == 0,
            "Closed messages and their container release all reserved space");
        bars[1].IsOpen = true;
        await DispatchAsync();
        _root.UpdateLayout();
        Check(panel.Visibility == Visibility.Visible && bars[1].ActualHeight > 0
            && bars[0].Visibility == Visibility.Collapsed && bars[2].Visibility == Visibility.Collapsed,
            "A newly opened message remains visible while closed siblings take no space");
        bars[1].IsOpen = false;
        await DispatchAsync();
        _root.UpdateLayout();
        Check(panel.Visibility == Visibility.Collapsed && panel.DesiredSize.Height == 0,
            "Closing the last message releases its margin again");
        _root.Children.Remove(panel);
        await DispatchAsync();
    }

    private async Task CheckHeaderAlignmentAsync()
    {
        var explorer = new WorkbenchExplorerHost { Width = 280 };
        _root.Children.Add(explorer);
        var refresh = (Button)explorer.FindName("ExplorerRefreshButton");
        var collapse = (Button)explorer.FindName("ExplorerCollapseButton");
        var primary = (Button)explorer.FindName("ExplorerPrimaryButton");
        var subtitle = (TextBlock)explorer.FindName("ExplorerSubtitleText");
        foreach (var hasSubtitle in new[] { false, true })
        foreach (var hasPrimary in new[] { false, true })
        {
            subtitle.Text = hasSubtitle ? @"G:\验收目录\较长的结果路径" : "";
            primary.Content = "选择目录";
            primary.Height = 40;
            primary.Visibility = hasPrimary ? Visibility.Visible : Visibility.Collapsed;
            await DispatchAsync();
            _root.UpdateLayout();
            var refreshTop = refresh.TransformToVisual(explorer).TransformPoint(default).Y;
            var collapseTop = collapse.TransformToVisual(explorer).TransformPoint(default).Y;
            Check(Math.Abs(refreshTop - collapseTop) < .01
                && refresh.ActualWidth == 30 && refresh.ActualHeight == 30
                && collapse.ActualWidth == 30 && collapse.ActualHeight == 30,
                $"Header buttons align at {refreshTop:F1}/{collapseTop:F1} DIP with subtitle={hasSubtitle}, primary={hasPrimary}");
        }
        _root.Children.Remove(explorer);
        await DispatchAsync();
    }

    private async Task CheckCompactTreeAsync()
    {
        var explorer = new WorkbenchExplorerHost { Width = 280 };
        _root.Children.Add(explorer);
        var tree = (TreeView)explorer.FindName("ExplorerTree");
        var nodes = Enumerable.Range(0, 6).Select(depth => new TreeViewNode
        {
            Content = new ExplorerItem
            {
                StableId = $"layout:{depth}", Title = $"Layout depth {depth}",
                Kind = depth == 5 ? ExplorerItemKind.ResultRecord : ExplorerItemKind.ResultScope,
                IconGlyph = depth == 5 ? "\uE8A5" : "\uE8B7",
            },
            IsExpanded = true,
        }).ToArray();
        for (var depth = 1; depth < nodes.Length; depth++) nodes[depth - 1].Children.Add(nodes[depth]);
        tree.RootNodes.Add(nodes[0]);
        foreach (var theme in new[] { ElementTheme.Light, ElementTheme.Dark })
        {
            explorer.RequestedTheme = theme;
            await DispatchAsync();
            _root.Measure(new Windows.Foundation.Size(400, 800));
            _root.Arrange(new Windows.Foundation.Rect(0, 0, 400, 800));
            _root.UpdateLayout();
            await DispatchAsync();
            var labels = Descendants<TextBlock>(tree)
                .Where(label => label.Text.StartsWith("Layout depth ")).OrderBy(label => label.Text).ToArray();
            var positions = labels.Select(label => label.TransformToVisual(explorer).TransformPoint(default).X).ToArray();
            Check(positions.Length == 6 && positions.Zip(positions.Skip(1)).All(pair => Math.Abs(pair.Second - pair.First - 10) < .1),
                $"{theme}: six tree levels use 10 DIP indentation: {string.Join(",", positions)}");
            var icons = Descendants<FontIcon>(tree).ToArray();
            Check(icons.Length == 6 && icons.Count(icon => icon.Glyph == "\uE8B7") == 5
                && icons.Count(icon => icon.Glyph == "\uE8A5") == 1
                && icons.All(icon => icon.FontFamily.Source.Contains("Segoe Fluent Icons")),
                $"{theme}: folder and file glyphs bind distinctly using the symbol font");
            nodes[0].IsExpanded = false;
            await DispatchAsync();
            nodes[0].IsExpanded = true;
            await DispatchAsync();
            _root.UpdateLayout();
            await DispatchAsync();
            tree.SelectedNode = nodes[^1];
            await DispatchAsync();
            Check(ReferenceEquals(tree.SelectedNode, nodes[^1]) && tree.ContainerFromNode(nodes[^1]) is not null,
                $"{theme}: a deep file remains selectable after collapsing and expanding its parent");
        }
        _root.Children.Remove(explorer);
        await DispatchAsync();
    }

    private static IEnumerable<T> Descendants<T>(DependencyObject parent) where T : DependencyObject
    {
        for (var index = 0; index < VisualTreeHelper.GetChildrenCount(parent); index++)
        {
            var child = VisualTreeHelper.GetChild(parent, index);
            if (child is T element) yield return element;
            foreach (var nested in Descendants<T>(child)) yield return nested;
        }
    }

    private async Task CheckSelectionsAsync()
    {
        var explorer = new WorkbenchExplorerHost();
        _root.Children.Add(explorer);
        _root.UpdateLayout();
        var adapter = new SnapshotAdapter("results");
        explorer.Attach(adapter);
        await DispatchAsync();
        _root.Measure(new Windows.Foundation.Size(400, 800));
        _root.Arrange(new Windows.Foundation.Rect(0, 0, 400, 800));
        _root.UpdateLayout();
        await DispatchAsync();
        var tree = (TreeView)explorer.FindName("ExplorerTree");
        tree.SelectionChanged += (_, args) => _selectionEvents.Add(
            $"selected={SelectedId(tree)} added={string.Join(',', args.AddedItems.Select(item => item is TreeViewNode n ? (n.Content as ExplorerItem)?.StableId : item.GetType().Name))} calls={adapter.Selections}");
        var title = (TextBlock)explorer.FindName("ExplorerSelectionTitleText");
        var card = (FrameworkElement)explorer.FindName("ExplorerSelectionCard");
        Check(adapter.Selections == 0, "Attaching a snapshot issues no selection commands");

        // A real TreeView event invokes Select; that synchronously publishes new items,
        // just as ClearResults/UpdateExplorer did in the reported stack overflow.
        tree.SelectedNode = tree.RootNodes[0];
        await DispatchAsync();
        Check(adapter.Selections == 1 && SelectedId(tree) == "a",
            "Selection can synchronously refresh/reorder the tree without recursively selecting");
        Check(title.Text == "A 1", "Selected detail card reflects the refreshed item");

        for (var i = 0; i < 100; i++) adapter.Publish(includeA: true);
        await DispatchAsync();
        Check(adapter.Selections == 1 && SelectedId(tree) == "a" && title.Text == "A 101",
            "Repeated snapshots retain selection and update details without page commands");

        adapter.Publish(includeA: false);
        await DispatchAsync();
        Check(adapter.Selections == 1 && tree.SelectedNode is null && card.Visibility == Visibility.Collapsed,
            "Removing the selected item clears stale details without a selection command");
        adapter.Publish(includeA: true);
        await DispatchAsync();
        Check(adapter.Selections == 1 && SelectedId(tree) == "a",
            "A returning selected item is restored without reopening the page selection");

        var other = new SnapshotAdapter("other");
        explorer.Attach(other);
        await DispatchAsync();
        Check(other.Selections == 0, "Changing adapter does not select its first node implicitly");
        explorer.Attach(adapter);
        await DispatchAsync();
        Check(adapter.Selections == 1 && SelectedId(tree) == "a",
            "Reattaching a context restores its selection without a command");
        _root.Measure(new Windows.Foundation.Size(400, 800));
        _root.Arrange(new Windows.Foundation.Rect(0, 0, 400, 800));
        _root.UpdateLayout();
        await DispatchAsync();
        var nextNode = tree.RootNodes.Single(n => n.Content is ExplorerItem { StableId: "b" });
        _selectionEvents.Add($"before-next loaded={tree.IsLoaded}, container={tree.ContainerFromNode(nextNode) is not null}, selected-count={tree.SelectedNodes.Count}");
        tree.SelectedNode = nextNode;
        await DispatchAsync();
        Check(adapter.Selections == 2 && SelectedId(tree) == "b",
            $"A subsequent actual selection is still delivered once (calls={adapter.Selections}, selected={SelectedId(tree)})");
    }

    private static string? SelectedId(TreeView tree) => (tree.SelectedNode?.Content as ExplorerItem)?.StableId;
    private void Check(bool condition, string description)
    {
        if (!condition) throw new InvalidOperationException(description);
        _checks.Add(description);
        Write(new { status = "running", checks = _checks });
    }
    private void Write(object value) => File.WriteAllText(_receipt,
        JsonSerializer.Serialize(value, new JsonSerializerOptions { WriteIndented = true }));
    private static async Task DispatchAsync()
    {
        var completion = new TaskCompletionSource();
        DispatcherQueue.GetForCurrentThread().TryEnqueue(DispatcherQueuePriority.Low, () => completion.SetResult());
        await completion.Task.WaitAsync(TimeSpan.FromSeconds(5));
    }

    private sealed class SnapshotAdapter(string context) : IWorkbenchExplorerAdapter
    {
        private int _revision;
        public int Selections { get; private set; }
        public string ContextKey => context;
        public string PrimaryActionText => "";
        public WorkbenchExplorerSnapshot Snapshot { get; private set; } = Make(context, 0, true);
        public event EventHandler? SnapshotChanged;
        public Task RefreshAsync(CancellationToken token) => Task.CompletedTask;
        public Task ExecutePrimaryActionAsync(CancellationToken token) => Task.CompletedTask;
        public Task ActivateAsync(ExplorerItem item, ExplorerActivationKind kind, CancellationToken token) => Task.CompletedTask;
        public void Select(ExplorerItem item)
        {
            if (++Selections > 6) throw new InvalidOperationException("Recursive selection command detected");
            Publish(includeA: true);
        }
        public void Publish(bool includeA)
        {
            Snapshot = Make(context, ++_revision, includeA);
            SnapshotChanged?.Invoke(this, EventArgs.Empty);
        }
        private static WorkbenchExplorerSnapshot Make(string context, int revision, bool includeA)
        {
            var a = new ExplorerItem { StableId = "a", Kind = ExplorerItemKind.ResultScope, Title = $"A {revision}" };
            var b = new ExplorerItem { StableId = "b", Kind = ExplorerItemKind.ResultScope, Title = $"B {revision}" };
            return new() { ContextKey = context, Title = context,
                RootItems = !includeA ? [b] : revision % 2 == 0 ? [a, b] : [b, a] };
        }
    }
}
