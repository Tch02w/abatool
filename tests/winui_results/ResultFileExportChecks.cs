using System.Security.Cryptography;
using System.Text.Json;
using AbaqusTools.WinUI.Services;

internal static class ResultFileExportChecks
{
    private sealed class InlineProgress(Action<ResultExportProgress> report) : IProgress<ResultExportProgress>
    { public void Report(ResultExportProgress value) => report(value); }

    public static async Task RunAsync(string directory)
    {
        var root = Path.GetFullPath(directory);
        if (root.StartsWith("C:", StringComparison.OrdinalIgnoreCase)) throw new Exception("Use G: GPTWork for test output");
        Directory.CreateDirectory(root);
        var source = Directory.CreateDirectory(Path.Combine(root, "源文件 中文")).FullName;
        var data = Directory.CreateDirectory(Path.Combine(source, "data")).FullName;
        var first = Path.Combine(data, "曲线.csv");
        var second = Path.Combine(source, "图例.json");
        var large = Path.Combine(source, "large.txt");
        File.WriteAllText(first, "时间,荷载\n1,2\n");
        File.WriteAllText(second, "{\"range\":[0,10]}");
        var bytes = new byte[16 * 1024 * 1024];
        new Random(42).NextBytes(bytes);
        File.WriteAllBytes(large, bytes);
        var sources = new[] { first, second, large };
        string Digest(string path) => Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(path)));
        var before = sources.ToDictionary(path => path, Digest);
        var checks = 0;
        void Check(bool value, string detail) { if (!value) throw new Exception(detail); checks++; }
        string Destination(string name) => Directory.CreateDirectory(Path.Combine(root, name)).FullName;
        ResultExportFile Item(string path, string? relative = null) => new(path, relative ?? Path.GetRelativePath(source, path));
        var normal = Destination("完整 导出");
        var report = await ResultFileExport.CopyAsync(source, normal, [Item(first), Item(second)], null, CancellationToken.None);
        Check(report.Succeeded && report.Completed.Count == 2 && report.Remaining.Count == 0, "Normal export failed");
        Check(Digest(Path.Combine(normal, "data", "曲线.csv")) == before[first], "Relative hierarchy/content changed");
        Check(Digest(Path.Combine(normal, "图例.json")) == before[second], "JSON export missing");
        var again = await ResultFileExport.CopyAsync(source, normal, [Item(first)], null, CancellationToken.None);
        Check(again.Succeeded && again.Completed.Single().Destination.EndsWith("曲线 (2).csv"), "Collision did not create a unique name");
        Check(Digest(Path.Combine(normal, "data", "曲线.csv")) == before[first], "Collision overwrote existing output");
        Check(System.IO.File.GetLastWriteTimeUtc(again.Completed[0].Destination) == System.IO.File.GetLastWriteTimeUtc(first), "Modification time changed");
        var failed = await ResultFileExport.CopyAsync(source, Destination("部分失败"),
            [Item(first), Item(Path.Combine(source, "missing.csv")), Item(second)], null, CancellationToken.None);
        Check(!failed.Succeeded && !failed.Cancelled && failed.Completed.Count == 1 && failed.Remaining.Count == 2 && failed.Error is not null, "Partial failure misreported");
        Check(Digest(failed.Completed[0].Destination) == before[first], "Partial failure removed completed export");
        using var cancel = new CancellationTokenSource();
        var progressSeen = false;
        var cancellationRoot = Destination("中途取消");
        var cancelled = await ResultFileExport.CopyAsync(source, cancellationRoot, [Item(first), Item(large), Item(second)],
            new InlineProgress(value => { if (value.Name == "large.txt" && value.Bytes > 0) { progressSeen = value.Bytes < value.Length; cancel.Cancel(); } }), cancel.Token);
        Check(progressSeen && cancelled.Cancelled && cancelled.Completed.Count == 1 && cancelled.Remaining.Count == 2, "Cancellation did not stop inside the large file");
        Check(!System.IO.File.Exists(Path.Combine(cancellationRoot, "large.txt")), "Partial file was published as a result");
        Check(!Directory.EnumerateFiles(cancellationRoot, "*.part", SearchOption.AllDirectories).Any(), "Owned partial was not removed");
        Check(Digest(cancelled.Completed[0].Destination) == before[first], "Cancellation removed completed file");
        using var beforeStart = new CancellationTokenSource();
        beforeStart.Cancel();
        var neverStarted = Destination("开始前取消");
        var stopped = await ResultFileExport.CopyAsync(source, neverStarted, [Item(first)], null, beforeStart.Token);
        Check(stopped.Cancelled && stopped.Completed.Count == 0 && !Directory.EnumerateFileSystemEntries(neverStarted).Any(), "Pre-cancelled operation wrote output");
        var outside = Path.Combine(root, "outside.txt");
        System.IO.File.WriteAllText(outside, "keep");
        var rejected = await ResultFileExport.CopyAsync(source, Destination("越界源"), [Item(outside)], null, CancellationToken.None);
        Check(rejected.Error is not null && rejected.Completed.Count == 0 && System.IO.File.ReadAllText(outside) == "keep", "Outside source accepted or changed");
        var fallback = Destination("显示路径回退");
        var bounded = await ResultFileExport.CopyAsync(source, fallback, [Item(first, "../escape.csv")], null, CancellationToken.None);
        Check(bounded.Succeeded && bounded.Completed[0].Destination == Path.Combine(fallback, "曲线.csv"), "Invalid display path escaped destination");
        var originalSelection = new List<ResultExportFile> { Item(first) };
        var pending = ResultFileExport.CopyAsync(source, Destination("选择快照"), originalSelection, null, CancellationToken.None);
        originalSelection.Clear();
        Check((await pending).Completed.Count == 1, "Later selection changed an in-flight export");
        var directoryCollision = Destination("同名文件夹");
        Directory.CreateDirectory(Path.Combine(directoryCollision, "图例.json"));
        var renamed = await ResultFileExport.CopyAsync(source, directoryCollision, [Item(second)], null, CancellationToken.None);
        Check(renamed.Succeeded && renamed.Completed[0].Destination.EndsWith("图例 (2).json"), "Directory collision failed");
        var allProgress = new List<ResultExportProgress>();
        var successLarge = await ResultFileExport.CopyAsync(source, Destination("大文件"), [Item(large)], new InlineProgress(allProgress.Add), CancellationToken.None);
        Check(successLarge.Succeeded && Digest(successLarge.Completed[0].Destination) == before[large], "Large export digest mismatch");
        Check(allProgress.First().Bytes == 0 && allProgress.Last().Completed == 1 && allProgress.Any(x => x.Bytes > 0 && x.Bytes < x.Length), "Byte progress missing");
        var invalidDestination = await ResultFileExport.CopyAsync(source, "relative", [Item(first)], null, CancellationToken.None);
        Check(invalidDestination.Error is not null && invalidDestination.Completed.Count == 0, "Relative destination accepted");
        Check(sources.All(path => Digest(path) == before[path]), "An original file was changed");
        using (var lockedSource = new FileStream(first, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            var lockedResult = await ResultFileExport.CopyAsync(source, Destination("源文件占用"), [Item(first)], null, CancellationToken.None);
            Check(lockedResult.Error is not null && lockedResult.Completed.Count == 0 && lockedResult.RetainedPartial is null,
                "Busy source was exported or left a partial");
        }
        var overlapRoot = Destination("并发重名");
        var overlaps = await Task.WhenAll(ResultFileExport.CopyAsync(source, overlapRoot, [Item(first)], null, CancellationToken.None),
            ResultFileExport.CopyAsync(source, overlapRoot, [Item(first)], null, CancellationToken.None));
        Check(overlaps.All(x => x.Succeeded && Digest(x.Completed[0].Destination) == before[first])
            && overlaps.Select(x => x.Completed[0].Destination).Distinct().Count() == 2, "Concurrent collision overwrote another export");
        Check(!Directory.EnumerateFiles(overlapRoot, "*.part", SearchOption.AllDirectories).Any(), "Completed operation left partials");
        System.IO.File.WriteAllText(Path.Combine(root, "verification.json"), JsonSerializer.Serialize(new
        { status = "verified", checks, sourceUnchanged = true, cancelledInsideFile = progressSeen, completedFilesRetained = true }));
        Console.WriteLine($"{checks} result export checks passed");
    }
}
