using AbaqusTools.WinUI.Services;

try
{
    if (args.Contains("--verify-failure-exit"))
    {
        throw new InvalidOperationException("Intentional test-runner failure-exit verification");
    }
    if (args.Length == 2 && args[0] == "--export-checks")
    {
        await ResultFileExportChecks.RunAsync(args[1]);
        return;
    }

    await RefreshLoadsAfterSelectionAsync();
    await IndexSuccessLoadsAfterBothBusyStatesAsync();
    await IndexFailureAndCancellationDoNotLoadAsync();
    await FailedRefreshClearsStateAsync();
    await FailedApplyClearsStateAsync();
    await SupersededRefreshDoesNotPublishAsync();
    await SupersededFailureDoesNotClearNewResultsAsync();
    await RecoveryDoesNotLoadBeforeIndexSuccessAsync();
    await NonTerminalIndexCannotRefreshAsync();
    RecordRequestsAreInvalidated();
    await ResultBrowserLocationChecks.RunAsync();
    await ExplicitResultRoutesAsync();
    CheckTablePreview();
    CheckRecyclePaths();
    Console.WriteLine("10 result-browser asynchronous lifecycle checks and table preview checks passed");
}
catch (Exception exception)
{
    Console.Error.WriteLine(exception);
    Environment.ExitCode = 1;
}

