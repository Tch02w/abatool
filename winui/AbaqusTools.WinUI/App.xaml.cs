using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;

namespace AbaqusTools.WinUI;

public partial class App : Application
{
    public App()
    {
        InitializeComponent();
        ControlPlane = new ControlPlaneHost();
        AppInstance.GetCurrent().Activated += OnInstanceActivated;
    }

    public static new App Current => (App)Application.Current;

    public ControlPlaneHost ControlPlane { get; }
    public WorkbenchSession Session { get; } = new();
    public Task PendingResultFileOperation { get; set; } = Task.CompletedTask;

    public MainWindow MainWindow => _mainWindow
        ?? throw new InvalidOperationException("主窗口尚未创建。");

    private MainWindow? _mainWindow;

    protected override void OnLaunched(LaunchActivatedEventArgs args)
    {
        _mainWindow = new MainWindow(ControlPlane);
        _mainWindow.Closed += OnMainWindowClosed;
        _mainWindow.Activate();
    }

    private void OnInstanceActivated(object? sender, AppActivationArguments args)
    {
        var window = _mainWindow;
        if (window is null)
        {
            return;
        }

        window.DispatcherQueue.TryEnqueue(window.Activate);
    }

    private async void OnMainWindowClosed(object sender, WindowEventArgs args)
    {
        AppInstance.GetCurrent().Activated -= OnInstanceActivated;
        if (_mainWindow is not null)
        {
            _mainWindow.Closed -= OnMainWindowClosed;
        }
        await ControlPlane.DisposeAsync();
    }
}
