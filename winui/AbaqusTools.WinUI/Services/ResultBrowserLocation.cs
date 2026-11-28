namespace AbaqusTools.WinUI.Services;

/// <summary>Keep the directory being edited separate from the visible result source.</summary>
internal sealed class ResultBrowserLocation
{
    public string DraftRoot { get; set; } = string.Empty;
    public string? LoadedRoot { get; private set; }
    public ResultDirectLocation? DirectBookmark { get; set; }
    public bool HasPendingRoot => LoadedRoot is not null && !SamePath(DraftRoot, LoadedRoot);

    public ResultRootRead BeginRead(string? explicitRoot = null, string? selectedScope = null)
    {
        var root = explicitRoot ?? DraftRoot.Trim();
        RetainMatchingBookmark(root, selectedScope);
        return new(root, DraftRoot, explicitRoot is null);
    }

    public void RetainMatchingBookmark(string root, string? scope)
    {
        if (DirectBookmark is { } bookmark && (scope is null
            || !SamePath(root, bookmark.Root) || !SamePath(scope, bookmark.Scope)))
            DirectBookmark = null;
    }

    public ResultDirectLocation? VisibleDirect(string? scope) =>
        DirectBookmark?.Matches(LoadedRoot, scope) == true ? DirectBookmark : null;

    public void Apply(ResultRootRead request, string resolvedRoot)
    {
        LoadedRoot = resolvedRoot;
        // A completed background refresh must not replace an unsubmitted directory.
        if (request.UsesDraft && DraftRoot == request.DraftAtStart) DraftRoot = resolvedRoot;
    }

    public void ClearLoadedRoot() => LoadedRoot = null;

    public string RequireLoadedRoot() => LoadedRoot
        ?? throw new InvalidOperationException("请先读取结果目录。");

    private static bool SamePath(string left, string right)
    {
        if (string.IsNullOrWhiteSpace(left)) return false;
        try
        {
            return string.Equals(Path.TrimEndingDirectorySeparator(Path.GetFullPath(left.Trim())),
                Path.TrimEndingDirectorySeparator(Path.GetFullPath(right)), StringComparison.OrdinalIgnoreCase);
        }
        catch (Exception error) when (error is ArgumentException or NotSupportedException or IOException)
        {
            return false;
        }
    }
}

internal sealed record ResultRootRead(string Root, string DraftAtStart, bool UsesDraft);

internal sealed record ResultDirectLocation(string Root, string Scope, string DirectoryPath)
{
    private static readonly StringComparer Paths = StringComparer.OrdinalIgnoreCase;

    public bool Matches(string? root, string? scope) => Paths.Equals(Root, root) && Paths.Equals(Scope, scope);
    public bool AtScope => Paths.Equals(DirectoryPath, Scope);
    public ResultDirectLocation? Parent() => AtScope ? null : this with { DirectoryPath = Path.GetDirectoryName(DirectoryPath)! };
    public ResultDirectLocation? Child(string path) => Paths.Equals(Path.GetDirectoryName(path), DirectoryPath)
        ? this with { DirectoryPath = path } : null;

    public void Capture(Dictionary<string, string> values)
    {
        values["DirectRoot"] = Root;
        values["DirectScope"] = Scope;
        values["DirectDirectory"] = DirectoryPath;
    }

    public static ResultDirectLocation? Restore(IReadOnlyDictionary<string, string> values)
    {
        if (!values.TryGetValue("DirectRoot", out var root) || !values.TryGetValue("DirectScope", out var scope)
            || !values.TryGetValue("DirectDirectory", out var directory)) return null;
        try
        {
            if (!new[] { root, scope, directory }.All(path => Path.IsPathFullyQualified(path)
                && Paths.Equals(Path.GetFullPath(path), path))) return null;
            var rootPrefix = Path.EndsInDirectorySeparator(root) ? root : root + Path.DirectorySeparatorChar;
            if (!scope.StartsWith(rootPrefix, StringComparison.OrdinalIgnoreCase) || !(Paths.Equals(scope, directory)
                || directory.StartsWith(scope + Path.DirectorySeparatorChar, StringComparison.OrdinalIgnoreCase))) return null;
            return new(root, scope, directory);
        }
        catch (Exception e) when (e is ArgumentException or NotSupportedException or IOException) { return null; }
    }

    public void ValidateFile(string path)
    {
        if (Child(path) is null) throw new IOException("文件已不属于当前直接浏览目录。");
        for (var current = path; current is not null; current = Path.GetDirectoryName(current))
        {
            var attributes = File.GetAttributes(current);
            if (Paths.Equals(current, path) && (attributes & FileAttributes.Directory) != 0)
                throw new IOException("所选结果已变为目录，请刷新目录。");
            if ((attributes & (FileAttributes.ReparsePoint | FileAttributes.Hidden)) != 0)
                throw new IOException("文件路径已变更为链接或隐藏项，请刷新目录。");
            if ((attributes & FileAttributes.Directory) != 0
                && File.Exists(Path.Combine(current, "_postprocess_incomplete.json")))
                throw new IOException("结果尚未完成发布，请稍后刷新目录。");
            if (Paths.Equals(current, Root)) return;
        }
        throw new IOException("文件已不属于当前结果范围。");
    }
}
