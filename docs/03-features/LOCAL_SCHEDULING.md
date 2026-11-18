# 本机队列调度与恢复（F004/F005）

WinUI 的正式队列由 Qt-free Python 控制面调度。`LocalQueueScheduling` 复用原提交器的 `SchedulerCore`、队列投影和 SQLite 存储；页面只提交参数、显示状态。PySide6 对照入口保留。此处是本机资源准入，不代表跨节点 Slurm 调度。

## 输入与派发顺序

- 输入为正式队列条目及「并行上限」。待运行且未暂停调度的条目必须设置 Core；0 表示未设置，开始请求返回字段错误。
- 先检查 Restart 前置作业，再按优先级从高到低、相同优先级的队列顺序分配。移动上下顺序只影响相同优先级的条目。
- 同名 Restart 父作业按明确的 oldjob 路径区分，包含计算根目录生成的实际工作目录。有多个未消歧的同名父作业时等待用户指定路径。队列父作业仍运行时，即使旧 ODB 已存在也不放行；没有队列父作业的外部 ODB 仍检查文件和 LCK。
- 同目录同名作业互斥。正在结束的执行线程和归档占用不会提前释放。

## 资源口径

派发到本机执行器后，先只读验证工作目录和命令，再逐文件准备输入。已有 LCK、缺失前置文件或取消策略拒绝时不会先覆盖目标输入；失败持久恢复后不自动重试。复制、取消和归档限制见 [工作目录准备](LOCAL_WORKSPACE.md)。

| 项目 | 本机准入规则 |
|---|---|
| 作业槽位 | 并行上限减去已观察到的活动作业及尚未收尾的本机执行记录 |
| 单作业 CPU | 沿用软件版本规则：Abaqus ≤2021 按逻辑线程，>2021 按物理核心；不是许可证规则 |
| 合计 CPU | 使用本机逻辑线程总数减活动队列作业的 Core，再逐项扣除新分配；活动外部作业的 Core 未知时不当作 0，暂停新的 CPU 分配 |
| 绝对内存与估计 | 取绝对配置与有来源估计的较大值；从系统可用内存的 85% 中扣除活动作业需求尚未体现在新鲜 RSS 中的部分，避免重复扣已驻留内存 |
| 百分比内存 | `90%` 是传给求解器的上限，不能当作实际占用或固定预留；当前不据此推算需求 |

已接入旧纯 Python 内存学习器、自有进程采样和后台重启后的历史估计，按模型身份区分，并显示估计来源。百分比设置仍不能保证总内存充足。冷启动、文件元信息、采样失败和峰值余量限制见 [内存观测说明](MEMORY_MONITORING.md)。实际 Windows helper 及自动测试不等于真实 Abaqus/MPI 高负载和原生业务验收。

## 持久状态、错误和取消

队列同目录中的 `scheduler_state.db` 保存作业、事件和每次执行的 `attemptId`；`joblist.json` 保留界面队列。分配必须完成两个存储的写入才可启动线程。两个文件不是一个跨文件原子事务：中途崩溃后保守恢复为「状态未知」，不根据保存的启动状态重复执行。

后台重启后不自动恢复派发。JSON 或 SQLite 中尚活动的记录，以及此前未核对的记录，保留执行身份并登记原工作目录扫描。SQLite 中有活动条目但 JSON 缺行时，重建仅供观察的外部条目。扫描更新的是实际状态，不重新取得进程控制权。观察到的外部作业不自动获得暂停/终止能力。

「状态未知」会阻止新资源分配，也不能被清理完成记录、删除或重新排队。扫描后若没有活动/结束证据则显示「待确认」，用户核对后才能明确重新排队。它不表示成功或零结果。原执行器返回未知时同样保留并扫描，退出检查不会把它当作安全空闲。

存储或线程启动失败会暂停新派发并在队列显示原因。启动失败释放未启动分配；运行中进度保存失败继续监控原执行器；最终结果保存失败保留未收尾状态，每 5 秒重试保存，绝不重新运行计算。保存成功后由用户重新开始队列。停止队列只停止派发；终止请求继续沿用自有执行器的合作停止。后台继续和关闭协议见 [退出说明](UI_INTERACTION.md)。

## 外部作业扫描与并发修改

在正式队列的「工作目录 → 扫描」读取外部作业。扫描期间 API 的 `externalScanActive` 为 true，页面显示「扫描中…」并禁止重复启动；状态读取返回最近已保存的队列，不等待进程枚举、目录检查或日志诊断。同一后台只进行一轮外部扫描，多目录共用一次进程列表。重复手动请求返回 409 `EXTERNAL_SCAN_BUSY`，周期扫描遇忙跳过本轮。

扫描在独立副本上计算结果，结束后重新读取当前队列。只有完整原记录仍匹配的条目才允许更新；扫描期间被编辑、删除、重新执行或被同名同目录条目替换的结果会跳过，且保留候选区和当前排序。本机执行器管理的活动记录及正在归档的记录不接受扫描覆盖。统计中的新增、更新按实际落盘计数；`staleResultsSkipped` 表示跳过的旧结果，可稍后刷新核对。

扫描失败不保存部分结果并释放扫描占用；关闭后台后不再合并迟到结果，手动请求返回 503 `CONTROL_PLANE_SHUTTING_DOWN`。扫描本身没有独立取消按钮；此修改也不意味着线程中的系统调用可即时终止。识别外部进程仍沿用目录、作业名、状态证据规则，不获得求解控制权；没有结束证据不能报告成功。

源码定位：`JobQueueService._run_external_scan`、`_scan_external_roots` 和 `external_job_scan_core.scan_external_jobs(additional_roots=...)`。回归入口 `tests/control_plane/test_external_scan_concurrency.py`；真实 Windows 自有非求解进程与生产 C# 客户端验证为 `packaging/verify_external_scan.py`。小型夹具响应时间不能代表工程负载或网络目录性能，原生界面显示仍需验收。锁与合并约定见 [ADR 0015](../submitter/adr/0015-external-scan-snapshot-merge.md)。

## 输出与性能边界

队列显示槽位、CPU、内存、依赖或目录冲突的等待原因；运行 API 增加 `schedulerMessage` 和操作的 `attemptId`。相同队列内容不重复替换 JSON，相同状态及消息不重复写调度事件。过期执行回调不能覆盖已完成结果。

源码：`modules/control_plane/local_scheduling.py`、`local_queue_runtime.py`、`job_queue_commands.py`，共享算法位于 `modules/submitter/scheduling.py`、`scheduler_adapter.py`、`scheduler_repository.py`。验证入口为 `tests/control_plane/test_local_scheduling.py`、`test_local_queue_runtime_api.py`、`test_shutdown_guard.py` 和 `tests/submitter/test_scheduler_adapter.py`。本轮实际结果与未验收范围见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。
