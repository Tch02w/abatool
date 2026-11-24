namespace AbaqusTools.WinUI.Services;

internal sealed class OdbPostprocessResultLocations
{
    private const string ResultDirectory = "AbaqusODBPostProcessor_Results";
    private static readonly StringComparer Paths = StringComparer.OrdinalIgnoreCase;
    private string? _root;
    private string? _requestId;
    private OdbPostprocessResult? _result;

    public void InputChanged(string input)
    {
        if (Paths.Equals(_root, FullPath(input))) return;
        _root = null;
        _requestId = null;
        _result = null;
    }

    public void Begin(string requestId, string kind, string input)
    {
        if (kind is not ("odb.postprocess.run" or "odb.postprocess.region")) return;
        _root = FullPath(input);
        _requestId = requestId;
        _result = null;
    }

    public void Complete(OdbPostprocessOperationSnapshot snapshot)
    {
        if (_requestId != snapshot.Request.ClientRequestId || !Paths.Equals(_root, FullPath(snapshot.Request.Root)))
            return;
        _result = snapshot.Status == "succeeded" ? snapshot.Result : null;
    }

    public static bool HasPublishedOutputs(OdbPostprocessResult? result) =>
        result is { OutputCount: > 0, ResultRoots.Count: > 0 } && result.Outputs.Count == result.OutputCount;

    public IReadOnlyList<string> Resolve(string input, string? discoveryRoot,
        IEnumerable<string> selectedOdbs, IEnumerable<string> discoveredOdbs)
    {
        var root = FullPath(input) ?? throw new InvalidOperationException("请先选择完整的 ODB 根目录。");
        var currentDiscovery = Paths.Equals(root, FullPath(discoveryRoot));
        var selected = currentDiscovery ? SourceResultRoots(root, selectedOdbs) : [];
        if (_requestId is not null && Paths.Equals(root, _root))
        {
            if (_result is not { } result || !HasPublishedOutputs(result))
                throw new InvalidOperationException("本次提取没有可打开的已发布结果。");
            // A receipt may refer to results that the user subsequently moved or removed.
            var outputs = result.Outputs.Select(FullPath).OfType<string>().Where(Directory.Exists).ToArray();
            var published = result.ResultRoots.Select(FullPath).OfType<string>().Distinct(Paths)
                .Where(path => IsBelow(path, root) && outputs.Any(output => IsBelow(output, path)))
                .ToArray();
            if (published.Length == 0) throw new InvalidOperationException("找不到本次提取回执对应的输出目录。");
            var matching = published.Intersect(selected, Paths).ToArray();
            return matching.Length > 0 ? matching : published;
        }

        if (discoveryRoot is not null && !currentDiscovery)
            throw new InvalidOperationException("ODB 根目录已改变，请先点击“发现 ODB”。");
        var sources = selected.Length > 0 ? selected : currentDiscovery ? SourceResultRoots(root, discoveredOdbs) : [];
        var existing = sources.Append(Path.Combine(root, ResultDirectory)).Distinct(Paths).Where(Directory.Exists).ToArray();
        if (existing.Length == 0) throw new InvalidOperationException("当前目录与所选 ODB 旁尚未找到已有结果目录。");
        return existing;
    }

    private static string[] SourceResultRoots(string root, IEnumerable<string> sources) =>
        sources.Select(FullPath).OfType<string>().Where(path => IsBelow(path, root))
            .Select(path => Path.Combine(Path.GetDirectoryName(path)!, ResultDirectory)).Distinct(Paths).ToArray();

    private static bool IsBelow(string path, string parent)
    {
        var relative = Path.GetRelativePath(parent, path);
        return relative is not ("." or "..") && !Path.IsPathRooted(relative)
            && !relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal);
    }

    private static string? FullPath(string? path)
    {
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path.Trim())) return null;
        try { return Path.TrimEndingDirectorySeparator(Path.GetFullPath(path.Trim())); }
        catch (Exception error) when (error is ArgumentException or IOException or NotSupportedException) { return null; }
    }
}
