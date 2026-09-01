using AbaqusTools.WinUI.Explorer;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Input;

namespace AbaqusTools.WinUI.Controls;

public sealed partial class WorkbenchExplorerHost : UserControl
{
    private readonly Dictionary<string, string> _selectedByContext = new(StringComparer.Ordinal);
    private readonly Dictionary<string, HashSet<string>> _expandedByContext = new(StringComparer.Ordinal);
    private IWorkbenchExplorerAdapter? _adapter;
    private WorkbenchExplorerSnapshot? _snapshot;
    private CancellationTokenSource? _refreshCancellation;
    private int _generation;
    private bool _manualRefreshBusy;

    public WorkbenchExplorerHost()
    {
        InitializeComponent();
    }

    public void Attach(IWorkbenchExplorerAdapter adapter)
    {
        if (ReferenceEquals(_adapter, adapter))
        {
            ApplySnapshot(adapter.Snapshot);
            return;
        }

        if (_adapter is not null)
        {
            _adapter.SnapshotChanged -= OnAdapterSnapshotChanged;
        }
        _refreshCancellation?.Cancel();
        _adapter = adapter;
        _adapter.SnapshotChanged += OnAdapterSnapshotChanged;
        ExplorerSearchBox.Text = string.Empty;
        ConfigureCommands();
        ApplySnapshot(adapter.Snapshot);
        _ = RefreshAsync(manual: false);
    }

    public async Task RefreshAsync(bool manual)
    {
        if (_adapter is null || (manual && _manualRefreshBusy))
        {
            return;
        }

        var adapter = _adapter;
        var generation = ++_generation;
        _refreshCancellation?.Cancel();
        _refreshCancellation?.Dispose();
        _refreshCancellation = new CancellationTokenSource();
        if (manual)
        {
            _manualRefreshBusy = true;
            ExplorerRefreshButton.IsEnabled = false;
        }
        ExplorerErrorInfoBar.IsOpen = false;
        try
        {
            await adapter.RefreshAsync(_refreshCancellation.Token);
            if (generation == _generation && ReferenceEquals(adapter, _adapter))
            {
                if (!ReferenceEquals(_snapshot, adapter.Snapshot))
                {
                    ApplySnapshot(adapter.Snapshot);
                }
            }
        }
        catch (OperationCanceledException)
        {
            // A newer route or refresh superseded this request.
        }
        catch (Exception exception)
        {
            ExplorerErrorInfoBar.Title = "浏览内容刷新失败";
            ExplorerErrorInfoBar.Message = exception.Message;
            ExplorerErrorInfoBar.IsOpen = true;
            ExplorerSummaryText.Text = "保留上一次成功内容 · 数据可能已过期";
        }
        finally
        {
            if (manual)
            {
                _manualRefreshBusy = false;
                ExplorerRefreshButton.IsEnabled = true;
            }
        }
    }

    private void ConfigureCommands()
    {
        var primaryText = _adapter?.PrimaryActionText ?? string.Empty;
        ExplorerPrimaryButton.Content = primaryText;
        ExplorerPrimaryButton.Visibility = string.IsNullOrWhiteSpace(primaryText)
            ? Visibility.Collapsed
            : Visibility.Visible;
    }

    private void OnAdapterSnapshotChanged(object? sender, EventArgs e)
    {
        if (!ReferenceEquals(sender, _adapter))
        {
            return;
        }
        void ApplyCurrentSnapshot()
        {
            if (ReferenceEquals(sender, _adapter) && _adapter is { } current)
            {
                ApplySnapshot(current.Snapshot);
            }
        }
        if (DispatcherQueue.HasThreadAccess)
        {
            ApplyCurrentSnapshot();
        }
        else
        {
            DispatcherQueue.TryEnqueue(ApplyCurrentSnapshot);
        }
    }

