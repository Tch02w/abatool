using AbaqusTools.WinUI.Services;
using Microsoft.UI;
using Microsoft.UI.Text;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Shapes;
using Windows.Foundation;
using Windows.Storage.Pickers;

namespace AbaqusTools.WinUI.Controls;

public sealed partial class OdbResultGraphEditor : UserControl
{
    private const int MaximumNodes = 256;
    private const double NodeWidth = 224;
    private const double NodeHeight = 128;
    private const double HorizontalGap = 64;
    private const double VerticalGap = 26;
    private readonly List<OdbResultGraphNode> _nodes = [];
    private readonly HashSet<string> _targets = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Border> _nodeCards = new(StringComparer.Ordinal);
    private readonly Dictionary<string, TextBlock> _nodeTitles = new(StringComparer.Ordinal);
    private readonly Dictionary<string, TextBlock> _nodePaths = new(StringComparer.Ordinal);
    private readonly Dictionary<string, Point> _positions = new(StringComparer.Ordinal);
    private OdbResultGraphSnapshot? _savedSnapshot;
    private string? _selectedNodeId;
    private bool _initialized;
    private bool _updatingFields;
    private bool _requestBusy;
    private bool _executionBusy;
    private bool _initialLoadDeferred;
    private int _planRequestVersion;

    public OdbResultGraphEditor()
    {
        InitializeComponent();
        _initialized = true;
        InitializeDraftRecovery();
        Loaded += OnEditorLoaded;
        RefreshInteractionState();
    }

    public event EventHandler<OdbResultBatchPlan>? PlansRequested;
    public event EventHandler? GraphChanged;

    public void InvalidatePlanRequest() => _planRequestVersion++;

    // Expose a copy: the explorer can inspect the current draft without mutating it.
    public OdbResultGraphSnapshot? Snapshot => _savedSnapshot is null && _nodes.Count == 0
        ? null
        : new OdbResultGraphSnapshot
        {
            SchemaVersion = _savedSnapshot?.SchemaVersion ?? 1,
            Revision = _savedSnapshot?.Revision ?? 0,
            OutputDirectory = OutputDirectoryTextBox.Text.Trim(),
            Nodes = _nodes.Select(CloneNode).ToArray(),
        };

    public bool HasUnsavedChanges { get; private set; }

    public async Task SaveForCloseAsync()
    {
        await WorkbenchSession.WaitForIdleAsync(() => _requestBusy, "结果图读写");
        if (!HasUnsavedChanges) return;
        if (_executionBusy || _savedSnapshot is null)
            throw new InvalidOperationException("结果图仍有未保存内容，请等待任务结束后保存再关闭。");
        _requestBusy = true;
        try
        {
            var snapshot = await App.Current.ControlPlane.SaveOdbResultGraphAsync(
                _savedSnapshot.Revision, OutputDirectoryTextBox.Text.Trim(), _nodes.Select(CloneNode).ToArray());
            ApplySnapshot(snapshot);
            await SaveDraftCheckpointAsync();
        }
        finally { _requestBusy = false; RefreshInteractionState(); }
    }

    public void SetExecutionBusy(bool busy)
    {
        _executionBusy = busy;
        RefreshInteractionState();
        if (!busy && _initialLoadDeferred && IsLoaded)
        {
            _ = LoadInitialGraphAsync();
        }
    }

    public void SelectNode(string nodeId)
    {
        if (!_nodes.Any(node => node.NodeId == nodeId))
        {
            return;
        }

        _selectedNodeId = nodeId;
        PopulateInspector();
        RefreshNodeSelection();
        RefreshInteractionState();
        if (_positions.TryGetValue(nodeId, out var position))
        {
            GraphScrollViewer.ChangeView(
                Math.Max(0, position.X * GraphScrollViewer.ZoomFactor - 24),
                Math.Max(0, position.Y * GraphScrollViewer.ZoomFactor - 24),
                null,
                disableAnimation: true);
        }
    }

    private async void OnEditorLoaded(object sender, RoutedEventArgs e)
    {
        await LoadInitialGraphAsync();
    }

