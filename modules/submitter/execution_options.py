"""Shared validated Abaqus GPU and precision arguments (no hardware inference)."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

EXPLICIT_PRECISIONS = frozenset({"default", "off", "explicit", "both", "constraint"})
OUTPUT_PRECISIONS = frozenset({"default", "single", "full"})


@dataclass(frozen=True)
class ExecutionOptions:
    gpu_count: int | None = None
    explicit_precision: str = "default"
    output_precision: str = "default"


def validate_execution_options(options):
    if options.gpu_count is not None and (type(options.gpu_count) is not int or not 0 <= options.gpu_count <= 1024):
        raise ValueError("GPU 数量必须是 0–1024 的整数，或留空沿用环境配置；0 表示关闭。")
    if not isinstance(options.explicit_precision, str) or options.explicit_precision not in EXPLICIT_PRECISIONS:
        raise ValueError("Explicit 计算精度选项无效。")
    if not isinstance(options.output_precision, str) or options.output_precision not in OUTPUT_PRECISIONS:
        raise ValueError("ODB 场输出精度选项无效。")
    validate_subroutine(options, getattr(options, "for_file", getattr(options, "fortran_path", "")))


def validate_subroutine(options, path):
    if (options.explicit_precision not in {"default", "off"} and isinstance(path, str)
            and Path(path).suffix.lower() in {".obj", ".o"}):
        raise ValueError("Explicit 双精度不能直接使用单个用户子程序目标文件；请选择源文件或配置预编译库。")


def parse_execution_options(payload):
    options = ExecutionOptions(payload.get("gpuCount"), payload.get("explicitPrecision", "default"),
                               payload.get("outputPrecision", "default"))
    validate_execution_options(options)
    validate_subroutine(options, payload.get("fortranPath", ""))
    return options


def execution_arguments(options):
    validate_execution_options(options)
    arguments = []
    if options.gpu_count is not None:
        arguments.append(f"gpus={options.gpu_count}")
    if options.explicit_precision != "default":
        arguments.append(f"double={options.explicit_precision}")
    if options.output_precision != "default":
        arguments.append(f"output_precision={options.output_precision}")
    return arguments