    private void ApplySnapshot(WorkbenchExplorerSnapshot snapshot)
    {
        _snapshot = snapshot;
        ExplorerTitleText.Text = snapshot.Title;
        ExplorerSubtitleText.Text = snapshot.Subtitle;
        ToolTipService.SetToolTip(ExplorerSubtitleText, snapshot.Subtitle);
        ExplorerSummaryText.Text = string.IsNullOrWhiteSpace(snapshot.Summary)
            ? $"更新于 {snapshot.CapturedAt:HH:mm:ss}"
            : snapshot.Summary;
        ExplorerEmptyText.Text = snapshot.EmptyMessage;
        ApplyFilter();
    }

    private void ApplyFilter()
    {
        if (_snapshot is null)
        {
            return;
        }

        var query = ExplorerSearchBox.Text.Trim();
        var items = string.IsNullOrWhiteSpace(query)
            ? _snapshot.RootItems
            : _snapshot.RootItems
                .Select(item => FilterItem(item, query))
                .Where(item => item is not null)
                .Cast<ExplorerItem>()
                .ToArray();

        SynchronizeNodes(ExplorerTree.RootNodes, items, _snapshot.ContextKey);
        ExplorerEmptyPanel.Visibility = ExplorerTree.RootNodes.Count == 0
            ? Visibility.Visible
            : Visibility.Collapsed;
        ExplorerTree.Visibility = ExplorerTree.RootNodes.Count == 0
            ? Visibility.Collapsed
            : Visibility.Visible;
        RestoreSelection(_snapshot.ContextKey);
    }

    private TreeViewNode CreateNode(ExplorerItem item, string contextKey)
    {
        var node = new TreeViewNode { Content = item };
        var expanded = ExpandedKeys(contextKey);
        node.IsExpanded = item.IsExpanded || expanded.Contains(item.StableId);
        foreach (var child in item.Children)
        {
            node.Children.Add(CreateNode(child, contextKey));
        }
        return node;
    }

    private void SynchronizeNodes(
        IList<TreeViewNode> nodes,
        IReadOnlyList<ExplorerItem> items,
        string contextKey)
    {
        for (var index = 0; index < items.Count; index++)
        {
            var item = items[index];
            var existingIndex = -1;
            for (var candidateIndex = index; candidateIndex < nodes.Count; candidateIndex++)
            {
                if (nodes[candidateIndex].Content is ExplorerItem candidate
                    && string.Equals(candidate.StableId, item.StableId, StringComparison.Ordinal))
                {
                    existingIndex = candidateIndex;
                    break;
                }
            }

            TreeViewNode node;
            if (existingIndex < 0)
            {
                node = CreateNode(item, contextKey);
                nodes.Insert(index, node);
            }
            else
            {
                node = nodes[existingIndex];
                if (existingIndex != index)
                {
                    nodes.RemoveAt(existingIndex);
                    nodes.Insert(index, node);
                }
                node.Content = item;
                SynchronizeNodes(node.Children, item.Children, contextKey);
            }
        }
        while (nodes.Count > items.Count)
        {
            nodes.RemoveAt(nodes.Count - 1);
        }
    }

    private void RestoreSelection(string contextKey)
    {
        if (!_selectedByContext.TryGetValue(contextKey, out var stableId))
        {
            return;
        }
        var node = FindNode(ExplorerTree.RootNodes, stableId);
        if (node is not null)
        {
            ExplorerTree.SelectedNode = node;
        }
    }

    private static TreeViewNode? FindNode(
        IEnumerable<TreeViewNode> nodes,
        string stableId)
    {
        foreach (var node in nodes)
        {
            if (node.Content is ExplorerItem item
                && string.Equals(item.StableId, stableId, StringComparison.Ordinal))
            {
                return node;
            }
            var nested = FindNode(node.Children, stableId);
            if (nested is not null)
            {
                return nested;
            }
        }
        return null;
    }

