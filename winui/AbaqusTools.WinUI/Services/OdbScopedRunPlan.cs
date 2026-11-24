using System.Security.Cryptography;
using System.Runtime.InteropServices;
using System.Text;
using AbaqusTools.WinUI.Models;

namespace AbaqusTools.WinUI.Services;

public enum OdbRunScopeKind { Selection, SingleModel, NamedGroup }

public sealed record OdbRunScope(OdbRunScopeKind Kind, string GroupName = "")
{
    public override string ToString() => Kind switch
    {
        OdbRunScopeKind.Selection => "按所选模型的全部分组运行",
        OdbRunScopeKind.SingleModel => "独立运行一个所选模型",
        _ => $"仅对比组 · {GroupName}",
    };
}

public sealed record OdbScopedRunPlan(OdbFileRow[] Rows, IReadOnlyList<OdbExecutionGroup> Groups, string Summary)
{
    public bool CanRun => Groups.Count > 0;

    public static OdbScopedRunPlan Resolve(OdbRunScope? scope, IEnumerable<OdbFileRow> selected,
        IReadOnlyCollection<OdbFileRow> workspace, string inputRoot, string? discoveredRoot, string? activeQueueRoot,
        IReadOnlyList<OdbPostprocessGroupQueueItem>? queuedGroups = null, bool workspaceReadable = true,
        IReadOnlyList<string>? groupExecutionOrder = null)
    {
        static OdbScopedRunPlan Block(string message) => new([], [], message);
        var comparer = StringComparer.OrdinalIgnoreCase;
        var root = OdbPostprocessResultLocations.FullPath(inputRoot);
        if (root is null || !comparer.Equals(root, OdbPostprocessResultLocations.FullPath(discoveredRoot)))
            return Block("请先点击“发现 ODB”，读取当前根目录。");
        if (!workspaceReadable) return Block("工作区配置无法读取。修复配置后请重新点击“发现 ODB”。");
        if (activeQueueRoot is not null && !comparer.Equals(root, OdbPostprocessResultLocations.FullPath(activeQueueRoot)))
            return Block("当前目录与运行中的队列不同，请回到该队列的工作区。");
        if (scope is null) return Block("请重新选择本次运行范围。");

        var rows = selected.DistinctBy(row => row.Path, comparer).ToArray();
        string summary;
        IReadOnlyList<OdbExecutionGroup> groups;
        switch (scope.Kind)
        {
            case OdbRunScopeKind.NamedGroup:
                bool IsMember(OdbFileRow row) => OdbComparisonGroups.ParseNames(row.ComparisonGroup)
                    .Contains(scope.GroupName, comparer);
                var total = workspace.Count(IsMember);
                if (total == 0) return Block($"“{scope.GroupName}”没有成员，请先向组内添加模型或重选范围。");
                rows = rows.Where(IsMember).ToArray();
                if (rows.Length == 0) return Block($"请勾选“{scope.GroupName}”中要运行的模型。");
                groups = [new(scope.GroupName, rows, false)];
                summary = $"“{scope.GroupName}”将运行 {rows.Length} / {total} 个成员，共用该组图例范围。";
                break;
            case OdbRunScopeKind.SingleModel:
                if (rows.Length != 1) return Block($"已勾选 {rows.Length} 个模型。独立运行需要恰好勾选一个模型。");
                groups = [new(rows[0].Name, rows, true)];
                summary = $"将独立运行 {rows[0].RelativePath}，单独计算图例范围。";
                break;
            case OdbRunScopeKind.Selection:
                if (rows.Length == 0) return Block("请勾选要运行的模型。");
                groups = OdbComparisonGroups.ForExecution(rows);
                var independent = groups.Count(group => group.Standalone);
                summary = $"已选 {rows.Length} 个模型，将运行 {groups.Count - independent} 个对比组、{independent} 个独立模型。";
                break;
            default:
                return Block("请重新选择本次运行范围。");
        }
        string? skipMessage = null;
        if (activeQueueRoot is not null && queuedGroups is { Count: > 0 })
        {
            var liveKeys = queuedGroups.Where(entry => entry.Status is "queued" or "running" or "cancelling")
                .Select(entry => entry.GroupKey).ToHashSet(StringComparer.Ordinal);
            var pending = new List<OdbExecutionGroup>();
            var skipped = new List<OdbExecutionGroup>();
            foreach (var group in groups)
            {
                string? key;
                try { key = QueueKey(group); }
                catch (Exception error) when (error is DllNotFoundException or EntryPointNotFoundException or BadImageFormatException
                    or ArgumentException or IOException or NotSupportedException) { key = null; }
                if (key is null) return Block($"无法核对“{group.Name}”的队列身份，请刷新队列状态。");
                if (liveKeys.Contains(key)) skipped.Add(group);
                else pending.Add(group);
            }
            if (skipped.Count > 0)
            {
                skipMessage = $"已在队列中，跳过{Labels(skipped)}。";
                if (pending.Count == 0) return Block(skipMessage + "待运行组可通过“编辑等待组”修改成员。");
                groups = pending;
                var paths = pending.SelectMany(group => group.Members).Select(row => row.Path).ToHashSet(comparer);
                rows = rows.Where(row => paths.Contains(row.Path)).ToArray();
            }
        }
        if (scope.Kind == OdbRunScopeKind.Selection && groupExecutionOrder is { Count: > 0 })
            groups = OdbComparisonGroups.OrderExecutionGroups(groups, groupExecutionOrder);
        if (skipMessage is not null) summary = $"将追加{Labels(groups)}。{skipMessage}";
        else if (groups.Count > 1) summary += $" 执行顺序为{Labels(groups)}。";
        var unready = rows.FirstOrDefault(row => !row.HasPostprocessConfiguration || row.PostprocessJob is null);
        return unready is null ? new(rows, groups, summary)
            : Block($"“{unready.RelativePath}”尚未就绪，请读取结构并检查提取参数。");
    }

