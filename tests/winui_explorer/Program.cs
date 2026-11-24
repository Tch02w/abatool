using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using WinRT;

namespace ExplorerControlChecks;

static class Program
{
    [STAThread]
    static void Main(string[] args)
    {
        ComWrappersSupport.InitializeComWrappers();
        Application.Start(callback =>
        {
            SynchronizationContext.SetSynchronizationContext(new DispatcherQueueSynchronizationContext(
                DispatcherQueue.GetForCurrentThread()));
            _ = new TestApp(Path.GetFullPath(args[0]), args.Length > 1 ? Path.GetFullPath(args[1]) : null);
        });
    }
}
