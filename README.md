# Abaqus Tools

用于 Abaqus 作业管理与 ODB 结果后处理的统一 PySide6 桌面程序。应用以原提交器工作台为主壳，在同一窗口中保留标题栏、菜单、资源/属性/日志区域，并加入 ODB 后处理和结果浏览页面。

## 工作台页面

- 提交与调度：新建作业、作业队列、作业概览、计算资源、重启动链和 ODB 合并。
- ODB 后处理：ODB 发现、版本检查/升级、批量提取、云图和动画生成。
- 结果浏览：按工程用途浏览索引、CSV、图片、GIF、日志及导出文件。
- “后处理”菜单可把提交器中当前作业的 ODB 目录直接交给后处理页。

窗口底部状态栏统一显示当前模块/作业或目录、队列摘要、远端连接、Abaqus PATH 探测和 Qt 绑定；各模块原有的详细进度与日志仍保留。

## 快速开始

仓库只使用根目录独立 `.venv`，并由 `.python-version` 固定使用稳定版
Python 3.14（当前验证版本为 CPython 3.14.4）。在根目录安装后，通过统一入口启动：

```powershell
uv sync --group dev
uv run python .\main.py
```

`Ctrl+7` 打开 ODB 后处理，`Ctrl+8` 打开结果浏览。也可通过工作台标签和“后处理”菜单切换。领域说明见 `docs/`。

架构分层与共享边界见 [docs/architecture.md](docs/architecture.md)。

## 仓库约定

- 源码、测试、文档和打包定义应提交；虚拟环境、IDE 配置、ODB 文件、求解器中间文件、缓存和结果文件不提交。
- 根级 `main.py` 是统一产品入口；`modules/submitter/__main__.py` 作为兼容入口保留提交器独立启动能力。
- `modules/workspace.py` 继承提交器工作台壳，只负责页面组合、跨模块路径路由和统一状态呈现，不承载领域计算规则。
- `modules/submitter/` 与 `modules/postprocessor/` 是同一产品下的领域模块；共享基础设施放在 `modules/common/`。
