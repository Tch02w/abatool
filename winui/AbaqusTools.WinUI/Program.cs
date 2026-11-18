using Microsoft.UI.Dispatching;
using Microsoft.UI.Xaml;
using Microsoft.Windows.AppLifecycle;
using WinRT;

namespace AbaqusTools.WinUI;

public static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        Services.WorkbenchProfile.Current.ConfigureBackendEnvironment();
        ComWrappersSupport.InitializeComWrappers();
        var current = AppInstance.GetCurrent();
        var primary = AppInstance.FindOrRegisterForKey(Services.WorkbenchProfile.Current.SingleInstanceKey);
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
