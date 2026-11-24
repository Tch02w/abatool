using AbaqusTools.WinUI.Models;

namespace AbaqusTools.WinUI.Services;

public sealed record OdbExecutionGroup(string Name, IReadOnlyList<OdbFileRow> Members, bool Standalone);
public sealed record OdbBrowserGroup(string Name, IReadOnlyList<OdbFileRow> Members, bool Unassigned = false);

public static class OdbComparisonGroups
{
    internal static bool TryParseLegendBound(string text, out double value) =>
        double.TryParse(text, out value) && double.IsFinite(value) && Math.Abs(value) <= 1e30;

    public static void ChangeGroup(IEnumerable<OdbFileRow> rows, string oldName, string? newName,
        IDictionary<string, IReadOnlyDictionary<string, OdbLegendOverride>> legends,
        IDictionary<string, List<string>> orders, List<string>? groupExecutionOrder = null) =>
        ChangeGroup(rows, row => row.ComparisonGroup, (row, value) => row.ComparisonGroup = value,
            oldName, newName, legends, orders, groupExecutionOrder);

    public static void ChangeGroup(OdbPostprocessWorkspace workspace, string oldName, string? newName) =>
        ChangeGroup(workspace.Rows, row => row.Group, (row, value) => row.Group = value,
            oldName, newName, workspace.Legends, workspace.GroupMemberOrder, workspace.GroupExecutionOrder);

    private static void ChangeGroup<TRow, TLegend>(IEnumerable<TRow> rows, Func<TRow, string> read,
        Action<TRow, string> write, string oldName, string? newName, IDictionary<string, TLegend> legends,
        IDictionary<string, List<string>> orders, List<string>? groupExecutionOrder)
    {
        var items = rows.ToArray();
        var names = items.SelectMany(row => ParseNames(read(row))).Concat(orders.Keys).Concat(legends.Keys)
            .ToHashSet(StringComparer.OrdinalIgnoreCase);
        var comparer = StringComparer.OrdinalIgnoreCase;
        if (!names.Contains(oldName)) throw new ArgumentException("对比组不存在。");
        if (newName is not null)
        {
            newName = newName.Trim();
            if (newName.Length == 0 || newName.Contains(';') || newName.Contains('；'))
                throw new ArgumentException("请输入一个非空组名，不要包含分号。");
            if (!comparer.Equals(oldName, newName)
                && names.Contains(newName))
                throw new ArgumentException("目标组名已存在，请使用其他名称；不会自动合并两组。");
        }
        foreach (var row in items)
            write(row, string.Join("；", ParseNames(read(row))
                .Select(name => comparer.Equals(name, oldName) ? newName : name)
                .Where(name => name is not null)));
        RenameKey(legends, oldName, newName);
        RenameKey(orders, oldName, newName);
        if (groupExecutionOrder is { Count: > 0 })
        {
            var updated = groupExecutionOrder.Select(name => name.Trim()).Where(names.Contains)
                .Select(name => comparer.Equals(name, oldName) ? newName : name)
                .OfType<string>().Distinct(comparer).ToArray();
            groupExecutionOrder.Clear();
            groupExecutionOrder.AddRange(updated);
        }
    }

    private static void RenameKey<T>(IDictionary<string, T> values, string oldName, string? newName)
    {
        var key = values.Keys.FirstOrDefault(name => name.Equals(oldName, StringComparison.OrdinalIgnoreCase));
        if (key is not null)
        {
            var value = values[key];
            values.Remove(key);
            if (newName is not null) values[newName] = value;
        }
    }

    public static IReadOnlyList<OdbFileRow> OrderMembers(IEnumerable<OdbFileRow> members, IEnumerable<string> paths)
    {
        var remaining = members.ToDictionary(row => Path.GetFullPath(row.Path), StringComparer.OrdinalIgnoreCase);
        var ordered = new List<OdbFileRow>();
        foreach (var path in paths)
            if (remaining.Remove(Path.GetFullPath(path), out var row)) ordered.Add(row);
        ordered.AddRange(remaining.Values);
        return ordered;
    }

    public static string[] OrderGroupNames(IEnumerable<string> availableNames, IEnumerable<string> savedOrder)
    {
        var comparer = StringComparer.OrdinalIgnoreCase;
        var names = availableNames.Distinct(comparer).ToArray();
        var remaining = names.ToDictionary(name => name, comparer);
        var ordered = new List<string>(names.Length);
        foreach (var configured in savedOrder)
            if (remaining.Remove(configured.Trim(), out var actual)) ordered.Add(actual);
        ordered.AddRange(names.Where(remaining.ContainsKey));
        return ordered.ToArray();
    }

