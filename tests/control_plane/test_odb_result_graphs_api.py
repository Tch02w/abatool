from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from modules.control_plane.contracts import ApiProblem
from modules.control_plane.odb_result_graphs import OdbResultGraphService
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
)


def node(
    tmp_path: Path, node_id: str, parent: str = "", *, draft: bool = False
) -> dict:
    odb = tmp_path / f"{node_id}.odb"
    if not draft:
        odb.write_bytes(b"source-odb-fixture")
    return {
        "nodeId": node_id,
        "name": "阶段",
        "parentNodeId": parent,
        "odbPath": "" if draft else str(odb),
        "inpPath": "",
    }


def save(
    service: OdbResultGraphService, nodes: list[dict], output: Path, revision: int = 0
) -> dict:
    return service.command(
        {
            "schemaVersion": 1,
            "action": "save",
            "expectedRevision": revision,
            "nodes": nodes,
            "outputDirectory": str(output),
        }
    )


def plans(service: OdbResultGraphService, *targets: str) -> dict:
    return service.plans({"schemaVersion": 1, "targetNodeIds": list(targets)})


def test_branch_plans_share_prefix_exclude_siblings_and_preserve_sources(
    tmp_path: Path,
) -> None:
    service = OdbResultGraphService(tmp_path / "graph.json")
    nodes = [
        node(tmp_path, "base"),
        node(tmp_path, "common", "base"),
        node(tmp_path, "left", "common"),
        node(tmp_path, "right", "common"),
        node(tmp_path, "empty", draft=True),
    ]
    save(service, nodes, tmp_path)
    before = {p: p.read_bytes() for p in tmp_path.iterdir() if p.is_file()}
    batch = plans(service, "left", "right", "left")
    assert batch["valid"] is True
    assert batch["graphRevision"] == 1
    left, right = batch["plans"]
    assert [item["jobId"] for item in left["ancestry"]] == ["base", "common", "left"]
    assert [item["jobId"] for item in right["ancestry"]] == ["base", "common", "right"]
    assert len(left["steps"]) == len(right["steps"]) == 2
    assert left["steps"][0]["outputOdb"] == right["steps"][0]["outputOdb"]
    assert left["steps"][1]["originalOdb"] == left["steps"][0]["outputOdb"]
    assert left["finalOutputOdb"] != right["finalOutputOdb"]
    assert "left" in Path(left["finalOutputOdb"]).name
    assert all(p.read_bytes() == original for p, original in before.items())
    assert not any(
        Path(step["outputOdb"]).exists()
        for plan in batch["plans"]
        for step in plan["steps"]
    )


@pytest.mark.parametrize("target", ["child", "base", "unknown"])
def test_invalid_ancestor_root_or_missing_target_blocks_entire_batch(
    tmp_path: Path, target: str
) -> None:
    service = OdbResultGraphService(tmp_path / "graph.json")
    save(
        service,
        [
            node(tmp_path, "base", draft=True),
            node(tmp_path, "child", "base"),
            node(tmp_path, "good"),
            node(tmp_path, "goodchild", "good"),
        ],
        tmp_path,
    )
    batch = plans(service, "goodchild", target)
    assert batch["valid"] is False
    assert batch["issues"]
    assert batch["plans"] == []


@pytest.mark.parametrize(
    "source_kind", ["missing", "empty", "wrong-extension", "relative"]
)
def test_unusable_source_is_not_executable(tmp_path: Path, source_kind: str) -> None:
    service = OdbResultGraphService(tmp_path / "graph.json")
    root, child = node(tmp_path, "root"), node(tmp_path, "child", "root")
    odb = Path(child["odbPath"])
    if source_kind == "missing":
        odb.unlink()
    elif source_kind == "empty":
        odb.write_bytes(b"")
    elif source_kind == "wrong-extension":
        child["odbPath"] = str(odb.with_suffix(".inp"))
        Path(child["odbPath"]).write_text("not an odb")
    else:
        child["odbPath"] = "child.odb"
    save(service, [root, child], tmp_path)
    assert plans(service, "child")["plans"] == []


@pytest.mark.parametrize("output", ["", "missing-directory", "relative"])
def test_missing_or_relative_output_directory_blocks_plan(
    tmp_path: Path, output: str
) -> None:
    service = OdbResultGraphService(tmp_path / "graph.json")
    payload = save(
        service, [node(tmp_path, "root"), node(tmp_path, "child", "root")], tmp_path
    )
    service.command(
        {
            "schemaVersion": 1,
            "action": "save",
            "expectedRevision": payload["revision"],
            "nodes": payload["nodes"],
            "outputDirectory": str(tmp_path / output)
            if output == "missing-directory"
            else output,
        }
    )
    assert plans(service, "child")["plans"] == []


def test_inp_metadata_derives_only_existing_sibling_odb_and_retains_drafts(
    tmp_path: Path,
) -> None:
    service = OdbResultGraphService(tmp_path / "graph.json")
    root, child = node(tmp_path, "root"), node(tmp_path, "child", "root")
    child["inpPath"] = str(tmp_path / "child.inp")
    Path(child["inpPath"]).write_text("*HEADING")
    child["odbPath"] = ""
    save(service, [root, child], tmp_path)
    assert plans(service, "child")["plans"][0]["steps"][0]["restartOdb"] == str(
        tmp_path / "child.odb"
    )
    (tmp_path / "child.odb").unlink()
    assert plans(service, "child")["valid"] is False
    assert service.snapshot()["nodes"][1]["odbPath"] == ""


