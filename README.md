# Abaqus Tools

Abaqus Tools 是面向 Windows 的 Abaqus 作业管理与 ODB 后处理工作台。当前原生前端使用 C#、.NET 10 和 WinUI 3；Python 3.14 控制面复用经过验证的提交、调度、SSH、ODB 与结果处理核心。PySide6 实现暂时保留为兼容与回滚入口，不参与原生页面渲染。

首次使用可从[安装说明](docs/05-development/INSTALLATION.md)和[八个页面的操作手册](docs/repowiki/user-guide.md)开始。队列支持对齐的行列线与保留选区的刷新。后处理支持运行中追加对比组、编辑等待组、取消单组后继续，并能在重开前台时接回队列。各项的工程测试、桌面实测及待验范围见[当前状态](docs/08-handoff/CURRENT_STATUS.md)。

## 功能

要让某个工况先出结果，在「ODB 后处理 → 选择与对比组 → 对比组执行顺序」里将对应组上移。运行前可以展开完整顺序，正在等待和执行的任务仍按入队时的顺序继续。[分组操作](docs/repowiki/postprocessor.md)

在「ODB 后处理」选中多个已读取结构的模型，点「对照提取参数…」可并排查看各自的分析步、集合、配筋和帧设置。可以逐个修改，或勾选少数字段复制到其余模型，保存前会标出哪些模型需要修正。「新建对比组…」支持先建空组，稍后再添加模型。[后处理使用说明](docs/repowiki/postprocessor.md)

以下是功能范围，不代表全部迁移验收已经完成。当前后处理可运行核心与剩余缺口见 [交接状态](docs/08-handoff/CURRENT_STATUS.md)；后续开发先从 [功能定位索引](docs/03-features/FUNCTION_INDEX.md) 找到代码与测试。

- 新建本机或远程作业，校验路径和资源参数并预览实际 Abaqus 命令。
- 本机启动前先检查工作目录、LCK 和输入，再逐文件准备；复制失败保留该文件旧目标，已接受的取消不再启动新进程。[准备与归档边界](docs/03-features/LOCAL_WORKSPACE.md)。
- 本机归档先复制并校验再发布，可选清理原计算目录；中断后可从作业概览「恢复归档」，核对已有副本继续处理，不重新求解。界面区分计算与归档结果，部分归档不用于 Restart。[归档及恢复限制](docs/03-features/LOCAL_ARCHIVE.md)、[候选版本变化](docs/05-development/CHANGELOG.md)。
- WinUI 新建作业和队列编辑可配置 GPU、Explicit 计算精度及 ODB 场输出精度；默认沿用环境，预览/本机/远端共用校验和参数，持久恢复保留选择。没有 GPU 独占分配，真实加速与原生操作仍待验收。见 [选项说明](docs/03-features/EXECUTION_OPTIONS.md)。
- 扫描候选 INP、管理正式队列，按优先级、CPU/绝对内存及依赖分配本机作业；后台重启保留身份并核对，未知状态不重复提交；[调度和恢复边界](docs/03-features/LOCAL_SCHEDULING.md)。
- 外部作业扫描期间仍可读取队列状态，多目录共享进程查询；扫描结束不会覆盖期间修改的记录，忙碌和跳过结果明确提示。
- 队列调度减少重复的历史内存文件查询；数据检查失败同样支持结束提醒和重启补查。实际进程验证范围及工程负载限制见 [验收记录](docs/06-testing/VALIDATION.md)。
- 观测本机作业的进程内存，区分当前占用、峰值和估计；结合历史及安全余量分配资源，多作业共享扫描。[内存口径与限制](docs/03-features/MEMORY_MONITORING.md)。
- 查看作业日志与 STA/MSG/DAT，管理本机和远端计算资源及文件传输。
- 远端通信较慢时，资源页可先显示最近一次完整状态，并明确提示更新中及旧采样；已知忙时不重复排入资源刷新，命令仍保留服务器身份校验。见 [连接状态说明](docs/03-features/REMOTE_JOBS.md)。
- 本机/远端作业结束后集中显示提醒，按执行身份去重；独立归档结果落盘后可在崩溃重启时补发，清除队列也保留已读历史；[提醒与保存边界](docs/03-features/JOB_NOTIFICATIONS.md)。
- 远端作业按完成输出、进程/锁及稳定文件确认结束；断线与后台重启可连接原服务器继续跟踪，恢复不重复提交。支持离线取消意图保存，未知状态明确显示。[远端确认与恢复边界](docs/03-features/REMOTE_JOBS.md)。
- 编辑并校验 Restart/oldjob 依赖链。
- 异步合并 ODB，支持逐步逐帧内容校验、校验回执、无结果帧提示、持久任务记录、重启去重与中断提示，以及取消、冲突策略和失败清理；[规则与边界](docs/03-features/ODB_MERGE.md)。
- 按独立结果图批量生成完整 ODB，后台保存计划与阶段，重启后检查并继续；[批量恢复边界](docs/03-features/ODB_RESULT_BATCH.md)。
- 定期保留页面输入、结果图、后处理工作区及未确认弹窗草稿；恢复时先核对原配置和来源，不自动确认参数。[草稿恢复与限制](docs/03-features/POSTPROCESSING.md)。
- 扫描与升级 ODB，按对比组提取、渲染和生成动画。运行时可追加组、修改等待组或取消当前组并继续，已发布的结果可单独浏览。[分组队列使用说明](docs/repowiki/postprocessor.md)
- 构建结果索引并预览文本、表格、图片和动画。
- 关闭前保存页面草稿，支持后台继续、停止后关闭或取消；联合检查受管任务及线程收尾，未知状态保留后台；[退出与恢复边界](docs/03-features/UI_INTERACTION.md)。

