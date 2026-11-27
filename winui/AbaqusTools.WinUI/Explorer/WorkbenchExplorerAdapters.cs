using AbaqusTools.WinUI.Services;

namespace AbaqusTools.WinUI.Explorer;

public abstract class WorkbenchExplorerAdapterBase : IWorkbenchExplorerAdapter
{
    public abstract string ContextKey { get; }

    public virtual string PrimaryActionText => string.Empty;

    public WorkbenchExplorerSnapshot Snapshot { get; private set; }

    public event EventHandler? SnapshotChanged;

    protected WorkbenchExplorerAdapterBase(string title, string emptyMessage)
    {
        Snapshot = new WorkbenchExplorerSnapshot
        {
            ContextKey = ContextKey,
            Title = title,
            EmptyMessage = emptyMessage,
        };
    }

    public abstract Task RefreshAsync(CancellationToken cancellationToken);

    public virtual Task ExecutePrimaryActionAsync(CancellationToken cancellationToken) =>
        Task.CompletedTask;

    public virtual void Select(ExplorerItem item)
    {
    }

    public virtual Task ActivateAsync(
        ExplorerItem item,
        ExplorerActivationKind activationKind,
        CancellationToken cancellationToken) => Task.CompletedTask;

    protected void Publish(WorkbenchExplorerSnapshot snapshot)
    {
        Snapshot = snapshot;
        SnapshotChanged?.Invoke(this, EventArgs.Empty);
    }

    internal static ExplorerItem Group(
        string id,
        string title,
        IEnumerable<ExplorerItem> children,
        string badge = "")
    {
        var item = new ExplorerItem
        {
            StableId = id,
            Kind = ExplorerItemKind.Group,
            Title = title,
            Badge = badge,
            IconGlyph = "\uE8B7",
            IsExpanded = true,
        };
        foreach (var child in children)
        {
            item.Children.Add(child);
        }
        return item;
    }
}

public sealed class WorkspaceExplorerAdapter : WorkbenchExplorerAdapterBase
{
    private readonly Func<Task<string?>> _chooseRoot;
    private readonly Func<ExplorerItem, Task> _activate;
    private readonly Action<ExplorerItem>? _select;
    private string _root = string.Empty;

    public override string ContextKey => "workspace";

    public override string PrimaryActionText => "选择目录";

    public WorkspaceExplorerAdapter(
        Func<Task<string?>> chooseRoot,
        Func<ExplorerItem, Task> activate,
        Action<ExplorerItem>? select = null)
        : base("工作目录", "选择工作目录后显示 INP、ODB 和用户子程序")
    {
        _chooseRoot = chooseRoot;
        _activate = activate;
        _select = select;
    }

    public void UsePath(string path)
    {
        var root = Directory.Exists(path) ? path : Path.GetDirectoryName(path) ?? string.Empty;
        if (string.IsNullOrWhiteSpace(root)
            || string.Equals(root, _root, StringComparison.OrdinalIgnoreCase))
        {
            return;
        }
        _root = root;
        _ = RefreshSafelyAsync();
    }

    private async Task RefreshSafelyAsync()
    {
        try
        {
            await RefreshAsync(CancellationToken.None);
        }
        catch (IOException)
        {
            PublishUnavailableSnapshot();
        }
        catch (UnauthorizedAccessException)
        {
            PublishUnavailableSnapshot();
        }
    }

    private void PublishUnavailableSnapshot() => Publish(new WorkbenchExplorerSnapshot
    {
        ContextKey = ContextKey,
        Title = "工作目录",
        Subtitle = _root,
        Summary = "目录读取失败",
        EmptyMessage = "当前目录不可访问，请重新选择工作目录",
    });

    public override async Task ExecutePrimaryActionAsync(CancellationToken cancellationToken)
    {
        var root = await _chooseRoot();
        cancellationToken.ThrowIfCancellationRequested();
        if (!string.IsNullOrWhiteSpace(root))
        {
            _root = root;
            await RefreshAsync(cancellationToken);
        }
    }

    public override async Task RefreshAsync(CancellationToken cancellationToken)
    {
        var snapshot = await WorkspaceExplorerDiscovery.ScanAsync(
            ContextKey,
            "工作目录",
            _root,
            cancellationToken);
        Publish(snapshot);
    }

    public override void Select(ExplorerItem item) => _select?.Invoke(item);