    public static IReadOnlyList<OdbExecutionGroup> OrderExecutionGroups(
        IReadOnlyList<OdbExecutionGroup> groups, IReadOnlyList<string> savedOrder)
    {
        if (savedOrder.Count == 0 || groups.Count < 2) return groups;
        var named = groups.Where(group => !group.Standalone).ToArray();
        if (named.Length < 2) return groups;
        var byName = named.ToDictionary(group => group.Name, StringComparer.OrdinalIgnoreCase);
        var names = OrderGroupNames(named.Select(group => group.Name), savedOrder);
        // A standalone model keeps its slot even if a named group shares its display name.
        var ordered = groups.ToArray();
        var nextName = 0;
        for (var slot = 0; slot < ordered.Length; slot++)
            if (!ordered[slot].Standalone) ordered[slot] = byName[names[nextName++]];
        return ordered;
    }

    public static IReadOnlyList<OdbExecutionGroup> ForExecution(IEnumerable<OdbFileRow> rows)
    {
        var memberships = new Dictionary<string, List<OdbFileRow>>(StringComparer.OrdinalIgnoreCase);
        var result = new List<OdbExecutionGroup>();
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var row in rows)
        {
            if (!seen.Add(Path.GetFullPath(row.Path))) continue;
            var names = ParseNames(row.ComparisonGroup);
            if (names.Length == 0)
            {
                result.Add(new(row.Name, [row], true));
                continue;
            }
            foreach (var name in names)
            {
                if (!memberships.TryGetValue(name, out var members))
                {
                    memberships[name] = members = [];
                    result.Add(new(name, members, false));
                }
                members.Add(row);
            }
        }
        return result;
    }

    public static string UpdateMembership(string current, string requested, string operation)
    {
        var names = ParseNames(requested);
        var existing = ParseNames(current);
        IEnumerable<string> result = operation switch
        {
            "replace" => names,
            "add" => existing.Concat(names).Distinct(StringComparer.OrdinalIgnoreCase),
            "remove" => existing.Except(names, StringComparer.OrdinalIgnoreCase),
            "clear" => [],
            _ => throw new ArgumentException("Unknown membership operation", nameof(operation)),
        };
        return string.Join("；", result);
    }

    public static string[] ParseNames(string value) => value
        .Replace('；', ';')
        .Split(';', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
        .Distinct(StringComparer.OrdinalIgnoreCase)
        .ToArray();

    public static string[] CatalogNames(IEnumerable<OdbFileRow> rows, IEnumerable<string> savedNames) =>
        savedNames.Concat(rows.SelectMany(row => ParseNames(row.ComparisonGroup)))
            .Distinct(StringComparer.OrdinalIgnoreCase).Order(StringComparer.OrdinalIgnoreCase).ToArray();

    public static (string[] NewNames, string[] DuplicateNames) PlanNewGroups(string text, IEnumerable<string> existing)
    {
        var known = existing.ToHashSet(StringComparer.OrdinalIgnoreCase);
        var added = new List<string>();
        var duplicates = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var name in text.Split(['\r', '\n', ';', '；'], StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries))
        {
            if (name.Contains('\t')) throw new ArgumentException("请粘贴一列组名，每个名称单独占一行。");
            if (known.Add(name)) added.Add(name);
            else duplicates.Add(name);
        }
        return (added.ToArray(), duplicates.ToArray());
    }

    public static IEnumerable<OdbBrowserGroup> ForBrowser(IEnumerable<OdbFileRow> rows, IEnumerable<string> savedNames)
    {
        var named = new Dictionary<string, List<OdbFileRow>>(StringComparer.OrdinalIgnoreCase);
        var unassigned = new List<OdbFileRow>();
        foreach (var name in savedNames) named.TryAdd(name, []);
        foreach (var row in rows)
        {
            var names = ParseNames(row.ComparisonGroup);
            if (names.Length == 0) unassigned.Add(row);
            foreach (var name in names)
            {
                if (!named.TryGetValue(name, out var members)) named[name] = members = [];
                members.Add(row);
            }
        }
        foreach (var (name, members) in named.OrderBy(entry => entry.Key, StringComparer.OrdinalIgnoreCase))
            yield return new(name, members);
        if (unassigned.Count > 0)
            yield return new(named.ContainsKey("未分组") ? "未加入对比组的模型" : "未分组", unassigned, true);
    }
}
