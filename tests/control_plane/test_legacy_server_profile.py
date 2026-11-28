from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest

from modules.common.json_io import json_file_lock
from modules.control_plane.contracts import ApiProblem
from modules.control_plane.events import EventStore
from modules.control_plane.remote_servers import RemoteServerService
from modules.submitter.app_settings import load_app_settings, save_settings_section
from tests.control_plane.test_remote_servers_api import FakeRemoteManager, command, profile_payload


def open_service(root):
    return RemoteServerService(EventStore(), root / "server_profiles.json", FakeRemoteManager())


def old_profile():
    return {
        "profile_name": "old", "host": "127.0.0.1", "username": r"LAB\user",
        "authentication": "SSH 私钥", "private_key_path": "旧密钥路径",
        "host_fingerprint": "SHA256:fixture", "port": 2209,
        "allowed_roots": ["计算", "归档"], "compute_root": "计算", "abaqus_command": "abq2025.bat",
    }


def test_old_profile_edited_and_deleted_in_place(tmp_path):
    config = tmp_path / "config.json"
    old = old_profile()
    save_settings_section("remote_server", old, path=config)
    initial = config.read_bytes()
    service = open_service(tmp_path)
    row, = service.snapshot()["profiles"]
    assert initial == config.read_bytes() and not (tmp_path / "server_profiles.json").exists()
    assert row["username"] == old["username"] and row["privateKeyPath"] == old["private_key_path"]
    assert row["authentication"] == old["authentication"] and row["allowedRoots"] == old["allowed_roots"]
    save_settings_section("workbench", {"setting": "changed after startup"}, path=config)
    service.execute(command("saveProfile", profile={**row, "port": 2210}))
    assert load_app_settings(config) == {
        "workbench": {"setting": "changed after startup"}, "remote_server": {**old, "port": 2210},
    }
    service.execute(command("saveProfile", profile=profile_payload()))
    service.execute(command("deleteProfile", profileName="old"))
    assert open_service(tmp_path).snapshot()["profiles"] == [profile_payload()]
    assert load_app_settings(config)["remote_server"] == {}


def test_existing_native_name_wins_and_delete_does_not_resurrect_old_endpoint(tmp_path):
    native = {**profile_payload(), "profileName": "old", "host": "native.invalid"}
    svc = open_service(tmp_path)
    svc.execute(command("saveProfile", profile=native))
    config = tmp_path / "config.json"
    old = old_profile()
    save_settings_section("remote_server", old, path=config)
    initial = config.read_bytes()
    svc = open_service(tmp_path)
    assert svc.snapshot()["profiles"] == [native]
    svc.execute(command("deleteProfile", profileName="old"))
    assert open_service(tmp_path).snapshot()["profiles"] == [] and config.read_bytes() == initial
    save_settings_section("remote_server", {**old, "profile_name": "renamed"}, path=config)
    renamed, = open_service(tmp_path).snapshot()["profiles"]
    assert renamed["profileName"] == "renamed" and renamed["host"] == old["host"]


@pytest.mark.parametrize("change", ["saveProfile", "deleteProfile", "connect"])
def test_changed_legacy_pin_or_identity_cannot_be_overwritten(tmp_path, change):
    config = tmp_path / "config.json"
    old = old_profile()
    save_settings_section("remote_server", old, path=config)
    svc = open_service(tmp_path)
    original, = svc.snapshot()["profiles"]
    save_settings_section("remote_server", {**old, "host_fingerprint": "SHA256:other"}, path=config)
    before = config.read_bytes()
    with pytest.raises(ApiProblem, match="其他窗口"):
        svc.execute(command(change, profile=original, profileName="old", saveProfile=False))
    assert config.read_bytes() == before
    assert svc._manager.requests == []