    public override Task ActivateAsync(
        ExplorerItem item,
        ExplorerActivationKind activationKind,
        CancellationToken cancellationToken) => _activate(item);
}

public sealed class QueueExplorerAdapter : WorkbenchExplorerAdapterBase
{
    private readonly ControlPlaneHost _controlPlane;
    private readonly Func<Task<string?>> _chooseRoot;
    private readonly Func<ExplorerItem, Task> _activate;
    private readonly Action<ExplorerItem>? _select;
    private string _root = string.Empty;
    private JobQueueSnapshot _queue = new();
    private bool _hasQueueSnapshot;
    private IReadOnlyList<ExplorerItem> _workspaceInputs = [];

    public override string ContextKey => "queue";

    public override string PrimaryActionText => "选择目录";

    public QueueExplorerAdapter(
        ControlPlaneHost controlPlane,
        Func<Task<string?>> chooseRoot,
        Func<ExplorerItem, Task> activate,
        Action<ExplorerItem>? select = null)
        : base("队列文件", "选择目录或添加 INP 后显示候选与正式队列")
    {
        _controlPlane = controlPlane;
        _chooseRoot = chooseRoot;
        _activate = activate;
        _select = select;
    }

    public void Update(JobQueueSnapshot snapshot)
    {
        var changed = !_hasQueueSnapshot || !_queue.HasSameExplorerContent(snapshot);
        _hasQueueSnapshot = true;
        _queue = snapshot;
        var inferredRoot = InferRoot(snapshot, _root);
        if (!string.Equals(inferredRoot, _root, StringComparison.OrdinalIgnoreCase))
        {
            _root = inferredRoot;
            _workspaceInputs = WorkspaceExplorerDiscovery.ScanInputFiles(_root);
            changed = true;
        }
        if (changed) Publish(BuildSnapshot());
    }

    public override async Task ExecutePrimaryActionAsync(CancellationToken cancellationToken)
    {
        var root = await _chooseRoot();
        cancellationToken.ThrowIfCancellationRequested();
        if (!string.IsNullOrWhiteSpace(root))
        {
            _root = root;
            await RefreshAsync(cancellationToken);
        }
    }

    public override async Task RefreshAsync(CancellationToken cancellationToken)
    {
        _queue = await _controlPlane.GetJobQueuesAsync();
        cancellationToken.ThrowIfCancellationRequested();
        _root = InferRoot(_queue, _root);
        _workspaceInputs = await Task.Run(
            () => WorkspaceExplorerDiscovery.ScanInputFiles(_root),
            cancellationToken);
        Publish(BuildSnapshot());
    }

    public override void Select(ExplorerItem item) => _select?.Invoke(item);

    public override Task ActivateAsync(
        ExplorerItem item,
        ExplorerActivationKind activationKind,
        CancellationToken cancellationToken) => _activate(item);

    private WorkbenchExplorerSnapshot BuildSnapshot()
    {
        var candidates = _queue.Candidates.Select(item => JobItem(item, true)).ToArray();
        var formal = _queue.QueueItems.Select(item => JobItem(item, false)).ToArray();
        var roots = new List<ExplorerItem>();
        if (_workspaceInputs.Count > 0)
        {
            roots.Add(Group(
                "queue:workspace",
                "工作目录 INP",
                _workspaceInputs,
                _workspaceInputs.Count.ToString()));
        }
        roots.Add(Group("queue:candidates", "候选作业", candidates, candidates.Length.ToString()));
        roots.Add(Group("queue:formal", "正式队列", formal, formal.Length.ToString()));
        return new WorkbenchExplorerSnapshot
        {
            ContextKey = ContextKey,
            Title = "队列文件",
            Subtitle = _root,
            Summary = $"候选 {_queue.CandidateCount} · 正式 {_queue.QueueCount}",
            EmptyMessage = "选择目录或添加 INP 后显示队列内容",
            RootItems = roots,
        };
    }

    private static ExplorerItem JobItem(JobQueueItem item, bool candidate) => new()
    {
        StableId = $"{(candidate ? "candidate" : "queue")}:{item.ItemId}",
        Kind = candidate ? ExplorerItemKind.CandidateJob : ExplorerItemKind.QueueJob,
        Title = string.IsNullOrWhiteSpace(item.JobName) ? Path.GetFileNameWithoutExtension(item.InpPath) : item.JobName,
        Subtitle = candidate ? item.Message : item.InpPath,
        Path = item.InpPath,
        EntityId = item.ItemId,
        Status = candidate ? (item.Valid ? "可加入" : "需要处理") : item.Status,
        Badge = candidate && item.Selected ? "已选" : item.Status,
        IconGlyph = candidate ? "\uE8A5" : "\uE9D5",
    };

