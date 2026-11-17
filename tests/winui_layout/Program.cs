using AbaqusTools.WinUI.Services;
using System.Xml.Linq;

try
{
    if (args.Contains("--verify-failure-exit"))
    {
        throw new InvalidOperationException("Intentional test-runner failure-exit verification");
    }

    Check(WindowLayoutConstraints.MinimumClientWidth == 1250,
        "The resource-page columns must dominate the navigation and responsive form width");
    Check(WindowLayoutConstraints.MinimumClientHeight() == 690,
        "Height must reserve shell chrome and two useful table viewports, not a full scrolling page");
    var normal = Size(1, 1920, 1080);
    Check(normal == new WindowLayoutConstraints.PixelSize(1266, 706),
        "100% DPI must include measured nonclient dimensions once");
    Check(Size(1.25, 2560, 1440) == new WindowLayoutConstraints.PixelSize(1583, 883),
        "125% DPI must round each physical minimum up");
    Check(Size(1.5, 1366, 768) == new WindowLayoutConstraints.PixelSize(1366, 768),
        "Small high-DPI screens must cap both minimum extents to the current work area");
    Check(Size(1, 1200, 1080) == new WindowLayoutConstraints.PixelSize(1200, 706)
        && Size(1, 1920, 600) == new WindowLayoutConstraints.PixelSize(1266, 600),
        "Work-area caps must apply independently, preserving the other dimension");
    Check(WindowLayoutConstraints.ClampToMinimum(800, 500, normal) == normal,
        "A restored startup window smaller than both limits must be enlarged");
    Check(WindowLayoutConstraints.ClampToMinimum(1400, 800, normal)
        == new WindowLayoutConstraints.PixelSize(1400, 800),
        "A valid user window size must not be changed");
    Check(WindowLayoutConstraints.ClampToMinimum(1400, 500, normal)
        == new WindowLayoutConstraints.PixelSize(1400, 706),
        "A resize correction must not shrink the unaffected dimension");
    Check(Size(2, 3840, 2160) == new WindowLayoutConstraints.PixelSize(2532, 1412)
        && Size(1, 1920, 1080) == normal,
        "Cross-monitor recomputation must use DIPs rather than scaling an earlier pixel minimum");
    Check(WindowLayoutConstraints.MinimumOuterSize(1, 16, 16, 1920, 1080, 72).Height == 730,
        "A measured taller navigation header must retain the same page viewport");
    foreach (var scale in new[] { 0d, -1d, double.NaN, double.PositiveInfinity })
    {
        Rejects(() => Size(scale, 1920, 1080));
    }
    Rejects(() => Size(1, 0, 1080));
    Rejects(() => WindowLayoutConstraints.MinimumOuterSize(1, -1, 16, 1920, 1080));
    VerifyLayoutSources();
    Console.WriteLine("13 window layout checks passed (DIP formulas, DPI, work-area caps, startup clamp, source dimensions)");
}
catch (Exception exception)
{
    Console.Error.WriteLine(exception);
    Environment.ExitCode = 1;
}

static WindowLayoutConstraints.PixelSize Size(double scale, int workWidth, int workHeight) =>
    WindowLayoutConstraints.MinimumOuterSize(scale, 16, 16, workWidth, workHeight);

static void Check(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

static void Rejects(Action action)
{
    try { action(); }
    catch (ArgumentOutOfRangeException) { return; }
    throw new InvalidOperationException("Invalid size inputs must not be converted into presenter constraints");
}

static void VerifyLayoutSources()
{
    var root = new DirectoryInfo(Directory.GetCurrentDirectory());
    while (root is not null && !File.Exists(Path.Combine(root.FullName, "winui/AbaqusTools.WinUI/MainWindow.xaml")))
    {
        root = root.Parent;
    }
    Check(root is not null, "Run the layout checks from within the repository");
    var ui = Path.Combine(root!.FullName, "winui/AbaqusTools.WinUI");
    var shell = XDocument.Load(Path.Combine(ui, "MainWindow.xaml"));
    XNamespace xaml = "http://schemas.microsoft.com/winfx/2006/xaml";
    var explorer = shell.Descendants().Single(element => (string?)element.Attribute(xaml + "Name") == "ExplorerHost");
    Check((string?)explorer.Attribute("Width") == "280", "Explorer layout changed: re-evaluate the global minimum");
    var navigationItems = shell.Descendants().Where(element => element.Name.LocalName == "NavigationViewItem").ToList();
    Check(navigationItems.Count == 8 && navigationItems.All(element => (string?)element.Attribute("MinWidth") == "118"),
        "Top navigation layout changed: re-evaluate the global minimum");
    var resources = XDocument.Load(Path.Combine(ui, "Pages/ComputeResourcesPage.xaml"));
    var resourceGrid = resources.Descendants().Single(element => element.Name.LocalName == "Grid"
        && element.Elements().Any(child => child.Name.LocalName == "Grid.ColumnDefinitions"
            && child.Elements().Any(column => (string?)column.Attribute("MinWidth") == "600")));
    Check((string?)resourceGrid.Attribute("ColumnSpacing") == "12"
        && resourceGrid.Descendants().Any(column => (string?)column.Attribute("MinWidth") == "310"),
        "Resource-page fixed column requirements changed");
    var queue = XDocument.Load(Path.Combine(ui, "Pages/JobQueuePage.xaml"));
    var policy = queue.Descendants().Single(element => (string?)element.Attribute(xaml + "Name") == "ExistingResultPolicyComboBox");
    var parallel = queue.Descendants().Single(element => (string?)element.Attribute(xaml + "Name") == "ParallelLimitNumberBox");
    Check((string?)policy.Attribute("Height") == "40" && (string?)policy.Attribute("VerticalAlignment") == "Center"
        && (string?)parallel.Attribute("VerticalAlignment") == "Center", "Queue policy and numeric input must share the row's vertical center");
}
