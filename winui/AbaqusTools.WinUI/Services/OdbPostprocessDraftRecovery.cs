using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using AbaqusTools.WinUI.Models;

namespace AbaqusTools.WinUI.Services;

public sealed record OdbDraftSource(string Path, long Size, long ModifiedUtcTicks);

public sealed class OdbDialogInputDraft
{
    public string Basis { get; init; } = "";
    public Dictionary<string, string> Inputs { get; init; } = [];
}

public sealed class OdbPostprocessRecoveryDraft
{
    public int Version { get; init; } = 1;
    public string Root { get; init; } = "";
    public string Basis { get; init; } = "";
    public List<OdbDraftSource> Sources { get; init; } = [];
    public OdbPostprocessWorkspace Workspace { get; init; } = new();
    public Dictionary<string, string> OutputInputs { get; init; } = [];
    public Dictionary<string, OdbDialogInputDraft> Dialogs { get; init; } = [];

    public void Validate()
    {
        if (Version != 1 || !Path.IsPathFullyQualified(Root) || Basis is null || Basis.Length != 64
            || Sources is null || Sources.Count > 10000 || Workspace is null || OutputInputs is null
            || Dialogs is null || Dialogs.Count > 128)
            throw new InvalidDataException("后处理恢复草稿格式无效，原文件已保留。");
        OdbPostprocessWorkspaceStore.Validate(Workspace);
        ValidateInputs(OutputInputs);
        foreach (var pair in Dialogs)
        {
            if (pair.Key.Length > 32768 || pair.Value is null || pair.Value.Basis is null || pair.Value.Basis.Length != 64)
                throw new InvalidDataException("弹窗草稿身份无效。");
            if (pair.Key.StartsWith(OdbPostprocessDraftRecovery.ComparisonDialogKind + " · ", StringComparison.Ordinal))
                ValidateComparisonInputs(pair.Value.Inputs);
            else ValidateInputs(pair.Value.Inputs);
        }
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var source in Sources)
            if (source is null || !Path.IsPathFullyQualified(source.Path) || source.Size < 0 || source.ModifiedUtcTicks < 0
                || !paths.Add(Path.GetFullPath(source.Path)))
                throw new InvalidDataException("恢复草稿包含无效或重复的ODB身份。");
        if (Workspace.Rows.Count != paths.Count || Workspace.Rows.Any(row => !paths.Contains(Path.GetFullPath(row.Path))))
            throw new InvalidDataException("恢复草稿的配置与ODB身份不对应。");
    }

    private static void ValidateInputs(Dictionary<string, string> inputs, int maximumEntries = 256)
    {
        if (inputs is null || inputs.Count > maximumEntries || inputs.Any(p => p.Key.Length > 1024 || p.Value is null || p.Value.Length > 65536))
            throw new InvalidDataException("恢复草稿输入过大或格式无效。");
    }

    private void ValidateComparisonInputs(Dictionary<string, string> inputs)
    {
        var fields = OdbPostprocessParameterComparison.Fields.Select(field => field.Key).ToHashSet(StringComparer.Ordinal);
        ValidateInputs(inputs, Sources.Count * fields.Count);
        long characters = 0;
        foreach (var (key, value) in inputs)
        {
            var slash = key.IndexOf('/');
            if (slash < 1 || !int.TryParse(key.AsSpan(0, slash), NumberStyles.None, CultureInfo.InvariantCulture, out var index)
                || index >= Sources.Count || !fields.Contains(key[(slash + 1)..])
                || index.ToString(CultureInfo.InvariantCulture) != key[..slash])
                throw new InvalidDataException("对照草稿的模型或参数标识无效。");
            characters += key.Length + value.Length;
            if (characters > 256L * 65536) throw new InvalidDataException("对照草稿输入内容过大。");
        }
    }

    public bool Matches(string root, string basis, IEnumerable<OdbDraftSource> sources) =>
        string.Equals(OdbPostprocessDraftRecovery.RootKey(Root), OdbPostprocessDraftRecovery.RootKey(root), StringComparison.Ordinal)
        && Basis == basis && OdbPostprocessDraftRecovery.SourceKey(Sources) == OdbPostprocessDraftRecovery.SourceKey(sources);
}