    private static string InferRoot(JobQueueSnapshot snapshot, string current) =>
        !string.IsNullOrWhiteSpace(current)
            ? current
            : snapshot.Candidates.Concat(snapshot.QueueItems)
                .Select(item => Path.GetDirectoryName(item.InpPath))
                .FirstOrDefault(path => !string.IsNullOrWhiteSpace(path)) ?? string.Empty;
}

public sealed class JobMonitorExplorerAdapter : WorkbenchExplorerAdapterBase
{
    private readonly ControlPlaneHost _controlPlane;
    private readonly Action<ExplorerItem> _select;
    private IReadOnlyList<ExplorerItem> _items = [];

    public override string ContextKey => "job-monitor";

    public JobMonitorExplorerAdapter(
        ControlPlaneHost controlPlane,
        Action<ExplorerItem> select)
        : base("运行作业", "本机正式队列和远端会话中尚无作业")
    {
        _controlPlane = controlPlane;
        _select = select;
    }

    public void Update(
        JobQueueSnapshot? localQueue,
        IReadOnlyList<RemoteJobOperationSnapshot> remoteJobs)
    {
        _items = (localQueue?.QueueItems ?? []).Select(LocalJobItem)
            .Concat(remoteJobs.Select(RemoteJobItem))
            .ToArray();
        Publish(BuildSnapshot(hasLocalQueue: localQueue is not null));
    }

    public override async Task RefreshAsync(CancellationToken cancellationToken)
    {
        var localTask = _controlPlane.GetLocalQueueRuntimeAsync();
        var remoteTask = _controlPlane.ListRemoteJobsAsync();
        await Task.WhenAll(localTask, remoteTask);
        cancellationToken.ThrowIfCancellationRequested();
        Update((await localTask).Queue, (await remoteTask).Operations);
    }

    public override void Select(ExplorerItem item) => _select(item);

    public override Task ActivateAsync(
        ExplorerItem item,
        ExplorerActivationKind activationKind,
        CancellationToken cancellationToken)
    {
        _select(item);
        return Task.CompletedTask;
    }

    private WorkbenchExplorerSnapshot BuildSnapshot(bool hasLocalQueue)
    {
        var active = _items.Where(item => IsActive(item.Status)).ToArray();
        var waiting = _items.Where(item => IsWaiting(item.Status)).ToArray();
        var abnormal = _items.Where(item => IsAbnormal(item.Status)).ToArray();
        var completed = _items.Except(active).Except(waiting).Except(abnormal).ToArray();
        return new WorkbenchExplorerSnapshot
        {
            ContextKey = ContextKey,
            Title = "运行作业",
            Summary = hasLocalQueue ? $"运行 {active.Length} · 等待 {waiting.Length} · 异常 {abnormal.Length}"
                : $"正在读取本机队列… · 远端作业 {_items.Count}",
            EmptyMessage = hasLocalQueue ? "本机正式队列和远端会话中尚无作业" : "正在读取本机队列…",
            RootItems =
            [
                Group("jobs:active", "运行中", active, active.Length.ToString()),
                Group("jobs:waiting", "等待与暂停", waiting, waiting.Length.ToString()),
                Group("jobs:abnormal", "异常", abnormal, abnormal.Length.ToString()),
                Group("jobs:completed", "最近完成", completed, completed.Length.ToString()),
            ],
        };
    }

    private static ExplorerItem LocalJobItem(JobQueueItem item) => new()
    {
        StableId = $"local:{item.ItemId}",
        Kind = ExplorerItemKind.LocalJob,
        Title = item.JobName,
        Subtitle = string.IsNullOrWhiteSpace(item.Elapsed) ? "本机" : $"本机 · {item.Elapsed}",
        Path = item.InpPath,
        EntityId = item.ItemId,
        Status = item.Status,
        Badge = item.Status,
        IconGlyph = "\uE9D5",
    };

