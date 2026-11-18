using System.Text;
using System.Text.Json;

namespace AbaqusTools.WinUI.Services;

public class RecoveryDraftFile<T>(string path, Action<T> validate, int maximumBytes = 4 * 1024 * 1024) where T : class
{
    private static readonly JsonSerializerOptions Options = new() { RespectNullableAnnotations = true };
    private readonly object _gate = new();
    private Task _tail = Task.CompletedTask;
    private bool _unreadable;
    private string? _lastJson;
    public string FilePath => path;
    public Task PendingWrites { get { lock (_gate) return _tail; } }

    public T? Load()
    {
        if (!File.Exists(path)) return null;
        try
        {
            if (new FileInfo(path).Length > maximumBytes) throw new InvalidDataException("恢复草稿超过读取上限。");
            var json = File.ReadAllText(path);
            var draft = JsonSerializer.Deserialize<T?>(json, Options);
            if (draft is not null) validate(draft);
            _lastJson = JsonSerializer.Serialize(draft, Options);
            return draft;
        }
        catch { _unreadable = true; throw; }
    }

    public Task SaveAsync(T? draft)
    {
        if (_unreadable) throw new IOException($"原恢复草稿无法读取，未覆盖：{path}");
        if (draft is not null) validate(draft);
        var json = JsonSerializer.Serialize(draft, Options);
        if (Encoding.UTF8.GetByteCount(json) > maximumBytes) throw new InvalidDataException("恢复草稿超过保存上限，原文件已保留。");
        lock (_gate)
        {
            _tail = _tail.ContinueWith(_ => Write(json), CancellationToken.None, TaskContinuationOptions.None, TaskScheduler.Default);
            return _tail;
        }
    }

    public Task<string?> PreserveAsync() => ArchiveAsync(clear: false);

    public Task<string?> ArchiveAndClearAsync() => ArchiveAsync(clear: true);

    private Task<string?> ArchiveAsync(bool clear)
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
                if (clear)
                {
                    Write("null");
                    _unreadable = false;
                }
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
