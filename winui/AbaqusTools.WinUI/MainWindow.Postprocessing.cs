using AbaqusTools.WinUI.Pages;
using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI;

public sealed partial class MainWindow
{
    private JobPostprocessTarget CaptureCurrentJobTarget()
    {
        if (ContentFrame.Content is JobQueuePage queue) return queue.CapturePostprocessTarget();
        if (ContentFrame.Content is JobOverviewPage overview)
            return overview.PostprocessTarget ?? throw new InvalidOperationException("请先在作业概览中选择一个作业。");
        if (ContentFrame.Content is NewJobPage draft) return draft.PostprocessTarget;
        if (App.Current.Session.GetRestoredPage("job-overview") is JobOverviewPage previous
            && previous.PostprocessTarget is { } selected) return selected;
        if (App.Current.Session.GetRestoredPage("new-job") is NewJobPage previousDraft)
            return previousDraft.PostprocessTarget;
        throw new InvalidOperationException("请先在作业概览或正式队列中选择一个作业。");
    }

    private async void OnCurrentJobPostprocessingMenuClicked(object sender, RoutedEventArgs args)
    {
        if (_menuCommandBusy || App.Current.Commands.Locked) return;
        _menuCommandBusy = true;
        UpdateCommandMenus();
        var origin = ContentFrame.Content;
        try
        {
            var target = CaptureCurrentJobTarget();
            var route = await JobPostprocessRoute.ResolveAsync(target, () => _controlPlane.GetLocalQueueRuntimeAsync());
            if (App.Current.Commands.Locked || !ReferenceEquals(origin, ContentFrame.Content)
                || target != CaptureCurrentJobTarget())
            {
                ReportPageStatus("当前选择已变化，本次未切换后处理文件");
                return;
            }
            if (StartupInfoBar.Title == "当前作业未送入后处理") StartupInfoBar.IsOpen = false;
            NavigateToRoute("odb-postprocessing");
            if (ContentFrame.Content is OdbPostprocessingPage page
                && await page.LoadOdbPathAsync(route.Path,
                    () => !App.Current.Commands.Locked && ReferenceEquals(page, ContentFrame.Content)))
                ReportPageStatus($"已定位作业 ODB · {route.Source} · {route.Path}");
        }
        catch (Exception error)
        {
            if (!_windowClosed && !App.Current.Commands.Locked && ReferenceEquals(origin, ContentFrame.Content))
            {
                StartupInfoBar.Severity = InfoBarSeverity.Warning;
                StartupInfoBar.Title = "当前作业未送入后处理";
                StartupInfoBar.Message = error is ControlPlaneException problem ? problem.ToDisplayMessage() : error.Message;
                StartupInfoBar.IsOpen = true;
                ReportPageStatus(StartupInfoBar.Message);
            }
        }
        finally { _menuCommandBusy = false; UpdateCommandMenus(); }
    }
}
