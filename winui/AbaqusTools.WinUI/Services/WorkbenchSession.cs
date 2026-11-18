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
    private readonly WorkbenchSessionStore _store = new(Path.Combine(
        Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "AbaqusTools", "workbench-session.json"));
    public WorkbenchSessionState State { get; }
    public string? LoadError { get; }
    public bool IsClosing { get; private set; }

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
        await App.Current.PendingResultFileOperation.WaitAsync(TimeSpan.FromSeconds(30));
        foreach (var page in _pages.Values)
            if (page.Save is not null) await page.Save();
        await SaveDraftAsync(window);
    }

    // No network, page save callbacks or operation waits: suitable for routine checkpoints.
    public Task SaveDraftAsync(WorkbenchWindowState window)
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
        return _store.SaveAsync(State);
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