static void Check(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

static void CheckRecyclePaths()
{
    var root = Path.Combine(Path.GetTempPath(), "result-recycle-" + Guid.NewGuid().ToString("N"));
    Directory.CreateDirectory(root);
    var export = Path.Combine(root, "curve.csv");
    var model = Path.Combine(root, "source.odb");
    File.WriteAllText(export, "time,force");
    File.WriteAllText(model, "fixture");
    try
    {
        Check(ResultFileRecycle.ValidatePath(root, export) == export, "Export should be accepted");
        foreach (var path in new[] { model, root, Path.Combine(root, "..", "outside.csv"), Path.Combine(root, "missing.csv") })
        {
            var rejected = false;
            try { ResultFileRecycle.ValidatePath(root, path); }
            catch (IOException) { rejected = true; }
            Check(rejected, $"Unsafe recycle path accepted: {path}");
        }
        Check(File.Exists(export) && File.Exists(model), "Path validation changed source files");
        Console.WriteLine("6 result recycle path checks passed");
    }
    finally
    {
        File.Delete(export);
        File.Delete(model);
        Directory.Delete(root);
    }
}

static TaskCompletionSource<string> PendingDiscovery() =>
    new(TaskCreationOptions.RunContinuationsAsynchronously);

static async Task ExplicitResultRoutesAsync()
{
    var loads = new ResultBrowserLoadCoordinator();
    var location = new ResultBrowserLocation { DraftRoot = "known" };
    var blocked = 0;
    var fileBusy = false;
    Task Read(string root, Task<string> reply)
    {
        var read = location.BeginRead(root);
        return loads.RefreshScopesAsync(() => reply, location.ClearLoadedRoot, value => location.Apply(read, value),
            () => Task.CompletedTask, error => throw error, () => { });
    }
    Task Route(string target) => loads.OpenRootAsync(target, () => fileBusy, () => blocked++, root =>
    {
        location.DraftRoot = root;
        return Read(root, Task.FromResult(root));
    });
    var beforeLoaded = Route("GJA");
    var latest = Route("GJB");
    Check(!beforeLoaded.IsCompleted && !latest.IsCompleted && !loads.CanAutoReadRoot, "First Loaded must restore fields before explicit routing");
    location.DraftRoot = "restored known";
    loads.CompleteInitialIndexCheck();
    await Task.WhenAll(beforeLoaded, latest);
    Check(location.RequireLoadedRoot() == "GJB" && location.DraftRoot == "GJB", "Restored draft or an older route displaced the target");

    loads.LeavePage();
    var oldReply = PendingDiscovery();
    var attachmentRefresh = Read("known", oldReply.Task);
    await Route("GJB");
    oldReply.SetResult("known");
    await attachmentRefresh;
    Check(location.RequireLoadedRoot() == "GJB" && location.DraftRoot == "GJB", "Cached page published a stale explorer response");
    await Route("GJA");
    Check(location.RequireLoadedRoot() == "GJA", "A route to the already visible page must still perform a read");
    fileBusy = true;
    await Route("forbidden");
    fileBusy = false;
    loads.BeginIndex();
    await Route("forbidden");
    loads.EndIndex();
    Check(blocked == 2 && location.RequireLoadedRoot() == "GJA", "Active file or index operations must retain their source");

    var coldPage = new ResultBrowserLoadCoordinator();
    var left = coldPage.OpenRootAsync("abandoned", () => false, () => { }, _ => throw new Exception("Left page opened a pending route"));
    coldPage.LeavePage();
    await left;
    coldPage.CompleteInitialIndexCheck();
    Check(coldPage.CanAutoReadRoot, "A departed cold route must allow a normal draft restore on return");
    Console.WriteLine("6 native result route lifecycle regressions passed");
}

static void CheckTablePreview()
{
    var empty = new ResultTablePreview([], []);
    Check(empty.ColumnCount == 0 && !empty.HasNext && empty.ToClipboardText() == "", "Empty preview");
    var headerOnly = new ResultTablePreview(["时间"], []);
    Check(headerOnly.RowCount == 0 && headerOnly.ToClipboardText() == "时间", "Header-only preview");
    var wideRow = Enumerable.Range(1, 17).Select(i => i.ToString()).ToArray();
    var table = new ResultTablePreview(["编号", ""], [wideRow, ["001", "A\tB", "含\"引号", "两\n行"]]);
    Check(table.ColumnCount == 17 && table.EndColumn == 8 && !table.HasPrevious, "Initial columns");
    Check(table.Header(0) == "编号" && table.Header(1) == "列 2" && table.Header(16) == "列 17", "Column names");
    table.Next();
    Check(table.FirstColumn == 8 && table.EndColumn == 16 && table.HasNext && table.HasPrevious, "Middle columns");
    table.Next();
    table.Next();
    Check(table.FirstColumn == 16 && table.EndColumn == 17 && !table.HasNext && table.Cell(1, 16) == "", "Last ragged column");
    var expected = "编号" + new string('\t', 16) + Environment.NewLine + string.Join("\t", wideRow)
        + Environment.NewLine + "001\t\"A\tB\"\t\"含\"\"引号\"\t\"两\n行\"" + new string('\t', 13);
    Check(table.ToClipboardText() == expected, "Copy includes all original columns and escapes tabs, quotes and newlines");
    table.Previous();
    table.Previous();
    table.Previous();
    Check(table.FirstColumn == 0 && !table.HasPrevious, "Return to first column");
}

static async Task RefreshLoadsAfterSelectionAsync()
{
    var view = new ResultView();
    var discovery = PendingDiscovery();
    var refresh = view.RefreshAsync(() => discovery.Task);
    Check(view.Loads.IsRefreshingScopes, "Discovery must retain its busy state until awaited work ends");
    Check(view.Scope is null && view.Records.Count == 0 && view.Preview is null,
        "A refresh must immediately invalidate the prior scope, rows and preview");
    Check(view.RecordLoads == 0, "Discovery cannot load records before it completes");
    discovery.SetResult("new-time");
    await refresh;
    Check(view.RecordLoads == 1 && view.Records.Single() == "new-time.csv",
        "Programmatic selection during refresh must be followed by exactly one real load");
    Check(view.BusyChanges.SequenceEqual(new[] { true, false }),
        "Scope busy state must be released before loading records");
}

static async Task IndexSuccessLoadsAfterBothBusyStatesAsync()
{
    var view = new ResultView();
    view.Loads.BeginIndex();
    var discovery = PendingDiscovery();
    var completion = view.Loads.CompleteIndexAsync("succeeded", () =>
    {
        Check(!view.Loads.IsIndexing, "Index success must release the index guard before refresh");
        return view.RefreshAsync(() => discovery.Task);
    });
    Check(view.Loads.IsRefreshingScopes && view.RecordLoads == 0,
        "Index success must await directory discovery before loading records");
    discovery.SetResult("indexed-time");
    await completion;
    Check(view.RecordLoads == 1 && view.Records.Single() == "indexed-time.csv",
        "Successful indexing must load records after both guards are released");
}

static async Task IndexFailureAndCancellationDoNotLoadAsync()
{
    foreach (var status in new[] { "failed", "cancelled" })
    {
        var view = new ResultView();
        view.Loads.BeginIndex();
        var refreshes = 0;
        await view.Loads.CompleteIndexAsync(status, () =>
        {
            refreshes++;
            return view.RefreshAsync(() => Task.FromResult("unexpected"));
        });
        Check(refreshes == 0 && view.RecordLoads == 0, $"{status} must not refresh or load new results");
        Check(!view.Loads.IsIndexing, $"{status} must release busy state");
    }
}

static async Task FailedRefreshClearsStateAsync()
{
    var view = new ResultView();
    var oldRequest = view.Loads.InvalidateRecords();
    var error = new IOException("result directory is unavailable");
    await view.RefreshAsync(() => Task.FromException<string>(error));
    Check(view.Scope is null && view.Records.Count == 0 && view.Preview is null,
        "Discovery failure must leave no old directory, records or preview");
    Check(view.Failures.Single() == error && view.RecordLoads == 0,
        "Discovery failure must be reported without triggering record reads");
    Check(!view.Loads.IsRefreshingScopes && !view.Loads.IsCurrentRecordRequest(oldRequest),
        "Failed refresh must release busy state and reject old record responses");
}

static async Task FailedApplyClearsStateAsync()
{
    var view = new ResultView();
    await view.RefreshAsync(() => Task.FromResult("partially-applied"), failApply: true);
    Check(view.Scope is null && view.Records.Count == 0 && view.Preview is null,
        "A tree-application exception must clear partially applied state");
    Check(view.Failures.Count == 1 && view.RecordLoads == 0 && !view.Loads.IsRefreshingScopes,
        "Apply failure cannot load records or leave the page busy");
}

static async Task SupersededRefreshDoesNotPublishAsync()
{
    var view = new ResultView();
    var oldDiscovery = PendingDiscovery();
    var newDiscovery = PendingDiscovery();
    var oldRefresh = view.RefreshAsync(() => oldDiscovery.Task);
    var newRefresh = view.RefreshAsync(() => newDiscovery.Task);
    oldDiscovery.SetResult("old-time");
    await oldRefresh;
    Check(view.Loads.IsRefreshingScopes && view.Scope is null && view.RecordLoads == 0,
        "Old completion must neither publish its tree nor release the new request's busy state");
    newDiscovery.SetResult("new-time");
    await newRefresh;
    Check(view.Scope == "new-time" && view.RecordLoads == 1,
        "Only the newest directory request may publish and load results");
}

static async Task SupersededFailureDoesNotClearNewResultsAsync()
{
    var view = new ResultView();
    var oldDiscovery = PendingDiscovery();
    var oldRefresh = view.RefreshAsync(() => oldDiscovery.Task);
    await view.RefreshAsync(() => Task.FromResult("new-time"));
    oldDiscovery.SetException(new IOException("old failure"));
    await oldRefresh;
    Check(view.Scope == "new-time" && view.Records.Single() == "new-time.csv"
        && view.Failures.Count == 0 && view.RecordLoads == 1,
        "Late failure must not clear or report against the new directory's results");
}

static async Task RecoveryDoesNotLoadBeforeIndexSuccessAsync()
{
    var view = new ResultView();
    view.Loads.BeginIndex();
    await view.RefreshAsync(() => Task.FromResult("recovering-time"));
    Check(view.Scope == "recovering-time" && view.RecordLoads == 0,
        "Recovering an active index may show the tree but must defer record loading");
    await view.Loads.CompleteIndexAsync("cancelled",
        () => view.RefreshAsync(() => Task.FromResult("unexpected")));
    Check(view.RecordLoads == 0, "Cancelled index recovery must not load results");
}

static async Task NonTerminalIndexCannotRefreshAsync()
{
    var loads = new ResultBrowserLoadCoordinator();
    loads.BeginIndex();
    var refreshed = false;
    try
    {
        await loads.CompleteIndexAsync("running", () =>
        {
            refreshed = true;
            return Task.CompletedTask;
        });
        throw new Exception("A nonterminal completion must be rejected");
    }
    catch (InvalidOperationException)
    {
        Check(loads.IsIndexing && !refreshed, "Nonterminal state must retain the index guard");
    }
}

static void RecordRequestsAreInvalidated()
{
    var loads = new ResultBrowserLoadCoordinator();
    var recoveryContext = loads.ContextRevision;
    var first = loads.InvalidateRecords();
    var second = loads.InvalidateRecords();
    Check(!loads.IsCurrentRecordRequest(first) && loads.IsCurrentRecordRequest(second),
        "A later filter/selection request must invalidate the former record response");
    loads.BeginIndex();
    var formerIndex = loads.IndexRevision;
    Check(!loads.IsCurrentRecordRequest(second) && !loads.CanLoadRecords,
        "Beginning an index must invalidate pending record responses and block new reads");
    Check(loads.ContextRevision != recoveryContext,
        "Beginning an index must invalidate a pending recovery lookup");
    loads.EndIndex();
    loads.BeginIndex();
    Check(!loads.IsCurrentIndexRequest(formerIndex),
        "A later index must reject progress and cleanup from the former owner");
}

// The actual production coordinator is linked into this executable. These callbacks
// represent the page's view effects; they intentionally exercise selection reentrancy.
sealed class ResultView
{
    public ResultBrowserLoadCoordinator Loads { get; } = new();
    public string? Scope { get; private set; } = "old-time";
    public List<string> Records { get; } = ["old.csv"];
    public string? Preview { get; private set; } = "old preview";
    public int RecordLoads { get; private set; }
    public List<Exception> Failures { get; } = [];
    public List<bool> BusyChanges { get; } = [];

    public Task RefreshAsync(Func<Task<string>> discover, bool failApply = false) =>
        Loads.RefreshScopesAsync(discover,
            () =>
            {
                Scope = null;
                Records.Clear();
                Preview = null;
            },
            scope =>
            {
                Scope = scope;
                if (failApply) throw new InvalidOperationException("tree application failed");
                // Equivalent to the page's SelectionChanged event during tree rebuild.
                if (Loads.CanLoadRecords) LoadRecords();
            },
            () =>
            {
                if (!Loads.CanLoadRecords)
                    throw new InvalidOperationException("Record callback ran with a busy guard");
                LoadRecords();
                return Task.CompletedTask;
            },
            Failures.Add,
            () => BusyChanges.Add(Loads.IsRefreshingScopes));

    private void LoadRecords()
    {
        if (Scope is null) throw new InvalidOperationException("No selected scope");
        RecordLoads++;
        Records.Add(Scope + ".csv");
    }
}
