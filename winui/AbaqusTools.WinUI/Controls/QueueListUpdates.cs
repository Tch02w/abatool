using System.Collections.ObjectModel;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Controls;

/// <summary>Keep row identity, containers and selection across queue observations.</summary>
public static class QueueListUpdates
{
    public static void Apply(ListView list, ObservableCollection<JobQueueItem> rows,
        IReadOnlyList<JobQueueItem> incoming)
    {
        var selected = list.SelectedItems.OfType<JobQueueItem>()
            .Select(item => item.ItemId).ToHashSet(StringComparer.Ordinal);
        var wanted = incoming.Select(item => item.ItemId).ToHashSet(StringComparer.Ordinal);
        for (var index = rows.Count - 1; index >= 0; index--)
            if (!wanted.Contains(rows[index].ItemId)) rows.RemoveAt(index);

        var existing = rows.ToDictionary(item => item.ItemId, StringComparer.Ordinal);
        for (var index = 0; index < incoming.Count; index++)
        {
            var snapshot = incoming[index];
            if (existing.TryGetValue(snapshot.ItemId, out var row))
            {
                if (!ReferenceEquals(rows[index], row)) rows.Move(rows.IndexOf(row), index);
                row.UpdateFrom(snapshot);
            }
            else rows.Insert(index, snapshot);
        }
        // WinUI may drop selection on a move; preserve only surviving identities.
        foreach (var row in rows)
            if (selected.Contains(row.ItemId) && !list.SelectedItems.Contains(row))
                list.SelectedItems.Add(row);
    }
}
