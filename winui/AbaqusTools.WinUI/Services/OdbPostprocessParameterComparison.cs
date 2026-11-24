using System.Globalization;
using System.Text;
using AbaqusTools.WinUI.Models;

namespace AbaqusTools.WinUI.Services;

public sealed record OdbComparisonIssue(string Path, string FieldKey, string Message);

public sealed class OdbComparisonField
{
    internal OdbComparisonField(string key, string label, Func<OdbPostprocessJobDraft, string> read,
        Action<OdbPostprocessJobDraft, string> write)
        => (Key, Label, Read, Write) = (key, label, read, write);

    public string Key { get; }
    public string Label { get; }
    internal Func<OdbPostprocessJobDraft, string> Read { get; }
    internal Action<OdbPostprocessJobDraft, string> Write { get; }
}

/// <summary>Edits private drafts for the selected models until every proposed change is valid.</summary>
public sealed class OdbPostprocessParameterComparison
{
    private static readonly CultureInfo NumericCulture = CultureInfo.InvariantCulture;
    public static IReadOnlyList<OdbComparisonField> Fields { get; } = Array.AsReadOnly<OdbComparisonField>(
    [
        new(nameof(OdbPostprocessJobDraft.StartStep), "起始分析步", d => d.StartStep, (d, v) => d.StartStep = v),
        new(nameof(OdbPostprocessJobDraft.EndStep), "结束分析步", d => d.EndStep, (d, v) => d.EndStep = v),
        new(nameof(OdbPostprocessJobDraft.FrameMode), "提取帧", d => d.FrameMode, (d, v) => d.FrameMode = v),
        new(nameof(OdbPostprocessJobDraft.ManualSequenceExpression), "手动帧序号", d => d.ManualSequenceExpression, (d, v) => d.ManualSequenceExpression = v),
        new(nameof(OdbPostprocessJobDraft.PrefractureSequenceIndex), "断裂前帧序号", d => d.PrefractureSequenceIndex.ToString(NumericCulture),
            (d, v) => d.PrefractureSequenceIndex = int.Parse(v, NumberStyles.Integer, NumericCulture)),
        new(nameof(OdbPostprocessJobDraft.LoadDirection), "加载方向", d => d.LoadDirection, (d, v) => d.LoadDirection = v),
        new(nameof(OdbPostprocessJobDraft.LoadSet), "加载节点集", d => d.LoadSet, (d, v) => d.LoadSet = v),
        new(nameof(OdbPostprocessJobDraft.PileType), "桩体类型", d => d.PileType, (d, v) => d.PileType = v),
        new(nameof(OdbPostprocessJobDraft.PileDisplaySet), "桩体显示集合", d => d.PileDisplaySet, (d, v) => d.PileDisplaySet = v),
        new(nameof(OdbPostprocessJobDraft.PileConcreteSet), "混凝土集合", d => d.PileConcreteSet, (d, v) => d.PileConcreteSet = v),
        new(nameof(OdbPostprocessJobDraft.PileSteelSet), "钢构件集合", d => d.PileSteelSet, (d, v) => d.PileSteelSet = v),
        new(nameof(OdbPostprocessJobDraft.SoilSet), "土体集合", d => d.SoilSet, (d, v) => d.SoilSet = v),
        new(nameof(OdbPostprocessJobDraft.ReinforcementMode), "主体配筋", d => d.ReinforcementMode, (d, v) => d.ReinforcementMode = v),
        new(nameof(OdbPostprocessJobDraft.RebarSet), "纵筋集合", d => d.RebarSet, (d, v) => d.RebarSet = v),
        new(nameof(OdbPostprocessJobDraft.LongitudinalMaterial), "纵筋材料", d => d.LongitudinalMaterial, (d, v) => d.LongitudinalMaterial = v),
        new(nameof(OdbPostprocessJobDraft.RebarDiameterMm), "纵筋直径 (mm)", d => d.RebarDiameterMm.ToString("R", NumericCulture),
            (d, v) => d.RebarDiameterMm = double.Parse(v, NumberStyles.Float, NumericCulture)),
    ]);
    private static readonly IReadOnlyDictionary<string, OdbComparisonField> ByKey = Fields.ToDictionary(f => f.Key);

    private sealed record Model(OdbPostprocessScanItem Scan, OdbPostprocessJobDraft Original)
    {
        public Dictionary<string, string> Edits { get; } = [];
    }

    private readonly Dictionary<string, Model> _models = new(StringComparer.OrdinalIgnoreCase);

    public OdbPostprocessParameterComparison(IEnumerable<OdbFileRow> rows)
    {
        foreach (var row in rows)
        {
            if (row.ScanDetails is not { } scan || !string.IsNullOrWhiteSpace(scan.Error) || row.PostprocessJob is null)
                throw new InvalidOperationException($"{row.Name}：请先读取模型结构。");
            _models.Add(row.Path, new Model(scan, row.PostprocessJob.Clone()));
        }
    }

    public string GetOriginalValue(string path, string fieldKey) => ByKey[fieldKey].Read(_models[path].Original);

