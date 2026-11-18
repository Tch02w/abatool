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
        registration = re.search(r'Session.Register\(this, "([^"]+)",\s*\[([^]]*)\]', code)
        if registration is None:
            continue
        route, fields = registration.groups()
        assert route not in routes
        routes.add(route)
        controls = {node.get("{http://schemas.microsoft.com/winfx/2006/xaml}Name"): node
                    for node in ET.parse(source.with_suffix("")).iter()}
        for field in re.findall(r'"([^"]+)"', fields):
            assert field in controls, (route, field)
            assert controls[field].tag.rsplit("}", 1)[-1] in {
                "TextBox", "NumberBox", "WorkbenchNumberBox", "ComboBox", "CheckBox", "ExecutionOptionsEditor"}, (route, field)
            assert not re.search(r"password|token|credential", field, re.IGNORECASE)
            count += 1
    assert routes == {"new-job", "job-queue", "job-overview", "compute-resources", "restart-chain",
                      "odb-merge", "odb-postprocessing", "result-browser"}
    assert count >= 30
