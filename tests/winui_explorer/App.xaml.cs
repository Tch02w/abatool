using System.Text.Json;
using AbaqusTools.WinUI.Controls;
using AbaqusTools.WinUI.Explorer;
using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

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
            await CheckSelectionsAsync();
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

    private async Task CheckSelectionsAsync()
    {
        var explorer = new WorkbenchExplorerHost();
        _root.Children.Add(explorer);
        _root.UpdateLayout();
        var adapter = new SnapshotAdapter("results");
        explorer.Attach(adapter);
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
