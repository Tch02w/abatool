# Abaqus Tools

用于 Abaqus 作业管理与 ODB 结果后处理的桌面工具集合。此仓库采用单一仓库、双独立应用的结构；两者共享 Abaqus 使用场景，但保持各自的运行环境、依赖和发布节奏。

## 应用

- `AbaqusSubmitter/`：单机 Abaqus 作业提交、队列调度、运行监控及远程连接。
- `AbaqusODBPostProcessor/`：ODB 发现、版本检查/升级、批量提取、云图和动画生成、结果浏览。

## 快速开始

两个应用均需在各自目录中安装依赖并运行：

```powershell
cd AbaqusSubmitter
uv sync --group dev
uv run python -m abaqus_submitter
```

```powershell
cd AbaqusODBPostProcessor
python -m venv .venv
.\.venv\Scripts\python -m pip install -e .
.\.venv\Scripts\python -m abaqus_odb_postprocessor.app
```

详细的运行、打包与领域说明分别见各应用目录内的 `README.md`。

## 仓库约定

- 源码、测试、文档和打包定义应提交；虚拟环境、IDE 配置、ODB 文件、求解器中间文件、缓存和结果文件不提交。
- 不将两个应用强行合并为一个 Python 包：提交器与后处理器的职责、依赖和入口不同。
- 跨应用的改动应在根目录说明其影响范围，并分别运行相关测试。
