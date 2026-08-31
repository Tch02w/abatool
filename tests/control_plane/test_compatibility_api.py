from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from modules.control_plane.compatibility import (
    ABAQUS_COMMAND_ENV,
    ABAQUS_RELEASE_ENV,
    AbaqusCompatibilitySettings,
    load_compatibility_settings,
)
from modules.control_plane.contracts import MAX_COMPATIBILITY_PATHS
from modules.postprocessor.process_runner import ProcessCancelled, ProcessController
from tests.control_plane.test_api import (
    api_request,
    json_response,
    running_control_plane,
    sse_data,
)


def compatibility_payload(
    root: Path,
    paths: list[Path | str],
    *,
    client_request_id: str = "request-1",
    force_rescan: bool = False,
) -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "clientRequestId": client_request_id,
        "root": str(root),
        "paths": [str(path) for path in paths],
        "forceRescan": force_rescan,
    }


def wait_for_operation(
    runtime,
    operation_id: str,
    statuses: set[str],
    *,
    timeout: float = 5.0,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_snapshot: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        response = api_request(runtime, f"/api/v1/operations/{operation_id}")
        assert response[0] == 200
        last_snapshot = json_response(response)
        if last_snapshot["status"] in statuses:
            return last_snapshot
        time.sleep(0.01)
    raise AssertionError(
        f"operation did not reach {sorted(statuses)}; last={last_snapshot}"
    )


def fake_settings() -> AbaqusCompatibilitySettings:
    return AbaqusCompatibilitySettings(
        command="fake-abaqus.bat",
        release="2099",
        cache_version="2099|fake-abaqus.bat",
    )


def test_compatibility_operation_reports_progress_results_and_events(
    tmp_path: Path,
) -> None:
    root = tmp_path / "中文 ODB 工程"
    root.mkdir()
    first = root / "case-1.odb"
    second = root / "子目录" / "case-2.odb"
    first.write_bytes(b"first")
    second.parent.mkdir()
    second.write_bytes(b"second")

    runner_started = threading.Event()
    release_runner = threading.Event()
    captured: dict[str, Any] = {}

    def runner(
        abaqus_command,
        paths,
        cache_dir,
        log=None,
        controller=None,
        *,
        force_rescan=False,
        abaqus_version="",
    ):
        selected = tuple(Path(path) for path in paths)
        captured.update(
            command=abaqus_command,
            paths=selected,
            cache_dir=cache_dir,
            controller=controller,
            force_rescan=force_rescan,
            abaqus_version=abaqus_version,
        )
        assert log is not None
        log(f"COMPAT_CACHE_HIT|{selected[0].name}|fingerprint")
        runner_started.set()
        assert release_runner.wait(5)
        log(f"ODB_CHECK|2|2|upgrade_required|{selected[1].name}")
        return {
            "mode": "check",
            "results": [
                {
                    "path": str(selected[0]),
                    "status": "valid",
                    "message": "可读取",
                    "size_bytes": selected[0].stat().st_size,
                    "step_count": 3,
                },
                {
                    "path": str(selected[1]),
                    "status": "upgrade_required",
                    "message": "需要升级",
                    "size_bytes": selected[1].stat().st_size,
                },
            ],
        }

    with running_control_plane(
        tmp_path,
        compatibility_runner=runner,
        compatibility_settings_provider=fake_settings,
    ) as runtime:
        response = api_request(
            runtime,
            "/api/v1/odb-compatibility-checks",
            method="POST",
            payload=compatibility_payload(
                root,
                [first, second],
                force_rescan=True,
            ),
        )
        assert response[0] == 202
        accepted = json_response(response)
        assert accepted["kind"] == "odb.compatibility.check"
        assert accepted["status"] in {"queued", "starting", "running"}
        assert accepted["results"] == []
        assert accepted["error"] is None
        assert runner_started.wait(5)

        running = wait_for_operation(runtime, accepted["operationId"], {"running"})
        assert running["progress"] == {
            "completed": 1,
            "total": 2,
            "currentItem": first.name,
        }
        assert running["request"] == {
            "clientRequestId": "request-1",
            "root": str(root.resolve()),
            "paths": [str(first.resolve()), str(second.resolve())],
            "forceRescan": True,
        }

        active_response = api_request(runtime, "/api/v1/operations?activeOnly=true")
        assert active_response[0] == 200
        active_payload = json_response(active_response)
        assert active_payload["schemaVersion"] == 1
        assert [item["operationId"] for item in active_payload["operations"]] == [
            accepted["operationId"]
        ]
        assert active_payload["eventCursor"] >= running["eventCursor"]

        release_runner.set()
        succeeded = wait_for_operation(
            runtime,
            accepted["operationId"],
            {"succeeded"},
        )
        assert succeeded["attemptId"] == accepted["attemptId"]
        assert succeeded["version"] > accepted["version"]
        assert succeeded["progress"] == {
            "completed": 2,
            "total": 2,
            "currentItem": "",
        }
        assert succeeded["error"] is None
        assert succeeded["results"] == [
            {
                "path": str(first.resolve()),
                "status": "valid",
                "message": "可读取",
                "sizeBytes": 5,
                "stepCount": 3,
            },
            {
                "path": str(second.resolve()),
                "status": "upgrade_required",
                "message": "需要升级",
                "sizeBytes": 6,
                "stepCount": None,
            },
        ]
        assert captured == {
            "command": "fake-abaqus.bat",
            "paths": (first.resolve(), second.resolve()),
            "cache_dir": root.resolve() / "cache",
            "controller": captured["controller"],
            "force_rescan": True,
            "abaqus_version": "2099|fake-abaqus.bat",
        }
        assert isinstance(captured["controller"], ProcessController)

        events_response = api_request(runtime, "/api/v1/events?after=0")
        events = [
            event
            for event in sse_data(events_response[2])
            if event["aggregateId"] == accepted["operationId"]
        ]
        assert [event["kind"] for event in events] == [
            "odb.compatibility.queued",
            "odb.compatibility.starting",
            "odb.compatibility.running",
            "odb.compatibility.progress",
            "odb.compatibility.progress",
            "odb.compatibility.succeeded",
        ]
        assert all(event["attemptId"] == accepted["attemptId"] for event in events)
        assert succeeded["eventCursor"] == events[-1]["sequence"]

        assert json_response(
            api_request(runtime, "/api/v1/operations?activeOnly=true")
        )["operations"] == []
        history = json_response(api_request(runtime, "/api/v1/operations"))
        assert [item["operationId"] for item in history["operations"]] == [
            accepted["operationId"]
        ]

        invalid_filter = api_request(runtime, "/api/v1/operations?activeOnly=1")
        assert invalid_filter[0] == 400
        assert json_response(invalid_filter)["error"]["code"] == "INVALID_ACTIVE_ONLY"


def test_compatibility_operation_preserves_all_six_file_statuses(
    tmp_path: Path,
) -> None:
    root = tmp_path / "six statuses"
    root.mkdir()
    statuses = [
        "valid",
        "upgrade_required",
        "newer_release",
        "invalid",
        "missing",
        "empty",
    ]
    odbs = [root / f"case-{index}.odb" for index in range(len(statuses))]
    for path in odbs:
        path.write_bytes(b"fixture")

    def runner(_command, paths, _cache_dir, _log=None, _controller=None, **_options):
        return {
            "results": [
                {
                    "path": str(path),
                    "status": status,
                    "message": f"message-{status}",
                    "size_bytes": path.stat().st_size,
                    "step_count": 2 if status == "valid" else None,
                }
                for path, status in zip(paths, statuses, strict=True)
            ]
        }

    with running_control_plane(
        tmp_path,
        compatibility_runner=runner,
        compatibility_settings_provider=fake_settings,
    ) as runtime:
        accepted = json_response(
            api_request(
                runtime,
                "/api/v1/odb-compatibility-checks",
                method="POST",
                payload=compatibility_payload(root, odbs),
            )
        )
        succeeded = wait_for_operation(runtime, accepted["operationId"], {"succeeded"})

    assert [item["status"] for item in succeeded["results"]] == statuses
    assert [item["message"] for item in succeeded["results"]] == [
        f"message-{status}" for status in statuses
    ]
    assert succeeded["results"][0]["stepCount"] == 2


def test_compatibility_client_request_id_is_idempotent_and_conflicts(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    odb = root / "model.odb"
    odb.write_bytes(b"odb")
    calls: list[tuple[Path, ...]] = []

    def runner(
        _command,
        paths,
        _cache_dir,
        _log=None,
        _controller=None,
        **_options,
    ):
        selected = tuple(Path(path) for path in paths)
        calls.append(selected)
        return {
            "results": [
                {
                    "path": str(path),
                    "status": "valid",
                    "message": "ok",
                    "size_bytes": path.stat().st_size,
                    "step_count": 1,
                }
                for path in selected
            ]
        }

    with running_control_plane(
        tmp_path,
        compatibility_runner=runner,
        compatibility_settings_provider=fake_settings,
    ) as runtime:
        payload = compatibility_payload(
            root,
            [odb],
            client_request_id="stable-request",
        )
        first = api_request(
            runtime,
            "/api/v1/odb-compatibility-checks",
            method="POST",
            payload=payload,
        )
        second = api_request(
            runtime,
            "/api/v1/odb-compatibility-checks",
            method="POST",
            payload=payload,
        )
        assert first[0] == second[0] == 202
        first_snapshot = json_response(first)
        second_snapshot = json_response(second)
        assert second_snapshot["operationId"] == first_snapshot["operationId"]
        assert second_snapshot["attemptId"] == first_snapshot["attemptId"]
        wait_for_operation(runtime, first_snapshot["operationId"], {"succeeded"})
        assert calls == [(odb.resolve(),)]

        conflict_payload = dict(payload)
        conflict_payload["forceRescan"] = True
        conflict = api_request(
            runtime,
            "/api/v1/odb-compatibility-checks",
            method="POST",
            payload=conflict_payload,
        )
        assert conflict[0] == 409
        problem = json_response(conflict)["error"]
        assert problem["code"] == "IDEMPOTENCY_CONFLICT"
        assert problem["details"]["operationId"] == first_snapshot["operationId"]


def test_compatibility_failure_is_a_terminal_structured_snapshot(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    odb = root / "broken.odb"
    odb.write_bytes(b"odb")

    def runner(*_args, **_kwargs):
        raise RuntimeError("Abaqus worker exited with code 17")

    with running_control_plane(
        tmp_path,
        compatibility_runner=runner,
        compatibility_settings_provider=fake_settings,
    ) as runtime:
        accepted = json_response(
            api_request(
                runtime,
                "/api/v1/odb-compatibility-checks",
                method="POST",
                payload=compatibility_payload(root, [odb]),
            )
        )
        failed = wait_for_operation(runtime, accepted["operationId"], {"failed"})
        assert failed["results"] == []
        assert failed["progress"]["total"] == 1
        assert failed["error"]["code"] == "COMPATIBILITY_CHECK_FAILED"
        assert failed["error"]["retryable"] is True
        assert "code 17" in failed["error"]["message"]


def test_compatibility_cancel_calls_process_controller_and_is_idempotent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    root = tmp_path / "root"
    root.mkdir()
    odb = root / "long-running.odb"
    odb.write_bytes(b"odb")
    runner_started = threading.Event()
    terminated = threading.Event()

    class DummyProcess:
        @staticmethod
        def poll():
            return None

    monkeypatch.setattr(
        ProcessController,
        "_terminate_tree",
        staticmethod(lambda _process: terminated.set()),
    )

    def runner(
        _command,
        _paths,
        _cache_dir,
        _log=None,
        controller=None,
        **_options,
    ):
        assert controller is not None
        process = DummyProcess()
        controller.attach(process)
        runner_started.set()
        deadline = time.monotonic() + 5
        while not controller.cancel_requested and time.monotonic() < deadline:
            time.sleep(0.005)
        controller.detach(process)
        if controller.cancel_requested:
            raise ProcessCancelled("cancelled by test")
        raise AssertionError("cancel was not delivered to ProcessController")

    with running_control_plane(
        tmp_path,
        compatibility_runner=runner,
        compatibility_settings_provider=fake_settings,
    ) as runtime:
        accepted = json_response(
            api_request(
                runtime,
                "/api/v1/odb-compatibility-checks",
                method="POST",
                payload=compatibility_payload(root, [odb]),
            )
        )
        assert runner_started.wait(5)
        cancelled_response = api_request(
            runtime,
            f"/api/v1/operations/{accepted['operationId']}/cancel",
            method="POST",
        )
        assert cancelled_response[0] == 202
        assert json_response(cancelled_response)["status"] in {
            "cancelling",
            "cancelled",
        }
        assert terminated.wait(5)
        cancelled = wait_for_operation(
            runtime,
            accepted["operationId"],
            {"cancelled"},
        )
        assert cancelled["results"] == []
        assert cancelled["error"] is None

        repeated = api_request(
            runtime,
            f"/api/v1/operations/{accepted['operationId']}/cancel",
            method="POST",
        )
        assert repeated[0] == 202
        repeated_snapshot = json_response(repeated)
        assert repeated_snapshot["status"] == "cancelled"
        assert repeated_snapshot["version"] == cancelled["version"]

        events = sse_data(api_request(runtime, "/api/v1/events?after=0")[2])
        operation_kinds = [
            event["kind"]
            for event in events
            if event["aggregateId"] == accepted["operationId"]
        ]
        assert "odb.compatibility.cancelling" in operation_kinds
        assert operation_kinds[-1] == "odb.compatibility.cancelled"
        assert "odb.compatibility.succeeded" not in operation_kinds


def test_compatibility_rejects_unsafe_or_invalid_paths(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "outside.odb"
    outside.write_bytes(b"outside")
    wrong_extension = root / "model.inp"
    wrong_extension.write_bytes(b"inp")
    calls = 0

    def runner(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return {"results": []}

    cases = [
        (
            compatibility_payload(
                root,
                [outside],
                client_request_id="outside",
            ),
            "PATH_OUTSIDE_ROOT",
        ),
        (
            compatibility_payload(
                root,
                [wrong_extension],
                client_request_id="extension",
            ),
            "INVALID_ODB_EXTENSION",
        ),
        (
            compatibility_payload(
                root,
                ["duplicate.odb", "duplicate.odb"],
                client_request_id="duplicate",
            ),
            "DUPLICATE_ODB_PATH",
        ),
        (
            compatibility_payload(
                root,
                [f"model-{index}.odb" for index in range(MAX_COMPATIBILITY_PATHS + 1)],
                client_request_id="too-many",
            ),
            "TOO_MANY_PATHS",
        ),
    ]

    with running_control_plane(
        tmp_path,
        compatibility_runner=runner,
        compatibility_settings_provider=fake_settings,
    ) as runtime:
        for payload, expected_code in cases:
            response = api_request(
                runtime,
                "/api/v1/odb-compatibility-checks",
                method="POST",
                payload=payload,
            )
            assert response[0] == 400
            assert json_response(response)["error"]["code"] == expected_code

        unknown_get = api_request(runtime, "/api/v1/operations/not-found")
        unknown_cancel = api_request(
            runtime,
            "/api/v1/operations/not-found/cancel",
            method="POST",
        )
        assert unknown_get[0] == unknown_cancel[0] == 404
        assert json_response(unknown_get)["error"]["code"] == "OPERATION_NOT_FOUND"
        assert json_response(unknown_cancel)["error"]["code"] == "OPERATION_NOT_FOUND"
        assert calls == 0


def test_compatibility_settings_honor_environment_overrides(monkeypatch) -> None:
    command = r"C:\SIMULIA Test\Commands\abaqus.bat"
    monkeypatch.setenv(ABAQUS_COMMAND_ENV, command)
    monkeypatch.setenv(ABAQUS_RELEASE_ENV, "2099HF1")

    settings = load_compatibility_settings()

    assert settings.command == command
    assert settings.release == "2099HF1"
    assert settings.cache_version == f"2099HF1|{os.path.normcase(command)}"
