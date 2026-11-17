# 开发、测试与发布

## 环境

- Python：仓库根目录 `.venv`，版本由 `.python-version` 固定为 3.14。
- .NET：.NET 10 SDK，WinUI 项目位于 `winui/AbaqusTools.WinUI`。
- Abaqus：本机命令与 release 从应用配置或后处理默认值读取；控制面只探测可用性，不在资源刷新时启动 Abaqus。

## 常用验证

```powershell
.\.venv\Scripts\python.exe -m ruff check modules\control_plane tests\control_plane tests\winui
.\.venv\Scripts\python.exe -m pytest -q --basetemp .\.pytest-tmp
dotnet restore .\winui\AbaqusTools.WinUI\AbaqusTools.WinUI.csproj -p:Platform=x64
dotnet build .\winui\AbaqusTools.WinUI\AbaqusTools.WinUI.csproj -p:Platform=x64 --no-restore
```

测试必须覆盖成功、失败、取消、重启恢复和路径越界。需要真实 Abaqus 或 SSH 的测试使用依赖注入替身，普通测试不得访问网络或修改用户作业目录。

## 生成物与本地状态

pytest 默认收集 tests，生成目录保留在 GPTWork。2026-11-18 的全量基线通过 648 项及 9 子检查，随后控制面/WinUI 修改后复核通过 195 项。详细命令、日志与尚未验证的发布要求见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

不提交 `.venv`、IDE 配置、`bin/obj`、Python 缓存、测试临时目录、ODB/求解器输出、应用数据库或日志。用户配置和队列保存在应用数据目录，不应复制进仓库。

## 发布前检查

1. 全量 Python 测试、Ruff 和 WinUI Release 构建通过。
2. 在真实 Windows 环境完成冷启动、关闭、Abaqus 探测、长任务取消和重连烟测。
3. 扫描凭据、私钥、绝对用户路径、运行数据库和求解结果。
4. 核对 Git 只包含源码、测试、文档和打包定义，再提交并推送。
