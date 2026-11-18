namespace AbaqusTools.WinUI.Services;

public enum NewJobResetResult { Completed, Cancelled, Busy }

/// <summary>Confirm first, persist an independent snapshot, then publish the reset.</summary>
public sealed class NewJobDraftReset
{
    public const string Route = "new-job";
    private static readonly string[] TaskFields =
        ["JobNameTextBox", "InputPathTextBox", "OldjobPathTextBox", "FortranPathTextBox"];
    public bool IsBusy { get; private set; }
    // Routine/OS checkpoints must not queue the old controls behind this write.
    public Task? PendingSave { get; private set; }

    public static bool HasTaskInputs(WorkbenchSessionState state) =>
        state.Pages.TryGetValue(Route, out var values)
        && TaskFields.Any(key => values.TryGetValue(key, out var value) && !string.IsNullOrWhiteSpace(value));

    public static WorkbenchSessionState CreateReset(WorkbenchSessionState source)
    {
        var next = new WorkbenchSessionState
        {
            SchemaVersion = source.SchemaVersion, LastRoute = Route,
            ExplorerVisible = source.ExplorerVisible,
            Window = new() { X = source.Window.X, Y = source.Window.Y, Width = source.Window.Width,
                Height = source.Window.Height, Maximized = source.Window.Maximized },
            Pages = source.Pages.ToDictionary(pair => pair.Key, pair => new Dictionary<string, string>(pair.Value)),
        };
        if (!next.Pages.TryGetValue(Route, out var values)) next.Pages[Route] = values = [];
        foreach (var key in TaskFields) values[key] = string.Empty;
        values["ExecutionLocationComboBox"] = "0";
        return next;
    }

    public async Task<NewJobResetResult> RunAsync(Func<WorkbenchSessionState> capture,
        Func<Task<bool>> confirm, Func<WorkbenchSessionState, Task> save,
        Action<WorkbenchSessionState> publish, Func<bool> canReset)
    {
        if (IsBusy || !canReset()) return NewJobResetResult.Busy;
        IsBusy = true;
        try
        {
            if (HasTaskInputs(capture()) && !await confirm()) return NewJobResetResult.Cancelled;
            // A system-session end or a submission may have started during the dialog.
            if (!canReset()) return NewJobResetResult.Busy;
            var next = CreateReset(capture());
            PendingSave = save(next);
            await PendingSave;
            publish(next);
            return NewJobResetResult.Completed;
        }
        finally { PendingSave = null; IsBusy = false; }
    }
}
