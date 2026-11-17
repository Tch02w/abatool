"""Keep handoff navigation usable without importing application runtimes.

Checks references, not functionality: a green result is NOT product acceptance.
Local GPTWork evidence is optional on a fresh clone and intentionally excluded.
"""
import ast
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit

import pytest


ROOT = Path(__file__).resolve().parents[2]
DOCS = [ROOT / "AGENTS.md", ROOT / "README.md", ROOT / "docs/INDEX.md"]
for directory in ("02-architecture", "03-features", "05-development", "06-testing", "08-handoff", "repowiki"):
    DOCS.extend(sorted((ROOT / "docs" / directory).rglob("*.md")))


@pytest.mark.parametrize("document", DOCS, ids=lambda path: path.relative_to(ROOT).as_posix())
def test_local_links_and_explicit_source_paths_exist(document):
    content = document.read_text(encoding="utf-8")
    assert content.strip(), f"Empty document: {document}"
    for target in re.findall(r"\]\(([^\s)]+)\)", content):
        parsed = urlsplit(target.strip("<>"))
        if parsed.scheme or not parsed.path:
            continue
        linked = (document.parent / unquote(parsed.path)).resolve()
        assert linked.is_relative_to(ROOT), f"Reference outside project: {document}: {target}"
        assert linked.exists(), f"Broken link: {document}: {target}"
    for target in re.findall(r"`((?:modules|winui|tests)/[^`]+)`", content):
        # Only exact code/test paths are written in this form in the new docs.
        assert (ROOT / target).exists(), f"Missing code/test path: {document}: {target}"


def test_feature_ids_are_unique_and_all_pages_are_locatable():
    content = (ROOT / "docs/03-features/FUNCTION_INDEX.md").read_text(encoding="utf-8")
    ids = re.findall(r"^\| (F\d{3})\b", content, re.MULTILINE)
    assert len(ids) >= 24 and len(ids) == len(set(ids))
    for page in (ROOT / "winui/AbaqusTools.WinUI/Pages").glob("*.xaml.cs"):
        assert page.relative_to(ROOT).as_posix() in content, f"Page missing from feature index: {page}"


@pytest.mark.parametrize("path,symbol", [
    ("modules/control_plane/region_extraction.py", "RegionExtractionRequest.from_payload"),
    ("modules/control_plane/region_extraction.py", "execute_region_extraction"),
    ("modules/control_plane/postprocessing.py", "PostprocessOperationManager"),
    ("modules/postprocessor/abaqus_scripts/scan_odb_core.py", "structure_catalog"),
    ("modules/postprocessor/abaqus_scripts/region_extract_core.py", "extract_rows"),
    ("modules/postprocessor/abaqus_scripts/region_solid_core.py", "extract_solid_rows"),
    ("modules/postprocessor/abaqus_scripts/solid_section_math.py", "section_config"),
    ("modules/postprocessor/postprocess_execution.py", "execute_postprocess_plan"),
    ("modules/control_plane/local_queue_runtime.py", "LocalQueueRuntimeManager"),
    ("modules/control_plane/odb_result_graphs.py", "OdbResultGraphService"),
    ("modules/control_plane/server.py", "ControlPlaneRuntime"),
    ("modules/submitter/external_job_scan_core.py", "scan_external_jobs"),
])
def test_key_documented_symbols_exist(path, symbol):
    node = ast.parse((ROOT / path).read_text(encoding="utf-8-sig"))
    for part in symbol.split("."):
        node = next((item for item in node.body if isinstance(item, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
                     and item.name == part), None)
        assert node is not None, f"Documented symbol missing: {path}: {symbol}"


def test_continuous_documentation_rule_is_in_agent_and_handoff_entrypoints():
    for path in ("AGENTS.md", "docs/08-handoff/CURRENT_STATUS.md", "docs/05-development/WORKFLOW.md"):
        text = (ROOT / path).read_text(encoding="utf-8")
        assert "每完成一个功能" in text
        assert "文档" in text and "功能索引" in text
    assert "TASK-001" in (ROOT / "docs/08-handoff/TASK_INDEX.md").read_text(encoding="utf-8")
