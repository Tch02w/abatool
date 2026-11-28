"""Draft allowlists must name concrete, supported XAML input controls."""

import re
import xml.etree.ElementTree as ET
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2] / "winui" / "AbaqusTools.WinUI"


def test_all_eight_page_draft_bindings_resolve_to_supported_inputs():
    routes = set()
    count = 0
    for source in (ROOT / "Pages").glob("*Page.xaml.cs"):
        code = source.read_text(encoding="utf-8")
        registration = re.search(r'([\w.]+)\.Register\(this, "([^"]+)",\s*\[([^]]*)\]', code)
        if registration is None:
            continue
        receiver, route, fields = registration.groups()
        if receiver != "App.Current.Session":
            assert re.search(rf'\bvar {re.escape(receiver)}\s*=\s*App\.Current\.Session;', code[:registration.start()]), route
        ordered_fields = []
        for expression in filter(None, (item.strip() for item in fields.split(","))):
            field = re.fullmatch(r'"(\w+)"|nameof\((\w+)\)', expression)
            assert field, (route, expression)
            ordered_fields.append(field[1] or field[2])
        if route == "new-job":
            # Switching to server-existing mode clears local paths. Restore that
            # dependency first so the saved remote paths are not subsequently erased.
            for path_field in ("InputPathTextBox", "OldjobPathTextBox", "FortranPathTextBox"):
                assert ordered_fields.index("ExecutionLocationComboBox") < ordered_fields.index(path_field)
        assert route not in routes
        routes.add(route)
        controls = {node.get("{http://schemas.microsoft.com/winfx/2006/xaml}Name"): node
                    for node in ET.parse(source.with_suffix("")).iter()}
        for field in ordered_fields:
            assert field in controls, (route, field)
            assert controls[field].tag.rsplit("}", 1)[-1] in {
                "TextBox", "NumberBox", "WorkbenchNumberBox", "ComboBox", "CheckBox", "ExecutionOptionsEditor"}, (route, field)
            assert not re.search(r"password|token|credential", field, re.IGNORECASE)
            count += 1
    assert routes == {"new-job", "job-queue", "job-overview", "compute-resources", "restart-chain",
                      "odb-merge", "odb-postprocessing", "result-browser"}
    assert count >= 30


def test_result_graph_checkpoint_captures_selected_inspector_before_change_notifications():
    controls = ROOT / "Controls"
    editor = (controls / "OdbResultGraphEditor.xaml.cs").read_text(encoding="utf-8")
    recovery = (controls / "OdbResultGraphEditor.Recovery.cs").read_text(encoding="utf-8")
    checkpoint = recovery.split("private Task SaveDraftCheckpointAsync()", 1)[1].split(
        "private void RefreshDraftRecovery()", 1
    )[0]
    assert checkpoint.index("_nodes.Select(CloneNode)") < checkpoint.index("ReadInspectorInto(selected)")
    assert "n.NodeId == _selectedNodeId" in checkpoint
    assert checkpoint.index("ReadInspectorInto(selected)") < checkpoint.index("_savedSnapshot.HasEdits")
    assert "if (!HasUnsavedChanges)" not in checkpoint

    read = editor.split("private bool ReadInspectorInto(", 1)[1].split("private void ", 1)[0]
    for field, control in (("Name", "NodeNameTextBox"), ("OdbPath", "NodeOdbTextBox"), ("InpPath", "NodeInpTextBox")):
        assert f"node.{field} = {control}.Text;" in read
    select = editor.split("public void SelectNode(", 1)[1].split("private async void", 1)[0]
    assert select.index("ApplyInspectorChanges();") < select.index("_selectedNodeId = nodeId;")
