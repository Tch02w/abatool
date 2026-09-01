using System.Collections.ObjectModel;

namespace AbaqusTools.WinUI.Explorer;

public enum ExplorerItemKind
{
    Group,
    Directory,
    InputFile,
    OdbFile,
    UserSubroutine,
    OutputFile,
    CandidateJob,
    QueueJob,
    LocalJob,
    RemoteJob,
    RestartChain,
    ResourceNode,
    MergeSource,
    MergeResult,
    ResultScope,
    ResultRecord,
    Other,
}

public enum ExplorerActivationKind
{
    Selection,
    Default,
}

public sealed class ExplorerItem
{
    public required string StableId { get; init; }

    public required ExplorerItemKind Kind { get; init; }

    public required string Title { get; init; }

    public string Subtitle { get; init; } = string.Empty;

    public string Path { get; init; } = string.Empty;

    public string EntityId { get; init; } = string.Empty;

    public string Status { get; init; } = string.Empty;

    public string Badge { get; init; } = string.Empty;

    public string IconGlyph { get; init; } = "\uE8B7";

    public bool IsExpanded { get; init; }

    public ObservableCollection<ExplorerItem> Children { get; } = [];
}

public sealed class WorkbenchExplorerSnapshot
{
    public required string ContextKey { get; init; }

    public required string Title { get; init; }

    public string Subtitle { get; init; } = string.Empty;

    public string Summary { get; init; } = string.Empty;

    public string EmptyMessage { get; init; } = "当前没有可浏览的内容";

    public DateTimeOffset CapturedAt { get; init; } = DateTimeOffset.Now;

    public IReadOnlyList<ExplorerItem> RootItems { get; init; } = [];
}

public interface IWorkbenchExplorerAdapter
{
    string ContextKey { get; }

    string PrimaryActionText { get; }

    WorkbenchExplorerSnapshot Snapshot { get; }

    event EventHandler? SnapshotChanged;

    Task RefreshAsync(CancellationToken cancellationToken);

    Task ExecutePrimaryActionAsync(CancellationToken cancellationToken);

    void Select(ExplorerItem item);

    Task ActivateAsync(
        ExplorerItem item,
        ExplorerActivationKind activationKind,
        CancellationToken cancellationToken);
}

public interface IWorkbenchExplorerPage
{
    IWorkbenchExplorerAdapter ExplorerAdapter { get; }
}