    public string GetValue(string path, string fieldKey)
        => _models[path].Edits.TryGetValue(fieldKey, out var value) ? value : GetOriginalValue(path, fieldKey);

    public IReadOnlyList<string> GetChoices(string path, string fieldKey)
    {
        var scan = _models[path].Scan;
        return fieldKey switch
        {
            nameof(OdbPostprocessJobDraft.StartStep) or nameof(OdbPostprocessJobDraft.EndStep) => scan.Steps,
            nameof(OdbPostprocessJobDraft.FrameMode) => ["auto", "all", "manual"],
            nameof(OdbPostprocessJobDraft.LoadDirection) => ["1", "3", "1+3"],
            nameof(OdbPostprocessJobDraft.PileType) => ["RC", "CFST"],
            nameof(OdbPostprocessJobDraft.ReinforcementMode) => ["required", "none"],
            nameof(OdbPostprocessJobDraft.LoadSet) => scan.AssemblyNodeSets,
            nameof(OdbPostprocessJobDraft.PileSteelSet) => ["", .. scan.AssemblyElementSets],
            nameof(OdbPostprocessJobDraft.PileDisplaySet) or nameof(OdbPostprocessJobDraft.PileConcreteSet)
                or nameof(OdbPostprocessJobDraft.SoilSet) or nameof(OdbPostprocessJobDraft.RebarSet) => scan.AssemblyElementSets,
            _ => [],
        };
    }

    public void SetValue(string path, string fieldKey, string value)
    {
        var model = _models[path];
        if (value == GetOriginalValue(path, fieldKey)) model.Edits.Remove(fieldKey);
        else model.Edits[fieldKey] = value;
    }

    public void CopyFields(string sourcePath, IEnumerable<string> targetPaths, IEnumerable<string> fieldKeys)
    {
        var source = fieldKeys.Distinct().ToDictionary(key => key, key => GetValue(sourcePath, key));
        foreach (var path in targetPaths)
            foreach (var (key, value) in source)
                SetValue(path, key, value);
    }

    public bool TryBuild(out IReadOnlyDictionary<string, OdbPostprocessJobDraft> changed,
        out IReadOnlyList<OdbComparisonIssue> issues)
    {
        var result = new Dictionary<string, OdbPostprocessJobDraft>(StringComparer.OrdinalIgnoreCase);
        var problems = new List<OdbComparisonIssue>();
        foreach (var (path, model) in _models)
        {
            if (model.Edits.Count == 0) continue;
            var candidate = model.Original.Clone();
            foreach (var (key, value) in model.Edits)
            {
                try { ByKey[key].Write(candidate, value.Trim()); }
                catch (Exception error) when (error is FormatException or OverflowException)
                {
                    problems.Add(new(path, key, key == nameof(OdbPostprocessJobDraft.PrefractureSequenceIndex)
                        ? "断裂前帧序号须为 -1 或非负整数" : "纵筋直径须为 1–100 mm 的有限数值"));
                }
            }
            var actualChanges = model.Edits.Keys.Where(key => ByKey[key].Read(candidate) != ByKey[key].Read(model.Original)).ToArray();
            if (actualChanges.Length == 0) continue;
            problems.AddRange(ValidateDraft(path, model.Scan, candidate));
            ValidateSequences(model.Scan, candidate, problems);
            if (candidate.ReinforcementMode == "none")
                foreach (var key in actualChanges.Where(k => k is nameof(OdbPostprocessJobDraft.RebarSet)
                    or nameof(OdbPostprocessJobDraft.LongitudinalMaterial) or nameof(OdbPostprocessJobDraft.RebarDiameterMm)))
                    problems.Add(new(path, key, "无纵筋模型不使用此参数，请撤回此项更改或修改该模型的配筋设置。"));
            result.Add(path, candidate);
        }
        issues = problems;
        changed = problems.Count == 0 ? result : new Dictionary<string, OdbPostprocessJobDraft>();
        return problems.Count == 0;
    }

