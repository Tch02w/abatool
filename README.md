# Abaqus Tools

用于 Abaqus 作业管理与 ODB 结果后处理的统一桌面程序。应用在同一主窗口中提供两个功能页，并共享一个 Python 安装、启动入口和发布流程。

## 功能页

- “作业提交与调度”：单机 Abaqus 作业提交、队列调度、运行监控及远程连接。
- “ODB 后处理”：ODB 发现、版本检查/升级、批量提取、云图和动画生成、结果浏览。

## 快速开始

仓库只使用根目录 `.venv`。在根目录安装后，通过唯一入口启动：

```powershell
uv sync --group dev
uv run python .\main.py
```

按 `Ctrl+1` 或 `Ctrl+2` 可切换功能页。领域说明见 `docs/`。

架构分层与共享边界见 [docs/architecture.md](docs/architecture.md)。

## 仓库约定

- 源码、测试、文档和打包定义应提交；虚拟环境、IDE 配置、ODB 文件、求解器中间文件、缓存和结果文件不提交。
- 根级 `main.py` 是唯一 GUI 入口；`modules/workspace.py` 只负责组合功能页。
- `modules/submitter/` 与 `modules/postprocessor/` 是同一产品下的领域模块；共享基础设施放在 `modules/common/`。
