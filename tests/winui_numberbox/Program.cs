using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using WinRT;

namespace NumberBoxControlChecks;

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
            _ = new TestApp(args.Length > 0 ? Path.GetFullPath(args[0]) : Path.Combine(AppContext.BaseDirectory, "verification.json"),
                args.Contains("--native-teardown"), args.Contains("--template-close"));
        });
    }
}