def test_output_names_do_not_overwrite_existing_outputs_or_unrelated_sources(
    tmp_path: Path,
) -> None:
    service = OdbResultGraphService(tmp_path / "graph.json")
    nodes = [
        node(tmp_path, "root"),
        node(tmp_path, "one", "root"),
        node(tmp_path, "two", "root"),
    ]
    first = save(service, nodes, tmp_path)
    initial = plans(service, "one")["plans"][0]["finalOutputOdb"]
    Path(initial).write_bytes(b"unrelated-source")
    unrelated = node(tmp_path, "unrelated", draft=True)
    unrelated["odbPath"] = initial
    save(service, nodes + [unrelated], tmp_path, first["revision"])
    batch = plans(service, "one", "two")
    paths = [plan["finalOutputOdb"] for plan in batch["plans"]]
    assert len(set(paths)) == 2
    assert initial not in paths
    assert Path(initial).read_bytes() == b"unrelated-source"


@pytest.mark.parametrize(
    "mutation",
    [
        "duplicate",
        "case-duplicate",
        "missing-parent",
        "self-cycle",
        "cycle",
        "unsafe-id",
        "not-list",
    ],
)
def test_invalid_forest_save_preserves_previous_document(
    tmp_path: Path, mutation: str
) -> None:
    service = OdbResultGraphService(tmp_path / "graph.json")
    nodes = [node(tmp_path, "root"), node(tmp_path, "child", "root")]
    save(service, nodes, tmp_path)
    before = service.path.read_bytes()
    if mutation == "duplicate":
        nodes.append(dict(nodes[0]))
    elif mutation == "case-duplicate":
        nodes.append({**nodes[0], "nodeId": "ROOT"})
    elif mutation == "missing-parent":
        nodes[1]["parentNodeId"] = "missing"
    elif mutation == "self-cycle":
        nodes[0]["parentNodeId"] = "root"
    elif mutation == "cycle":
        nodes[0]["parentNodeId"] = "child"
    elif mutation == "unsafe-id":
        nodes[1]["nodeId"] = "../bad"
    else:
        nodes = None
    with pytest.raises(ApiProblem) as error:
        save(service, nodes, tmp_path, 1)
    assert error.value.status == 400
    assert service.path.read_bytes() == before


def test_persistence_revision_conflict_and_corrupt_file_are_lossless(
    tmp_path: Path,
) -> None:
    service = OdbResultGraphService(tmp_path / "graph.json")
    assert service.snapshot()["revision"] == 0
    assert not service.path.exists()
    snapshot = save(service, [node(tmp_path, "draft", draft=True)], tmp_path)
    restored = OdbResultGraphService(service.path)
    assert restored.snapshot() == snapshot
    with pytest.raises(ApiProblem) as error:
        save(restored, [], tmp_path, 0)
    assert error.value.status == 409
    assert restored.snapshot() == snapshot
    service.path.write_text("broken JSON")
    with pytest.raises(ApiProblem):
        save(service, [], tmp_path, 1)
    assert service.path.read_text() == "broken JSON"


def test_simultaneous_stale_saves_allow_exactly_one_revision(tmp_path: Path) -> None:
    path = tmp_path / "graph.json"
    services = [OdbResultGraphService(path), OdbResultGraphService(path)]

    def attempt(service: OdbResultGraphService) -> int:
        try:
            save(service, [], tmp_path)
            return 200
        except ApiProblem as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(attempt, services)) == [200, 409]
    assert services[0].snapshot()["revision"] == 1


def test_http_endpoints_require_auth_persist_and_never_mutate_job_queue(
    tmp_path: Path,
) -> None:
    graph_path = tmp_path / "state" / "result_graph.json"
    queue_path = tmp_path / "joblist.json"
    queue_path.write_text(json.dumps({"candidates": [], "queue_items": []}))
    queue_before = queue_path.read_bytes()
    with running_control_plane(
        tmp_path, odb_result_graph_path=graph_path, joblist_path=queue_path
    ) as runtime:
        for endpoint, method in [
            ("odb-result-graph", "GET"),
            ("odb-result-graph-commands", "POST"),
            ("odb-result-graph-plans", "POST"),
        ]:
            assert (
                api_request(
                    runtime,
                    "/api/v1/" + endpoint,
                    method=method,
                    payload={} if method == "POST" else None,
                    token=None,
                )[0]
                == 401
            )
        assert (
            "odb.resultGraph"
            in json_response(api_request(runtime, "/healthz"))["capabilities"]
        )
        assert (
            json_response(api_request(runtime, "/api/v1/odb-result-graph"))["revision"]
            == 0
        )
        response = api_request(
            runtime,
            "/api/v1/odb-result-graph-commands",
            method="POST",
            payload={
                "schemaVersion": 1,
                "action": "save",
                "expectedRevision": 0,
                "outputDirectory": str(tmp_path),
                "nodes": [node(tmp_path, "base"), node(tmp_path, "child", "base")],
            },
        )
        assert response[0] == 200
        assert json_response(response)["revision"] == 1
        response = api_request(
            runtime,
            "/api/v1/odb-result-graph-plans",
            method="POST",
            payload={"schemaVersion": 1, "targetNodeIds": ["child"]},
        )
        assert response[0] == 200
        assert json_response(response)["valid"] is True
    assert queue_path.read_bytes() == queue_before
    assert OdbResultGraphService(graph_path).snapshot()["revision"] == 1
