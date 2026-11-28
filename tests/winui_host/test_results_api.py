import json
import shutil
import subprocess
from pathlib import Path
from zipfile import ZipFile

import pytest

from modules.postprocessor.result_catalog import classify_result, result_section
from modules.postprocessor.result_index import build_result_index
from tests.control_plane.test_api import running_control_plane


@pytest.mark.skipif(shutil.which("dotnet") is None, reason="Requires .NET 10 SDK")
def test_native_result_pages_and_table_previews(tmp_path: Path) -> None:
    root = tmp_path / "results"
    batch = root / "试验组" / "20261117_120000"
    data = batch / "模型" / "data"
    data.mkdir(parents=True)
    for number in range(500):
        (data / f"measurement_{number}.csv").write_text("time,value\n0,1\n", encoding="utf-8")
    csv = data / "wide.csv"
    csv.write_text("编号,备注,载荷\n" + ("001,," + "x" * 4096 + "\n") * 260, encoding="utf-8-sig")
    xlsx = data / "工作表.xlsx"
    with ZipFile(xlsx, "w") as archive:
        main = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
        rel = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{main}" xmlns:r="{rel}"><sheets>'
                         '<sheet name="摘要" r:id="r1"/><sheet name="数据" r:id="r2"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                         f'<Relationship Id="r1" Type="{rel}/worksheet" Target="worksheets/sheet1.xml"/>'
                         f'<Relationship Id="r2" Type="{rel}/worksheet" Target="worksheets/sheet2.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet2.xml", f'<worksheet xmlns="{main}"><sheetData><row r="1">'
                         '<c r="A1"><v>17.5</v></c></row></sheetData></worksheet>')
        archive.writestr("xl/worksheets/sheet1.xml",
            '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
            '<sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>零点</t></is></c>'
            '<c r="I1"><v>-0.75</v></c></row>'
            '<row r="3"><c r="B3"><v>3</v></c></row></sheetData></worksheet>')
    build_result_index(batch, classify_result, result_section)
    project = Path(__file__).with_name("ControlPlaneHost.Tests.csproj")
    with running_control_plane(tmp_path / "state") as runtime:
        completed = subprocess.run([
            "dotnet", "run", "--project", str(project), "-c", "Release",
            "--artifacts-path", str(tmp_path / "build"), "--", "--results-api",
            str(runtime.descriptor_path), str(root), str(batch), str(csv), str(xlsx),
        ], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120, check=False)
    assert completed.returncode == 0, completed.stdout + completed.stderr
    result = json.loads(completed.stdout.strip().splitlines()[-1])
    assert (result["firstPage"], result["secondPage"], result["total"]) == (500, 2, 502)
    assert result["csv"]["headers"] == ["编号", "备注", "载荷"]
    assert len(result["csv"]["rows"]) == 25 and result["csv"]["truncated"]
    assert result["csv"]["rows"][0] == ["001", "", "x" * 4096]
    assert result["limited"]["rows"] == result["csv"]["rows"][:2] and result["limited"]["truncated"]
    assert result["xlsx"]["headers"] == list("ABCDEFGHI")
    assert result["xlsx"]["rows"] == [
        ["零点"] + [""] * 7 + ["-0.75"], [""] * 9, ["", "3"] + [""] * 7,
    ]
    assert not result["xlsx"]["truncated"]
    assert result["xlsx"]["worksheets"] == ["摘要", "数据"] and result["xlsx"]["selectedWorksheet"] == "摘要"
    assert result["worksheet"]["selectedWorksheet"] == "数据" and result["worksheet"]["rows"] == [["17.5"]]
