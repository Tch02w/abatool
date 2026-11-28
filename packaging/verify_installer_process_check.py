"""Exercise the Inno installer's process-location checks without installing an application."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
from uuid import uuid4


PROBE = r"""
procedure Check(Condition: Boolean; Description: String);
begin
  if not Condition then RaiseException(Description);
  if not SaveStringToFile(ExpandConstant('{param:receipt}'), Description + #13#10, True) then
    RaiseException('Could not write receipt');
end;

function InitializeSetup: Boolean;
var
  Locator, Services, ProcessClass, EmptyRow: Variant;
  Own, Other, Gone: LongWord;
  Root, Message: String;
begin
  Own := StrToInt(ExpandConstant('{param:own}'));
  Other := StrToInt(ExpandConstant('{param:other}'));
  Gone := StrToInt(ExpandConstant('{param:gone}'));
  Root := Lowercase(AddBackslash(ExpandConstant('{param:root}')));
  Locator := CreateOleObject('WbemScripting.SWbemLocator');
  Services := Locator.ConnectServer('', 'root\CIMV2');
  Message := ProcessLocationError(Services, Own, '', Root);
  Check(Pos('此目录', Message) > 0, 'live process inside target blocked after recheck');
  Check(ProcessLocationError(Services, Other, '', Root) = '', 'live process outside target allowed after recheck');
  Check(ProcessLocationError(Services, Gone, '', Root) = '', 'exited process allowed after recheck');
  ProcessClass := Services.Get('Win32_Process');
  EmptyRow := ProcessClass.SpawnInstance_();
  Message := LiveProcessError(Own, ProcessPath(EmptyRow), Root);
  Check(Pos(IntToStr(Own), Message) > 0, 'persistent unknown location blocked with PID');
  Result := False;
end;
"""


def verify(compiler: Path, work: Path) -> Path:
    case = work.resolve() / f"installer-process-check-{uuid4().hex[:10]}"
    case.mkdir(parents=True)
    temporary = case / "temp"
    temporary.mkdir()
    env = dict(os.environ, TEMP=str(temporary), TMP=str(temporary), TMPDIR=str(temporary))
    template = Path(__file__).with_name("installer.iss.in").read_text(encoding="utf-8")
    settings = (
        "[Setup]\nAppName=Process check\nAppVersion=1\nDefaultDirName={tmp}\\ProcessCheck\n"
        "PrivilegesRequired=lowest\nCreateAppDir=no\nUninstallable=no\nOutputDir=.\n"
        "OutputBaseFilename=check\n[Code]\n"
    )
    script = case / "check.iss"
    script.write_text(settings + template.split("[Code]\n", 1)[1] + PROBE, encoding="utf-8-sig")
    with (case / "compile.log").open("w", encoding="utf-8") as log:
        subprocess.run([compiler.resolve(), script], cwd=case, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True, timeout=60)
    processes = []
    names = ("target", "target-other", "finished")
    try:
        for name in names:
            directory = case / name
            directory.mkdir()
            executable = directory / "AbaqusTools.ControlPlane.exe"
            shutil.copy2(Path(os.environ["SystemRoot"]) / "System32/cmd.exe", executable)
            processes.append(subprocess.Popen(
                [executable, "/D", "/Q"], stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, env=env, cwd=directory, creationflags=subprocess.CREATE_NO_WINDOW,
            ))
        own, other, gone = processes
        gone.communicate(b"exit\r\n", timeout=10)
        receipt = case / "checks.txt"
        log_path = case / "setup.log"
        result = subprocess.run(
            [case / "check.exe", "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", f"/LOG={log_path}",
             f"/own={own.pid}", f"/other={other.pid}", f"/gone={gone.pid}", f"/root={case / names[0]}",
             f"/receipt={receipt}"], cwd=case, env=env, timeout=60,
        )
        checks = receipt.read_text(encoding="ascii").splitlines() if receipt.exists() else []
        log_text = log_path.read_text(encoding="utf-8-sig")
        if (result.returncode != 1 or len(checks) != 4 or "InitializeSetup returned False" not in log_text
                or f"进程 {gone.pid} 已不在工作台进程中" not in log_text
                or any(f"重新取得进程 {p.pid} 的路径" not in log_text for p in (own, other))
                or own.poll() is not None or other.poll() is not None):
            raise RuntimeError(f"Process guard verification failed. See {log_path}")
    finally:
        for process in processes:
            if process.poll() is None:
                process.communicate(b"exit\r\n", timeout=10)
    report = case / "verification.json"
    report.write_text(json.dumps(dict(checks=checks, processIds=[p.pid for p in processes],
                                     processExitCodes=[p.returncode for p in processes],
                                     probeExitCode=result.returncode, installed=False),
                                 indent=2), encoding="utf-8")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("compiler", type=Path)
    parser.add_argument("--work", type=Path, default=Path(__file__).resolve().parents[1] / "GPTWork")
    options = parser.parse_args()
    print(verify(options.compiler, options.work))