    private async Task LoadInitialGraphAsync()
    {
        // A cached page can be loaded again while holding an unsaved draft.
        if (_savedSnapshot is null && !HasUnsavedChanges && !_requestBusy
            && !App.Current.Session.IsClosing)
        {
            // Parent recovery can lock the editor before its first Loaded event.
            // Resume this read when recovery releases the lock, without retrying errors.
            _initialLoadDeferred = _executionBusy;
            if (!_initialLoadDeferred) await LoadGraphAsync();
        }
    }

    private async Task LoadGraphAsync()
    {
        if (_requestBusy || _executionBusy)
        {
            return;
        }

        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            ApplySnapshot(await App.Current.ControlPlane.GetOdbResultGraphAsync());
        }
        catch (Exception exception)
        {
            ShowError("无法读取结果合并图", exception);
        }
        finally
        {
            _requestBusy = false;
            RefreshInteractionState();
        }
    }

    private async void OnSaveClicked(object sender, RoutedEventArgs e)
    {
        if (_requestBusy || _executionBusy || _savedSnapshot is null)
        {
            return;
        }

        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            var snapshot = await App.Current.ControlPlane.SaveOdbResultGraphAsync(
                _savedSnapshot.Revision,
                OutputDirectoryTextBox.Text.Trim(),
                _nodes.Select(CloneNode).ToArray());
            ApplySnapshot(snapshot);
            try { await SaveDraftCheckpointAsync(); }
            catch (Exception error) { ShowError("正式图已保存，但恢复草稿未能更新", error); return; }
            ShowState("结果合并图已保存", "生成前会检查所选路径中的 ODB 和输出位置。", InfoBarSeverity.Success);
        }
        catch (Exception exception)
        {
            // Keep the local draft, including on a server revision conflict.
            ShowError("保存失败，当前编辑已保留", exception);
        }
        finally
        {
            _requestBusy = false;
            RefreshInteractionState();
        }
    }

    private async void OnReloadClicked(object sender, RoutedEventArgs e)
    {
        if (_requestBusy || _executionBusy)
        {
            return;
        }

        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            if (HasUnsavedChanges)
            {
                var confirmed = await ConfirmAsync(
                    "放弃未保存的编辑？",
                    "先保留草稿副本，再用已保存的结果合并图替换当前编辑。",
                    "放弃并重新读取");
                if (!confirmed) return;
                var saving = SaveDraftCheckpointAsync();
                // No timer may recreate the discarded checkpoint while reload awaits HTTP.
                _checkpointPaused = true;
                await saving;
                await _recoveryStore.ArchiveAndClearAsync();
            }
            ApplySnapshot(await App.Current.ControlPlane.GetOdbResultGraphAsync());
            ShowState("结果合并图已读取", "选择节点编辑文件，保存后可生成完整结果。", InfoBarSeverity.Informational);
        }
        catch (Exception error) { ShowError("无法重新读取，当前编辑仍保留", error); }
        finally
        {
            _checkpointPaused = false;
            _requestBusy = false;
            RefreshInteractionState();
        }
    }

    private void ApplySnapshot(OdbResultGraphSnapshot snapshot)
    {
        if (snapshot.Nodes.Count > MaximumNodes)
        {
            throw new InvalidOperationException($"结果合并图最多支持 {MaximumNodes} 个节点。当前草稿已保留。");
        }

        _savedSnapshot = snapshot;
        _nodes.Clear();
        _nodes.AddRange(snapshot.Nodes.Select(CloneNode));
        _targets.IntersectWith(_nodes.Select(node => node.NodeId));
        if (!_nodes.Any(node => node.NodeId == _selectedNodeId))
        {
            _selectedNodeId = _nodes.FirstOrDefault()?.NodeId;
        }

        _updatingFields = true;
        OutputDirectoryTextBox.Text = snapshot.OutputDirectory;
        _updatingFields = false;
        HasUnsavedChanges = false;
        PopulateInspector();
        RenderGraph();
        RefreshInteractionState();
        GraphChanged?.Invoke(this, EventArgs.Empty);
    }

    private void OnAddRootClicked(object sender, RoutedEventArgs e) => AddNode(null);

    private void OnAddNextClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedNodeId is not null && !_nodes.Any(node => node.ParentNodeId == _selectedNodeId))
        {
            AddNode(_selectedNodeId);
        }
    }

    private void OnAddBranchClicked(object sender, RoutedEventArgs e)
    {
        if (_selectedNodeId is not null)
        {
            AddNode(_selectedNodeId);
        }
    }

    private void AddNode(string? parentNodeId)
    {
        if (!CanEdit || _nodes.Count >= MaximumNodes)
        {
            return;
        }

        var node = new OdbResultGraphNode
        {
            NodeId = Guid.NewGuid().ToString("N"),
            Name = $"节点 {_nodes.Count + 1}",
            ParentNodeId = parentNodeId ?? string.Empty,
        };
        _nodes.Add(node);
        _selectedNodeId = node.NodeId;
        MarkDraftChanged();
        RenderGraph();
        PopulateInspector();
        SelectNode(node.NodeId);
        NodeNameTextBox.Focus(FocusState.Programmatic);
        NodeNameTextBox.SelectAll();
    }

    private async void OnRemoveNodeClicked(object sender, RoutedEventArgs e)
    {
        var node = SelectedNode;
        if (!CanEdit || node is null)
        {
            return;
        }

        var subtree = new HashSet<string>(StringComparer.Ordinal) { node.NodeId };
        var pending = new Queue<string>();
        pending.Enqueue(node.NodeId);
        while (pending.TryDequeue(out var parentId))
        {
            foreach (var child in _nodes.Where(item => item.ParentNodeId == parentId))
            {
                if (subtree.Add(child.NodeId))
                {
                    pending.Enqueue(child.NodeId);
                }
            }
        }

        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            if (!await ConfirmAsync(
                "删除当前节点及后续节点？",
                $"将从结果合并图移除“{DisplayName(node)}”及其后续分支，共 {subtree.Count} 个节点。\n源 ODB 和 INP 文件不受影响；保存后生效。",
                "删除节点"))
            {
                return;
            }

            _nodes.RemoveAll(item => subtree.Contains(item.NodeId));
            _targets.ExceptWith(subtree);
            _selectedNodeId = _nodes.FirstOrDefault(item => item.NodeId == node.ParentNodeId)?.NodeId
                ?? _nodes.FirstOrDefault()?.NodeId;
            MarkDraftChanged();
            RenderGraph();
            PopulateInspector();
        }
        catch (Exception exception)
        {
            ShowError("无法删除节点", exception);
        }
        finally
        {
            _requestBusy = false;
            RefreshInteractionState();
        }
    }

    private void OnNodeFieldsChanged(object sender, TextChangedEventArgs e)
    {
        if (!_initialized || _updatingFields || !CanEdit || SelectedNode is not { } node)
        {
            return;
        }

        if (node.Name == NodeNameTextBox.Text && node.OdbPath == NodeOdbTextBox.Text
            && node.InpPath == NodeInpTextBox.Text) return;
        node.Name = NodeNameTextBox.Text;
        node.OdbPath = NodeOdbTextBox.Text;
        node.InpPath = NodeInpTextBox.Text;
        UpdateNodeLabels(node);
        UpdateNodeValidation(node);
        MarkDraftChanged();
    }

    private void OnOutputDirectoryChanged(object sender, TextChangedEventArgs e)
    {
        if (_initialized && !_updatingFields && CanEdit)
        {
            MarkDraftChanged();
        }
    }

    private void MarkDraftChanged()
    {
        // WinUI can deliver TextChanged after programmatic field population.
        var changed = _savedSnapshot is not null && _savedSnapshot.HasEdits(OutputDirectoryTextBox.Text, _nodes);
        if (!changed && !HasUnsavedChanges) return;
        HasUnsavedChanges = changed;
        RefreshInteractionState();
        GraphChanged?.Invoke(this, EventArgs.Empty);
    }

    private void PopulateInspector()
    {
        var node = SelectedNode;
        _updatingFields = true;
        NodeNameTextBox.Text = node?.Name ?? string.Empty;
        NodeOdbTextBox.Text = node?.OdbPath ?? string.Empty;
        NodeInpTextBox.Text = node?.InpPath ?? string.Empty;
        _updatingFields = false;
        NodeContextText.Text = node is null
            ? "点击节点查看和编辑；勾选框用于批量选择结果目标。"
            : string.IsNullOrWhiteSpace(node.ParentNodeId)
                ? "根节点 · 作为此结果链的起始阶段"
                : $"上一阶段：{DisplayName(_nodes.FirstOrDefault(item => item.NodeId == node.ParentNodeId))}";
        UpdateNodeValidation(node);
    }

    private void UpdateNodeValidation(OdbResultGraphNode? node)
    {
        NodeValidationText.Text = node is null ? string.Empty
            : string.IsNullOrWhiteSpace(node.OdbPath)
                ? "待配置 ODB：当前节点可以保存为草稿，生成时须补齐 ODB。关联 INP 不替代结果文件。"
                : "已配置 ODB 路径。生成前将检查文件和完整祖先路径。";
    }

    private async void OnChooseNodeOdbClicked(object sender, RoutedEventArgs e) => await PickNodeFileAsync(".odb");

    private async void OnChooseNodeInpClicked(object sender, RoutedEventArgs e) => await PickNodeFileAsync(".inp");

    private async Task PickNodeFileAsync(string extension)
    {
        var node = SelectedNode;
        if (!CanEdit || node is null)
        {
            return;
        }

        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            var picker = new FileOpenPicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
                CommitButtonText = extension == ".odb" ? "选择本阶段 ODB" : "选择关联 INP",
            };
            picker.FileTypeFilter.Add(extension);
            InitializePicker(picker);
            var file = await picker.PickSingleFileAsync();
            if (file is null)
            {
                return;
            }

            if (extension == ".odb")
            {
                node.OdbPath = file.Path;
            }
            else
            {
                node.InpPath = file.Path;
            }
            if (string.IsNullOrWhiteSpace(node.Name) || node.Name.StartsWith("节点 ", StringComparison.Ordinal))
            {
                node.Name = System.IO.Path.GetFileNameWithoutExtension(file.Path);
            }
            PopulateInspector();
            UpdateNodeLabels(node);
            MarkDraftChanged();
        }
        catch (Exception exception)
        {
            ShowError("无法选择节点文件", exception);
        }
        finally
        {
            _requestBusy = false;
            RefreshInteractionState();
        }
    }

    private async void OnChooseOutputClicked(object sender, RoutedEventArgs e)
    {
        if (!CanEdit)
        {
            return;
        }

        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            var picker = new FolderPicker
            {
                SuggestedStartLocation = PickerLocationId.DocumentsLibrary,
                CommitButtonText = "选择完整结果输出目录",
            };
            picker.FileTypeFilter.Add("*");
            InitializePicker(picker);
            var folder = await picker.PickSingleFolderAsync();
            if (folder is not null)
            {
                _updatingFields = true;
                OutputDirectoryTextBox.Text = folder.Path;
                _updatingFields = false;
                MarkDraftChanged();
            }
        }
        catch (Exception exception)
        {
            ShowError("无法选择输出目录", exception);
        }
        finally
        {
            _requestBusy = false;
            RefreshInteractionState();
        }
    }

    private async void OnGenerateSelectedClicked(object sender, RoutedEventArgs e)
    {
        var ids = _targets.Count > 0
            ? _nodes.Where(node => _targets.Contains(node.NodeId)).Select(node => node.NodeId).ToArray()
            : _selectedNodeId is null ? [] : new[] { _selectedNodeId };
        await RequestPlansAsync(ids);
    }

    private async void OnGenerateLeavesClicked(object sender, RoutedEventArgs e)
    {
        var parents = _nodes.Select(node => node.ParentNodeId).ToHashSet(StringComparer.Ordinal);
        var ids = _nodes.Where(node => !parents.Contains(node.NodeId)).Select(node => node.NodeId).ToArray();
        await RequestPlansAsync(ids);
    }

    private async Task RequestPlansAsync(IReadOnlyList<string> targetIds)
    {
        if (!CanEdit || HasUnsavedChanges || targetIds.Count == 0)
        {
            return;
        }

        // The new check supersedes the last generated graph plan, even if it fails.
        GraphChanged?.Invoke(this, EventArgs.Empty);
        OdbResultBatchPlan? readyPlan = null;
        var requestVersion = _planRequestVersion;
        _requestBusy = true;
        RefreshInteractionState();
        try
        {
            var plan = await App.Current.ControlPlane.PreviewOdbResultGraphPlansAsync(targetIds);
            if (requestVersion != _planRequestVersion) return;
            if (!plan.Valid || plan.Plans.Count == 0)
            {
                ShowState("结果生成计划需要修正",
                    plan.Issues.Count > 0 ? string.Join(Environment.NewLine, plan.Issues) : "所选节点尚无可执行的结果生成路径。",
                    InfoBarSeverity.Warning);
                return;
            }

            if (plan.GraphRevision != _savedSnapshot?.Revision)
            {
                ShowState("结果合并图已被更新", "请重新读取并确认节点内容，再生成结果。", InfoBarSeverity.Warning);
                return;
            }

            readyPlan = plan;
        }
        catch (Exception exception)
        {
            ShowError("无法检查结果生成计划", exception);
        }
        finally
        {
            _requestBusy = false;
            RefreshInteractionState();
        }

        if (readyPlan is not null)
        {
            PlansRequested?.Invoke(this, readyPlan);
        }
    }

    private void RenderGraph()
    {
        GraphCanvas.Children.Clear();
        _nodeCards.Clear();
        _nodeTitles.Clear();
        _nodePaths.Clear();
        _positions.Clear();
        EmptyGraphPanel.Visibility = _nodes.Count == 0 ? Visibility.Visible : Visibility.Collapsed;

        var ids = _nodes.Select(node => node.NodeId).ToHashSet(StringComparer.Ordinal);
        var children = _nodes.GroupBy(node => node.ParentNodeId ?? string.Empty)
            .ToDictionary(group => group.Key, group => group.ToArray(), StringComparer.Ordinal);
        var visited = new HashSet<string>(StringComparer.Ordinal);
        var row = 0;
        double PlaceNode(OdbResultGraphNode node, int depth)
        {
            if (!visited.Add(node.NodeId))
            {
                return _positions.TryGetValue(node.NodeId, out var known) ? known.Y : 24;
            }

            var childRows = new List<double>();
            foreach (var child in children.GetValueOrDefault(node.NodeId, []))
            {
                if (!visited.Contains(child.NodeId))
                {
                    childRows.Add(PlaceNode(child, depth + 1));
                }
            }

            var top = childRows.Count > 0 ? (childRows[0] + childRows[^1]) / 2 : 24 + row++ * (NodeHeight + VerticalGap);
            _positions[node.NodeId] = new Point(24 + depth * (NodeWidth + HorizontalGap), top);
            return top;
        }

        foreach (var root in _nodes.Where(node => string.IsNullOrWhiteSpace(node.ParentNodeId) || !ids.Contains(node.ParentNodeId)))
        {
            PlaceNode(root, 0);
        }
        // Keep an invalid imported graph inspectable; validation remains the service's responsibility.
        foreach (var node in _nodes.Where(node => !visited.Contains(node.NodeId)))
        {
            PlaceNode(node, 0);
        }

        var lineBrush = ThemeBrush("TextFillColorSecondaryBrush");
        foreach (var node in _nodes)
        {
            if (!_positions.TryGetValue(node.ParentNodeId ?? string.Empty, out var parent)
                || !_positions.TryGetValue(node.NodeId, out var child))
            {
                continue;
            }

            var start = new Point(parent.X + NodeWidth, parent.Y + NodeHeight / 2);
            var end = new Point(child.X, child.Y + NodeHeight / 2);
            var midX = (start.X + end.X) / 2;
            GraphCanvas.Children.Add(new Polyline
            {
                Stroke = lineBrush,
                StrokeThickness = 1.5,
                Points = new PointCollection { start, new(midX, start.Y), new(midX, end.Y), end },
                IsHitTestVisible = false,
            });
            GraphCanvas.Children.Add(new Polygon
            {
                Fill = lineBrush,
                Points = new PointCollection { end, new(end.X - 7, end.Y - 4), new(end.X - 7, end.Y + 4) },
                IsHitTestVisible = false,
            });
        }

        foreach (var node in _nodes)
        {
            var card = CreateNodeCard(node);
            var position = _positions[node.NodeId];
            Canvas.SetLeft(card, position.X);
            Canvas.SetTop(card, position.Y);
            GraphCanvas.Children.Add(card);
            _nodeCards[node.NodeId] = card;
        }

        GraphCanvas.Width = Math.Max(220, _positions.Values.Select(point => point.X + NodeWidth + 24).DefaultIfEmpty(220).Max());
        GraphCanvas.Height = Math.Max(408, _positions.Values.Select(point => point.Y + NodeHeight + 24).DefaultIfEmpty(408).Max());
        RefreshNodeSelection();
    }

    private Border CreateNodeCard(OdbResultGraphNode node)
    {
        var title = new TextBlock { FontWeight = FontWeights.SemiBold, TextTrimming = TextTrimming.CharacterEllipsis };
        var path = new TextBlock { FontSize = 12, TextTrimming = TextTrimming.CharacterEllipsis, Foreground = ThemeBrush("TextFillColorSecondaryBrush") };
        _nodeTitles[node.NodeId] = title;
        _nodePaths[node.NodeId] = path;
        var labels = new StackPanel { Spacing = 6, HorizontalAlignment = HorizontalAlignment.Stretch };
        labels.Children.Add(title);
        labels.Children.Add(path);
        var editButton = new Button
        {
            Content = labels,
            HorizontalAlignment = HorizontalAlignment.Stretch,
            HorizontalContentAlignment = HorizontalAlignment.Stretch,
            VerticalAlignment = VerticalAlignment.Stretch,
            Background = new SolidColorBrush(Colors.Transparent),
            BorderThickness = new Thickness(0),
            Padding = new Thickness(10, 8, 10, 4),
        };
        editButton.Click += (_, _) => SelectNode(node.NodeId);
        Microsoft.UI.Xaml.Automation.AutomationProperties.SetName(editButton, $"编辑节点 {DisplayName(node)}");
        var target = new CheckBox
        {
            Content = "生成此节点完整结果",
            FontSize = 12,
            IsChecked = _targets.Contains(node.NodeId),
            Margin = new Thickness(10, 0, 8, 5),
        };
        void OnTargetChanged(object sender, RoutedEventArgs args)
        {
            var changed = target.IsChecked is true
                ? _targets.Add(node.NodeId)
                : _targets.Remove(node.NodeId);
            if (changed) GraphChanged?.Invoke(this, EventArgs.Empty);
            RefreshInteractionState();
        }
        target.Checked += OnTargetChanged;
        target.Unchecked += OnTargetChanged;
        var grid = new Grid();
        grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(1, GridUnitType.Star) });
        grid.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
        grid.Children.Add(editButton);
        Grid.SetRow(target, 1);
        grid.Children.Add(target);
        UpdateNodeLabels(node);
        return new Border
        {
            Width = NodeWidth,
            Height = NodeHeight,
            BorderThickness = new Thickness(2),
            CornerRadius = new CornerRadius(6),
            Background = ThemeBrush("CardBackgroundFillColorDefaultBrush"),
            Child = grid,
        };
    }

    private void UpdateNodeLabels(OdbResultGraphNode node)
    {
        if (_nodeTitles.TryGetValue(node.NodeId, out var title))
        {
            title.Text = DisplayName(node);
            ToolTipService.SetToolTip(title, node.Name);
        }
        if (_nodePaths.TryGetValue(node.NodeId, out var path))
        {
            path.Text = string.IsNullOrWhiteSpace(node.OdbPath)
                ? "待配置 ODB（草稿）"
                : System.IO.Path.GetFileName(node.OdbPath.Replace('/', '\\'));
            ToolTipService.SetToolTip(path, node.OdbPath);
        }
    }

    private void RefreshNodeSelection()
    {
        foreach (var (id, card) in _nodeCards)
        {
            card.BorderBrush = ThemeBrush(id == _selectedNodeId ? "AbaqusAccentBrush" : "CardStrokeColorDefaultBrush");
        }
    }

    private OdbResultGraphNode? SelectedNode => _nodes.FirstOrDefault(node => node.NodeId == _selectedNodeId);

    private bool CanEdit => _initialized && _savedSnapshot is not null && !_requestBusy && !_executionBusy && !RecoveryPending;

    private void RefreshInteractionState()
    {
        if (!_initialized)
        {
            return;
        }

        var selected = SelectedNode;
        RefreshDraftRecovery();
        SaveGraphButton.IsEnabled = CanEdit && HasUnsavedChanges;
        ReloadGraphButton.IsEnabled = !_requestBusy && !_executionBusy;
        AddRootButton.IsEnabled = CanEdit && _nodes.Count < MaximumNodes;
        AddNextButton.IsEnabled = AddRootButton.IsEnabled && selected is not null
            && !_nodes.Any(node => node.ParentNodeId == selected.NodeId);
        ToolTipService.SetToolTip(AddNextButton, "为尚无后续的节点添加下一阶段；已有后续时可添加分支。");
        AddBranchButton.IsEnabled = AddRootButton.IsEnabled && selected is not null;
        RemoveNodeButton.IsEnabled = CanEdit && selected is not null;
        OutputDirectoryTextBox.IsEnabled = CanEdit;
        ChooseOutputButton.IsEnabled = CanEdit;
        InspectorFields.IsEnabled = CanEdit && selected is not null;
        GraphCanvas.IsHitTestVisible = CanEdit;
        GenerateSelectedButton.IsEnabled = CanEdit && !HasUnsavedChanges && (_targets.Count > 0 || selected is not null);
        GenerateLeavesButton.IsEnabled = CanEdit && !HasUnsavedChanges && _nodes.Count > 0;
        var generationHint = HasUnsavedChanges ? "请先保存当前编辑，再检查并生成结果。" : "已勾选时使用勾选目标；未勾选时使用当前编辑节点。";
        ToolTipService.SetToolTip(GenerateSelectedButton, generationHint);
        ToolTipService.SetToolTip(GenerateLeavesButton, HasUnsavedChanges ? generationHint : "分别生成每个末端节点的完整祖先路径结果。");
        DraftStateText.Text = _requestBusy ? "正在处理…"
            : _executionBusy ? "正在生成结果"
            : HasUnsavedChanges ? "有未保存编辑，请先保存"
            : _savedSnapshot is null ? "尚未读取" : $"已保存 · 版本 {_savedSnapshot.Revision}";
        GraphSummaryText.Text = $"{_nodes.Count} 个节点 · 已勾选 {_targets.Count} 个目标 · 结果图独立保存";
    }

    private void OnZoomOutClicked(object sender, RoutedEventArgs e) => ChangeZoom(GraphScrollViewer.ZoomFactor / 1.2f);
    private void OnResetZoomClicked(object sender, RoutedEventArgs e) => ChangeZoom(1f);
    private void OnZoomInClicked(object sender, RoutedEventArgs e) => ChangeZoom(GraphScrollViewer.ZoomFactor * 1.2f);

    private void ChangeZoom(float factor) => GraphScrollViewer.ChangeView(null, null, Math.Clamp(factor, 0.4f, 1.5f), disableAnimation: true);

    private async Task<bool> ConfirmAsync(string title, string message, string primaryText)
    {
        var dialog = new ContentDialog
        {
            XamlRoot = XamlRoot,
            Title = title,
            Content = message,
            PrimaryButtonText = primaryText,
            CloseButtonText = "取消",
            DefaultButton = ContentDialogButton.Close,
        };
        return await dialog.ShowAsync() == ContentDialogResult.Primary;
    }

    private void ShowError(string title, Exception exception) => ShowState(title,
        exception is ControlPlaneException controlPlane ? controlPlane.ToDisplayMessage() : exception.Message,
        InfoBarSeverity.Error);

    private void ShowState(string title, string message, InfoBarSeverity severity)
    {
        App.Current.MainWindow.ShowFeedback(title, message, severity);
    }

    private static void InitializePicker(object picker)
    {
        var handle = WinRT.Interop.WindowNative.GetWindowHandle(App.Current.MainWindow);
        WinRT.Interop.InitializeWithWindow.Initialize(picker, handle);
    }

    private static Brush ThemeBrush(string resourceKey) => App.Current.Resources[resourceKey] as Brush
        ?? new SolidColorBrush(Colors.Gray);

    private static string DisplayName(OdbResultGraphNode? node) => string.IsNullOrWhiteSpace(node?.Name)
        ? "未命名节点" : node.Name;

    private static OdbResultGraphNode CloneNode(OdbResultGraphNode node) => new()
    {
        NodeId = node.NodeId,
        Name = node.Name,
        ParentNodeId = node.ParentNodeId,
        OdbPath = node.OdbPath,
        InpPath = node.InpPath,
    };
}
