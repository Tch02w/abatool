from pathlib import Path
from xml.etree import ElementTree

WINUI = Path(__file__).resolve().parents[2] / "winui" / "AbaqusTools.WinUI"
PAGES = WINUI / "Pages"
CONTROLS = WINUI / "Controls"
NAME = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"


def test_transient_feedback_leaves_progress_controls_and_actionable_recovery_in_place():
    for xaml, kept, removed in [
        (PAGES / "ComputeResourcesPage.xaml", "TransferProgressBar", {"ResourceInfoBar"}),
        (PAGES / "RestartChainPage.xaml", "EmptyChainPanel", {"ChainInfoBar"}),
        (PAGES / "OdbMergePage.xaml", "MergeProgressBar", {"MergePlanInfoBar"}),
        (PAGES / "OdbPostprocessingPage.xaml", "WorkspaceRecoveryInfoBar", {"ErrorInfoBar", "WarningInfoBar"}),
        (CONTROLS / "OdbResultGraphEditor.xaml", "GraphRecoveryInfoBar", {"GraphInfoBar"}),
    ]:
        names = {node.get(NAME) for node in ElementTree.parse(xaml).iter()}
        assert kept in names and names.isdisjoint(removed)
        assert "App.Current.MainWindow.ShowFeedback(" in xaml.with_suffix(".xaml.cs").read_text(encoding="utf-8")


def test_polling_and_implicit_plan_checks_do_not_repeat_action_feedback():
    resources = (PAGES / "ComputeResourcesPage.xaml.cs").read_text(encoding="utf-8")
    polling = resources.split("private async Task RefreshRemoteSnapshotInBackgroundAsync()", 1)[1].split(
        "private async void OnRefreshClicked", 1
    )[0]
    assert "ShowRemoteActionErrorAsync(exception, notify: false)" in polling
    assert "ShowInfo(" not in polling and "ShowFeedback(" not in polling
    merge = (PAGES / "OdbMergePage.xaml.cs").read_text(encoding="utf-8")
    assert "ApplyDraftPreview(preview, notifySuccess: true);" in merge
    assert "ApplyDraftPreview(preview);" in merge
    batch = (PAGES / "OdbMergePage.ResultGraph.cs").read_text(encoding="utf-8")
    assert "if (!snapshot.IsActive && notifyTerminal)" in batch
    queue = (PAGES / "OdbPostprocessingPage.GroupQueue.cs").read_text(encoding="utf-8")
    assert "previous.OperationId == queue.OperationId && !queue.IsActive" in queue
    assert "if (finished) ShowGroupQueueOutcome(queue);" in queue
