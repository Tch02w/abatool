namespace AbaqusTools.WinUI.Services;

/// <summary>UI-thread state shared by menus, page buttons and their action guards.</summary>
public sealed class WorkbenchCommandState
{
    public event Action? Changed;
    public long QueueRevision { get; private set; }
    public long RemoteRevision { get; private set; }
    public bool QueueKnown { get; private set; }
    public bool QueueActive { get; private set; }
    public bool QueueBusy { get; private set; }
    public bool ResourceBusy { get; private set; }
    public bool RemoteRefreshBusy { get; private set; }
    public bool LocalRefreshBusy { get; private set; }
    public bool Locked { get; private set; }
    public bool RemoteKnown { get; private set; }
    public RemoteServerConnection Connection { get; private set; } = new();
    public RemoteServerProfile? ConnectedProfile { get; private set; }
    private HashSet<string> _activeIds = [];
    private HashSet<string> _selectedIds = [];
    public bool CanStartQueue => !Locked && !QueueBusy && QueueKnown && !QueueActive;
    public bool CanStopQueue => !Locked && !QueueBusy && QueueKnown && QueueActive;
    public bool CanTerminateSelected => !Locked && !QueueBusy && QueueKnown && _activeIds.Overlaps(_selectedIds);
    public bool CanEditQueueOptions => !Locked && !QueueBusy && QueueKnown && !QueueActive;
    public bool CanUseRemote => !Locked && !ResourceBusy && !RemoteRefreshBusy && RemoteKnown
        && Connection.Status == "connected" && !Connection.IsBusy && ConnectedProfile is not null;
    public bool CanRefreshLocal => !Locked && !ResourceBusy && !LocalRefreshBusy;
    public bool CanUseSelectedRemote(string? profile) => CanUseRemote
        && string.Equals(profile, Connection.ProfileName, StringComparison.Ordinal);
    public IReadOnlyList<string> SelectedActiveIds => _selectedIds.Where(_activeIds.Contains).ToArray();

    public bool QueueObservationIsCurrent(long revision) => revision == QueueRevision && !QueueBusy;
    public bool RemoteObservationIsCurrent(long revision) => revision == RemoteRevision && !ResourceBusy && !RemoteRefreshBusy;
    public void ApplyQueue(LocalQueueRuntimeSnapshot value)
    {
        QueueKnown = true; QueueActive = value.Active; _activeIds = value.ActiveItemIds.ToHashSet(StringComparer.Ordinal);
        QueueRevision++; Changed?.Invoke();
    }
    public void ApplyRemote(RemoteServersSnapshot value)
    {
        RemoteKnown = true; Connection = value.Connection;
        ConnectedProfile = value.Profiles.FirstOrDefault(profile => profile.ProfileName == Connection.ProfileName);
        RemoteRevision++; Changed?.Invoke();
    }
    public void InvalidateQueue() { QueueKnown = false; QueueRevision++; Changed?.Invoke(); }
    public void InvalidateRemote() { RemoteKnown = false; RemoteRevision++; Changed?.Invoke(); }
    public void SetQueueBusy(bool value)
    {
        if (QueueBusy == value) return;
        QueueBusy = value; QueueRevision++; Changed?.Invoke();
    }
    public void SetResourceBusy(bool value)
    {
        if (ResourceBusy == value) return;
        ResourceBusy = value; RemoteRevision++; Changed?.Invoke();
    }
    public void SetLocalRefreshBusy(bool value)
    {
        if (LocalRefreshBusy == value) return;
        LocalRefreshBusy = value; Changed?.Invoke();
    }
    public void SetRemoteRefreshBusy(bool value)
    {
        if (RemoteRefreshBusy == value) return;
        RemoteRefreshBusy = value; RemoteRevision++; Changed?.Invoke();
    }
    public void SetLocked(bool value)
    {
        if (Locked == value) return;
        Locked = value; QueueRevision++; RemoteRevision++; Changed?.Invoke();
    }
    public void SelectQueueItems(IEnumerable<string> ids)
    {
        var next = ids.ToHashSet(StringComparer.Ordinal);
        if (_selectedIds.SetEquals(next)) return;
        _selectedIds = next; Changed?.Invoke();
    }
}
