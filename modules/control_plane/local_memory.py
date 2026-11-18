"""Qt-free memory learning and explicit provenance for native scheduling."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import time
from pathlib import Path

from modules.submitter.memory_monitor import (
    JobMemoryEstimate,
    JobMemoryUsage,
    MemoryMonitorService,
)
from modules.submitter.scheduler_adapter import parse_memory_request_bytes


def _profile_file_signature(value):
    try:
        path = Path(value).resolve()
        info = path.stat()
        if not stat.S_ISREG(info.st_mode):
            return None
        return (os.path.normcase(str(path)), info.st_size, info.st_mtime_ns)
    except OSError:
        return None


def memory_profile_key(item, *, file_cache=None):
    """A conservative history hint, not a claim to fingerprint every INP include."""
    files = []
    for value in (item.source_inp_path or item.inp_path, item.fortran_path, item.oldjob_path):
        if not value:
            continue
        if file_cache is None:
            signature = _profile_file_signature(value)
        else:
            if value not in file_cache:
                file_cache[value] = _profile_file_signature(value)
            signature = file_cache[value]
        if signature is None:
            return ""
        files.append(signature)
    if not files:
        return ""
    data = (files, item.cores, item.abaqus_command, item.run_mode, item.datacheck_only)
    # Preserve old/default history keys; explicit overrides have separate profiles.
    if item.gpu_count is not None or item.explicit_precision != "default" or item.output_precision != "default":
        data += (item.gpu_count, item.explicit_precision, item.output_precision)
    return hashlib.sha256(json.dumps(data, ensure_ascii=False).encode("utf-8")).hexdigest()


class LocalMemoryMonitor:
    def __init__(self, repository):
        self.repository = repository
        self.service = MemoryMonitorService()
        self.profiles = {}
        self.attempt_profiles = {}
        self.last_samples = {}
        self.live_estimates = {}
        self.session_reference_bytes = 0
        self.dirty = {}
        self.notice = ""
        for key, raw in repository.load_memory_profiles().items():
            try:
                profile = json.loads(raw)
                if not isinstance(profile, dict) or any(type(profile.get(field)) is not int or profile[field] < 0
                    for field in ("peak", "estimated", "samples")) or profile["estimated"] < profile["peak"]:
                    raise ValueError("Invalid memory profile")
                self.profiles[key] = profile
            except (ValueError, TypeError):
                self.notice = "部分内存历史无法读取，已忽略这些估计并保留原记录。"

    def begin(self, item):
        key = memory_profile_key(item)
        self.attempt_profiles[item.attempt_id] = key
        # An unreadable source can still be monitored, but has no reusable history.
        monitor_key = key or "attempt:" + item.attempt_id
        profile = self.profiles.get(key, {})
        estimate = self.service.job_estimates.setdefault(monitor_key, JobMemoryEstimate(job_name=monitor_key))
        estimate.peak_memory = max(estimate.peak_memory, int(profile.get("peak", 0)))
        estimate.estimated_memory = max(estimate.estimated_memory, int(profile.get("estimated", 0)))
        state = self.service.register_job(job_key=item.attempt_id, job_name=monitor_key, work_dir=item.effective_work_dir)
        self.service.activate_job(item.attempt_id)
        return state

    def apply(self, item, observation, peak):
        item.memory_observed_at = observation.observed_at
        item.memory_observation_status = observation.status
        item.pids = list(observation.pids)
        item.pid_create_times = {str(pid): stamp for pid, stamp in observation.pid_create_times}
        item.effective_work_dir = observation.work_dir or item.effective_work_dir
        item.memory_peak_bytes = max(item.memory_peak_bytes, peak, observation.rss_bytes or 0)
        if observation.rss_bytes is None and not peak:
            # Keep the last value for diagnostics; admission will not deduct it.
            return
        if observation.rss_bytes is not None:
            item.rss_bytes = observation.rss_bytes
        state = self.service.tracking_states.get(item.attempt_id) or self.begin(item)
        now = time.monotonic()
        new_peak = item.memory_peak_bytes > state.memory_peak
        if observation.observed_at <= self.last_samples.get(item.attempt_id, 0):
            return
        if new_peak or now >= state.next_sample_at:
            usage = JobMemoryUsage(state.job_name, rss_bytes=max(item.memory_peak_bytes, observation.rss_bytes or 0),
                                   process_count=len(observation.pids), process_names=observation.process_names,
                                   pids=observation.pids)
            self.service.apply_usage_snapshot(due_job_keys=[item.attempt_id], usage_by_job={item.attempt_id: usage},
                                             step_by_job_key={item.attempt_id: observation.step}, now=now)
            self.last_samples[item.attempt_id] = observation.observed_at
        estimate = self.service.job_estimates[state.job_name]
        item.memory_estimated_bytes = max(estimate.estimated_memory, int(item.memory_peak_bytes * self.service.safety_factor))
        item.memory_sample_count = estimate.sample_count
        item.memory_estimate_source = "observed"
        self.live_estimates[item.attempt_id] = item.memory_estimated_bytes
        self.session_reference_bytes = max(self.session_reference_bytes, item.memory_estimated_bytes)
        key = self.attempt_profiles.get(item.attempt_id, "")
        if key:
            previous = self.profiles.get(key, {})
            profile = {"peak": max(item.memory_peak_bytes, int(previous.get("peak", 0))),
                       "estimated": max(item.memory_estimated_bytes, int(previous.get("estimated", 0))),
                       "samples": max(item.memory_sample_count, int(previous.get("samples", 0)))}
            if profile != previous:
                self.profiles[key] = profile
                self.dirty[key] = profile

    def flush(self):
        for key, profile in list(self.dirty.items()):
            try:
                self.repository.save_memory_profile(key, profile)
            except Exception:  # noqa: BLE001 - advisory history must not stop an owned solver
                self.notice = "内存历史暂未保存，仍使用本次观测；稍后重试保存。"
                return
            self.dirty.pop(key, None)
        if self.notice.startswith("内存历史暂未保存"):
            self.notice = ""

    def finish(self, attempt_id):
        self.service.finalize_job(attempt_id)
        self.live_estimates.pop(attempt_id, None)
        self.flush()

    def project_estimates(self, items):
        """Return job-ID keyed estimates; never accidentally match duplicate names."""
        estimates = {}
        reference = self.session_reference_bytes
        # Only one projection pass shares file metadata. A later pass probes
        # again so changes and temporarily unreadable files invalidate history.
        file_cache = {}
        for item in items:
            profile = self.profiles.get(memory_profile_key(item, file_cache=file_cache), {}) if self.profiles else {}
            learned = max(int(profile.get("estimated", 0)), self.live_estimates.get(item.attempt_id, 0))
            if learned:
                estimates[item.job_id] = learned
                item.memory_estimated_bytes = learned
                item.memory_estimate_source = "observed" if item.attempt_id in self.live_estimates else "history"
            elif not parse_memory_request_bytes(item.memory) and reference:
                estimates[item.job_id] = reference
                item.memory_estimated_bytes = reference
                item.memory_estimate_source = "reference"
            else:
                item.memory_estimated_bytes = 0
                item.memory_estimate_source = ""
        return estimates