    private static ExplorerItem RemoteJobItem(RemoteJobOperationSnapshot operation) => new()
    {
        StableId = $"remote:{operation.OperationId}",
        Kind = ExplorerItemKind.RemoteJob,
        Title = operation.Request.JobName,
        Subtitle = string.IsNullOrWhiteSpace(operation.WorkDirectory) ? "远端" : operation.WorkDirectory,
        Path = operation.Request.InputPath,
        EntityId = operation.OperationId,
        Status = operation.Status,
        Badge = $"{operation.Percent}%",
        IconGlyph = "\uE968",
    };

    private static bool IsActive(string status) => status is "运行中" or "正在启动" or "starting" or "running" or "cancelling";

    private static bool IsWaiting(string status) => status.Contains("等待", StringComparison.Ordinal)
        || status.Contains("暂停", StringComparison.Ordinal)
        || status is "queued";

    private static bool IsAbnormal(string status) => status.Contains("失败", StringComparison.Ordinal)
        || status.Contains("异常", StringComparison.Ordinal)
        || status.Contains("终止", StringComparison.Ordinal)
        || status is "failed" or "cancelled";
}

public sealed class ProjectExplorerAdapter : WorkbenchExplorerAdapterBase
{
    private readonly ControlPlaneHost _controlPlane;
    private readonly Func<ExplorerItem, Task> _activate;
    private string _selectedInputPath = string.Empty;

    public override string ContextKey => "project";

    public ProjectExplorerAdapter(
        ControlPlaneHost controlPlane,
        Func<ExplorerItem, Task> activate)
        : base("项目", "选择 INP 或加入队列后显示项目内容")
    {
        _controlPlane = controlPlane;
        _activate = activate;
    }

    public void UsePath(string path)
    {
        _selectedInputPath = path.Trim();
        _ = RefreshSafelyAsync();
    }

    private async Task RefreshSafelyAsync()
    {
        try
        {
            await RefreshAsync(CancellationToken.None);
        }
        catch (HttpRequestException)
        {
            PublishControlPlaneUnavailableSnapshot();
        }
        catch (InvalidOperationException)
        {
            PublishControlPlaneUnavailableSnapshot();
        }
    }

    private void PublishControlPlaneUnavailableSnapshot() => Publish(new WorkbenchExplorerSnapshot
    {
        ContextKey = ContextKey,
        Title = "项目",
        Summary = "控制面暂不可用",
        EmptyMessage = "控制面恢复后将自动显示项目内容",
    });

    public override async Task RefreshAsync(CancellationToken cancellationToken)
    {
        var queue = await _controlPlane.GetJobQueuesAsync();
        cancellationToken.ThrowIfCancellationRequested();
        var inputs = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        if (!string.IsNullOrWhiteSpace(_selectedInputPath))
        {
            inputs.Add(_selectedInputPath);
        }
        foreach (var item in queue.Candidates.Concat(queue.QueueItems))
        {
            if (!string.IsNullOrWhiteSpace(item.InpPath))
            {
                inputs.Add(item.InpPath);
            }
        }

        var inputItems = inputs.Select(WorkspaceExplorerDiscovery.FileItem).ToArray();
        var odbItems = inputs.SelectMany(WorkspaceExplorerDiscovery.DiscoverSiblingOdbs)
            .Distinct(StringComparer.OrdinalIgnoreCase)
            .Select(WorkspaceExplorerDiscovery.FileItem)
            .ToArray();
        var jobs = queue.QueueItems.Select(item => new ExplorerItem
        {
            StableId = $"project:job:{item.ItemId}",
            Kind = ExplorerItemKind.QueueJob,
            Title = item.JobName,
            Subtitle = item.Status,
            Path = item.InpPath,
            EntityId = item.ItemId,
            Status = item.Status,
            Badge = item.Status,
            IconGlyph = "\uE9D5",
        }).ToArray();
        var restarts = queue.QueueItems.Where(item =>
                !string.IsNullOrWhiteSpace(item.OldjobName)
                || !string.IsNullOrWhiteSpace(item.OldjobPath))
            .Select(item => new ExplorerItem
            {
                StableId = $"project:restart:{item.ItemId}",
                Kind = ExplorerItemKind.RestartChain,
                Title = $"{item.OldjobName} → {item.JobName}",
                Subtitle = item.OldjobPath,
                Path = item.OldjobPath,
                EntityId = item.ItemId,
                IconGlyph = "\uE895",
            }).ToArray();
        Publish(new WorkbenchExplorerSnapshot
        {
            ContextKey = ContextKey,
            Title = "项目",
            Subtitle = inputs.Select(Path.GetDirectoryName).FirstOrDefault(path => !string.IsNullOrWhiteSpace(path)) ?? string.Empty,
            Summary = $"输入 {inputItems.Length} · 结果 {odbItems.Length} · 作业 {jobs.Length}",
            RootItems =
            [
                Group("project:inputs", "输入文件", inputItems, inputItems.Length.ToString()),
                Group("project:results", "结果文件", odbItems, odbItems.Length.ToString()),
                Group("project:jobs", "作业", jobs, jobs.Length.ToString()),
                Group("project:restarts", "重启动链", restarts, restarts.Length.ToString()),
            ],
        });
    }

