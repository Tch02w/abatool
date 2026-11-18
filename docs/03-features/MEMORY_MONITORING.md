# 本机内存观测与估计（F005/F007）

原生控制面复用纯 Python `MemoryMonitorService` 的峰值和稳定学习规则，不导入 Qt 计时器。当前占用、观测峰值、调度估计是不同量，不能把 Abaqus 的 `90%` 参数当作实际占用。

## 采样与界面

自有执行器每轮约 1 秒取得一次进程快照，多作业共用 `ProcessSnapshotCache`，0.75 秒内的并发请求只扫描一次。按本次启动时间核对求解进程或自有 launcher 的 PID/创建时间，再统计其可核实的子进程；不把祖先进程或另一目录的同名作业加进来。启动时间匹配留有 2 秒容差。这里统计进程工作集合计，可能包含共享页，不等于物理内存唯一页数。

全局扫描异常、部分进程内存或创建时间不可读时，显示“暂不可读”；未找到本次作业进程显示“采集中”。超过 10 秒或时间戳在未来时显示“待更新”。这些状态不作为零内存，也不再用旧 RSS 抵扣资源预留。采样异常不会使执行器放弃监控已启动作业。

首次样本和结束前立即保存，中间最多每 5 秒批量保存各作业观测。批次保留期间出现的最高值，后续读取失败也不会抹掉已观测峰值。稳定学习沿用 15 秒学习/90 秒巡查、新峰值重新学习的规则；新峰值无需等巡查周期结束。

队列表格和作业概览显示当前状态/占用；鼠标停在内存值上可看峰值、估计值及来源：“同模型历史”“已观测峰值含安全余量”或“本次运行的其他作业参考”。仅构建和显示逻辑已验收，真实原生鼠标布局仍需验收。

外部或后台重启后恢复的作业沿用原工作目录扫描，每 5 秒更新可核实的 PID 创建时间及正 RSS。无有效 RSS 时标不可读；扫描时间更新不因数值未变而丢失。已有执行身份的活动观察记录可参与学习，但不因此获得终止或暂停外部进程的所有权。外部内存覆盖范围仍依赖原扫描器的进程识别，不能据此声称所有 MPI/远端进程都被覆盖。

## 调度规则

1. 先取系统**当前可用内存的 85%**，为其他程序保留余量。这不是总内存的 85%。
2. 每个作业的需求取绝对内存配置与对应模型历史估计的较大值；估计至少为已观测峰值的 1.10 倍。
3. 无本模型历史且没有绝对配置时，使用本次后台运行中其他作业的最大估计作为明确标注的参考。不把它描述为该模型实测值。后台重启不会把所有历史模型的最大值强加给新模型。
4. 从预算中扣除活动作业需求尚未体现在新鲜 RSS 中的部分。系统可用内存已经排除了实际占用，不重复扣整份 RSS。再逐项扣除新分配需求。
5. 冷启动、无绝对配置且无任何样本时，没有可证明的内存需求，仍按并行上限、CPU 和其他条件准入；可用内存为 0 时暂停派发。估计不能保证后续峰值或避免所有内存不足。

百分比参数继续传给求解器。当前没有新增“保证不超内存”的开关，也不自动终止高占用作业。整体资源规则见 [本机调度](LOCAL_SCHEDULING.md)。

## 历史身份与恢复

历史按模型输入的绝对路径、大小、修改时间，加 CPU、Abaqus 命令、运行方式、Datacheck 选项，以及非空 Fortran/oldjob 文件元信息生成键。同名不同目录、源文件元信息或选项改变会分开记录。缺文件时不能沿用该模型历史。

这是估计记录的匹配条件，**不是整个模型依赖闭包的内容验证**：不会递归校验 INP include、用户子程序外部资源等。旧样本可能没有经历后续高内存步骤；峰值和安全系数仍只是调度参考。

