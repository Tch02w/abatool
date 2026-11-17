# Abaqus Tools

Abaqus Tools 是面向 Windows 的 Abaqus 作业管理与 ODB 后处理工作台。当前原生前端使用 C#、.NET 10 和 WinUI 3；Python 3.14 控制面复用经过验证的提交、调度、SSH、ODB 与结果处理核心。PySide6 实现暂时保留为兼容与回滚入口，不参与原生页面渲染。

## 功能

以下是功能范围，不代表全部迁移验收已经完成。当前后处理可运行核心与剩余缺口见 [交接状态](docs/08-handoff/CURRENT_STATUS.md)；后续开发先从 [功能定位索引](docs/03-features/FUNCTION_INDEX.md) 找到代码与测试。

- 新建本机或远程作业，校验路径和资源参数并预览实际 Abaqus 命令。
- 扫描候选 INP、管理正式队列、限制并行数、暂停/恢复/终止和恢复运行状态。
- 查看作业日志与 STA/MSG/DAT，管理本机和远端计算资源及文件传输。
- 编辑并校验 Restart/oldjob 依赖链。
- 异步合并 ODB，支持逐步逐帧内容校验、校验回执、无结果帧提示、持久任务记录、重启去重与中断提示，以及取消、冲突策略和失败清理；[规则与边界](docs/03-features/ODB_MERGE.md)。
- 按独立结果图批量生成完整 ODB，后台保存计划与阶段，重启后检查并继续；[批量恢复边界](docs/03-features/ODB_RESULT_BATCH.md)。
- 扫描与升级 ODB，按组批量提取、渲染、生成动画和工程结果。
- 构建结果索引并预览文本、表格、图片和动画。

## 原生工作台

首次使用请按 [使用手册](docs/repowiki/user-guide.md)操作。当前版本支持分组统一云图范围、GIF 统一帧率或统一时长、结果列表分页和表格预览；结果清理位于「更多 → 移到回收站」。

要求：Windows、.NET 10 SDK，以及仓库根目录的 Python 3.14 `.venv`。

```powershell
uv sync --group dev
dotnet restore .\winui\AbaqusTools.WinUI\AbaqusTools.WinUI.csproj -p:Platform=x64
dotnet run --project .\winui\AbaqusTools.WinUI\AbaqusTools.WinUI.csproj -p:Platform=x64
```

WinUI 客户端只连接 `127.0.0.1` 上的随机端口控制面，使用进程级随机 token 鉴权；需要时自动启动：

```powershell
.\.venv\Scripts\python.exe -m modules.control_plane
```

如需指定解释器，可设置 `ABAQUS_TOOLS_PYTHON`。只有仓库位于非标准布局时才需要设置 `ABAQUS_TOOLS_ROOT`。

开发者可用 `.\.venv\Scripts\python.exe packaging/build_release.py` 构建携带 .NET、Windows App SDK 和 Python 控制面的 Windows x64 完整目录。使用者需整体解压并运行其中的 `AbaqusTools.WinUI.exe`；目标机器仍需配置自己的 Abaqus。构建、诊断与未完成的发布门槛见 [发布说明](docs/05-development/RELEASE.md)。

## 兼容入口

迁移验收期间仍保留以下 PySide6 入口，用于行为对照与回滚：

```powershell
uv run python .\main.py
uv run abaqus-submitter
uv run abaqus-odb-post
uv run abaqus-odb-results
```

## 项目结构

```text
winui/AbaqusTools.WinUI/   原生 WinUI 3 客户端
modules/control_plane/     Qt-free 本机 HTTP 控制面
modules/submitter/         作业、队列、调度、SSH 与 ODB 合并核心
modules/postprocessor/     ODB 批处理、渲染、缓存与结果浏览核心
modules/common/            路径与 JSON 等共享基础设施
tests/                     领域、API 与 WinUI 契约测试
docs/                      架构、协议、ADR 与 RepoWiki
```

## 开发验证

```powershell
.\.venv\Scripts\python.exe -m ruff check modules\control_plane tests\control_plane tests\winui
.\.venv\Scripts\python.exe -m pytest -q --basetemp GPTWork/pytest-full
dotnet build .\winui\AbaqusTools.WinUI\AbaqusTools.WinUI.csproj -p:Platform=x64 --no-restore
```

虚拟环境、IDE 配置、测试临时目录、`bin/obj`、ODB 和求解器输出均不提交。应用配置、队列、SSH 非敏感配置和运行数据库位于用户应用数据目录，不写入源码树。

## 文档

- [软件使用手册](docs/repowiki/user-guide.md)

- [文档与交接总入口](docs/INDEX.md)
- [智能体持续维护规则](AGENTS.md)：每完成一个功能同步完成对应文档更新。
- [功能 → 代码 → 测试索引](docs/03-features/FUNCTION_INDEX.md)
- [当前状态与准确续接点](docs/08-handoff/CURRENT_STATUS.md)
- [RepoWiki](docs/repowiki/README.md)
- [整体架构](docs/architecture.md)
- [控制面 API 契约](docs/api-contract.md)
- [WinUI 迁移与验收合同](docs/winui-migration.md)
