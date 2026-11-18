# 开发、验证与持续文档工作流

## 环境与启动

当前工作区 `G:\PythonProject\abaqusTool`；独立 Python 3.14 `.venv`；WinUI 项目 .NET 10。版本约束见 `pyproject.toml`、`.python-version` 和 `winui/AbaqusTools.WinUI/AbaqusTools.WinUI.csproj`。

```powershell
cd G:\PythonProject\abaqusTool
.\.venv\Scripts\python.exe --version
dotnet build .\winui\AbaqusTools.WinUI\AbaqusTools.WinUI.csproj -c Debug
Start-Process .\winui\AbaqusTools.WinUI\bin\Debug\net10.0-windows10.0.26100.0\win-x64\AbaqusTools.WinUI.exe
```

最后一行是用户主动启动可见应用的命令。开发验证不要自动关闭已有窗口来替换文件。实际 Abaqus 验收当前使用 `D:\SIMULIA\Commands\abaqus.bat`，需在新机器核实安装和许可，不假定该路径通用。

## 原生验收使用独立配置

用户已于 2026-11-18 明确允许恢复桌面验收。每次启动前检查已有测试进程和后台，不能因窗口暂未出现再次启动长任务。独立配置用于原生验收，默认运行方式和日常配置保持不变，约定见 [ADR0022](../submitter/adr/0022-isolated-workbench-profiles.md)。

从项目根目录运行，使用新的 G: 验收目录；替换 `$nativeCandidate` 为本轮已构建并核对的程序路径：

```powershell
$nativeCase = Join-Path (Get-Location) ('GPTWork/native-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path (Join-Path $nativeCase 'temp') -Force | Out-Null
$env:ABAQUS_TOOLS_PROFILE_DIR = Join-Path $nativeCase 'profile'
$env:TEMP = Join-Path $nativeCase 'temp'
$env:TMP = $env:TEMP
$env:ABAQUS_TOOLS_ROOT = (Get-Location).Path
$env:ABAQUS_TOOLS_PYTHON = Join-Path (Get-Location) '.venv/Scripts/python.exe'
# $nativeCandidate 须指向已核对的完整构建目录，用户已授权本次可见桌面验收。
Start-Process -FilePath $nativeCandidate -WorkingDirectory $nativeCase -PassThru
```

显式配置必须是绝对路径且不能与日常目录相同；不使用链接或别名指向同一目录。启动器应按进程传递环境，或在专用终端执行，避免影响日常启动。它会覆盖后台的两项 Python 数据目录变量，不搬迁旧数据；`TEMP`/`TMP`、Abaqus 工作目录和输出目录仍须显式核对。禁止 C: ODB 的限制继续有效。原生编辑后检查磁盘草稿、后台环境、正常退出及日常配置摘要；截图、鼠标或窗口操作失败须单独记录，不能用自动检查代替。

## 每个功能的完成条件

1. 在功能索引找到固定编号，确认上下游、协议、配置和相关测试。
2. 实现与验证：分别注明模拟测试、真实 Abaqus、真实 HTTP、原生点击和数值校核覆盖范围。
3. **立即同步文档**：功能说明和定位 → 验收结果 → 当前任务 → 当前状态。每完成一个功能，完成一份对应的文档更新，不积压到项目末尾。
4. 代码变更和必要文档更新一起交付。路径检查通过不代表语义正确，仍须核实调用关系与边界。
5. 未通过的验收保留为问题，不把它写成“后续优化”从完成条件中排除。

需要写入任务记录的内容：修改原因、功能编号、实际文件/符号、命令、结果、证据路径、未验证项、失败复现、准确续接点。没有变化的章节不必重复改写。

## 验证命令

用户于2026-11-18追加验证边界：**禁止向C:盘放置任何ODB文件，未经明确同意不得移动用户ODB**。可直接只读访问其他盘中已获授权的目录，缺访问权限时仅申请对应目录。所有ODB测试副本/占位文件/生成结果和测试临时目录均使用G:盘GPTWork；历史C:盘跨卷验收记录仅作历史证据，不能照搬为下一次命令。每个执行会话在运行测试前设置并核对TEMP/TMP（变量不跨工具调用继承）：

```powershell
$verificationTemp = Join-Path (Get-Location) ('GPTWork/temp-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verificationTemp | Out-Null
$env:TEMP = $verificationTemp
$env:TMP = $verificationTemp
.\.venv\Scripts\python.exe -c "import tempfile; print(tempfile.gettempdir())"
```

