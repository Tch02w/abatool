using AbaqusTools.WinUI.Models;

namespace AbaqusTools.WinUI.Services;

public sealed record OdbExecutionGroup(string Name, IReadOnlyList<OdbFileRow> Members, bool Standalone);

public static class OdbComparisonGroups
{
    internal static bool TryParseLegendBound(string text, out double value) =>
        double.TryParse(text, out value) && double.IsFinite(value) && Math.Abs(value) <= 1e30;

    public static void ChangeGroup(IEnumerable<OdbFileRow> rows, string oldName, string? newName,
        IDictionary<string, IReadOnlyDictionary<string, OdbLegendOverride>> legends,
        IDictionary<string, List<string>> orders)
    {
        var items = rows.ToArray();
        var names = items.SelectMany(row => ParseNames(row.ComparisonGroup)).ToArray();
        var comparer = StringComparer.OrdinalIgnoreCase;
        if (!names.Contains(oldName, comparer)) throw new ArgumentException("对比组不存在。");
        if (newName is not null)
        {
            newName = newName.Trim();
            if (newName.Length == 0 || newName.Contains(';') || newName.Contains('；'))
                throw new ArgumentException("请输入一个非空组名，不要包含分号。");
            if (!comparer.Equals(oldName, newName)
                && (names.Contains(newName, comparer) || legends.ContainsKey(newName) || orders.ContainsKey(newName)))
                throw new ArgumentException("目标组名已存在，请使用其他名称；不会自动合并两组。");
        }
        foreach (var row in items)
            row.ComparisonGroup = string.Join("；", ParseNames(row.ComparisonGroup)
                .Select(name => comparer.Equals(name, oldName) ? newName : name)
                .Where(name => name is not null));
        if (legends.TryGetValue(oldName, out var legend))
        {
            legends.Remove(oldName);
            if (newName is not null) legends[newName] = legend;
        }
        if (orders.TryGetValue(oldName, out var order))
        {
            orders.Remove(oldName);
            if (newName is not null) orders[newName] = order;
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
                if (!members.Contains(row)) members.Add(row);
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

    public static IEnumerable<IGrouping<string, OdbFileRow>> ForBrowser(IEnumerable<OdbFileRow> rows) =>
        rows.SelectMany(row =>
            {
                var names = ParseNames(row.ComparisonGroup);
                return (names.Length == 0 ? ["未分组"] : names)
                    .Select(name => (Name: name, Row: row));
            })
            .GroupBy(item => item.Name, item => item.Row, StringComparer.OrdinalIgnoreCase)
            .OrderBy(group => group.Key, StringComparer.OrdinalIgnoreCase);
}
