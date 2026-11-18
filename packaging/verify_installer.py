"""Exercise test-identity installers only, under a fresh GPTWork directory."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path
from uuid import uuid4

import psutil
from build_installer import APP_ID, ROOT, digest, verified_bundle


def registered(app_id):
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + app_id + "_is1",
                            access=winreg.KEY_READ | winreg.KEY_WOW64_64KEY) as key:
            return winreg.QueryValueEx(key, "InstallLocation")[0]
    except FileNotFoundError:
        return None


def shortcut_path(app_id):
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                        r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders") as key:
        programs = Path(winreg.QueryValueEx(key, "Programs")[0])
    return programs / f"Abaqus Workbench Test {app_id.rsplit('.', 1)[1]}.lnk"


class OwnedProcesses:
    def __init__(self):
        self.known = {}

    def observe(self, process):
        try:
            parent = psutil.Process(process.pid)
            for item in [parent, *parent.children(recursive=True)]:
                self.known[item.pid] = item.create_time()
        except psutil.NoSuchProcess:
            pass

    def live(self):
        result = []
        for pid, created in self.known.items():
            try:
                item = psutil.Process(pid)
                if abs(item.create_time() - created) < .001:
                    result.append(item)
            except psutil.NoSuchProcess:
                pass
        return result

    def stop_owned(self):
        _, unfinished = psutil.wait_procs(self.live(), timeout=10)
        forced = [item.pid for item in unfinished]
        for item in reversed(unfinished):
            try:
                item.terminate()
            except psutil.NoSuchProcess:
                pass
        _, alive = psutil.wait_procs(self.live(), timeout=10)
        return forced, [item.pid for item in alive]


def run(arguments, log_path, owners, *, environment=None, timeout=180):
    with log_path.open("wb") as stream:
        process = subprocess.Popen([str(a) for a in arguments], stdout=stream, stderr=subprocess.STDOUT,
                                   env=environment, creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + timeout
        while process.poll() is None:
            owners.observe(process)
            if time.monotonic() >= deadline:
                raise TimeoutError(f"Owned command exceeded {timeout}s: {log_path}")
            time.sleep(.1)
        return process.returncode


def installed_hashes(target, report, *, require_ui_resources=True):
    payload = target / "versions" / report["payloadId"]
    manifest, entries = verified_bundle(payload, require_ui_resources=require_ui_resources)
    assert manifest["sourceCommit"] == report["bundleSourceCommit"]
    assert entries["release-manifest.json"]["sha256"] == report["bundleManifestSha256"]


def verify(old_report, new_report, host, *, legacy_old=False):
    reports = [json.loads(path.read_text(encoding="utf-8")) for path in (old_report, new_report)]
    old, new = reports
    # Old test installers predate the XAML publishing fix. Only their exact
    # historical inventory may be accepted; new payloads always use the full gate.
    verified_bundle(Path(old["bundle"]), require_ui_resources=not legacy_old)
    verified_bundle(Path(new["bundle"]))
    for report in reports:
        assert report["testOnly"] and report["status"] == "compiled"
        assert report["appId"].startswith(APP_ID + ".Test.")
        assert digest(Path(report["installer"])) == report["sha256"]
    assert old["appId"] == new["appId"] and old["payloadId"] != new["payloadId"]
    assert registered(new["appId"]) is None, "Test identity is already installed; do not overwrite it"
    shortcut = shortcut_path(new["appId"])
    assert not shortcut.exists(), "Test shortcut already exists; do not overwrite it"
    work = ROOT / "GPTWork" / f"installer-lifecycle-{uuid4().hex[:12]}"
    work.mkdir()
    target = work / "中文 安装目录"
    foreign = work / "foreign"
    foreign.mkdir()
    (foreign / "keep.txt").write_bytes(b"unrelated directory")
    owners = OwnedProcesses()
    report = {"status": "running", "work": str(work), "target": str(target), "appId": new["appId"],
              "oldInstaller": str(old_report), "newInstaller": str(new_report), "steps": [],
              "solverStarted": False, "nativeWindowOpened": False, "legacyOldInventoryOnly": legacy_old}
    print(f"VERIFICATION_DIRECTORY={work}", flush=True)

    def step(name):
        report["steps"].append(name)
        (work / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(name, flush=True)

    def install(build, path, label):
        return run([build["installer"], "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                    f"/DIR={path}", f"/LOG={work / (label + '.log')}"], work / (label + "-process.log"), owners)

    def check_shortcut(build, label):
        assert shortcut.is_file()
        log = work / (label + "-shortcut.log")
        command = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new(); "
                   "$link=(New-Object -ComObject WScript.Shell).CreateShortcut($env:ABAQUS_TEST_SHORTCUT); "
                   "[Console]::WriteLine($link.TargetPath)")
        assert run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command], log, owners,
                   environment=dict(os.environ, ABAQUS_TEST_SHORTCUT=str(shortcut))) == 0
        assert Path(log.read_text(encoding="utf-8-sig").strip()).resolve() == (
            target / "versions" / build["payloadId"] / "AbaqusTools.WinUI.exe").resolve()

    def uninstall(label):
        # The uninstaller removes registered files. Verify ownership and absolute scope first.
        resolved = target.resolve()
        assert resolved.is_relative_to(work.resolve()) and resolved != work.resolve()
        assert (resolved / ".abatool-installation").read_text() == new["appId"]
        uninstaller = resolved / "unins000.exe"
        assert uninstaller.is_file() and uninstaller.resolve().parent == resolved
        assert Path(registered(new["appId"])).resolve() == resolved
        return run([uninstaller, "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                    f"/LOG={work / (label + '.log')}"], work / (label + "-process.log"), owners)

    try:
        assert install(old, foreign, "foreign-rejected") != 0
        assert (foreign / "keep.txt").read_bytes() == b"unrelated directory"
        assert not (foreign / ".abatool-installation").exists() and registered(new["appId"]) is None
        assert not shortcut.exists()
        step("foreign directory refused without registration")
        junction_target = work / "junction-target"
        junction_target.mkdir()
        link = work / "linked-directory"
        assert run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                    "New-Item -ItemType Junction -Path $env:ABAQUS_TEST_LINK -Target $env:ABAQUS_TEST_TARGET | Out-Null"],
                   work / "junction-create.log", owners,
                   environment=dict(os.environ, ABAQUS_TEST_LINK=str(link), ABAQUS_TEST_TARGET=str(junction_target))) == 0
        assert link.is_junction()
        assert install(old, link / "child", "junction-rejected") != 0
        assert list(junction_target.iterdir()) == [] and registered(new["appId"]) is None
        assert not shortcut.exists()
        step("junction ancestor refused without writing its target")
        assert install(old, target, "install-old") == 0
        assert Path(registered(new["appId"])).resolve() == target.resolve()
        installed_hashes(target, old, require_ui_resources=not legacy_old)
        check_shortcut(old, "old")
        keep = target / "用户保留数据.txt"
        keep.write_bytes(b"user content is not an installer payload")
        step("first installation and every payload digest verified")
        descriptor = work / "runtime" / "control-plane.json"
        environment = dict(os.environ, ABAQUS_SUBMITTER_DATA_DIR=str(work / "data"),
                           ABAQUS_POSTPROCESSOR_DATA_DIR=str(work / "post-data"))
        executable = target / "versions" / old["payloadId"] / "control-plane" / "AbaqusTools.ControlPlane.exe"
        with (work / "backend.log").open("wb") as stream:
            backend = subprocess.Popen([str(executable), "--descriptor", str(descriptor)], env=environment,
                                       stdout=stream, stderr=subprocess.STDOUT, creationflags=subprocess.CREATE_NO_WINDOW)
            deadline = time.monotonic() + 30
            while not descriptor.exists():
                owners.observe(backend)
                assert backend.poll() is None and time.monotonic() < deadline
                time.sleep(.1)
            owners.observe(backend)
            assert install(new, target, "upgrade-busy") != 0
            assert uninstall("uninstall-busy") != 0
            assert backend.poll() is None and keep.read_bytes() == b"user content is not an installer payload"
            installed_hashes(target, old, require_ui_resources=not legacy_old)
            assert not (target / "versions" / new["payloadId"]).exists()
            step("live owned backend blocks upgrade and uninstall without termination")
            assert run([host, "--close-api", descriptor, "idle"], work / "backend-close.log", owners) == 0
            assert backend.wait(timeout=20) == 0
        assert install(new, target, "upgrade-new") == 0
        installed_hashes(target, old, require_ui_resources=not legacy_old)
        installed_hashes(target, new)
        check_shortcut(new, "new")
        assert keep.read_bytes() == b"user content is not an installer payload"
        step("upgrade verifies new payload and preserves previous version and user file")
        payload = target / "versions" / new["payloadId"]
        assert run([host, "--launch-bundle", payload, work / "installed-host"], work / "installed-host.log", owners) == 0
        step("installed production host startup APIs and shutdown passed")
        assert uninstall("uninstall-final") == 0
        assert registered(new["appId"]) is None
        assert not shortcut.exists()
        assert keep.read_bytes() == b"user content is not an installer payload"
        assert not (target / "versions").exists()
        step("uninstall removes registered versions and registration while retaining user file")
        verified_bundle(Path(old["bundle"]), require_ui_resources=not legacy_old)
        verified_bundle(Path(new["bundle"]))
        report["status"] = "verified"
    except Exception as error:
        report.update(status="failed", error=f"{type(error).__name__}: {error}")
        raise
    finally:
        report["forcedCleanupPids"], report["remainingOwnedPids"] = owners.stop_owned()
        if report["status"] == "verified" and (report["forcedCleanupPids"] or report["remainingOwnedPids"]):
            report.update(status="failed", error="Successful workflow left live owned processes")
        report["ownedPids"] = list(owners.known)
        report["registrationRemaining"] = registered(new["appId"])
        (work / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    assert report["status"] == "verified" and report["registrationRemaining"] is None
    print(json.dumps(report), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("old_report", type=Path)
    parser.add_argument("new_report", type=Path)
    parser.add_argument("host", type=Path)
    parser.add_argument("--legacy-old", action="store_true",
                        help="Verify historical old test payload inventory without claiming complete UI resources; new payload stays strict")
    args = parser.parse_args()
    verify(args.old_report, args.new_report, args.host.resolve(), legacy_old=args.legacy_old)
