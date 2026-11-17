using System.Text.Json;

namespace AbaqusTools.WinUI.Services;

public sealed class WorkbenchWindowState
{
    public int X { get; set; }
    public int Y { get; set; }
    public int Width { get; set; } = 1280;
    public int Height { get; set; } = 800;
    public bool Maximized { get; set; } = true;
}

public sealed class WorkbenchSessionState
{
    public int SchemaVersion { get; set; } = 1;
    public string LastRoute { get; set; } = "new-job";
    public WorkbenchWindowState Window { get; set; } = new();
    public Dictionary<string, Dictionary<string, string>> Pages { get; set; } = [];
}

/// <summary>Only allowlisted UI draft values; no passwords, tokens or runtime truth.</summary>
public sealed class WorkbenchSessionStore(string path)
{
    private static readonly JsonSerializerOptions Options = new() { WriteIndented = true, RespectNullableAnnotations = true };
    private bool _unreadable;

    public WorkbenchSessionState Load()
    {
        if (!File.Exists(path)) return new();
        try
        {
            var state = JsonSerializer.Deserialize<WorkbenchSessionState>(File.ReadAllText(path), Options)
                ?? throw new InvalidDataException("工作台草稿为空。");
            Validate(state);
            return state;
        }
        catch
        {
            _unreadable = true;
            throw;
        }
    }

    private static void Validate(WorkbenchSessionState state)
    {
        if (state.SchemaVersion != 1 || state.Pages is null || state.Window is null
            || state.Pages.Count > 8 || state.Window.Width <= 0 || state.Window.Height <= 0
            || state.Pages.Any(p => p.Value is null || p.Value.Count > 64
                || p.Value.Any(v => v.Value is null || v.Value.Length > 32768)))
            throw new InvalidDataException("工作台草稿格式无效或版本不受支持，原文件已保留。");
    }

    public void Save(WorkbenchSessionState state)
    {
        if (_unreadable) throw new IOException($"原工作台草稿无法读取，未覆盖它。请先检查：{path}");
        Validate(state);
        var directory = Path.GetDirectoryName(path) ?? throw new IOException("草稿目录无效。");
        Directory.CreateDirectory(directory);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            File.WriteAllText(temporary, JsonSerializer.Serialize(state, Options));
            File.Move(temporary, path, overwrite: true);
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
