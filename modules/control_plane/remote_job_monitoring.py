"""Evidence-based remote completion; an absent process is not a success signal."""
from __future__ import annotations

from dataclasses import dataclass

from modules.submitter.constants import (
    COMPLETE_MARKERS,
    ERROR_MARKERS,
    TERMINATE_MARKERS,
)

from .compatibility import CANCELLED, FAILED, RUNNING, SUCCEEDED

# DAT/MSG also contain recoverable diagnostics. Require an explicit error or
# fatal summary for these; a later successful analysis must not become failed
# merely because a warning contains one of these phrases.
FATAL_MARKERS = tuple(marker for marker in ERROR_MARKERS if marker not in {
    "NUMERICAL SINGULARITY", "ZERO PIVOT", "EXCESSIVE DISTORTION",
})
JOB_TERMINATION_MARKERS = tuple(marker for marker in TERMINATE_MARKERS if marker not in {
    "TERMINATED", "HAS BEEN STOPPED",
})


@dataclass
class RemoteCompletionState:
    signature: str = ""
    stable_inactive_polls: int = 0
    error_seen: bool = False
    termination_seen: bool = False

    def observe(self, snapshot, *, job_name, datacheck=False, cancelling=False, paused=False):
        text = "\n".join(str(snapshot.get(key) or "") for key in
                         ("sta_tail", "log_tail", "dat_tail", "msg_tail")).upper()
        self.error_seen |= any(marker in text for marker in FATAL_MARKERS)
        self.termination_seen |= any(marker in text for marker in JOB_TERMINATION_MARKERS) or any(
            line.strip() == f"ABAQUS JOB {job_name.upper()} TERMINATED" for line in text.splitlines())
        # A datacheck normally has no successful-analysis STA. Its job-specific
        # completion line is accepted; merely exiting or finishing pre.exe is not.
        complete = any(marker in text for marker in COMPLETE_MARKERS) or any(
            line.strip() == f"ABAQUS JOB {job_name.upper()} COMPLETED" for line in text.splitlines())
        signature = snapshot.get("output_signature")
        readable = (snapshot.get("probe_complete") is True and isinstance(signature, str) and bool(signature)
                    and type(snapshot.get("process_active")) is bool and type(snapshot.get("lock_exists")) is bool)
        if not readable:
            self.signature = ""
            self.stable_inactive_polls = 0
            return RUNNING, "远端状态暂不可读，等待重新核对", None
        active = snapshot["process_active"] or snapshot["lock_exists"]
        if active:
            self.stable_inactive_polls = 0
        else:
            self.stable_inactive_polls = self.stable_inactive_polls + 1 if signature == self.signature else 1
        self.signature = signature
        if active or self.stable_inactive_polls < 3:
            if self.error_seen:
                phase = "检测到远端错误，等待进程退出确认"
            elif cancelling or self.termination_seen:
                phase = "正在确认远端作业已停止"
            elif complete:
                phase = "已收到完成输出，正在确认进程和文件已结束"
            else:
                phase = "已暂停" if paused else "远端 Abaqus 运行中"
            return RUNNING, phase, None
        if self.error_seen:
            return FAILED, "Abaqus 远端输出包含失败标记", "ABAQUS_REMOTE_ERROR"
        if cancelling:
            return CANCELLED, "远端作业已取消", None
        if self.termination_seen:
            return FAILED, "远端作业已终止", "REMOTE_JOB_TERMINATED"
        if complete:
            return SUCCEEDED, "远端数据检查完成" if datacheck else "远端作业完成", None
        if self.stable_inactive_polls >= 5:
            return FAILED, "远端进程结束，未发现成功标记", "REMOTE_JOB_EXIT_UNCONFIRMED"
        return RUNNING, "远端进程已结束，等待完成证据", None


def new_tail_lines(previous: str, current: str) -> list[str]:
    """Append only the suffix after the largest overlap of two bounded tails."""
    before = [line.strip() for line in previous.splitlines() if line.strip()]
    after = [line.strip() for line in current.splitlines() if line.strip()]
    if before == after:
        return []
    for count in range(min(len(before), len(after)), 0, -1):
        if before[-count:] == after[:count]:
            return after[count:]
    return after