上例须从本项目G:盘工作目录执行，并为pytest指定新的G:盘`--basetemp`。审查脚本显式目标和Abaqus工作目录，不能只设置环境变量就假定全部输出合规。应用JSON配置仍可位于LocalApplicationData；本限制针对验证时的ODB文件放置与用户原件移动，不擅自改动产品可选目录功能。

pytest 默认只收集 `tests` 内的检查，忽略 GPTWork、虚拟环境和构建输出。指定验收范围时仍可传入明确的测试路径。

原生操作未获恢复时，整套回归需设置 `QT_QPA_PLATFORM=offscreen` 并排除 `tests/submitter/test_native_window_startup.py`；该文件会主动移除此环境变量并打开窗口，不能默认为无界面检查。排除项须记录为待验。测试临时目录使用 GPTWork 新建子目录，避免复用基目录覆盖旧回执。HTTP 夹具 `running_control_plane` 默认将队列、服务器配置和结果图放到各自 `tmp_path`；重复同一路径仍验证持久恢复，显式传入路径优先。不让 Qt 测试留下的共享队列干扰退出检查。

文档链接和代码路径：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/common/test_documentation_navigation.py -q --basetemp=GPTWork/pytest-docs
```

通用内力提取快速回归：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/postprocessor/test_region_extraction.py tests/postprocessor/test_region_worker.py tests/postprocessor/test_solid_sections.py tests/control_plane/test_region_extraction_api.py -q --tb=short --basetemp=GPTWork/pytest-region-status
```

后处理扩大回归与原生模型：

```powershell
.\.venv\Scripts\python.exe -m pytest tests/postprocessor tests/control_plane tests/winui tests/winui_host/test_region_api.py -q --tb=short --basetemp=GPTWork/pytest-postprocess
dotnet run --project tests/winui_postprocess/OdbPostprocess.Tests.csproj
dotnet run --project tests/winui_results/ResultBrowser.Tests.csproj --artifacts-path GPTWork/build-results-tests
```

真实 Abaqus 的人工 ODB 校核（需 CAE 许可，会创建新的隔离目录，不启动求解）：

```powershell
.\.venv\Scripts\python.exe tests/abaqus/verify_region_fixture.py --abaqus D:/SIMULIA/Commands/abaqus.bat --output-parent GPTWork/real-odb-validation
```

该脚本支持 `--cases solid_local_set solid_assembly solid_reverse solid_x solid_inclined solid_centroid`，本轮这六组实体校核已通过。未指定 cases 时还包含通用梁读取样例；不能把人工梁测试作为用户工程验收。样例生成必须有 `.created.json` 成功回执及匹配 SHA256，不能只看 Abaqus 的退出码。

已有 WinUI 窗口占用默认 Debug 输出时，不关闭用户窗口来替换文件。构建到 GPTWork 候选目录时必须同时指定 `OutputPath` 和 `OutDir`；只指定 OutDir，WinUI XAML 编译器仍会尝试覆盖默认目录的 XBF，导致 MSB3027/MSB3021 文件占用失败。

## 文件整理与数据安全

| 目录/文件 | 用途 | 整理原则 |
|---|---|---|
| `modules`、`winui` | 正式源码 | 移动前查导入/项目文件/打包配置，改完更新功能索引 |
| `tests` | 可重复测试与验收脚本 | 不把真实 ODB 或凭据放进测试源码 |
| `docs` | 长期知识、功能定位、任务 | 已有有效文档保留；新旧入口互链；过期记录标历史 |
| `GPTWork` | 本地样本副本、报告、失败日志、构建和测试临时物 | 当前不删除；先保留证据、列清单再做授权清理 |
| `.venv`、`bin/obj`、缓存 | 环境及可重建产物 | 不进入 Git；不在任务/程序仍使用时清理 |
| 用户应用数据目录 | 配置、队列、数据库 | 不按“无用文件”删除，不搬进仓库 |

本次先完成文档分类和导航，不移动业务模块或大量 GPTWork 结果，避免历史报告的绝对路径失效。后处理交付后再安排目录清理，记录被移动内容、旧新路径和恢复方式。

## 交接后的维护责任

后续智能体必须遵守根目录 AGENTS 的更新门槛。若新增功能没有对应索引/测试/说明，应先补齐；发现旧说明与代码矛盾，应修正文档而非盲目改变正确代码。完成任务时更新 [任务索引](../08-handoff/TASK_INDEX.md)，未完成时保留准确续接点。提交/推送仍需用户授权，不由文档规则自动授权。