    public override Task ActivateAsync(
        ExplorerItem item,
        ExplorerActivationKind activationKind,
        CancellationToken cancellationToken) => _activate(item);
}

public abstract class PageExplorerAdapterBase : WorkbenchExplorerAdapterBase
{
    private readonly Func<Task>? _refresh;
    private readonly Action<ExplorerItem>? _select;
    private readonly Func<ExplorerItem, Task>? _activate;

    protected PageExplorerAdapterBase(
        string title,
        string emptyMessage,
        Func<Task>? refresh = null,
        Action<ExplorerItem>? select = null,
        Func<ExplorerItem, Task>? activate = null)
        : base(title, emptyMessage)
    {
        _refresh = refresh;
        _select = select;
        _activate = activate;
    }

    public override async Task RefreshAsync(CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        if (_refresh is not null)
        {
            await _refresh();
        }
    }

    public override void Select(ExplorerItem item) => _select?.Invoke(item);

    public override Task ActivateAsync(
        ExplorerItem item,
        ExplorerActivationKind activationKind,
        CancellationToken cancellationToken) => _activate?.Invoke(item) ?? Task.CompletedTask;

    public void Update(
        string subtitle,
        string summary,
        IReadOnlyList<ExplorerItem> rootItems,
        string emptyMessage = "") => Publish(new WorkbenchExplorerSnapshot
    {
        ContextKey = ContextKey,
        Title = Snapshot.Title,
        Subtitle = subtitle,
        Summary = summary,
        EmptyMessage = string.IsNullOrWhiteSpace(emptyMessage)
            ? Snapshot.EmptyMessage
            : emptyMessage,
        RootItems = rootItems,
    });
}

public sealed class ResourceExplorerAdapter : PageExplorerAdapterBase
{
    public override string ContextKey => "resources";
    public ResourceExplorerAdapter(Func<Task> refresh, Action<ExplorerItem> select)
        : base("计算资源", "尚无可用资源节点", refresh, select) { }
}

public sealed class RestartChainExplorerAdapter : PageExplorerAdapterBase
{
    public override string ContextKey => "restart-chain";
    public RestartChainExplorerAdapter(Func<Task> refresh, Action<ExplorerItem> select)
        : base("重启动计算", "正式队列中尚无重启动作业", refresh, select) { }
}

public sealed class OdbMergeExplorerAdapter : PageExplorerAdapterBase
{
    public override string ContextKey => "odb-merge";
    public OdbMergeExplorerAdapter(Action<ExplorerItem> select)
        : base("完整结果", "请选择 ODB 或从重启动节点生成计划", select: select) { }
}

public sealed class PostprocessingExplorerAdapter : PageExplorerAdapterBase
{
    public override string ContextKey => "odb-postprocessing";
    public PostprocessingExplorerAdapter(Func<Task> refresh, Action<ExplorerItem> select, Func<ExplorerItem, Task> activate)
        : base("后处理 ODB", "选择目录后显示 ODB 与对比组", refresh, select, activate) { }
}

public sealed class ResultExplorerAdapter : PageExplorerAdapterBase
{
    public override string ContextKey => "result-browser";
    public ResultExplorerAdapter(Func<Task> refresh, Action<ExplorerItem> select, Func<ExplorerItem, Task> activate)
        : base("结果目录", "读取目录后显示范围与结果文件", refresh, select, activate) { }
}

internal static class WorkspaceExplorerDiscovery
{
    private static readonly HashSet<string> VisibleExtensions = new(
        [".inp", ".odb", ".for", ".f", ".f90", ".obj", ".sta", ".msg", ".dat", ".log"],
        StringComparer.OrdinalIgnoreCase);

