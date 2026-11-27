# 开发、测试与发布

## 环境

- Python：仓库根目录 `.venv`，版本由 `.python-version` 固定为 3.14。
- .NET：.NET 10 SDK，WinUI 项目位于 `winui/AbaqusTools.WinUI`。
- Abaqus：本机命令与 release 从应用配置或后处理默认值读取；控制面只探测可用性，不在资源刷新时启动 Abaqus。

## 常用验证

```powershell
$verificationTemp = Join-Path (Get-Location) ('GPTWork/test-' + [guid]::NewGuid().ToString('N'))
New-Item -ItemType Directory -Path $verificationTemp | Out-Null
$env:TEMP = $verificationTemp
$env:TMP = $verificationTemp
$env:ABAQUS_SUBMITTER_DATA_DIR = Join-Path $verificationTemp 'submitter'
$env:ABAQUS_POSTPROCESSOR_DATA_DIR = Join-Path $verificationTemp 'postprocessor'
$env:QT_QPA_PLATFORM = 'offscreen'
.\.venv\Scripts\python.exe -m ruff check modules\control_plane tests\control_plane tests\winui
.\.venv\Scripts\python.exe -X utf8 -m pytest tests -q --ignore=tests/submitter/test_native_window_startup.py --basetemp (Join-Path $verificationTemp 'pytest')
dotnet restore .\winui\AbaqusTools.WinUI\AbaqusTools.WinUI.csproj -p:Platform=x64
dotnet build .\winui\AbaqusTools.WinUI\AbaqusTools.WinUI.csproj -p:Platform=x64 --no-restore
```

从本项目G:根目录运行上述命令，临时文件、应用测试配置和占位ODB均留在GPTWork；环境变量只用于本次验收终端。排除的显式窗口启动测试单独验收，不计为通过。测试必须覆盖成功、失败、取消、重启恢复和路径越界；普通测试使用Abaqus/SSH替身，不访问真实网络或修改用户作业目录。

## 生成物与本地状态

pytest默认收集tests，生成目录保留在GPTWork。不同源码阶段的结果不累计；当前版本和正在进行的检查见[当前状态](../08-handoff/CURRENT_STATUS.md)，精确命令、日志、失败与未验项见[TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

不提交 `.venv`、IDE 配置、`bin/obj`、Python 缓存、测试临时目录、ODB/求解器输出、应用数据库或日志。用户配置和队列保存在应用数据目录，不应复制进仓库。

## PySide 队列回滚

需要在 PySide 中继续处理 WinUI 保存的队列时，从当前项目根目录运行 `.\.venv\Scripts\python.exe .\main.py`。项目保留的 PySide 入口能识别新版队列字段。实际检查中，仅更改另一条候选的勾选并保存后，原作业的 GPU 数量和 ODB 场输出精度仍保持设置值。迁移前版本 `f5e9484` 可以读回旧字段，但用它重新保存队列会丢弃上述两项设置。[双向读写实测](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md#2026-11-28--旧队列双向读写与-pyside-回滚)

## 发布前检查

1. 全量 Python 测试、Ruff 和 WinUI Release 构建通过。
2. 在真实 Windows 环境完成冷启动、关闭、Abaqus 探测、长任务取消和重连烟测。
3. 扫描凭据、私钥、绝对用户路径、运行数据库和求解结果。
4. 核对 Git 只包含源码、测试、文档和打包定义，再提交并推送。
