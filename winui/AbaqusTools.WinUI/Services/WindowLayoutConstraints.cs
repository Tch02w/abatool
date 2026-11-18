namespace AbaqusTools.WinUI.Services;

/// <summary>Layout dimensions are DIPs; presenter limits and work areas are physical pixels.</summary>
public static class WindowLayoutConstraints
{
    public const double ExplorerWidth = 280;
    public const double NavigationWidth = 8 * 118;
    public const double ResourcePageWidth = ExplorerWidth + 2 * 24 + 600 + 12 + 310;
    public const double SingleColumnFormWidth = ExplorerWidth + 2 * 24 + 2 * 17 + 108 + 10 + 160;
    public static double MinimumClientWidth => MinimumClientWidthFor(explorerVisible: true);
    public static double MinimumClientWidthFor(bool explorerVisible) => Math.Max(NavigationWidth,
        Math.Max(ResourcePageWidth, SingleColumnFormWidth) - (explorerVisible ? 0 : ExplorerWidth));

    // Reserve the fixed shell and a useful viewport, not the full height of scrollable pages.
    // Each queue pane has three control rows (40), three gaps (10), a table header (34),
    // one visible data row (40), and the card's padding/border (2 * 17).
    public const double QueuePaneViewportHeight = 3 * 40 + 3 * 10 + 34 + 40 + 2 * 17;
    public const double PageViewportHeight = 20 + 24 + 12 + 2 * QueuePaneViewportHeight;
    public const double DefaultNavigationHeight = 48;

    public static double MinimumClientHeight(double navigationHeight = DefaultNavigationHeight) =>
        38 + Math.Max(DefaultNavigationHeight, navigationHeight) + 32 + PageViewportHeight;

    public static PixelSize MinimumOuterSize(
        double scale, double frameWidthDip, double frameHeightDip,
        int workAreaWidth, int workAreaHeight,
        double navigationHeight = DefaultNavigationHeight, bool explorerVisible = true)
    {
        if (!double.IsFinite(scale) || scale <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(scale));
        }
        if (workAreaWidth <= 0 || workAreaHeight <= 0)
        {
            throw new ArgumentOutOfRangeException(nameof(workAreaWidth));
        }
        if (!double.IsFinite(frameWidthDip) || frameWidthDip < 0
            || !double.IsFinite(frameHeightDip) || frameHeightDip < 0
            || !double.IsFinite(navigationHeight) || navigationHeight < 0)
        {
            throw new ArgumentOutOfRangeException(nameof(frameWidthDip));
        }

        return new PixelSize(
            BoundedPixels((MinimumClientWidthFor(explorerVisible) + frameWidthDip) * scale, workAreaWidth),
            BoundedPixels((MinimumClientHeight(navigationHeight) + frameHeightDip) * scale, workAreaHeight));
    }

    public static PixelSize ClampToMinimum(int width, int height, PixelSize minimum) =>
        new(Math.Max(width, minimum.Width), Math.Max(height, minimum.Height));

    private static int BoundedPixels(double value, int workAreaExtent) =>
        (int)Math.Min(workAreaExtent, Math.Ceiling(value));

    public readonly record struct PixelSize(int Width, int Height);
}
