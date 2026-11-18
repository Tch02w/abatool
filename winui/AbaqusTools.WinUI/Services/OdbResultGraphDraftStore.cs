using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace AbaqusTools.WinUI.Services;

public sealed class OdbResultGraphDraft
{
    public int Version { get; init; } = 1;
    public string Context { get; init; } = "";
    public OdbResultGraphSnapshot Basis { get; init; } = new();
    public OdbResultGraphSnapshot Edited { get; init; } = new();
    public string? SelectedNodeId { get; init; }
    public List<string> Targets { get; init; } = [];

    public bool Matches(string context, OdbResultGraphSnapshot current) =>
        string.Equals(Path.GetFullPath(Context), Path.GetFullPath(context), StringComparison.OrdinalIgnoreCase)
        && Fingerprint(Basis) == Fingerprint(current);

    public void Validate()
    {
        if (Version != 1 || string.IsNullOrWhiteSpace(Context) || !Path.IsPathFullyQualified(Context)
            || Context.Length > 32768
            || Basis is null || Edited is null || Targets is null || Targets.Count > 256)
            throw new InvalidDataException("结果图草稿格式无效，原文件已保留。");
        _ = Path.GetFullPath(Context);
        ValidateGraph(Basis);
        ValidateGraph(Edited);
        if (Basis.Revision != Edited.Revision || Targets.Any(id => id is null || !Edited.Nodes.Any(n => n.NodeId == id))
            || (SelectedNodeId is not null && !Edited.Nodes.Any(n => n.NodeId == SelectedNodeId)))
            throw new InvalidDataException("结果图草稿的版本或选择无效，原文件已保留。");
    }

    private static void ValidateGraph(OdbResultGraphSnapshot graph)
    {
        if (graph.SchemaVersion != 1 || graph.Revision < 0 || graph.OutputDirectory is null
            || graph.OutputDirectory.Length > 32768 || graph.Nodes is null || graph.Nodes.Count > 256
            || graph.Nodes.Any(n => n is null || string.IsNullOrWhiteSpace(n.NodeId)
                || new[] { n.NodeId, n.Name, n.ParentNodeId, n.OdbPath, n.InpPath }.Any(s => s is null || s.Length > 32768)))
            throw new InvalidDataException("结果图草稿节点无效，原文件已保留。");
        var ids = graph.Nodes.Select(n => n.NodeId).ToHashSet(StringComparer.Ordinal);
        if (ids.Count != graph.Nodes.Count || graph.Nodes.Any(n => n.ParentNodeId.Length > 0 && !ids.Contains(n.ParentNodeId)))
            throw new InvalidDataException("结果图草稿引用了缺失或重复节点。");
        var parents = graph.Nodes.ToDictionary(n => n.NodeId, n => n.ParentNodeId, StringComparer.Ordinal);
        foreach (var id in ids)
        {
            var visited = new HashSet<string>(StringComparer.Ordinal);
            for (var next = id; next.Length > 0; next = parents[next])
                if (!visited.Add(next)) throw new InvalidDataException("结果图草稿包含循环依赖。");
        }
    }

    private static string Fingerprint(OdbResultGraphSnapshot graph) => Convert.ToHexString(SHA256.HashData(
        JsonSerializer.SerializeToUtf8Bytes(new { graph.SchemaVersion, graph.Revision, graph.OutputDirectory,
            Nodes = graph.Nodes.OrderBy(n => n.NodeId, StringComparer.Ordinal).Select(n =>
                new { n.NodeId, n.Name, n.ParentNodeId, n.OdbPath, n.InpPath }) })));
}

/// <summary>Local UI recovery only; never writes the backend's formal result graph.</summary>
public sealed class OdbResultGraphDraftStore(string path)
{
    private const int MaximumBytes = 4 * 1024 * 1024;
    private static readonly JsonSerializerOptions Options = new() { RespectNullableAnnotations = true };
    private readonly object _gate = new();
    private Task _tail = Task.CompletedTask;
    private bool _unreadable;
    private string? _lastJson;
    public string FilePath => path;

    public OdbResultGraphDraft? Load()
    {
        if (!File.Exists(path)) return null;
        try
        {
            if (new FileInfo(path).Length > MaximumBytes) throw new InvalidDataException("结果图草稿超过读取上限。");
            var json = File.ReadAllText(path);
            var draft = JsonSerializer.Deserialize<OdbResultGraphDraft?>(json, Options);
            draft?.Validate();
            _lastJson = JsonSerializer.Serialize(draft, Options);
            return draft;
        }
        catch { _unreadable = true; throw; }
    }

    public Task SaveAsync(OdbResultGraphDraft? draft)
    {
        if (_unreadable) throw new IOException($"原结果图草稿无法读取，未覆盖：{path}");
        draft?.Validate();
        var json = JsonSerializer.Serialize(draft, Options);
        if (Encoding.UTF8.GetByteCount(json) > MaximumBytes) throw new InvalidDataException("结果图草稿超过保存上限，原文件已保留。");
        lock (_gate)
        {
            _tail = _tail.ContinueWith(_ => Write(json), CancellationToken.None, TaskContinuationOptions.None, TaskScheduler.Default);
            return _tail;
        }
    }

    public Task<string?> ArchiveAndClearAsync()
    {
        lock (_gate)
        {
            var task = _tail.ContinueWith(_ =>
            {
                string? archive = null;
                if (File.Exists(path))
                {
                    archive = path + ".preserved-" + DateTime.UtcNow.ToString("yyyyMMdd-HHmmss") + "-" + Guid.NewGuid().ToString("N") + ".json";
                    // Finish preserving and flushing before clearing the active checkpoint.
                    using var input = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read);
                    using var output = new FileStream(archive, FileMode.CreateNew, FileAccess.Write, FileShare.None);
                    input.CopyTo(output);
                    output.Flush(flushToDisk: true);
                }
                Write("null");
                _unreadable = false;
                return archive;
            }, CancellationToken.None, TaskContinuationOptions.None, TaskScheduler.Default);
            _tail = task;
            return task;
        }
    }

    private void Write(string json)
    {
        if (json == _lastJson && File.Exists(path)) return;
        Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary = path + "." + Guid.NewGuid().ToString("N") + ".tmp";
        try
        {
            using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
            {
                stream.Write(Encoding.UTF8.GetBytes(json));
                stream.Flush(flushToDisk: true);
            }
            File.Move(temporary, path, overwrite: true);
            _lastJson = json;
        }
        finally { if (File.Exists(temporary)) File.Delete(temporary); }
    }
}