    private static string Labels(IReadOnlyList<OdbExecutionGroup> items)
    {
        var first = string.Join("、", items.Take(3).Select(group => group.Standalone
            ? $"独立模型“{group.Members[0].RelativePath}”" : $"对比组“{group.Name}”"));
        return items.Count > 3 ? $"{first}等 {items.Count} 项" : first;
    }

    private static string? QueueKey(OdbExecutionGroup group)
    {
        // postprocess_group_queue._group_inputs uses ntpath.normcase for a file
        // and Python str.casefold (full Unicode folding) for a named group.
        if (group.Standalone)
        {
            var path = Path.GetFullPath(group.Members[0].Path);
            var capacity = LCMapStringEx("", 0x100, path, path.Length, null, 0, 0, 0, 0);
            var buffer = new char[capacity];
            if (capacity == 0 || LCMapStringEx("", 0x100, path, path.Length, buffer, capacity, 0, 0, 0) != capacity) return null;
            return "odb:" + new string(buffer);
        }
        var name = group.Name;
        if (name.All(char.IsAscii)) return "group:" + name.ToLowerInvariant();
        int status = 0;
        var folded = new char[name.Length + 1];
        var length = u_strFoldCase(folded, folded.Length, name, name.Length, 0, ref status);
        if (status == 15) // U_BUFFER_OVERFLOW_ERROR on expanding folds such as ligatures.
        {
            status = 0;
            folded = new char[length + 1];
            length = u_strFoldCase(folded, folded.Length, name, name.Length, 0, ref status);
        }
        return status > 0 ? null : "group:" + new string(folded, 0, length);
    }

    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    [DllImport("icuuc.dll", CharSet = CharSet.Unicode, ExactSpelling = true, CallingConvention = CallingConvention.Cdecl)]
    private static extern int u_strFoldCase([Out] char[] output, int capacity, string value, int length, uint options, ref int status);

    [DefaultDllImportSearchPaths(DllImportSearchPath.System32)]
    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, ExactSpelling = true)]
    private static extern int LCMapStringEx(string locale, uint flags, string value, int length, [Out] char[]? output,
        int capacity, nint version, nint reserved, nint sort);

    // Both new queues and appended entries get a snapshot from the same builder.
    // The waiting-group editor also uses it after an explicit workspace sync.
    internal static OdbPostprocessRunCreateRequest BuildRequest(string root, OdbFileRow[] rows,
        IReadOnlyList<OdbExecutionGroup> groups, OdbPostprocessOutputOptions output, bool forceRescan,
        IReadOnlyDictionary<string, List<string>> memberOrder,
        IReadOnlyDictionary<string, IReadOnlyDictionary<string, OdbLegendOverride>> legends) => new()
    {
        Root = root.Trim(),
        ParallelWorkers = output.ParallelWorkers,
        ForceRescan = forceRescan,
        FullTimehistoryFreebody = output.FullTimehistory,
        RebarMethod = output.RebarMethod,
        ExpectedLongitudinalRebarCount = output.ExpectedRebarCount,
        ImageSizeUnit = output.ImageUnit,
        ImageWidth = output.ImageWidth,
        ImageHeight = output.ImageHeight,
        ExportWhiteBackgroundPng = output.WhiteBackground,
        ExportTransparentBackgroundPng = output.TransparentBackground,
        AnimationFps = output.AnimationFps,
        AnimationDurationSeconds = output.AnimationTimingMode == "duration" ? output.AnimationDurationSeconds : null,
        RebarCutToleranceMm = output.RebarTolerance,
        Jobs = rows.Select(row => row.PostprocessJob!.Clone()).ToArray(),
        Groups = groups.Select(group => new OdbPostprocessGroupDraft
        {
            Id = StableGroupDraftId(root, group),
            Name = group.Name,
            Standalone = group.Standalone,
            Members = OdbComparisonGroups.OrderMembers(group.Members,
                !group.Standalone && memberOrder.TryGetValue(group.Name, out var order) ? order : [])
                .Select(row => row.Path).ToArray(),
            LegendOverrides = !group.Standalone && legends.TryGetValue(group.Name, out var overrides)
                ? new Dictionary<string, OdbLegendOverride>(overrides) : new Dictionary<string, OdbLegendOverride>(),
        }).ToArray(),
    };

    private static string StableGroupDraftId(string root, OdbExecutionGroup group)
    {
        // Preserve existing queue identities, including the original volume-root normalization.
        static string PathKey(string path) => Path.GetFullPath(path.Trim()).TrimEnd(Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar);
        var identity = group.Standalone ? "odb|" + PathKey(group.Members[0].Path) : "group|" + group.Name.Trim();
        var bytes = Encoding.UTF8.GetBytes((PathKey(root) + "|" + identity).ToUpperInvariant());
        return "g-" + Convert.ToHexString(SHA256.HashData(bytes))[..32].ToLowerInvariant();
    }
}
