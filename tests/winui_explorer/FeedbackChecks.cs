using AbaqusTools.WinUI.Controls;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Automation.Peers;
using Microsoft.UI.Xaml.Automation.Provider;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Media;
using Microsoft.UI.Xaml.Media.Imaging;
using Windows.Storage.Streams;

namespace ExplorerControlChecks;

public sealed partial class TestApp
{
    private async Task CheckFeedbackHostAsync()
    {
        var surface = new Grid();
        var page = new Button { Content = "页面操作", VerticalAlignment = VerticalAlignment.Top };
        var host = new WorkbenchFeedbackHost { Margin = new Thickness(12),
            HorizontalAlignment = HorizontalAlignment.Right, VerticalAlignment = VerticalAlignment.Bottom };
        surface.Children.Add(page);
        surface.Children.Add(host);
        _root.Children.Add(surface);
        await DispatchAsync();
        var bar = (InfoBar)host.FindName("FeedbackBar");
        var pending = (TextBlock)host.FindName("PendingCount");
        var card = (Border)host.FindName("Card");
        var initial = page.TransformToVisual(surface).TransformPoint(default);
        foreach (var theme in new[] { ElementTheme.Light, ElementTheme.Dark })
        {
            host.RequestedTheme = theme;
            host.Show("保存失败", "请核对目录", InfoBarSeverity.Error);
            await DispatchAsync();
            surface.UpdateLayout();
            var end = host.TransformToVisual(surface).TransformPoint(new(host.ActualWidth, host.ActualHeight));
            var current = page.TransformToVisual(surface).TransformPoint(default);
            Check(bar.IsOpen && bar.Severity == InfoBarSeverity.Error && card.ActualTheme == theme
                && current == initial && Math.Abs(surface.ActualHeight - end.Y - 12) < 1
                && Math.Abs(surface.ActualWidth - end.X - 12) < 1,
                $"Shell feedback is bottom-right in {theme} with unchanged page bounds");
            var bitmap = new RenderTargetBitmap();
            await bitmap.RenderAsync(card);
            using var pixels = DataReader.FromBuffer(await bitmap.GetPixelsAsync());
            var bgra = new byte[checked((int)pixels.UnconsumedBufferLength)];
            pixels.ReadBytes(bgra);
            var corner = 4 * (bitmap.PixelWidth * 7 + 7);
            var red = bgra[corner + 2];
            var green = bgra[corner + 1];
            Check(red > green && (theme == ElementTheme.Light ? green > 150 : green < 130)
                && bgra[corner + 3] == 255, $"{theme} error card renders an opaque severity color RGB({red},{green},{bgra[corner]})");
            host.Show("保存失败", "请核对目录", InfoBarSeverity.Error);
            Check(pending.Visibility == Visibility.Collapsed, "Duplicate visible feedback is coalesced");
            CloseNativeInfoBar(bar);
            await DispatchAsync();
            Check(!bar.IsOpen && card.Visibility == Visibility.Collapsed, "Native close immediately dismisses the only card");
        }
        host.Show("成功", "已保存", InfoBarSeverity.Success);
        host.Show("消息", "已应用", InfoBarSeverity.Informational);
        host.Show("错误一", "详情", InfoBarSeverity.Error);
        host.Show("错误二", "第二条详情", InfoBarSeverity.Error);
        host.Show("错误一", "详情", InfoBarSeverity.Error);
        await DispatchAsync();
        Check(pending.Text.Contains('3'), "Different waiting notifications are retained and repeated errors coalesce");
        await Task.Delay(1600);
        Check(FindClose(bar).Focus(FocusState.Keyboard), "Keyboard can focus the native close button");
        await Task.Delay(2700);
        Check(bar.Title == "成功", "Keyboard focus pauses an active success notification");
        Check(page.Focus(FocusState.Keyboard), "Focus can return to the underlying page");
        await Task.Delay(2900);
        Check(bar.IsOpen && bar.Title == "错误一", "Focus departure resumes the remaining time and queues errors first");
        await Task.Delay(4300);
        Check(bar.Title == "错误一", "Errors remain until explicitly dismissed");
        CloseNativeInfoBar(bar);
        await DispatchAsync();
        Check(bar.IsOpen && bar.Title == "错误二", "The second pending error is presented");
        CloseNativeInfoBar(bar);
        await DispatchAsync();
        Check(bar.Title == "消息", "The normal notification survives both errors");
        await Task.Delay(4350);
        Check(!bar.IsOpen, "An informational notification expires after four seconds");

        var dialog = new ContentDialog { Title = "模态确认", CloseButtonText = "关闭", XamlRoot = surface.XamlRoot };
        var dialogTask = dialog.ShowAsync().AsTask();
        await Task.Delay(300);
        host.Show("警告", "请检查", InfoBarSeverity.Warning);
        await Task.Delay(250);
        Check(!bar.IsOpen, "A modal dialog defers new feedback");
        dialog.Hide();
        await dialogTask;
        await Task.Delay(350);
        Check(bar.IsOpen && bar.Title == "警告", "Feedback is presented after the modal closes");
        await Task.Delay(4100);
        Check(bar.IsOpen, "A warning is still visible after four seconds");
        await Task.Delay(4050);
        Check(!bar.IsOpen, "A warning expires after eight seconds");
        host.Stop();
        host.Show("已关闭", "不再显示", InfoBarSeverity.Error);
        Check(!bar.IsOpen, "A stopped host no longer displays messages");
        _root.Children.Remove(surface);
        await DispatchAsync();
    }

    private static Button FindClose(InfoBar bar)
    {
        bar.ApplyTemplate();
        return FindCloseDescendant(bar) ?? throw new InvalidOperationException("InfoBar has no native close button");
    }

    private static Button? FindCloseDescendant(DependencyObject element)
    {
        if (element is Button { Name: "CloseButton" } close) return close;
        for (var i = 0; i < VisualTreeHelper.GetChildrenCount(element); i++)
            if (FindCloseDescendant(VisualTreeHelper.GetChild(element, i)) is { } button) return button;
        return null;
    }

    private static void CloseNativeInfoBar(InfoBar bar)
    {
        var peer = new ButtonAutomationPeer(FindClose(bar));
        ((IInvokeProvider)peer.GetPattern(PatternInterface.Invoke)).Invoke();
    }
}
