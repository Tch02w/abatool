using AbaqusTools.WinUI.Services;
using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;

namespace AbaqusTools.WinUI.Pages;

public sealed partial class OdbPostprocessingPage
{
    private static string DialogDraftKey(string kind, string target) => kind + " · " + target;

    private async Task<ContentDialogResult> ShowRecoverableDialogAsync(ContentDialog dialog, StackPanel panel,
        string kind, string target, object basis, Dictionary<string, Control> inputs,
        Func<Dictionary<string, string>>? extraCapture = null, Action<IReadOnlyDictionary<string, string>>? extraRestore = null)
    {
        var key = DialogDraftKey(kind, target);
        var signature = OdbPostprocessDraftRecovery.Fingerprint(new { basis, Sources = OdbPostprocessDraftRecovery.SourceKey(CurrentDraftSources()) });
        _dialogDrafts.TryGetValue(key, out var old);
        var pending = old is not null;
        var resolving = false;
        // A close must not race the preserve/restore writes and apply cancelled input later.
        dialog.Closing += (_, args) => { if (resolving) args.Cancel = true; };
        Dictionary<string, string> Capture()
        {
            var values = CaptureInputs(inputs);
            if (extraCapture is not null) foreach (var pair in extraCapture()) values[pair.Key] = pair.Value;
            return values;
        }
        var initial = OdbPostprocessDraftRecovery.Fingerprint(Capture());
        void CaptureActive()
        {
            if (pending) return;
            var values = Capture();
            if (OdbPostprocessDraftRecovery.Fingerprint(values) == initial) _dialogDrafts.Remove(key);
            else _dialogDrafts[key] = new() { Basis = signature, Inputs = values };
        }
        var body = new StackPanel { Spacing = panel.Spacing };
        var children = panel.Children.ToArray();
        panel.Children.Clear();
        foreach (var child in children) body.Children.Add(child);
        var banner = new InfoBar { Title = "发现上次未确认的填写", IsClosable = false, IsOpen = pending,
            Severity = InfoBarSeverity.Warning, Message = old?.Basis == signature
                ? "可恢复继续编辑，仍须点击本窗口的保存按钮才应用。"
                : "对应配置或结构已经变化，未套用旧输入。可查看内容或先保留副本再忽略。" };
        var actions = new StackPanel { Spacing = 6 };
        var row = new StackPanel { Orientation = Orientation.Horizontal, Spacing = 6 };
        var restore = new Button { Content = "恢复填写", IsEnabled = old?.Basis == signature };
        var preview = new Button { Content = "查看填写" };
        var ignore = new Button { Content = "保留副本并忽略" };
        var text = new TextBox { Text = old is null ? "" : InputSummary(old.Inputs), IsReadOnly = true,
            AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, MaxHeight = 160, Visibility = Visibility.Collapsed };
        preview.Click += (_, _) => text.Visibility = text.Visibility == Visibility.Visible ? Visibility.Collapsed : Visibility.Visible;
        row.Children.Add(restore); row.Children.Add(preview); row.Children.Add(ignore);
        actions.Children.Add(row); actions.Children.Add(text); banner.Content = actions;
        panel.Children.Add(banner); panel.Children.Add(body);
        var primaryEnabled = dialog.IsPrimaryButtonEnabled;
        var secondaryEnabled = dialog.IsSecondaryButtonEnabled;
        void EnableEditing(bool enabled)
        {
            body.Visibility = enabled ? Visibility.Visible : Visibility.Collapsed;
            dialog.IsPrimaryButtonEnabled = enabled && primaryEnabled;
            dialog.IsSecondaryButtonEnabled = enabled && secondaryEnabled;
        }
        EnableEditing(!pending);
        async Task Resolve(bool apply)
        {
            if (resolving) return;
            resolving = true;
            restore.IsEnabled = ignore.IsEnabled = false;
            try
            {
                await SavePostprocessDraftAsync();
                if (_draftFile is not null) await _draftFile.PreserveAsync();
                if (apply && old is not null)
                {
                    var before = Capture();
                    try
                    {
                        RestoreInputs(inputs, old.Inputs);
                        extraRestore?.Invoke(old.Inputs);
                    }
                    catch
                    {
                        RestoreInputs(inputs, before);
                        extraRestore?.Invoke(before);
                        throw;
                    }
                }
                pending = false;
                _dialogDrafts.Remove(key);
                banner.IsOpen = false;
                EnableEditing(true);
                CaptureActive();
                await SavePostprocessDraftAsync();
            }
            catch (Exception error) { banner.Message = error.Message + " 原草稿仍保留。"; banner.IsOpen = true; }
            finally { resolving = false; restore.IsEnabled = pending && old?.Basis == signature; ignore.IsEnabled = pending; }
        }
        restore.Click += async (_, _) => await Resolve(apply: true);
        ignore.Click += async (_, _) => await Resolve(apply: false);
        _captureOpenDialog = CaptureActive;
        ContentDialogResult result;
        try
        {
            result = await dialog.ShowAsync();
            if (result == ContentDialogResult.None && !pending) _dialogDrafts.Remove(key);
            else CaptureActive();
        }
        catch (Exception error)
        {
            CaptureActive();
            ShowWarning(error.Message, "弹窗未正常关闭，填写仍作为草稿保留");
            return ContentDialogResult.None;
        }
        finally { _captureOpenDialog = null; }
        if (result == ContentDialogResult.None)
        {
            try { await SavePostprocessDraftAsync(); }
            catch (Exception error) { ShowWarning(error.Message, "取消已生效，恢复草稿未能更新"); }
        }
        return result;
    }

    private async Task CompleteDialogDraftAsync(string kind, string target)
    {
        _dialogDrafts.Remove(DialogDraftKey(kind, target));
        try { await SavePostprocessDraftAsync(); }
        catch (Exception error) { ShowWarning(error.Message, "配置已应用，但恢复草稿未能更新"); }
    }
}