public static class OdbPostprocessDraftRecovery
{
    public const string ComparisonDialogKind = "对照提取参数";
    // Prepare new rows without modifying the live page or reusing prior scan validity.
    public static IReadOnlyList<OdbFileRow> PrepareRows(OdbPostprocessRecoveryDraft draft, IEnumerable<OdbFileRow> current)
    {
        draft.Validate();
        var rows = current.ToArray();
        if (SourceKey(draft.Sources) != SourceKey(rows.Select(row => new OdbDraftSource(row.Path, row.SizeBytes, row.ModifiedAt.UtcDateTime.Ticks))))
            throw new InvalidDataException("ODB列表已变化，未套用旧草稿。");
        var saved = draft.Workspace.Rows.ToDictionary(row => RootKey(row.Path), StringComparer.Ordinal);
        return rows.Select(row =>
        {
            var state = saved[RootKey(row.Path)];
            var restored = new OdbFileRow(new OdbDiscoveryItem { Path = row.Path, Name = row.Name, RelativePath = row.RelativePath,
                SizeBytes = row.SizeBytes, ModifiedAt = row.ModifiedAt });
            restored.ComparisonGroup = state.Group;
            if (state.Draft is not null) restored.UpdatePostprocessJob(state.Draft.Clone());
            restored.MarkStructureAnalysisIncomplete("已恢复配置草稿，请重新读取ODB结构后核对。");
            return restored;
        }).ToArray();
    }

    public static string RootKey(string root) => Path.GetFullPath(root).TrimEnd('\\', '/').ToUpperInvariant();
    public static string FileName(string root) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(RootKey(root)))) + ".json";
    public static string SourceKey(IEnumerable<OdbDraftSource> sources) => Fingerprint(sources
        .Select(s => new { Path = RootKey(s.Path), s.Size, s.ModifiedUtcTicks }).OrderBy(s => s.Path, StringComparer.Ordinal));

    public static string Fingerprint<T>(T value)
    {
        using var stream = new MemoryStream();
        using (var writer = new Utf8JsonWriter(stream)) WriteCanonical(writer, JsonSerializer.SerializeToElement(value));
        return Convert.ToHexString(SHA256.HashData(stream.ToArray()));
    }

    private static void WriteCanonical(Utf8JsonWriter writer, JsonElement value)
    {
        if (value.ValueKind == JsonValueKind.Object)
        {
            writer.WriteStartObject();
            foreach (var prop in value.EnumerateObject().OrderBy(p => p.Name, StringComparer.Ordinal))
            { writer.WritePropertyName(prop.Name); WriteCanonical(writer, prop.Value); }
            writer.WriteEndObject();
        }
        else if (value.ValueKind == JsonValueKind.Array)
        {
            writer.WriteStartArray();
            foreach (var item in value.EnumerateArray()) WriteCanonical(writer, item);
            writer.WriteEndArray();
        }
        else value.WriteTo(writer);
    }

    public static bool OutputChanged(OdbPostprocessOutputOptions value, IReadOnlyDictionary<string, string> raw)
    {
        var expected = new Dictionary<string, object>
        {
            ["并行进程"] = value.ParallelWorkers, ["全部帧"] = value.FullTimehistory,
            ["纵筋方法"] = value.RebarMethod, ["预期纵筋数"] = value.ExpectedRebarCount,
            ["图像单位"] = value.ImageUnit, ["图像宽度"] = value.ImageWidth, ["图像高度"] = value.ImageHeight,
            ["GIF方式"] = value.AnimationTimingMode, ["GIF帧率"] = value.AnimationFps,
            ["GIF时长"] = value.AnimationDurationSeconds, ["纵筋容差"] = value.RebarTolerance,
            ["白底"] = value.WhiteBackground, ["透明底"] = value.TransparentBackground,
        };
        return expected.Any(pair => !raw.TryGetValue(pair.Key, out var text) || (pair.Value switch
        {
            bool flag => text != (flag ? "true" : "false"),
            string label => text != label,
            _ => !double.TryParse(text, NumberStyles.Float | NumberStyles.AllowThousands, CultureInfo.CurrentCulture, out var parsed)
                || !double.IsFinite(parsed) || parsed != Convert.ToDouble(pair.Value, CultureInfo.InvariantCulture),
        }));
    }
}
