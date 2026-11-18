using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace AbaqusTools.WinUI.Services;

public sealed class OdbPostprocessWorkspace
{
    public int Version { get; set; } = 1;
    public OdbPostprocessOutputOptions Output { get; set; } = new();
    public List<OdbPostprocessSavedRow> Rows { get; set; } = [];
    public Dictionary<string, List<string>> GroupMemberOrder { get; set; } = [];
    public Dictionary<string, Dictionary<string, OdbLegendOverride>> Legends { get; set; } = [];
}

public sealed class OdbPostprocessOutputOptions
{
    public int ParallelWorkers { get; set; } = 2;
    public bool FullTimehistory { get; set; }
    public string RebarMethod { get; set; } = "element_cut";
    public int ExpectedRebarCount { get; set; }
    public string ImageUnit { get; set; } = "px";
    public int ImageWidth { get; set; } = 1500;
    public int ImageHeight { get; set; } = 1000;
    public int AnimationFps { get; set; } = 25;
    public string AnimationTimingMode { get; set; } = "fps";
    public double AnimationDurationSeconds { get; set; } = 4;
    public double RebarTolerance { get; set; } = 0.0001;
    public bool WhiteBackground { get; set; } = true;
    public bool TransparentBackground { get; set; } = true;

    public void Validate()
    {
        var min = ImageUnit == "mm" ? 30 : 320;
        var max = ImageUnit == "mm" ? 500 : 4096;
        // Saved workspaces may come from a larger machine; clamp on restore.
        if (ParallelWorkers < 1 || ExpectedRebarCount is < 0 or > 10000
            || RebarMethod is not ("element_cut" or "legacy_interpolation")
            || ImageUnit is not ("px" or "mm")
            || ImageWidth < min || ImageWidth > max || ImageHeight < min || ImageHeight > max
            || AnimationFps is < 1 or > 60 || AnimationTimingMode is not ("fps" or "duration")
            || !double.IsFinite(AnimationDurationSeconds) || AnimationDurationSeconds < 0.01
            || !double.IsFinite(RebarTolerance)
            || RebarTolerance < 0 || RebarTolerance > 100)
            throw new InvalidDataException("后处理输出设置无效。");
    }
}

public sealed class OdbPostprocessSavedRow
{
    public string Path { get; set; } = "";
    public string Group { get; set; } = "";
    public bool Selected { get; set; }
    public OdbPostprocessJobDraft? Draft { get; set; }
}

/// <summary>Only editable drafts are persisted; never persist structure validity.</summary>
public sealed class OdbPostprocessWorkspaceStore(string directory)
{
    private static readonly JsonSerializerOptions JsonOptions = new() { RespectNullableAnnotations = true };
    private string FilePath(string root)
    {
        var key = System.IO.Path.GetFullPath(root).TrimEnd('\\', '/').ToUpperInvariant();
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(key)));
        return System.IO.Path.Combine(directory, hash + ".json");
    }

    public OdbPostprocessWorkspace? Load(string root)
    {
        var path = FilePath(root);
        if (!File.Exists(path)) return null;
        var state = JsonSerializer.Deserialize<OdbPostprocessWorkspace>(File.ReadAllText(path), JsonOptions)
            ?? throw new InvalidDataException("后处理配置为空。");
        Validate(state);
        return state;
    }

    internal static void Validate(OdbPostprocessWorkspace state)
    {
        if (state.Version != 1 || state.Rows is null || state.Legends is null || state.Output is null
            || state.GroupMemberOrder is null
            || state.GroupMemberOrder.Any(pair => pair.Value is null || pair.Value.Any(string.IsNullOrWhiteSpace))
            || state.Rows.Any(row => row is null || string.IsNullOrWhiteSpace(row.Path) || row.Group is null)
            || state.Legends.Any(group => group.Value is null || group.Value.Any(field => field.Value is null)))
            throw new InvalidDataException("后处理配置版本或内容无效。");
        state.Output.Validate();
        var paths = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        foreach (var row in state.Rows)
            if (!paths.Add(System.IO.Path.GetFullPath(row.Path)))
                throw new InvalidDataException("后处理配置包含重复的 ODB 路径。");
    }

    public void Save(string root, OdbPostprocessWorkspace state)
    {
        Validate(state);
        var json = JsonSerializer.Serialize(state, JsonOptions);
        Directory.CreateDirectory(directory);
        var path = FilePath(root);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temporary, json);
            File.Move(temporary, path, overwrite: true);
        }
        finally
        {
            if (File.Exists(temporary)) File.Delete(temporary);
        }
    }
}
