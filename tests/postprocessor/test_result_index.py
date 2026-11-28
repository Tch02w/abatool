from __future__ import annotations

import json
import os
import shutil
import socket
import sqlite3
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from modules.postprocessor.result_browser import (
    classify_result,
    result_section,
)
from modules.postprocessor.result_index import (
    INDEX_FILENAME,
    INDEX_SCHEMA_VERSION,
    ResultIndexCancelled,
    ResultIndexInvalid,
    ResultIndexLocked,
    build_result_index,
    index_path,
    load_result_index,
    lock_path,
    read_result_index,
    update_result_index_scopes,
)


@pytest.mark.skipif(os.name != "nt", reason="Windows writer ownership and legacy marker sharing")
def test_live_writer_keeps_previous_index_readable_and_excludes_a_second_writer(tmp_path, monkeypatch):
    batch = make_time_directory(tmp_path)
    build_result_index(batch, classify_result, result_section)
    original = index_path(batch).read_bytes()
    (batch / "added.txt").write_text("new", encoding="utf-8")
    entered = threading.Event()
    release = threading.Event()

    def hold_writer(path):
        entered.set()
        assert release.wait(20)
        return classify_result(path)

    def no_signal(*_):
        pytest.fail("Checking result-index ownership must not send process signals")

    monkeypatch.setattr(os, "kill", no_signal)
    with ThreadPoolExecutor(max_workers=1) as pool:
        active = pool.submit(build_result_index, batch, hold_writer, result_section)
        try:
            assert entered.wait(15)
            with pytest.raises(ResultIndexLocked):
                update_result_index_scopes(batch, [batch], classify_result, result_section)
            with pytest.raises(PermissionError):
                lock_path(batch).read_text(encoding="utf-8")  # Legacy marker reader.
            assert index_path(batch).read_bytes() == original
            assert "added.txt" not in {row["name"] for row in load_result_index(batch).records}
        finally:
            release.set()
        active.result(timeout=15)
    assert "added.txt" in {row["name"] for row in load_result_index(batch).records}
    assert not lock_path(batch).exists()


@pytest.mark.parametrize("owner", ["live", "exited", "foreign", "malformed", "invalid_pid"])
def test_respects_migration_era_index_owner(tmp_path, monkeypatch, owner):
    import psutil

    batch = make_time_directory(tmp_path)
    marker = lock_path(batch)
    saved = {"host": socket.gethostname(), "pid": os.getpid(), "token": "legacy"}
    if owner == "foreign":
        saved["host"] += "-other"
    if owner == "invalid_pid":
        saved["pid"] = 0
    contents = json.dumps(saved) if owner != "malformed" else "[]"
    marker.write_text(contents, encoding="utf-8")
    observed = []

    def pid_exists(pid):
        observed.append(pid)
        return owner != "exited"

    monkeypatch.setattr(psutil, "pid_exists", pid_exists)
    monkeypatch.setattr(os, "kill", lambda *_: pytest.fail("Expected a read-only PID check"))
    if owner == "exited":
        build_result_index(batch, classify_result, result_section)
        assert not marker.exists()
        assert len(load_result_index(batch).records) == 2
    else:
        with pytest.raises(ResultIndexLocked):
            build_result_index(batch, classify_result, result_section)
        assert marker.read_text(encoding="utf-8") == contents
        assert not index_path(batch).exists()
    assert observed == ([os.getpid()] if owner in {"live", "exited"} else [])


@pytest.mark.skipif(os.name != "nt", reason="Windows SQLite readers hold the current filename open")
@pytest.mark.parametrize("outcome", ["publish", "cancel", "timeout"])
def test_index_publication_while_a_validated_reader_is_open(tmp_path, monkeypatch, outcome):
    from modules.postprocessor import result_index

    batch = make_time_directory(tmp_path)
    build_result_index(batch, classify_result, result_section)
    target = index_path(batch)
    original = target.read_bytes()
    (batch / "new.txt").write_text("new", encoding="utf-8")
    replacing = threading.Event()
    cancellation = threading.Event()
    replace = os.replace

    def observe_replace(source, destination):
        if destination == target:
            replacing.set()
        replace(source, destination)

    monkeypatch.setattr(os, "replace", observe_replace)
    if outcome == "timeout":
        monkeypatch.setattr(result_index, "_INDEX_PUBLISH_WAIT_SECONDS", 0.2)
    with ThreadPoolExecutor(max_workers=1) as pool:
        with read_result_index(batch) as (_, count, rows):
            writer = pool.submit(build_result_index, batch, classify_result, result_section, cancellation)
            assert replacing.wait(5)
            if outcome == "cancel":
                cancellation.set()
                with pytest.raises(ResultIndexCancelled):
                    writer.result(timeout=3)
            elif outcome == "timeout":
                with pytest.raises(PermissionError):
                    writer.result(timeout=3)
            else:
                with pytest.raises(TimeoutError):
                    writer.result(timeout=0.4)
            assert len(list(rows)) == count
            assert target.read_bytes() == original
        if outcome == "publish":
            writer.result(timeout=5)
        assert len(load_result_index(batch).records) == count + (outcome == "publish")
    assert not any(p.name.endswith(".lock") or ".tmp-" in p.name for p in batch.iterdir())


def make_time_directory(root: Path, name: str = "20260724_120000") -> Path:
    time_directory = root / "对比组" / name
    first = time_directory / "GJA-1-R_U100D"
    second = time_directory / "GJA-2-R_U100D"
    (first / "data").mkdir(parents=True)
    (second / "plots").mkdir(parents=True)
    (first / "data" / "load_point_raw.csv").write_text(
        "TotalTime,U3\n0,0\n", encoding="utf-8"
    )
    (second / "plots" / "axial_force.png").write_bytes(b"png")
    return time_directory


