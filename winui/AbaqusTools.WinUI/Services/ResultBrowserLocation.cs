namespace AbaqusTools.WinUI.Services;

/// <summary>Keep the directory being edited separate from the visible result source.</summary>
internal sealed class ResultBrowserLocation
{
    public string DraftRoot { get; set; } = string.Empty;
    public string? LoadedRoot { get; private set; }
    public bool HasPendingRoot => LoadedRoot is not null && !SamePath(DraftRoot, LoadedRoot);

    public ResultRootRead BeginRead(string? explicitRoot = null) =>
        new(explicitRoot ?? DraftRoot.Trim(), DraftRoot, explicitRoot is null);

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
