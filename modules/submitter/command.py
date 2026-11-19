"""Command building helpers shared by the Qt frontend."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path

from .constants import DEFAULT_CPUS, JOB_NAME_MAX_LENGTH, JOB_NAME_FORBIDDEN_CHARACTERS, MAX_CPUS, STATUS_STARTING
from .execution_options import execution_arguments, validate_execution_options
from .models import QueueItem

MEMORY_OPTIONS = ("%", "GB", "MB")


@dataclass(frozen=True)
class SubmitOptions:
    inp_file: str = ""
    job_name: str = ""
    cpus: int = DEFAULT_CPUS
    oldjob_path: str = ""
    oldjob_arg: str = ""
    for_file: str = ""
    interactive: bool = False
    datacheck: bool = False
    memory_value: str = ""
    memory_unit: str = "%"
    abaqus_command: str = "abaqus"
    ask_delete_off: bool = False
    gpu_count: int | None = None
    explicit_precision: str = "default"
    output_precision: str = "default"


def derive_job_name(inp_file: str) -> str:
    """Return the default Abaqus job name for an INP file."""
    if not inp_file:
        return ""
    return Path(inp_file).stem


def derive_oldjob_name(oldjob_path: str) -> str:
    """Return the oldjob argument from an ODB path or raw name."""
    if not oldjob_path:
        return ""
    value = oldjob_path.strip()
    path = Path(value)
    if path.suffix.lower() == ".odb":
        return path.stem
    if path.is_absolute() or str(path.parent) not in {"", "."}:
        return path.name
    return value


def inp_has_restart_keyword(inp_file: str) -> bool:
    """Return whether the INP header contains a Restart keyword."""
    if not inp_file:
        return False
    try:
        with open(inp_file, "r", encoding="gbk", errors="ignore") as stream:
            head = stream.read(32768)
    except OSError:
        return False
    return "*restart" in head.lower()


def validate_job_name(job_name: str) -> tuple[bool, str]:
    """Validate an Abaqus job name."""
    if not job_name:
        return False, "作业名称不能为空。"
    if len(job_name) > JOB_NAME_MAX_LENGTH:
        return False, "Abaqus 作业名称最多允许 80 个字符。"
    if job_name.casefold() == "assembly":
        return False, "Assembly 是 Abaqus/CAE 保留名称，不能用作作业名。"
    if job_name.startswith(("-", "_")) or job_name.endswith("_"):
        return False, "Abaqus 作业名称不能以短横线或下划线开头，也不能以下划线结尾。"
    invalid = next((char for char in job_name if char in JOB_NAME_FORBIDDEN_CHARACTERS
                    or char.isspace() or ord(char) < 32 or ord(char) == 127), None)
    if invalid is not None:
        label = repr(invalid) if invalid.isspace() or ord(invalid) < 32 or ord(invalid) == 127 else invalid
        return False, f"Abaqus 作业名称包含不允许的字符：{label}。"
    return True, ""


def validate_cpus(cpus_text: str) -> tuple[bool, int, str]:
    """Validate the CPU field and return the parsed value."""
    try:
        cpus = int(cpus_text.strip())
    except ValueError:
        return False, 0, "Core 必须是整数。"
    if cpus < 0 or cpus > MAX_CPUS:
        return False, cpus, f"Core 必须在 0 到 {MAX_CPUS} 之间。"
    return True, cpus, ""


def memory_argument(memory_value: str, memory_unit: str) -> str:
    """Build the Abaqus memory argument."""
    unit = (memory_unit or "%").strip()
    value = (memory_value or "").strip()
    if not value:
        return ""
    if unit == "%":
        return f"{value}%"
    return f"{value}{unit.lower()}"


def validate_memory_argument(argument: str) -> tuple[bool, str]:
    """Validate an Abaqus memory argument."""
    if not argument:
        return True, ""
    if re.fullmatch(r"\d+%", argument):
        return True, ""
    if re.fullmatch(r"\d+(\.\d+)?\s*(mb|gb|MB|GB)", argument):
        return True, ""
    return False, "Mem 支持整数百分比，或 MB/GB 数值，例如 80%、4096MB、8GB。"


def build_abaqus_command(options: SubmitOptions) -> str:
    """Build the Abaqus command line from UI options."""
    abaqus_command = (options.abaqus_command or "abaqus").strip()
    if re.search(r"\s", abaqus_command) and not (
        abaqus_command.startswith('"') and abaqus_command.endswith('"')
    ):
        abaqus_command = f'"{abaqus_command}"'
    parts = [f"{abaqus_command} job={quote_job_argument(options.job_name)}"]

    if options.datacheck and options.inp_file:
        input_name = os.path.basename(options.inp_file)
        if re.search(r"[\s&()^]", input_name):
            input_name = f'"{input_name}"'
        parts.append(f"input={input_name}")

    oldjob_argument = (options.oldjob_arg or "").strip() or derive_oldjob_name(options.oldjob_path)
    if oldjob_argument:
        oldjob_argument = quote_job_argument(oldjob_argument)
        parts.append(f"oldjob={oldjob_argument}")

    if options.for_file:
        parts.append(f'user="{options.for_file}"')

    if options.cpus != 0:
        parts.append(f"cpus={options.cpus}")

    memory = memory_argument(options.memory_value, options.memory_unit)
    if memory:
        parts.append(f"memory={memory}")

    parts.extend(execution_arguments(options))

    if options.ask_delete_off:
        parts.append("ask_delete=OFF")

    if options.datacheck:
        parts.append("datacheck")

    if options.interactive:
        parts.append("interactive")

    return " ".join(parts)


def quote_job_argument(value: str) -> str:
    """Preserve shell-sensitive characters allowed by Abaqus, e.g. caret."""
    return f'"{value}"' if re.search(r"[\s^]", value) else value


def literal_windows_command(command: str) -> tuple[str, dict[str, str]]:
    """Expand literal percent signs once, without expanding names like %PATH%."""
    environment = dict(os.environ)
    if os.name == "nt" and "%" in command:
        environment["ABAQUS_TOOLS_LITERAL_PERCENT"] = "%"
        command = command.replace("%", "%ABAQUS_TOOLS_LITERAL_PERCENT%")
    return command, environment


def validate_options(options: SubmitOptions) -> tuple[bool, str]:
    """Validate a submit request."""
    try:
        validate_execution_options(options)
    except ValueError as exc:
        return False, str(exc)
    if not options.inp_file:
        return False, "请先选择 INP 文件。"
    if not Path(options.inp_file).exists():
        return False, "INP 文件不存在。"

    ok, message = validate_job_name(options.job_name)
    if not ok:
        return False, f"作业名不合法：{options.job_name or '空'}（{message}）"

    oldjob_name = derive_oldjob_name(options.oldjob_path)
    if oldjob_name:
        ok, message = validate_job_name(oldjob_name)
        if not ok:
            return False, f"Restart 依赖作业名不合法：{oldjob_name}（{message}）"
        if oldjob_name == options.job_name:
            return False, "当前作业名称不能与 oldjob 名称相同。"

    memory = memory_argument(options.memory_value, options.memory_unit)
    ok, message = validate_memory_argument(memory)
    if not ok:
        return False, message

    return True, ""


def parse_memory_text(memory: str) -> tuple[str, str]:
    value = (memory or "").strip()
    if not value:
        return "", "%"
    lower = value.lower()
    if lower.endswith("gb"):
        return value[:-2].strip(), "GB"
    if lower.endswith("mb"):
        return value[:-2].strip(), "MB"
    if lower.endswith("%"):
        return value[:-1].strip(), "%"
    return value, "%"


def queue_item_to_options(
    item: QueueItem,
    *,
    default_cpus: int,
) -> SubmitOptions:
    memory_value, memory_unit = parse_memory_text(item.memory)
    return SubmitOptions(
        inp_file=item.inp_path,
        job_name=item.job_name or derive_job_name(item.inp_path),
        cpus=int(item.cores or 0),
        gpu_count=item.gpu_count,
        explicit_precision=item.explicit_precision,
        output_precision=item.output_precision,
        oldjob_path=item.oldjob_path,
        for_file=item.fortran_path,
        interactive=item.interactive,
        datacheck=item.datacheck_only,
        memory_value=memory_value,
        memory_unit=memory_unit,
        abaqus_command=item.abaqus_command or "abaqus",
    )


def build_direct_submit_queue_item(
    options: SubmitOptions,
    *,
    notify: bool,
) -> QueueItem:
    memory = ""

    if options.memory_value:
        memory = f"{options.memory_value}{'%' if options.memory_unit == '%' else options.memory_unit.lower()}"

    return QueueItem(
        inp_path=options.inp_file,
        source_inp_path=options.inp_file,
        job_name=options.job_name,
        source="direct_submit",
        status=STATUS_STARTING,
        selected=False,
        valid=True,
        message="正在提交",
        run_mode=("restart" if options.oldjob_path else "normal"),
        oldjob_name=derive_oldjob_name(options.oldjob_path),
        oldjob_path=options.oldjob_path,
        fortran_path=options.for_file,
        cores=options.cpus,
        gpu_count=options.gpu_count,
        explicit_precision=options.explicit_precision,
        output_precision=options.output_precision,
        memory=memory,
        interactive=options.interactive,
        datacheck_only=options.datacheck,
        complete_notify=notify,
        abaqus_command=options.abaqus_command or "abaqus",
        is_external=False,
        effective_work_dir=str(Path(options.inp_file).parent),
    )
