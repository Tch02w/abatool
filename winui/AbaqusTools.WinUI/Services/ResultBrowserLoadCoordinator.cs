namespace AbaqusTools.WinUI.Services;

/// <summary>
/// Orders scope discovery, selection and record loading without depending on XAML events.
/// Selection events raised while rebuilding the tree are deliberately deferred until
/// discovery has finished; only a successful index operation may trigger a new refresh.
/// </summary>
internal sealed class ResultBrowserLoadCoordinator
{
    private long _scopeRevision;
    private long _recordRevision;
    private long _contextRevision;
    private long _indexRevision;
    private readonly TaskCompletionSource _initialIndexCheck = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private TaskCompletionSource _leftPage = new(TaskCreationOptions.RunContinuationsAsynchronously);
    private long _routeRevision;

    public bool IsRefreshingScopes { get; private set; }
    public bool IsIndexing { get; private set; }
    public bool CanLoadRecords => !IsRefreshingScopes && !IsIndexing;
    public long ContextRevision => _contextRevision;
    public long IndexRevision => _indexRevision;
    public bool CanAutoReadRoot => _initialIndexCheck.Task.IsCompleted && _routeRevision == 0;
    public bool InitialIndexChecked => _initialIndexCheck.Task.IsCompleted;

    public void CompleteInitialIndexCheck() => _initialIndexCheck.TrySetResult();

    public void LeavePage()
    {
        _leftPage.TrySetResult();
        _leftPage = new(TaskCreationOptions.RunContinuationsAsynchronously);
        _routeRevision = 0;
    }

    public async Task OpenRootAsync(string root, Func<bool> fileBusy, Action blocked, Func<string, Task> read)
    {
        var revision = ++_routeRevision;
        var left = _leftPage.Task;
        // Session fields restore on the first Loaded. Reattaching a cached page can also
        // start an older sidebar read before the frame reports IsLoaded.
        await Task.WhenAny(_initialIndexCheck.Task, left);
        if (left.IsCompleted || revision != _routeRevision) return;
        if (IsIndexing || fileBusy()) { blocked(); return; }
        await read(root);
    }

    public bool IsCurrentIndexRequest(long revision) => revision == _indexRevision;

    public long InvalidateRecords() => ++_recordRevision;

    public bool IsCurrentRecordRequest(long revision) => revision == _recordRevision;

    public void BeginIndex()
    {
        _contextRevision++;
        _indexRevision++;
        IsIndexing = true;
        InvalidateRecords();
    }

    public void EndIndex() => IsIndexing = false;

    public async Task CompleteIndexAsync(string status, Func<Task> refreshAfterSuccess)
    {
        if (status is not ("succeeded" or "failed" or "cancelled"))
        {
            throw new InvalidOperationException("索引尚未结束，不能加载结果。");
        }

        EndIndex();
        if (status == "succeeded")
        {
            await refreshAfterSuccess();
        }
    }

    public async Task RefreshScopesAsync<T>(
        Func<Task<T>> discover,
        Action clear,
        Action<T> apply,
        Func<Task> loadSelectedScope,
        Action<Exception> showFailure,
        Action stateChanged)
    {
        var revision = ++_scopeRevision;
        _contextRevision++;
        IsRefreshingScopes = true;
        InvalidateRecords();
        var succeeded = false;
        try
        {
            clear();
            stateChanged();
            var response = await discover();
            if (revision != _scopeRevision)
            {
                return;
            }

            apply(response);
            succeeded = true;
        }
        catch (Exception exception)
        {
            if (revision == _scopeRevision)
            {
                clear();
                showFailure(exception);
            }
        }
        finally
        {
            if (revision == _scopeRevision)
            {
                IsRefreshingScopes = false;
                stateChanged();
            }
        }

        if (succeeded && revision == _scopeRevision && !IsIndexing)
        {
            await loadSelectedScope();
        }
    }
}