def test_time_directory_index_is_persistent_and_excludes_itself(
    tmp_path: Path,
) -> None:
    time_directory = make_time_directory(tmp_path)

    metadata = build_result_index(
        time_directory, classify_result, result_section
    )
    loaded = load_result_index(time_directory)

    assert index_path(time_directory) == time_directory / INDEX_FILENAME
    assert index_path(time_directory).is_file()
    assert int(metadata["schema_version"]) == INDEX_SCHEMA_VERSION
    assert metadata["canonical_path"] == str(time_directory.resolve()).lower()
    assert {record["name"] for record in loaded.records} == {
        "load_point_raw.csv",
        "axial_force.png",
    }
    assert all(
        record["name"] != INDEX_FILENAME for record in loaded.records
    )


@pytest.mark.skipif(os.name != "nt", reason="Windows file attributes only")
def test_result_index_stays_hidden_after_incremental_replacement(
    tmp_path: Path,
) -> None:
    time_directory = make_time_directory(tmp_path)
    build_result_index(time_directory, classify_result, result_section)
    database = index_path(time_directory)

    assert database.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN

    update_result_index_scopes(
        time_directory,
        [time_directory / "GJA-1-R_U100D"],
        classify_result,
        result_section,
    )

    assert database.stat().st_file_attributes & stat.FILE_ATTRIBUTE_HIDDEN


def test_copied_index_is_rejected_until_rebuilt(tmp_path: Path) -> None:
    original = make_time_directory(tmp_path / "original")
    build_result_index(original, classify_result, result_section)
    copied = tmp_path / "copied" / original.name
    shutil.copytree(original, copied)

    with pytest.raises(ResultIndexInvalid, match="不匹配"):
        load_result_index(copied)


def test_older_metadata_without_count_uses_the_same_read_only_snapshot(tmp_path: Path) -> None:
    batch = make_time_directory(tmp_path)
    build_result_index(batch, classify_result, result_section)
    with closing(sqlite3.connect(index_path(batch))) as connection:
        connection.execute("DELETE FROM metadata WHERE key = 'record_count'")
        connection.commit()
    before = index_path(batch).read_bytes()
    loaded = load_result_index(batch)
    assert loaded.metadata["record_count"] == str(len(loaded.records)) == "2"
    assert index_path(batch).read_bytes() == before


def test_cancelled_refresh_keeps_the_previous_complete_index(
    tmp_path: Path,
) -> None:
    time_directory = make_time_directory(tmp_path)
    build_result_index(time_directory, classify_result, result_section)
    previous = load_result_index(time_directory)
    (time_directory / "GJA-1-R_U100D" / "new.txt").write_text(
        "new", encoding="utf-8"
    )
    cancellation = threading.Event()
    cancellation.set()

    with pytest.raises(ResultIndexCancelled):
        build_result_index(
            time_directory,
            classify_result,
            result_section,
            cancellation,
        )

    retained = load_result_index(time_directory)
    assert retained.records == previous.records


def test_incremental_update_replaces_only_completed_odb_scope(
    tmp_path: Path,
) -> None:
    time_directory = make_time_directory(tmp_path)
    build_result_index(time_directory, classify_result, result_section)
    first = time_directory / "GJA-1-R_U100D"
    old_file = first / "data" / "load_point_raw.csv"
    old_file.unlink()
    replacement = first / "data" / "timeline_alignment.csv"
    replacement.write_text("Step,Frame\nLoad,1\n", encoding="utf-8")

    update_result_index_scopes(
        time_directory,
        [first],
        classify_result,
        result_section,
    )
    loaded = load_result_index(time_directory)
    names = {record["name"] for record in loaded.records}

    assert "load_point_raw.csv" not in names
    assert "timeline_alignment.csv" in names
    assert "axial_force.png" in names


def test_incremental_scope_treats_underscore_as_a_literal_character(
    tmp_path: Path,
) -> None:
    time_directory = tmp_path / "组A" / "20260724_120000"
    selected = time_directory / "GJA-1-R_U100D"
    similar = time_directory / "GJA-1-RXU100D"
    selected.mkdir(parents=True)
    similar.mkdir(parents=True)
    (selected / "selected.txt").write_text("old", encoding="utf-8")
    (similar / "must-remain.txt").write_text("keep", encoding="utf-8")
    build_result_index(time_directory, classify_result, result_section)

    (selected / "selected.txt").unlink()
    (selected / "replacement.txt").write_text("new", encoding="utf-8")
    update_result_index_scopes(
        time_directory,
        [selected],
        classify_result,
        result_section,
    )

    names = {
        record["name"] for record in load_result_index(time_directory).records
    }
    assert names == {"replacement.txt", "must-remain.txt"}


def test_private_index_commits_schema_and_rows_together(tmp_path, monkeypatch):
    from modules.postprocessor import result_index

    batch = tmp_path / "batch"
    batch.mkdir()
    (batch / "load_point_raw.csv").write_text("time,load\n0,123\n", encoding="utf-8")
    insert_rows = result_index._insert_rows

    def check_transaction(connection, *args, **kwargs):
        assert connection.in_transaction
        assert connection.execute("PRAGMA synchronous").fetchone()[0] == 2  # FULL
        database = Path(connection.execute("PRAGMA database_list").fetchone()[2])
        with closing(sqlite3.connect(database.as_uri() + "?mode=ro", uri=True)) as reader:
            assert not reader.execute("SELECT name FROM sqlite_master").fetchall()
        return insert_rows(connection, *args, **kwargs)

    monkeypatch.setattr(result_index, "_insert_rows", check_transaction)
    build_result_index(batch, classify_result, result_section)
    assert [row["name"] for row in load_result_index(batch).records] == ["load_point_raw.csv"]
