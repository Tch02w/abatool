using AbaqusTools.WinUI.Services;

try
{
    if (args.Contains("--verify-failure-exit"))
    {
        throw new InvalidOperationException("Intentional test-runner failure-exit verification");
    }

    UnchangedSnapshotsDoNotWrite();
    SelectedTextSurvivesNewLogs();
    ChangedHeaderAndTruncatedLogsKeepCopyText();
    DragStartDefersWithoutAnExistingSelection();
    PendingSnapshotsAreCoalesced();
    SwitchingJobsDiscardsPendingOldLogs();
    IdenticalTextForAnotherJobResetsSelection();
    RevertedSnapshotClearsPendingUpdate();
    ScrollPolicyPreservesReadingPosition();
    Console.WriteLine("9 runtime-log interaction behavior checks passed");
}
catch (Exception exception)
{
    Console.Error.WriteLine(exception);
    Environment.ExitCode = 1;
}

static void Check(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

static void UnchangedSnapshotsDoNotWrite()
{
    var view = new LogView();
    view.Snapshot("local:A", "line 1\r\nline 2");
    view.Select(0, 6);
    for (var count = 0; count < 20; count++)
        view.Snapshot("local:A", "line 1\r\nline 2");
    Check(view.Writes == 1 && view.Copy() == "line 1" && !view.State.HasPendingText,
        "Unchanged polling snapshots must not assign Text or disturb copy selection");
}

static void SelectedTextSurvivesNewLogs()
{
    var view = new LogView();
    view.Snapshot("local:A", "old line\r\nselected line");
    view.Select(10, 13);
    view.Snapshot("local:A", "old line\r\nselected line\r\nnew line");
    Check(view.Writes == 1 && view.Copy() == "selected line" && view.State.HasPendingText,
        "New log content must stay pending while text is selected");
    view.PointerDown = false;
    view.Flush();
    Check(view.Copy() == "selected line" && view.Writes == 1,
        "Pointer release must not flush while a selection remains for keyboard/context-menu copy");
    view.Select(0, 0);
    view.Flush();
    Check(view.Writes == 2 && view.Text.EndsWith("new line", StringComparison.Ordinal)
        && !view.State.HasPendingText,
        "Clearing the selection must apply the pending log once");
}

static void ChangedHeaderAndTruncatedLogsKeepCopyText()
{
    var view = new LogView();
    const string original = "进度：9%\r\n历史中文日志\r\nlatest";
    view.Snapshot("local:A", original);
    var start = original.IndexOf("历史", StringComparison.Ordinal);
    view.Select(start, "历史中文日志".Length);
    view.Snapshot("local:A", "进度：100%\r\nlatest\r\nfinished");
    Check(view.Copy() == "历史中文日志" && view.Text == original,
        "Changing headers and tail-window truncation must not replace selected old text");
    view.Select(0, 0);
    view.Flush();
    Check(view.Text == "进度：100%\r\nlatest\r\nfinished",
        "After reading, replace with the latest full snapshot without stitching discarded logs");
}

static void DragStartDefersWithoutAnExistingSelection()
{
    var view = new LogView();
    view.Snapshot("remote:A", "old");
    view.PointerDown = true;
    view.Snapshot("remote:A", "new");
    Check(view.Text == "old" && view.State.HasPendingText,
        "A pointer-down before the first selected character must also defer updates");
    view.PointerDown = false;
    view.Flush();
    Check(view.Text == "new", "A completed click with no selection may release the pending snapshot");
}

static void PendingSnapshotsAreCoalesced()
{
    var view = new LogView();
    view.Snapshot("remote:A", "initial");
    view.Select(0, 7);
    for (var count = 1; count <= 100; count++)
        view.Snapshot("remote:A", $"snapshot {count}");
    Check(view.Copy() == "initial" && view.Writes == 1,
        "Multiple polls must retain a stable selection without writing intermediate snapshots");
    view.Select(0, 0);
    view.Flush();
    view.Flush();
    Check(view.Text == "snapshot 100" && view.Writes == 2,
        "Only the newest pending full snapshot should be applied, exactly once");
}

static void SwitchingJobsDiscardsPendingOldLogs()
{
    var view = new LogView();
    view.Snapshot("local:A", "A old");
    view.Select(0, 1);
    view.Snapshot("local:A", "A pending");
    view.Snapshot("local:B", "B log");
    view.Flush();
    Check(view.Text == "B log" && view.SelectionLength == 0 && !view.State.HasPendingText,
        "A job switch must clear the old selection and discard pending text from the former job");
    view.Snapshot(null, "No job");
    Check(view.Text == "No job" && view.LastResetView,
        "Removing the selected job must reset the log view rather than retaining another job's content");
}

static void IdenticalTextForAnotherJobResetsSelection()
{
    var view = new LogView();
    view.Snapshot("local:A", "running");
    view.Select(0, 7);
    view.Snapshot("remote:A", "running");
    Check(view.Writes == 2 && view.SelectionLength == 0 && view.LastResetView,
        "Local/remote job identity changes must reset context even when their text happens to match");
}

static void RevertedSnapshotClearsPendingUpdate()
{
    var view = new LogView();
    view.Snapshot("local:A", "visible");
    view.Select(0, 7);
    view.Snapshot("local:A", "pending");
    view.Snapshot("local:A", "visible");
    view.Select(0, 0);
    view.Flush();
    Check(view.Writes == 1 && view.Text == "visible" && !view.State.HasPendingText,
        "A snapshot matching the current display supersedes stale deferred text without a write");
}

static void ScrollPolicyPreservesReadingPosition()
{
    Check(!RuntimeLogUpdateState.ShouldFollowTail(120, 900),
        "Reading earlier lines must not force the view to the bottom");
    Check(RuntimeLogUpdateState.ShouldFollowTail(899.5, 900),
        "A reader at the bottom should follow new output despite subpixel rounding");
    Check(RuntimeLogUpdateState.ShouldFollowTail(0, 0),
        "A log that initially fits in the viewport should follow appended output");
}

// Model the destructive Text assignment that caused the bug: an assignment clears
// native text selection. The production state must avoid issuing it while copying.
sealed class LogView
{
    public RuntimeLogUpdateState State { get; } = new("placeholder");
    public string Text { get; private set; } = "placeholder";
    public int SelectionStart { get; private set; }
    public int SelectionLength { get; private set; }
    public bool PointerDown { get; set; }
    public int Writes { get; private set; }
    public bool LastResetView { get; private set; }

    public void Select(int start, int length)
    {
        SelectionStart = start;
        SelectionLength = length;
    }

    public string Copy() => Text.Substring(SelectionStart, SelectionLength);

    public void Snapshot(string? key, string text) =>
        Apply(State.SetSnapshot(key, text, PointerDown || SelectionLength > 0));

    public void Flush() => Apply(State.Flush(PointerDown || SelectionLength > 0));

    private void Apply(RuntimeLogTextUpdate? update)
    {
        if (update is null) return;
        Text = update.Text;
        SelectionStart = 0;
        SelectionLength = 0;
        LastResetView = update.ResetView;
        Writes++;
    }
}
