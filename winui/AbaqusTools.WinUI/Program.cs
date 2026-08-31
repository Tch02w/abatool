using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;
using WinRT;

namespace AbaqusTools.WinUI;

public static class Program
{
    private const string SingleInstanceKey = "AbaqusTools.WinUI.Primary";

    [STAThread]
    public static void Main(string[] args)
    {
        ComWrappersSupport.InitializeComWrappers();
        var current = AppInstance.GetCurrent();
        var primary = AppInstance.FindOrRegisterForKey(SingleInstanceKey);
        if (!primary.IsCurrent)
        {
            primary
                .RedirectActivationToAsync(current.GetActivatedEventArgs())
                .AsTask()
                .GetAwaiter()
                .GetResult();
            return;
        }

        Application.Start(callback =>
        {
            var context = new DispatcherQueueSynchronizationContext(
                DispatcherQueue.GetForCurrentThread());
            SynchronizationContext.SetSynchronizationContext(context);
            _ = new App();
        });
    }
}
