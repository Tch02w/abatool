# ADR 0022：原生工作台的独立验收配置

- 状态：已实现；原生路径、输入保存和同配置重复启动已验证，完整八页交互仍待验。
- 日期：2026-11-18
- 范围：F001/F022/F023

## 问题

只给 Python 设置测试数据目录不能隔离原生工作台：原先单实例标识、控制面描述符、页面草稿、结果图草稿和后处理工作区仍使用日常配置。桌面验收可能连接已有后台或改写用户填写，独立 HTTP 夹具不能证明没有这些影响。

## 决定

`winui/AbaqusTools.WinUI/Services/WorkbenchProfile.cs` 在进程启动时读取 `ABAQUS_TOOLS_PROFILE_DIR`。省略时保留原有 `%LOCALAPPDATA%/AbaqusTools` 路径和 `AbaqusTools.WinUI.Primary` 单实例标识，不改既有 Python 数据环境变量。

显式设置时必须是完整绝对路径，不能等于日常配置目录；错误直接阻止启动，不回退日常配置。规范化完整路径、末尾分隔符和大小写后生成单实例标识，同配置重复启动转交已有窗口，不同配置相互独立。该路径不是目录链接的真实目标解析，不应使用符号链接、联接或其他别名指向同一份配置。

| 数据 | 独立配置下的位置 |
|---|---|
| 控制面描述符、启动锁及运行存储 | `runtime/` |
| Python 调度配置及队列 | `submitter/`，覆盖子进程的 `ABAQUS_SUBMITTER_DATA_DIR` |
| Python 后处理配置 | `postprocessor/`，覆盖子进程的 `ABAQUS_POSTPROCESSOR_DATA_DIR` |
| 页面输入与窗口状态 | `workbench-session.json` |
| 结果图编辑草稿 | `result-graph-draft.json` |
| 后处理工作区、恢复草稿及弹窗草稿 | `postprocess-workspaces/`、`postprocess-recovery/` |

原生入口和 `ControlPlaneHost` 均先配置子进程环境，避免直接主机测试遗漏这一步。已有数据不复制、不搬迁、不删除；取消、失败及关闭仍沿用各存储与操作的原协议。它不是安全沙箱，不限制用户选择的模型和输出路径，也不自动改 `TEMP`/`TMP`。验收须另设 G: 临时目录，并核对 worker 的显式输出位置。

## 验证和边界

`tests/winui_host/WorkbenchProfileChecks.cs` 的 14 项检查覆盖默认兼容、路径规范化、不同实例标识、无效路径和 Python 环境；`tests/winui_host/test_shutdown_api.py` 调用生产类包装验证。G: 独立原生窗口中，名称/CPU 编辑实际落盘；同配置再次启动退出 0 且后台 PID 不变；普通关闭后后台与描述符退出；记录的两份日常 JSON 摘要不变。

详细原生回执、版本差异和截图/鼠标工具限制见 [TASK-002](../../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。这不替代真实旧配置、全部页面恢复或有任务时关闭验收。独立配置启动命令见 [开发流程](../../05-development/WORKFLOW.md)。