    private static ExplorerItem? FilterItem(ExplorerItem item, string query)
    {
        var filteredChildren = item.Children
            .Select(child => FilterItem(child, query))
            .Where(child => child is not null)
            .Cast<ExplorerItem>()
            .ToArray();
        var matches = item.Title.Contains(query, StringComparison.OrdinalIgnoreCase)
            || item.Subtitle.Contains(query, StringComparison.OrdinalIgnoreCase)
            || item.Status.Contains(query, StringComparison.OrdinalIgnoreCase)
            || item.Path.Contains(query, StringComparison.OrdinalIgnoreCase);
        if (!matches && filteredChildren.Length == 0)
        {
            return null;
        }

        var clone = new ExplorerItem
        {
            StableId = item.StableId,
            Kind = item.Kind,
            Title = item.Title,
            Subtitle = item.Subtitle,
            Path = item.Path,
            EntityId = item.EntityId,
            Status = item.Status,
            Badge = item.Badge,
            IconGlyph = item.IconGlyph,
            IsExpanded = true,
        };
        foreach (var child in filteredChildren)
        {
            clone.Children.Add(child);
        }
        return clone;
    }

    private HashSet<string> ExpandedKeys(string contextKey)
    {
        if (!_expandedByContext.TryGetValue(contextKey, out var keys))
        {
            keys = new HashSet<string>(StringComparer.Ordinal);
            _expandedByContext[contextKey] = keys;
        }
        return keys;
    }

    private async void OnPrimaryActionClicked(object sender, RoutedEventArgs e)
    {
        if (_adapter is null)
        {
            return;
        }
        try
        {
            await _adapter.ExecutePrimaryActionAsync(CancellationToken.None);
        }
        catch (Exception exception)
        {
            ExplorerErrorInfoBar.Title = "操作失败";
            ExplorerErrorInfoBar.Message = exception.Message;
            ExplorerErrorInfoBar.IsOpen = true;
        }
    }

    private async void OnRefreshClicked(object sender, RoutedEventArgs e) =>
        await RefreshAsync(manual: true);

    private void OnSearchTextChanged(AutoSuggestBox sender, AutoSuggestBoxTextChangedEventArgs args)
    {
        if (args.Reason == AutoSuggestionBoxTextChangeReason.UserInput)
        {
            ApplyFilter();
        }
    }

    private void OnTreeSelectionChanged(
        TreeView sender,
        TreeViewSelectionChangedEventArgs args)
    {
        if (_adapter is null
            || _snapshot is null
            || ExplorerTree.SelectedNode?.Content is not ExplorerItem item)
        {
            ExplorerSelectionCard.Visibility = Visibility.Collapsed;
            return;
        }

        _selectedByContext[_snapshot.ContextKey] = item.StableId;
        ExplorerSelectionTitleText.Text = item.Title;
        ExplorerSelectionSubtitleText.Text = item.Subtitle;
        ExplorerSelectionStatusText.Text = item.Status;
        ExplorerSelectionCard.Visibility = item.Kind == ExplorerItemKind.Group
            ? Visibility.Collapsed
            : Visibility.Visible;
        _adapter.Select(item);
    }

    private async void OnTreeDoubleTapped(object sender, DoubleTappedRoutedEventArgs e)
    {
        if (_adapter is null
            || ExplorerTree.SelectedNode?.Content is not ExplorerItem item
            || item.Kind == ExplorerItemKind.Group)
        {
            return;
        }
        await _adapter.ActivateAsync(item, ExplorerActivationKind.Default, CancellationToken.None);
        e.Handled = true;
    }

    private void OnNodeExpanding(TreeView sender, TreeViewExpandingEventArgs args)
    {
        if (_snapshot is not null && args.Node.Content is ExplorerItem item)
        {
            ExpandedKeys(_snapshot.ContextKey).Add(item.StableId);
        }
    }

    private void OnNodeCollapsed(TreeView sender, TreeViewCollapsedEventArgs args)
    {
        if (_snapshot is not null && args.Node.Content is ExplorerItem item)
        {
            ExpandedKeys(_snapshot.ContextKey).Remove(item.StableId);
        }
    }
}