    public static Task<WorkbenchExplorerSnapshot> ScanAsync(
        string contextKey,
        string title,
        string root,
        CancellationToken cancellationToken) => Task.Run(
        () =>
        {
            if (string.IsNullOrWhiteSpace(root) || !Directory.Exists(root))
            {
                return new WorkbenchExplorerSnapshot
                {
                    ContextKey = contextKey,
                    Title = title,
                    EmptyMessage = "选择工作目录后显示 INP、ODB 和用户子程序",
                };
            }

            var files = Directory.EnumerateFiles(root)
                .Where(path => VisibleExtensions.Contains(Path.GetExtension(path)))
                .OrderBy(path => Path.GetFileName(path), StringComparer.OrdinalIgnoreCase)
                .Select(FileItem)
                .ToArray();
            cancellationToken.ThrowIfCancellationRequested();
            var groups = files.GroupBy(item => GroupKey(item.Kind))
                .Select(group => WorkbenchExplorerAdapterBase.Group(
                    $"{contextKey}:group:{group.Key}",
                    group.Key,
                    group,
                    group.Count().ToString()))
                .ToArray();
            return new WorkbenchExplorerSnapshot
            {
                ContextKey = contextKey,
                Title = title,
                Subtitle = root,
                Summary = $"找到 {files.Length} 个相关文件",
                EmptyMessage = "目录中没有 INP、ODB 或用户子程序",
                RootItems = groups,
            };
        },
        cancellationToken);

    public static IReadOnlyList<ExplorerItem> ScanInputFiles(string root)
    {
        if (string.IsNullOrWhiteSpace(root) || !Directory.Exists(root))
        {
            return [];
        }
        try
        {
            return Directory.EnumerateFiles(root, "*.inp")
                .OrderBy(path => Path.GetFileName(path), StringComparer.OrdinalIgnoreCase)
                .Select(FileItem)
                .ToArray();
        }
        catch (IOException)
        {
            return [];
        }
        catch (UnauthorizedAccessException)
        {
            return [];
        }
    }

    public static IEnumerable<string> DiscoverSiblingOdbs(string inputPath)
    {
        var root = Path.GetDirectoryName(inputPath);
        if (string.IsNullOrWhiteSpace(root) || !Directory.Exists(root))
        {
            return [];
        }
        try
        {
            return Directory.EnumerateFiles(root, "*.odb").ToArray();
        }
        catch (IOException)
        {
            return [];
        }
        catch (UnauthorizedAccessException)
        {
            return [];
        }
    }

    public static ExplorerItem FileItem(string path)
    {
        var extension = Path.GetExtension(path);
        var kind = extension.ToLowerInvariant() switch
        {
            ".inp" => ExplorerItemKind.InputFile,
            ".odb" => ExplorerItemKind.OdbFile,
            ".for" or ".f" or ".f90" or ".obj" => ExplorerItemKind.UserSubroutine,
            ".sta" or ".msg" or ".dat" or ".log" => ExplorerItemKind.OutputFile,
            _ => ExplorerItemKind.Other,
        };
        var info = new FileInfo(path);
        return new ExplorerItem
        {
            StableId = $"file:{path.ToUpperInvariant()}",
            Kind = kind,
            Title = Path.GetFileName(path),
            Subtitle = info.Exists ? $"{FormatSize(info.Length)} · {info.LastWriteTime:yyyy-MM-dd HH:mm}" : path,
            Path = path,
            Status = info.Exists ? "可用" : "已不存在",
            IconGlyph = kind switch
            {
                ExplorerItemKind.InputFile => "\uE8A5",
                ExplorerItemKind.OdbFile => "\uE8A5",
                ExplorerItemKind.UserSubroutine => "\uE943",
                _ => "\uE7C3",
            },
        };
    }

    private static string GroupKey(ExplorerItemKind kind) => kind switch
    {
        ExplorerItemKind.InputFile => "Abaqus 输入文件",
        ExplorerItemKind.OdbFile => "ODB 结果与依赖",
        ExplorerItemKind.UserSubroutine => "用户子程序",
        ExplorerItemKind.OutputFile => "运行输出",
        _ => "其他",
    };

    private static string FormatSize(long size) => size switch
    {
        >= 1073741824 => $"{size / 1073741824d:0.0} GB",
        >= 1048576 => $"{size / 1048576d:0.0} MB",
        >= 1024 => $"{size / 1024d:0.0} KB",
        _ => $"{size} B",
    };
}
