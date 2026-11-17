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

    public bool IsRefreshingScopes { get; private set; }
    public bool IsIndexing { get; private set; }
    public bool CanLoadRecords => !IsRefreshingScopes && !IsIndexing;
    public long ContextRevision => _contextRevision;
    public long IndexRevision => _indexRevision;

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