峰值、估计和采样数保存在 `scheduler_state.db` 的 `scheduler_meta` 内，键前缀 `memory_profile:`。它是兼容 schema 1 的附加元信息，旧读者可忽略，既有作业/事件表不改变。损坏的单条历史忽略但不删除；写失败保留本次内存记录并重试，不能因此重复执行计算。队列持久化失败仍暂停新派发并保留原执行器监控。

重新执行生成新的 attempt，当前占用与本次采样归零，历史估计仍可参考；已结束 attempt 的迟到回调不能覆盖新记录。停止与关闭继续遵循原退出协议。

## 代码和验证

历史查找只在存在已保存历史时读取文件元信息；没有历史时仍使用本次观测/参考估计，但不为查找不存在的记录遍历模型路径。同一轮投影中，相同文件路径共用一次解析和stat（INP、子程序及oldjob都适用）；每轮重新建立缓存，文件大小/修改时间变化、删除和恢复可重新判定，不跨轮沿用旧文件身份。估计值仍按作业ID、CPU/精度等配置分别计算。没有活动归档时，调度不额外解析目录来检查不存在的归档冲突。准入公式和已有历史键格式均不变。

`packaging/verify_scheduler_load.py <完整目录或--source> <ControlPlaneHost.Tests.exe>` 使用261行隔离队列（256条暂停记录共用一个微型INP），5次真实自有非求解进程与正式客户端检查CPU/内存等待、停止/终止、失败、恢复和状态读取。声明的资源用于验证准入，每个helper仅约8MiB缓冲，不是CPU满载、Abaqus/MPI、261个不同工程模型或网络盘性能验收。具体响应时间及失败证据见TASK-002。

追加 `--distinct-held` 时暂停记录使用独立目录/文件，队列合计261个不同源路径。现有冻结包此模式已通过：260次GET中位38.81ms、P95 279.41ms、最大446.39ms，资源准入和5次执行/提醒重启恢复继续通过。它覆盖本地独立文件路径元信息查询，文件内容仍为微型合成输入，不能外推到网络盘、工程解析、Abaqus/MPI或CPU压力。

- 采集：`modules/submitter/runtime_observation.py` / `ProcessSnapshotCache`、`observe_local_job`；`local_job_execution.py` / `execute_local_job`。
- 学习：`modules/control_plane/local_memory.py` / `LocalMemoryMonitor`，复用 `modules/submitter/memory_monitor.py` / `MemoryMonitorService`。
- 接入：`LocalQueueRuntimeManager._receive_observation`、`_flush_observations`；`LocalQueueScheduling.reserve`；`JobQueueService._scan_external_roots`。
- 投影：`job_queues.py`、`JobQueueContracts.cs`、`JobOverviewPage.xaml.cs`、`JobQueuePage.xaml`。
- 测试：`tests/submitter/test_runtime_observation.py`、`tests/control_plane/test_local_memory.py`、`tests/winui_host/MemoryPresentationChecks.cs`。
- 实际 Windows 进程验证：`.\.venv\Scripts\python.exe packaging/verify_local_memory.py`；冻结包加 `--bundle <AbaqusTools目录>`。程序在 GPTWork 创建 96 MiB Python 测试进程，核对身份/占用/历史、两次启动和退出，不调用 Abaqus 求解，不改原模型。测试失败时保留未确认结束的自有后台并打印 PID，先检查原句柄，不重复启动。

实际回执、失败和未验收范围见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

2026-11-18 对已运行的 GJA-13_V40D 做只读核对：Standard 主进程及 SMAEqsDirSolverUnsymmetric 子进程均被识别，三个快照 PID/创建时间一致，快照内 RSS 求和与监测输出一致，最后合计 20514975744 字节。未控制作业、未读写 ODB 内容或启动新求解。扫描耗时首轮 13.43 秒、后两轮 0.258/0.298 秒；这是单次环境实测，冷启动延迟仍需关注，不能泛化为全负载性能结论。回执 `GPTWork/live-solver-memory-045301de9317/verification.json`，不代表 MPI/多作业高负载/原生显示验收。
