from pathlib import Path


PAGE = Path(__file__).resolve().parents[2] / "winui/AbaqusTools.WinUI/Pages/JobOverviewPage.xaml.cs"


def test_overview_poll_does_not_rebind_or_edit_an_open_job_selector():
    source = PAGE.read_text(encoding="utf-8")
    constructor = source.split("public JobOverviewPage()", 1)[1].split("public IWorkbenchExplorerAdapter", 1)[0]
    assert source.count("JobSelector.ItemsSource =") == 1
    assert "JobSelector.ItemsSource = _jobChoices;" in constructor
    assert "JobSelector.DropDownClosed" in constructor
    refresh = source.split("private JobOverviewEntry? RefreshJobChoices()", 1)[1].split("private void OnJobSelectionChanged", 1)[0]
    guard = refresh.index("if (JobSelector.IsDropDownOpen) return selected;")
    assert guard < refresh.index("_jobChoices.RemoveAt(")
    assert guard < refresh.index("_jobChoices.Add(")
    assert guard < refresh.index("JobSelector.SelectedItem =")
