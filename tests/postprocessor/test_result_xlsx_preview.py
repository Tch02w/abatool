"""Real ZIP/XML previews must not materialize unused workbook strings."""
from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from modules.postprocessor.result_catalog import read_xlsx_preview

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def workbook(path: Path, rows: str, *, string_count: int = 20000) -> Path:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        with archive.open("xl/sharedStrings.xml", "w") as stream:
            stream.write(f'<sst xmlns="{NS}">'.encode())
            stream.write('<si><r><t>载荷</t></r><r><t> N</t></r></si>'.encode())
            for index in range(1, string_count):
                stream.write(f'<si><t>value-{index}-{"x" * 128}</t></si>'.encode())
            stream.write(b"</sst>")
        archive.writestr("xl/worksheets/sheet1.xml", f'<worksheet xmlns="{NS}"><sheetData>{rows}</sheetData></worksheet>')
    return path


def track_shared_reads(monkeypatch):
    counts = []
    original = zipfile.ZipExtFile.read

    def read(stream, size=-1):
        data = original(stream, size)
        if stream.name == "xl/sharedStrings.xml":
            counts.append(len(data))
        return data

    monkeypatch.setattr(zipfile.ZipExtFile, "read", read)
    return counts


def test_early_preview_stops_before_unused_shared_string_tail(tmp_path, monkeypatch):
    path = workbook(tmp_path / "large.xlsx", '<row r="1"><c r="A1" t="s"><v>0</v></c>'
                    '<c r="B1" t="s"><v>5</v></c><c r="C1" t="s"><v>0</v></c></row>')
    reads = track_shared_reads(monkeypatch)
    headers, rows = read_xlsx_preview(path, 1)
    assert headers == ["A", "B", "C"]
    assert rows == [["载荷 N", "value-5-" + "x" * 128, "载荷 N"]]
    with zipfile.ZipFile(path) as archive:
        string_bytes = archive.getinfo("xl/sharedStrings.xml").file_size
    assert sum(reads) < string_bytes // 10, "Preview read the unused shared-string tail"


def test_numeric_and_inline_preview_never_reads_shared_strings(tmp_path, monkeypatch):
    path = workbook(tmp_path / "numeric.xlsx", '<row r="1"><c r="A1"><v>12.5</v></c>'
                    '<c r="B1" t="inlineStr"><is><t>说明</t></is></c></row>')
    reads = track_shared_reads(monkeypatch)
    assert read_xlsx_preview(path, 1) == (["A", "B"], [["12.5", "说明"]])
    assert sum(reads) == 0


def test_late_shared_reference_is_resolved_without_losing_order(tmp_path):
    path = workbook(tmp_path / "late.xlsx", '<row r="1"><c r="A1" t="s"><v>19999</v></c>'
                    '<c r="B1" t="s"><v>0</v></c></row>')
    assert read_xlsx_preview(path, 1) == (["A", "B"], [["value-19999-" + "x" * 128, "载荷 N"]])


@pytest.mark.parametrize("reference", ["-1", "99", "not-an-index"])
def test_invalid_shared_reference_is_an_error_not_a_blank_or_other_cell(tmp_path, reference):
    path = workbook(tmp_path / "invalid.xlsx", f'<row r="1"><c r="A1" t="s"><v>{reference}</v></c></row>', string_count=2)
    with pytest.raises((ValueError, IndexError)):
        read_xlsx_preview(path, 1)


def test_first_sheet_relationship_sparse_rows_and_cached_formula(tmp_path):
    path = tmp_path / "first-sheet.xlsx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("xl/workbook.xml", f'<workbook xmlns="{NS}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="首表" r:id="rId2"/></sheets></workbook>')
        archive.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId2" Target="/xl/worksheets/sheet2.xml"/></Relationships>')
        archive.writestr("xl/worksheets/sheet2.xml", f'<worksheet xmlns="{NS}"><dimension ref="A1:D100"/><sheetData><row r="2"><c r="C2"><f>1+2</f><v>3</v></c><c r="D2" t="inlineStr"><is><t>首表</t></is></c></row></sheetData></worksheet>')
    assert read_xlsx_preview(path, 2) == (["A", "B", "C", "D"], [["", "", "", ""], ["", "", "3", "首表"]])