## 原生工作台

GitHub 仓库提供源码和使用手册。交接文档中以 `GPTWork/` 开头的是开发机上的构建或验证目录。首次使用时，拿到完整 Windows 目录包可直接运行其中的 `AbaqusTools.WinUI.exe`，拿到安装程序则按安装说明操作。只有源码时，可使用下方构建命令。[安装说明](docs/05-development/INSTALLATION.md)

八个页面共用适度紧凑的留白，侧栏右上角折线按钮或Ctrl+B收起/展开；收起后保留小型展开入口，内容随当前页面显示相关目录、作业或结果。实际候选与待验范围见当前状态。

首次使用请按 [使用手册](docs/repowiki/user-guide.md)操作。当前版本支持分组统一云图范围、GIF 统一帧率或统一时长、结果列表分页和表格预览；结果清理位于「更多 → 移到回收站」。

以下是源码启动方式，要求 Windows、.NET 10 SDK，以及仓库根目录的 Python 3.14 `.venv`。安装候选/完整目录携带运行库，操作与验收限制见[安装说明](docs/05-development/INSTALLATION.md)。

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

从本项目 G 盘目录执行。下例将临时文件放入新的 GPTWork 目录，ODB 验证文件必须留在 G 盘。此命令运行离屏自动回归；可见窗口启动、鼠标交互和工程出图各有独立验收步骤。[维护工作流](docs/05-development/WORKFLOW.md) · [原生页面验收](docs/06-testing/NATIVE_ACCEPTANCE.md)

```powershell
$verificationTemp = Join-Path (Get-Location) ('GPTWork/temp-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verificationTemp | Out-Null
$env:TEMP = $verificationTemp
$env:TMP = $verificationTemp
$env:QT_QPA_PLATFORM = 'offscreen'
$env:ABAQUS_SUBMITTER_DATA_DIR = Join-Path $verificationTemp 'submitter'
$env:ABAQUS_POSTPROCESSOR_DATA_DIR = Join-Path $verificationTemp 'postprocessor'
.\.venv\Scripts\python.exe -m ruff check modules\control_plane tests\control_plane tests\winui
.\.venv\Scripts\python.exe -m pytest tests -q --ignore=tests/submitter/test_native_window_startup.py --basetemp (Join-Path $verificationTemp 'pytest')
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
