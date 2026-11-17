using AbaqusTools.WinUI.Models;

namespace AbaqusTools.WinUI.Services;

public sealed record OdbDiscoveryRows(IReadOnlyList<OdbFileRow> Rows, IReadOnlyList<OdbFileRow> SelectedRows);

public static class OdbDiscoveryReconciler
{
    public static OdbDiscoveryRows Reconcile(
        IEnumerable<OdbDiscoveryItem> items, IEnumerable<OdbFileRow> previous,
        IEnumerable<string> selectedPaths, bool sameRoot)
    {
        var known = previous.ToDictionary(row => Path.GetFullPath(row.Path), StringComparer.OrdinalIgnoreCase);
        var selected = selectedPaths.Select(Path.GetFullPath).ToHashSet(StringComparer.OrdinalIgnoreCase);
        var rows = items.Select(item => sameRoot && known.TryGetValue(Path.GetFullPath(item.Path), out var old)
            ? old.WithDiscovery(item) : new OdbFileRow(item)).ToArray();
        return new(rows, rows.Where(row => !sameRoot || selected.Contains(Path.GetFullPath(row.Path))).ToArray());
    }
}