def test_concurrent_native_changes_do_not_overwrite_the_other_process(tmp_path):
    svc = open_service(tmp_path)
    peer = open_service(tmp_path)
    svc.execute(command("saveProfile", profile=profile_payload()))
    with pytest.raises(ApiProblem, match="配置已变化"):
        peer.execute(command("saveProfile", profile={**profile_payload(), "port": 23}))
    assert open_service(tmp_path).snapshot()["profiles"] == [profile_payload()]


@pytest.mark.parametrize("old,warning", [
    ({}, False), ({"host": "", "username": "", "profile_name": ""}, False),
    ({"host": "example.invalid", "username": ""}, True),
    ({**old_profile(), "allowed_roots": "unexpected"}, True),
])
def test_incomplete_old_config_does_not_block_valid_native_profiles(tmp_path, old, warning):
    config = tmp_path / "config.json"
    save_settings_section("remote_server", old, path=config)
    before = config.read_bytes()
    svc = open_service(tmp_path)
    assert svc.snapshot()["profiles"] == []
    assert bool(svc.snapshot()["profilesError"]) is warning
    svc.execute(command("saveProfile", profile=profile_payload()))
    assert open_service(tmp_path).snapshot()["profiles"] == [profile_payload()]
    assert config.read_bytes() == before


def test_damaged_settings_are_not_overwritten_on_later_edit(tmp_path):
    config = tmp_path / "config.json"
    save_settings_section("remote_server", old_profile(), path=config)
    svc = open_service(tmp_path)
    config.write_bytes(b"broken")
    with pytest.raises(ApiProblem, match="无法读取"):
        svc.execute(command("deleteProfile", profileName="old"))
    assert config.read_bytes() == b"broken"


@pytest.mark.parametrize("damage", ["bad_json", "unreadable"])
def test_unreadable_legacy_file_allows_independent_native_edit_and_delete(tmp_path, damage):
    row = profile_payload()
    open_service(tmp_path).execute(command("saveProfile", profile=row))
    config = tmp_path / "config.json"
    if damage == "bad_json":
        config.write_bytes(b"invalid")
    else:
        config.mkdir()
    svc = open_service(tmp_path)
    assert svc.snapshot()["profiles"] == [row] and svc.snapshot()["profilesError"]
    edited = {**row, "port": 2222}
    svc.execute(command("saveProfile", profile=edited))
    svc = open_service(tmp_path)
    assert svc.snapshot()["profiles"] == [edited]
    svc.execute(command("deleteProfile", profileName=row["profileName"]))
    assert open_service(tmp_path).snapshot()["profiles"] == []
    assert config.is_dir() if damage == "unreadable" else config.read_bytes() == b"invalid"


def test_blocked_settings_writer_does_not_block_other_files(tmp_path):
    config = tmp_path / "config.json"
    started = Event()
    saved = Event()

    def competing_save():
        started.set()
        save_settings_section("other", {"marker": 1}, path=config)
        saved.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        with json_file_lock(config):
            waiting = pool.submit(competing_save)
            assert started.wait(2)
            immediate = pool.submit(save_settings_section, "separate", {"marker": 2},
                                    path=tmp_path / "another.json")
            immediate.result(timeout=3)
            assert not saved.is_set()
        waiting.result(timeout=5)
    assert saved.is_set()
    assert load_app_settings(config) == {"other": {"marker": 1}}


def test_explicit_native_store_named_config_cannot_overwrite_other_settings(tmp_path):
    path = tmp_path / "config.json"
    svc = RemoteServerService(EventStore(), path, FakeRemoteManager())
    svc.execute(command("saveProfile", profile=profile_payload()))
    assert RemoteServerService(EventStore(), path).snapshot()["profiles"] == [profile_payload()]
    path.write_bytes(b'{"workbench": {"marker": 1}}')
    original = path.read_bytes()
    svc = RemoteServerService(EventStore(), path)
    with pytest.raises(ApiProblem, match="拒绝覆盖"):
        svc.execute(command("saveProfile", profile=profile_payload()))
    assert path.read_bytes() == original