    internal static List<OdbComparisonIssue> ValidateDraft(string path, OdbPostprocessScanItem scan, OdbPostprocessJobDraft d)
    {
        var issues = new List<OdbComparisonIssue>();
        void Add(string field, string message) => issues.Add(new(path, field, message));
        var steps = scan.Steps.ToList();
        int start = steps.IndexOf(d.StartStep), end = steps.IndexOf(d.EndStep);
        if (start < 0) Add(nameof(d.StartStep), "请选择有效的起始分析步");
        if (end < 0 || end < start) Add(nameof(d.EndStep), "结束分析步必须有效且不早于起始分析步");
        if (d.LoadDirection is not ("1" or "3" or "1+3")) Add(nameof(d.LoadDirection), "请选择加载方向");
        if (!scan.AssemblyNodeSets.Contains(d.LoadSet)) Add(nameof(d.LoadSet), "请选择加载节点集");
        foreach (var (key, value) in new[] { (nameof(d.PileDisplaySet), d.PileDisplaySet),
            (nameof(d.PileConcreteSet), d.PileConcreteSet), (nameof(d.SoilSet), d.SoilSet) })
            if (!scan.AssemblyElementSets.Contains(value)) Add(key, $"请重新选择{ByKey[key].Label}");
        if (d.PileSteelSet.Length > 0 && !scan.AssemblyElementSets.Contains(d.PileSteelSet))
            Add(nameof(d.PileSteelSet), "请重新选择钢构件集合");
        if (d.ReinforcementMode is not ("required" or "none")) Add(nameof(d.ReinforcementMode), "请选择纵筋配置");
        if (d.ReinforcementMode != "none" && !scan.AssemblyElementSets.Contains(d.RebarSet))
            Add(nameof(d.RebarSet), "请重新选择纵筋集合");
        if (d.ReinforcementMode != "none" && string.IsNullOrWhiteSpace(d.LongitudinalMaterial))
            Add(nameof(d.LongitudinalMaterial), "请填写纵筋材料");
        if (d.FrameMode is not ("auto" or "all" or "manual")) Add(nameof(d.FrameMode), "请选择提取帧方式");
        else if (d.FrameMode == "manual" && string.IsNullOrWhiteSpace(d.ManualSequenceExpression))
            Add(nameof(d.ManualSequenceExpression), "请填写手动帧序号");
        if (d.PileType is not ("RC" or "CFST")) Add(nameof(d.PileType), "请选择桩体类型");
        if (!double.IsFinite(d.RebarDiameterMm) || d.RebarDiameterMm < 1 || d.RebarDiameterMm > 100)
            Add(nameof(d.RebarDiameterMm), "纵筋直径应为 1–100 mm");
        return issues;
    }

    private static void ValidateSequences(OdbPostprocessScanItem scan, OdbPostprocessJobDraft d, List<OdbComparisonIssue> issues)
    {
        var available = SequenceCount(scan, d.StartStep, d.EndStep);
        if (available == 0) issues.Add(new(d.Path, nameof(d.EndStep), "所选分析步范围没有可用帧"));
        if (d.PrefractureSequenceIndex is < -1 or > 1_000_000)
            issues.Add(new(d.Path, nameof(d.PrefractureSequenceIndex), "断裂前帧序号应为 -1（自动）或 0–1000000 的整数"));
        else if (available.HasValue && d.PrefractureSequenceIndex >= available)
            issues.Add(new(d.Path, nameof(d.PrefractureSequenceIndex), "断裂前帧序号超出本模型所选分析步范围"));
        if (d.FrameMode != "manual" || string.IsNullOrWhiteSpace(d.ManualSequenceExpression)) return;
        var tokens = d.ManualSequenceExpression.Replace('，', ',').Split(',',
            StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries);
        var field = nameof(d.ManualSequenceExpression);
        if (tokens.Length == 0) issues.Add(new(d.Path, field, "请填写手动帧序号"));
        foreach (var token in tokens)
        {
            // Both endpoints suffice: the executor numbers these frames contiguously, even across steps.
            var ends = token.Split('-', StringSplitOptions.TrimEntries);
            if (ends.Length > 2 || !TrySequenceNumber(ends[0], out var first) || !TrySequenceNumber(ends[^1], out var last))
            {
                issues.Add(new(d.Path, field, $"无法识别帧序号“{token}”，请使用 0,10,20-25 的格式"));
                break;
            }
            if (available.HasValue && Math.Max(first, last) >= available)
            {
                issues.Add(new(d.Path, field, $"帧序号“{token}”超出本模型所选分析步范围"));
                break;
            }
        }
    }

    private static bool TrySequenceNumber(string value, out int index)
    {
        if (int.TryParse(value, NumberStyles.AllowLeadingSign, NumericCulture, out index)) return index >= 0;
        // Python int() also accepts Unicode decimal digits and underscores between digits in a frame index.
        var digits = value.StartsWith('+') ? value[1..] : value;
        var normalized = new StringBuilder();
        foreach (var group in digits.Split('_'))
        {
            if (group.Length == 0) return false;
            foreach (var rune in group.EnumerateRunes())
            {
                if (Rune.GetUnicodeCategory(rune) != UnicodeCategory.DecimalDigitNumber) return false;
                normalized.Append((char)('0' + (int)Rune.GetNumericValue(rune)));
            }
        }
        return int.TryParse(normalized.ToString(), NumberStyles.None, NumericCulture, out index);
    }

    private static long? SequenceCount(OdbPostprocessScanItem scan, string start, string end)
    {
        // Older scan caches predate frame catalogs. Runtime prescan verifies the exact range in that case.
        if (scan.StructureCatalog.SchemaVersion != 1) return null;
        long count = 0;
        var selected = false;
        foreach (var step in scan.Steps)
        {
            var first = step == start;
            selected |= first;
            if (!selected) continue;
            var entry = scan.StructureCatalog.Steps.FirstOrDefault(s => s.Name == step);
            if (entry is null) return null;
            count += first ? entry.Frames.Count : Math.Max(0, entry.Frames.Count - 1);
            if (step == end) return count;
        }
        return null;
    }
}
