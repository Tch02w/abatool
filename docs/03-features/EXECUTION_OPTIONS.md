# GPU 与精度选项（F003/F004/F005/F010/F028）

## 使用方法

新建作业的“执行环境与资源”下展开“GPU 与精度（可选）”；正式队列选择一个未运行作业，点“编辑”也可修改同一组选项。修改队列仅影响下一次执行，不能改变已运行求解的参数。新建作业的未提交选择与数字原始输入随工作台草稿保存。

| 选项 | 默认 | 明确设置后的行为 |
|---|---|---|
| GPU 数量 | 不勾选“指定”，沿用环境配置 | 勾选后 0 发送 `gpus=0`，正整数发送指定数量；允许 0–1024 整数，此上限是输入校验范围，不代表硬件可用数量 |
| Explicit 计算精度 | 沿用环境配置，不追加参数 | 单精度 off、分析双精度 explicit、预处理及分析双精度 both、仅约束双精度 constraint |
| ODB 场输出精度 | 沿用环境配置，不追加参数 | single 或 full，与计算精度独立 |

字段旁小问号沿用悬停说明；数字使用常驻下/上折线和居中数值。重新关闭指定 GPU 并将两项精度选为默认，就撤销命令覆盖。不要把“未指定 GPU”与明确的 0 混为同一含义。损坏的自定义草稿保持原字符串，阻止带默认值误提交；用户明确点“恢复默认设置”后才能重填，关闭窗口不会悄悄改写损坏内容。

## Abaqus 语义与边界

依据 [Abaqus 2025 执行参数文档](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEEXCRefMap/simaexc-c-analysisproc.htm)：GPU 选项用于有兼容设备的 Standard 求解器加速，MPI 参数为跨主机总数。Explicit 的 double 控制其计算精度；它不改变 Standard 求解精度。full 控制 ODB 场输出：Standard 节点/单元可双精度；Explicit 节点双精度还需相应计算精度，单元场输出不提供双精度；历史输出仍为单精度。Explicit 双精度不能将单个 `.obj` / `.o` 作为用户子程序传入，需源文件或正确配置预编译库。

软件不推断 INP（含 INCLUDE、重启动）的完整分析类型，不承诺 GPU 兼容性或实际加速。当前调度仍管理 CPU/内存/目录/依赖，**没有独占 GPU 分配或显存记账**；并发 GPU 作业可能共用设备。真实 GPU 求解未验收，不通过新求解替代既有模型验收。计算精度不会修复网格/材料/边界条件误差，全精度输出可能增大 ODB。

## 配置与执行链

Python `QueueItem`、`LocalJobDraft`、`SubmitOptions` 和远端请求统一包含 `gpu_count`（None 或整数）、`explicit_precision` / `output_precision`（默认 default）。旧队列和远端记录缺字段时回到默认，不改变原命令。所有值由 `modules/submitter/execution_options.py` 校验，拒绝布尔/小数/字符串 GPU 数和未知精度；精度枚举不是自由命令文本。

本机预览、QueueItem 转换及执行器共用参数生成；执行前先校验，错误发生在工作区复制和结果备份之前。远端预览和生产 PowerShell 启动器使用同一组经过校验的参数字符串，启动脚本再次检查允许形式。持久恢复保存选项，请求幂等签名包括三项；相同请求 ID 改变选项返回冲突，不重放作业。

内存估计键包含明确 GPU/精度覆盖，避免混用不同执行条件的历史；全默认仍使用原键，不让升级前默认作业历史整体失效。PySide6 对照入口保留，没有新增 Qt 编辑控件；新参数的编辑入口是 WinUI。

## HTTP

草稿预览、入队 draft、远端预览/创建支持可选 `gpuCount`、`explicitPrecision`、`outputPrecision`。GPU 省略/null 代表默认，0 是关闭；精度省略为 default，显式 null 无效。参数错误为 400 `INVALID_EXECUTION_OPTIONS`。队列投影和远端 request 快照返回相同字段。

updateCandidate / updateQueueItem 省略字段表示保留原值；显式 `gpuCount:null` 撤销 GPU 覆盖；精度传 default 撤销对应覆盖。新客户端只在编辑这组设置时发送它们，不使旧客户端编辑名称/内存的动作清空新参数。

## 定位与验收

- 参数及命令：`modules/submitter/execution_options.py`、`modules/submitter/command.py`、`modules/submitter/job_draft.py`、`modules/submitter/local_job_execution.py`；API `modules/control_plane/job_drafts.py`、`modules/control_plane/job_queue_commands.py`、`modules/control_plane/remote_jobs.py`、`modules/control_plane/remote_job_recovery.py`；历史键 `modules/control_plane/local_memory.py`。
- 共用编辑区：`winui/AbaqusTools.WinUI/Controls/ExecutionOptionsEditor.cs`；数值/草稿契约 `winui/AbaqusTools.WinUI/Services/ExecutionOptionsContracts.cs`；`WorkbenchSession` 保存原始输入；F003/F004 调用生产 `ControlPlaneHost`，F010 同步远端请求。
- 重点测试：`tests/control_plane/test_execution_options.py`、`tests/winui_host/ExecutionOptionChecks.cs`、`tests/winui_host/test_execution_options_api.py`。真实 Windows 等待命令和生产 PowerShell 仅证明参数传递，不代表 GPU 求解或精度数值结果已验收。准确测试、失败和后续动作见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

后台能力为 `job.execution-options-v1`。正式客户端在发送这组参数前核对同一后台实例的能力；连接旧后台时明确提示安全退出旧后台后更新，不发送预览/提交/编辑 POST，不自动停止原作业或替换其后台。
