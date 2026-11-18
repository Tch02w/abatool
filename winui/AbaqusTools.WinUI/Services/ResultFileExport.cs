namespace AbaqusTools.WinUI.Services;

public sealed record ResultExportFile(string Path, string RelativePath);
public sealed record ResultExportedFile(string Source, string Destination);
public sealed record ResultExportProgress(int Completed, int Total, string Name, long Bytes, long Length);
public sealed record ResultExportOutcome(IReadOnlyList<ResultExportedFile> Completed,
    IReadOnlyList<ResultExportFile> Remaining, bool Cancelled, string? Error, string? RetainedPartial)
{
    public bool Succeeded => Remaining.Count == 0 && !Cancelled && Error is null;
}

/// <summary>Bounded-memory export. Only fully copied files receive a final result name.</summary>
public static class ResultFileExport
{
    public static Task<ResultExportOutcome> CopyAsync(string root, string destination,
        IReadOnlyList<ResultExportFile> files, IProgress<ResultExportProgress>? progress, CancellationToken cancellationToken)
    {
        var captured = files.ToArray();
        return Task.Run(() => CopyCoreAsync(root, destination, captured, progress, cancellationToken));
    }

    private static async Task<ResultExportOutcome> CopyCoreAsync(string root, string destination,
        ResultExportFile[] files, IProgress<ResultExportProgress>? progress, CancellationToken token)
    {
        var completed = new List<ResultExportedFile>();
        string? partial = null;
        try
        {
            if (!Path.IsPathFullyQualified(root) || !Path.IsPathFullyQualified(destination))
                throw new IOException("请选择完整的结果根目录和导出目录。");
            root = Path.GetFullPath(root);
            destination = Path.GetFullPath(destination);
            if (!Directory.Exists(destination)) throw new DirectoryNotFoundException("导出目录不存在。");
            RejectLinks(destination);
            var buffer = new byte[1024 * 1024];
            foreach (var file in files)
            {
                token.ThrowIfCancellationRequested();
                var source = Path.GetFullPath(file.Path);
                var relative = Path.GetRelativePath(root, source);
                if (Escapes(relative)) throw new IOException("所选文件已不属于当前结果目录：" + source);
                RejectLinks(source);
                // Keep the existing export layout; invalid display paths fall back to the basename.
                var folderPart = Escapes(file.RelativePath) ? "" : Path.GetDirectoryName(file.RelativePath) ?? "";
                var folder = Path.GetFullPath(Path.Combine(destination, folderPart));
                if (Escapes(Path.GetRelativePath(destination, folder))) throw new IOException("导出子目录无效。");
                RejectLinks(folder);
                Directory.CreateDirectory(folder);
                RejectLinks(folder);
                var name = Path.GetFileName(source);
                var timestamp = File.GetLastWriteTimeUtc(source);
                long length;
                await using (var input = new FileStream(source, FileMode.Open, FileAccess.Read, FileShare.Read,
                    buffer.Length, FileOptions.Asynchronous | FileOptions.SequentialScan))
                {
                    length = input.Length;
                    var temporary = Path.Combine(folder, ".abatool-export-" + Guid.NewGuid().ToString("N") + ".part");
                    await using (var output = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                        buffer.Length, FileOptions.Asynchronous | FileOptions.SequentialScan))
                    {
                        partial = temporary; // Cleanup owns this file only after CreateNew succeeded.
                        long bytes = 0;
                        long lastReport = 0;
                        progress?.Report(new(completed.Count, files.Length, name, bytes, length));
                        int count;
                        while ((count = await input.ReadAsync(buffer, token)) != 0)
                        {
                            await output.WriteAsync(buffer.AsMemory(0, count), token);
                            bytes += count;
                            if (bytes == count || Environment.TickCount64 - lastReport >= 100)
                            {
                                progress?.Report(new(completed.Count, files.Length, name, bytes, length));
                                lastReport = Environment.TickCount64;
                            }
                        }
                        await output.FlushAsync(token);
                        if (bytes != length || input.Length != length || File.GetLastWriteTimeUtc(source) != timestamp)
                            throw new IOException("源文件在导出期间发生变化，未发布该副本：" + source);
                    }
                }
                token.ThrowIfCancellationRequested();
                RejectLinks(folder);
                File.SetLastWriteTimeUtc(partial!, timestamp);
                var target = PublishUnique(partial!, folder, name, token);
                partial = null;
                completed.Add(new(source, target));
                progress?.Report(new(completed.Count, files.Length, name, length, length));
            }
            return new(completed, [], false, null, null);
        }
        catch (Exception error)
        {
            string? cleanupError = null;
            if (partial is not null)
            {
                try { File.Delete(partial); partial = null; }
                catch (Exception cleanup) { cleanupError = "临时副本未能移除：" + cleanup.Message; }
            }
            var cancelled = error is OperationCanceledException && token.IsCancellationRequested;
            var message = cancelled ? cleanupError : error.Message + (cleanupError is null ? "" : "\n" + cleanupError);
            return new(completed, files.Skip(completed.Count).ToArray(), cancelled, message, partial);
        }
    }

    private static bool Escapes(string path) => Path.IsPathRooted(path)
        || path.Split([Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar]).Any(segment => segment == "..");

    private static void RejectLinks(string path)
    {
        for (string? current = path; current is not null; current = Path.GetDirectoryName(current))
            if ((File.Exists(current) || Directory.Exists(current)) && (File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new IOException("路径包含链接，请选择实际存放目录：" + current);
    }

    private static string PublishUnique(string partial, string folder, string name, CancellationToken token)
    {
        for (var index = 1; index <= 10000; index++)
        {
            token.ThrowIfCancellationRequested();
            var candidate = Path.Combine(folder, index == 1 ? name
                : $"{Path.GetFileNameWithoutExtension(name)} ({index}){Path.GetExtension(name)}");
            if (File.Exists(candidate) || Directory.Exists(candidate)) continue;
            try { File.Move(partial, candidate, overwrite: false); return candidate; }
            catch (IOException) when (File.Exists(candidate) || Directory.Exists(candidate)) { }
        }
        throw new IOException("重名文件过多，请选择其他导出目录。");
    }
}
