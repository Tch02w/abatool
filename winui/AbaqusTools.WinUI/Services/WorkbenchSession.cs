using Microsoft.UI.Xaml;
using Microsoft.UI.Xaml.Controls;
using Microsoft.UI.Xaml.Navigation;

namespace AbaqusTools.WinUI.Services;

public sealed class WorkbenchSession
{
    private sealed record Entry(Page Page, string[] Fields, Func<Task>? Save, Action? Pause, Action? Resume)
    {
        public bool Restored { get; set; }
    }
    private readonly Dictionary<string, Entry> _pages = [];
    private readonly Dictionary<string, Func<Task>> _checkpoints = [];
    private readonly NewJobDraftReset _newJobReset = new();
    private readonly WorkbenchSessionStore _store = new(Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AbaqusTools", "workbench-session.json"));
    public WorkbenchSessionState State { get; }
    public string? LoadError { get; }
    public bool IsClosing { get; private set; }
    public bool IsResettingNewJob => _newJobReset.IsBusy;

    public Page? GetRestoredPage(string route) =>
        _pages.TryGetValue(route, out var entry) && entry.Restored ? entry.Page : null;

    public Task<NewJobResetResult> ResetNewJobAsync(WorkbenchWindowState window,
        Func<Task<bool>> confirm, Action applyPage, Func<bool> canReset) => _newJobReset.RunAsync(
            () => { CapturePageDrafts(window); return State; }, confirm, _store.SaveAsync,
            next =>
            {
                State.Pages[NewJobDraftReset.Route] = next.Pages[NewJobDraftReset.Route];
                State.LastRoute = next.LastRoute;
                applyPage();
            }, () => !IsClosing && canReset());

    public WorkbenchSession()
    {
        try { State = _store.Load(); }
        catch (Exception error) { State = new(); LoadError = error.Message; }
    }

    public void Register(Page page, string route, string[] fields, Func<Task>? save = null,
        Action? pause = null, Action? resume = null)
    {
        page.NavigationCacheMode = NavigationCacheMode.Required;
        var entry = new Entry(page, fields, save, pause, resume);
        _pages[route] = entry;
        page.Loaded += (_, _) =>
        {
            if (entry.Restored) return;
            entry.Restored = true;
            if (!State.Pages.TryGetValue(route, out var values)) return;
            foreach (var name in fields)
            {
                if (!values.TryGetValue(name, out var value)) continue;
                switch (page.FindName(name))
                {
                    case Controls.ExecutionOptionsEditor execution: execution.RestoreDraft(value); break;
                    case TextBox text: text.Text = value; break;
                    case NumberBox number: number.Text = value; break;
                    case ComboBox combo when int.TryParse(value, out var index) && index >= 0 && index < combo.Items.Count:
                        combo.SelectedIndex = index; break;
                    case CheckBox check: check.IsChecked = value == "true"; break;
                }
            }
        };
    }

    public async Task SaveForCloseAsync(WorkbenchWindowState window)
    {
        IsClosing = true;
        foreach (var page in _pages.Values) page.Pause?.Invoke();
        try { await App.Current.PendingResultFileOperation.WaitAsync(TimeSpan.FromSeconds(30)); }
        catch (TimeoutException)
        {
            throw new TimeoutException("结果导出或清理仍在进行，关闭已取消。可等待完成，或返回结果浏览取消导出后再关闭。");
        }
        foreach (var page in _pages.Values)
            if (page.Save is not null) await page.Save();
        await SaveDraftAsync(window);
    }

    // Each callback must capture UI state synchronously and return disk-only work.
    public void RegisterCheckpoint(string key, Func<Task> captureAndSave) => _checkpoints[key] = captureAndSave;

    // No network, page save callbacks or operation waits: suitable for routine checkpoints.
    public Task SaveDraftAsync(WorkbenchWindowState window)
    {
        var writes = new List<Task>();
        try
        {
            if (_newJobReset.PendingSave is { } resetting) writes.Add(resetting);
            else { CapturePageDrafts(window); writes.Add(_store.SaveAsync(State)); }
        }
        catch (Exception error) { writes.Add(Task.FromException(error)); }
        foreach (var capture in _checkpoints.Values)
        {
            try { writes.Add(capture()); }
            catch (Exception error) { writes.Add(Task.FromException(error)); }
        }
        return Task.WhenAll(writes);
    }

    private void CapturePageDrafts(WorkbenchWindowState window)
    {
        foreach (var (route, entry) in _pages)
        {
            // A constructed page may not have restored its inputs yet.
            if (!entry.Restored) continue;
            var values = new Dictionary<string, string>();
            foreach (var name in entry.Fields)
            {
                values[name] = entry.Page.FindName(name) switch
                {
                    Controls.ExecutionOptionsEditor execution => execution.CaptureDraft(),
                    TextBox text => text.Text,
                    NumberBox number => number.Text,
                    ComboBox combo => combo.SelectedIndex.ToString(),
                    CheckBox check => check.IsChecked == true ? "true" : "false",
                    _ => throw new InvalidOperationException($"草稿字段不存在：{route}/{name}"),
                };
            }
            State.Pages[route] = values;
        }
        State.Window = window;
    }

    public void ResumeAfterCancelledClose()
    {
        IsClosing = false;
        foreach (var entry in _pages.Values)
            if (entry.Page.IsLoaded) entry.Resume?.Invoke();
    }

    public static async Task WaitForIdleAsync(Func<bool> busy, string description)
    {
        var deadline = DateTime.UtcNow.AddSeconds(15);
        while (busy())
        {
            if (DateTime.UtcNow >= deadline) throw new TimeoutException($"{description}尚未结束，关闭已取消。");
            await Task.Delay(50);
        }
    }
}
