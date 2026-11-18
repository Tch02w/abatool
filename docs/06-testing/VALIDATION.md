# 验收记录与已知缺口

F027最新完整包 **`GPTWork/release-win-x64-10aba0ad350a/AbaqusTools`**（干净e31a358）完成1662文件/19worker用户账户摘要、包内依赖 `GPTWork/bundle-probe-v7sw1_nd/verification.json`、正式主机启动/API/退出检查。新提醒补发 `GPTWork/archive-notice-live-2af35a395468/verification.json` 与原归档恢复 `GPTWork/archive-recovery-live-7e74fa0a82cd/verification.json` 均verified，全部自有进程结束，无Abaqus。前者验证已保存结果而未回调时结束生产者、清除队列、正式客户端补发/已读、二次重启仍已读；两者核对原输入及完整归档摘要。下方新包待验状态由本回执补齐；原生/跨卷/工程负载/目标机仍未覆盖。

归档提醒最终相关回归 `GPTWork/archive-notice-delivery-20261118.xml/log` **86项通过（202.82秒）**，含5项补发/损坏/取消/缓存/元数据一致性、归档恢复/核心、通知、关闭、执行和WinUI壳层；覆盖范围不同于原生视觉验收。新完整包仍待验证，下方“最终相关检查待验证”由本项补齐。

F027归档提醒补发源码：`GPTWork/archive-notice-live-5dbd1b38a22d/verification.json` verified，实际结束已保存结果但未写提醒的自有进程、删除夹具队列，新后台仍补发；正式C#客户端已读后第二次重启不重复。最终文件摘要与原INP不变、全部自有进程结束，无求解。C#14项通知/定位检查及既有主机检查通过，Release零警告/错误26.35秒。4项初轮专项通过；最终相关检查/新完整包待验证。失败与准确进程状态见TASK-002顶部，不把首轮4秒等待超时当作缺陷断言复现。

归档恢复最终完整包 **`GPTWork/release-win-x64-8791f815c891/AbaqusTools`**（干净源码 `6cb343d6e7ead730a0f00ff36169f98a448b1d4c`）已通过1662文件/19worker的用户账户摘要核对、依赖 `GPTWork/bundle-probe-ugqe389y/verification.json`、正式主机 `GPTWork/archive-observation-frozen-host-20261118.log`。冻结恢复 `GPTWork/archive-recovery-live-49c8ff630a0e/verification.json` verified：实际中断自有复制/清理进程，新后台经正式客户端恢复原执行、复用完整副本、完整SHA256、源输入不变、第二次重启和提醒无重放。首次读取状态2.5/2.9ms，仅代表该小夹具；全部自有进程结束，未运行Abaqus。下方首包失败后的“待重建”已由本回执补齐。原生、真实跨卷/大文件及其他整体迁移缺口仍未完成。

归档恢复打包复核发现：首包 `GPTWork/release-win-x64-89d3b6ab518e/AbaqusTools` 来源干净 `fc7f8b8`，1662 文件/19 worker、依赖/正式主机启动通过，但冻结恢复首次读取状态超时，回执 `GPTWork/archive-recovery-live-e14df1f5caa0/verification.json` failed，所有自有进程结束，未认定通过。定向检查 `archive-observation-before-20261118.log` 1 项失败，证明已确认求解完成的归档仍在自动扫描目录。将恢复观察和显式监测目录分开，仅自动扫描活动/未知记录后，`archive-observation-final-20261118.xml/log` **79 项通过（38.39 秒）**，源码真实进程回执 `GPTWork/archive-recovery-live-df2804ad50e8/verification.json` 再次通过。新冻结包待重建验证，旧失败现场保留。

归档恢复最终相关检查 `GPTWork/archive-recovery-delivery-20261118.xml/log` **185 项全部通过（96.09 秒）**，包含归档核心/恢复、执行器、真实 HTTP、队列/调度/通知/关闭、WinUI 壳层与 47 项文档导航；与下方集合重叠，不累计。没有把模拟/壳层检查视为原生业务页验收。

2026-11-18 F005 独立归档恢复：`GPTWork/archive-recovery-final-20261118.xml/log` **40 项通过（34.85 秒）**，覆盖 14 项恢复核心、6 项真实 HTTP、20 项调度。之前相关回归 `archive-recovery-regression-20261118.xml/log` **117 项通过（68.60 秒）**；集合重叠不累计。C# `archive-recovery-host-tests-20261118.log` 11 项归档显示/兼容及原有检查通过，原生 Release `archive-recovery-winui-20261118.log` 零警告/错误（22.42 秒）。源码真实进程回执 `GPTWork/archive-recovery-live-323ba9721d6f/verification.json` verified：复制中、部分清理后结束自有进程，原生跨进程锁释放，新后台正式客户端恢复原执行、复用完整副本、全摘要校验、源 INP 不变、第二次重启及提醒不重放；所有自有进程结束，没有启动 Abaqus。新冻结包、跨卷负载和原生操作尚未验证。以下为上一阶段发布保护证据；本次不以其替代新恢复功能验收。

F005 归档发布保护：旧版关闭清理仍移动源文件、坏根路径异常的 2 项复现失败已保存，`GPTWork/archive-before-20261118.xml/log`。改为目标盘复制校验、完整发布、可选清理并独立报告归档状态后，最终 **34 项归档/执行/API 通过（6.79 秒）**，`GPTWork/archive-final-20261118.xml/log`；相关队列/调度/通知/关闭/准备/壳层 **105 项通过（67.07 秒）**，`GPTWork/archive-regression-20261118.xml/log`。包含真实 NTFS junction、Windows 子进程在发布前/后中断、失败记录重启恢复；未运行 Abaqus。C# 新增 6 项展示/兼容和既有检查通过，Release 零警告/错误。独立归档恢复/重试、实际跨卷/大文件和原生界面仍未完成，见 [归档说明](../03-features/LOCAL_ARCHIVE.md)。

归档完整包 **`GPTWork/release-win-x64-2c2808add94d/AbaqusTools`** 来自干净 `1f295df`，1662 文件/19 worker 摘要和用户账户可读检查通过。依赖 `GPTWork/bundle-probe-p4tay3kv/verification.json`、本轮正式 C# 主机 `GPTWork/archive-frozen-host-20261118.log` 通过。冻结正式执行器回执 `GPTWork/frozen-archive-5538576f393c/verification.json` 为 verified：非工程夹具分别归档成功并清理、归档失败且保留结果；两次后台启动保留同一执行/归档状态，提醒正确，没有自动重算，清单完整摘要及源 INP 不变。后台/夹具四个自有进程均结束，没有 Abaqus 求解。文档导航 47 项通过；不是归档中途崩溃后自动接续证明。

F003/F005 工作目录准备：旧代码在已有 LCK 时仍先改写输入和 Restart 文件，复现日志 `GPTWork/workspace-before-20261118.log`；现改为只读计划和命令校验在前、逐文件临时写入后发布，加入准备取消与启动同步保护。扩展回归 110 项通过（137.87 秒），最终专项含真实 HTTP/重启 **35 项通过（11.45 秒）**，分别为 `GPTWork/workspace-regression-final-20261118.xml`、`GPTWork/workspace-delivery-final-20261118.xml`。含真实 NTFS junction/硬链接、复制中取消/失败、源变化、临时名碰撞和 Windows 回显参数验证；未运行 Abaqus。测试初稿对重启后的开始请求预期 202，实际正确返回没有可调度作业 409，已修正测试而非修改产品防重试行为。不是全目录事务、完整源摘要或归档完成验收；范围见 [准备说明](../03-features/LOCAL_WORKSPACE.md)。

准备保护完整包为 **`GPTWork/release-win-x64-e3e69bc08715/AbaqusTools`**，干净来源 `4f40281`，1659 文件/19 worker 全摘要和用户账户可读检查通过。依赖 `GPTWork/bundle-probe-vun0fu70/verification.json`、正式主机 `GPTWork/workspace-frozen-host-20261118.log`、冻结 LCK 拒绝/两次重启 `GPTWork/frozen-workspace-1ac420a2e39b/verification.json` 均通过；冻结正常启动/取消/历史恢复 helper 为 `GPTWork/local-memory-live-c608394af626/verification.json`，两个独立执行、源文件不变、无自动重放通过。本轮未重复通知专项，未启动求解或原生窗口，全部自有进程结束。文档/壳层/API 81 项通过；不与重叠测试累计。

F008 状态读取响应优化：旧版在阻塞远端刷新期间 GET 连接视图超过测试的 2 秒等待界限，失败回执 `GPTWork/remote-responsive-before-20261118.xml`。独立快照发布后，新专项 7 项及远端/通知/关闭/壳层相关 **127 项通过，187.46 秒**，`GPTWork/remote-responsive-regression-20261118.xml`；C# 新增 4 项显示/旧协议兼容与既有检查通过，Release 零警告/错误。验证覆盖慢通信时读取、连接切换不沿用旧资源、错误清除忙态、返回值独立和实际命令继续串行。真实 SSH、原生资源页仍待验证；不能据本修正宣称历史 `remote-jobs` GET 的全部偶发超时已解决。

本轮 F008 完整包为 **`GPTWork/release-win-x64-f4d22485d254/AbaqusTools`**，干净来源 `6890ffa`，1658 文件/19 worker 全摘要和用户账户可读检查通过。包内依赖回执 `GPTWork/bundle-probe-p6825n94/verification.json`，正式 C# 主机日志 `GPTWork/remote-responsive-frozen-host-20261118.log`，冻结接口/两次启动配置恢复回执 `GPTWork/frozen-remote-snapshot-7f0a7826cef3/verification.json` 均通过。PIDs 161360/180528 已结束，描述文件清除；无 SSH/求解，慢 I/O 由源码真实 HTTP 隔离夹具覆盖。最终源码专项/文档 51 项、交接前壳层/文档 79 项通过，集合重叠不累计。

11 月 18 日补充 F012 冻结进程中断验收：`GPTWork/frozen-batch-interruption-691d9fb533f3/verification.json`。最新完整包的隔离后台在测试子进程仍存活时被中断；第二次启动恢复暂停批次与 `ODB_MERGE_INTERRUPTED` 子任务，继续请求明确失败，后续阶段未启动；第三次启动恢复同一失败记录。计划两阶段、仅一条子操作/一次测试命令，三份夹具摘要未变、没有发布结果。三个后台和四个已捕获后代 PID 均确认结束，未启动 Abaqus。这补充冻结进程生命周期证据，不代表真实 ODB 内容或真实 Abaqus 崩溃验收。工具及续接点见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

F028 最终完整目录 **`GPTWork/release-win-x64-d1ad1556cf70/AbaqusTools`**（干净 `35b2372`）已从用户账户核对 1658 文件/19 worker 全部摘要、包内依赖，并通过本轮 C# 正式主机的包内预览/入队/保留/撤销与安全退出。回执 **`GPTWork/execution-options-host-d1ad1556cf70/verification.json`**，没有求解、SSH 或原生交互；全部自有检查已结束。下文“完整包待验”由本回执补齐，原生/GPU 实测和整体迁移仍未完成。

F028 GPU/Explicit/ODB 精度已贯通新建、队列、实际启动及恢复。扩展 **138 项通过，178.86 秒**（`GPTWork/execution-options-final-20261118.xml`），C# 新增 11 项及原有主机检查通过，包含真实 HTTP 预览/入队/保留/撤销和实际 Windows cmd/PowerShell 参数回显；没有 Abaqus/GPU 求解或 SSH。初次 UI 构建类型错误已修正，后续 Release 零警告/错误；最后坏草稿保留和能力检查已构建通过（13.03 秒），46 项能力/API/文档检查通过；完整包仍待验证。详情见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。以下候选为上一轮，不含 F028。

F027 新完整目录 **`GPTWork/release-win-x64-2df945d26036/AbaqusTools`**（干净 `2ff6740`）已通过用户账户 1657 文件/19 worker 摘要、包内依赖和本轮正式 C# 主机启动/API/退出。冻结通知双后台/实际等待 helper/正式客户端回执 **`GPTWork/local-memory-live-966282df5338/verification.json`** 确认两次执行、持久恢复、已读和新提醒，无自动重放且源不变。全部自有进程已结束，未执行 Abaqus/SSH 或原生操作；下文“完整包待构建”由本回执补齐。

F027 本轮源码提醒/跨后台恢复/已读确认已验证；API、提取取消、真实远端恢复进程、通知和关闭专项 **48 项通过**，最终 Release 零警告/错误，C# 新增 10 项及既有检查通过。扩展初轮为 **289 通过 / 2 失败**，不是全通过；成功响应未读取可选正文的问题已取得旧实现失败/新实现通过的真实 TCP 证据并修正，远端负载下 5 秒超时仅专项复核通过。源码真实 Windows 双后台/96 MiB helper/正式 C# 客户端回执 `GPTWork/local-memory-live-88f62b2d8635/verification.json`；全部自有进程已结束，没有 Abaqus/SSH 或原生操作。新完整包待构建，准确命令、失败和续接点见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。以下包属于前一阶段。

F008/F010 新完整目录 **`GPTWork/release-win-x64-a7e34c128937/AbaqusTools`**（干净 `7e09e1a`）已通过用户账户 1655 文件/19 worker 摘要、包内依赖和当前正式 C# 主机启动/API/退出；独立连接文件已清理。本轮检查均已结束，旧原生窗口未替换。下面源码阶段“完整包待构建”由本回执补齐；真实 SSH、MPI、原生操作和其他迁移缺口仍在，见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

2026-11-18 F008/F010 持久恢复：扩展 `remote-recovery-broad-20261118.xml` 为 291 通过/1 失败（结果提取取消路径 HTTP 被 Windows 中止）；随后 `remote-recovery-final-20261118.xml` 54 项通过，覆盖该路径。实际 PowerShell 双后台进程检查 `remote-recovery-process-20261118.xml` 1 项通过（15.83 秒），启动回执丢失后退出旧后台、任务仍存活、新后台接回原 PID、启动计数 1、最终稳定成功，回执 `GPTWork/pytest-remote-recovery-process/test_real_launcher_survives_ba0/verification.json`。C# 6 项恢复显示与原有主机检查通过。此证据是本机真实脚本/进程，不是 SSH、MPI 或原生页面验收；新完整包待构建。见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。以下为前阶段记录。

最后记录字段保护及不可读控制专项后，`remote-recovery-delivery-20261118.xml` **81 项通过，127.54 秒**，包含恢复、服务器、传输、关闭和 42 项文档检查；最终 Release 零警告/错误（13.56 秒），所有修改 Python Ruff 通过。两个测试后台和实际 launcher/helper 已确认结束。完整包另验，不把构建代替发布验收。

F010 最终候选 **`GPTWork/release-win-x64-b2bb97c3929a/AbaqusTools`**（干净 `11ee6ff`）已通过用户账户 1654 文件/19 worker、包内依赖和正式主机启动/API/退出；所有本轮测试/构建已结束。回执见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。下段源码阶段“新包待验证”已由此回执补齐，真实 SSH/原生/持久恢复的缺口仍在。

11 月 18 日本轮 F010 修复数据检查无输出误成功、完成文本提前终结，以及重复追加远端日志；区分 DAT/MSG 警告诊断与明确错误。最终远端/服务器/传输/关闭相关 **50 项通过**，`GPTWork/remote-confirm-final3-20261118.xml`，包括实际本机执行生产 PowerShell 启动/探测脚本，未连接 SSH 或调用求解。F005/F007 对已运行 GJA-13_V40D 的三个只读快照覆盖主进程和真实求解子进程，回执 `GPTWork/live-solver-memory-045301de9317/verification.json`；首轮扫描 13.43 秒冷启动延迟仍需关注。新 F010 完整包待验证，迁移远端恢复和真实场景仍有缺口，见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

11 月 18 日 F005/F007 内存观测与历史已实现，314 项扩展回归通过；末次外部刷新时间戳、首样本立即保存和 85% 预算修改后 45 项专项通过。C# 新增 6 项显示检查及已有主机检查通过，Release 0 警告/0 错误，文档导航 41 项通过。源码实际 96 MiB helper 两次后台启动、历史恢复、明确重新排队和正常退出通过；首样本延迟的失败已修正并保留。最终完整包 `GPTWork/release-win-x64-5a09eb59688b/AbaqusTools`（干净 `a4e8212`）已从用户账户核对 1653 文件/19 worker、依赖、正式主机及冻结内存验证；双启动和历史回执 `GPTWork/local-memory-live-aafe45770a9f/verification.json`。本轮自有进程已结束，未调用 Abaqus 求解。原生悬停及真实 Abaqus/MPI 高负载未验收，详见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。以下包记录属于上一阶段。

本轮最终完整包 `GPTWork/release-win-x64-b0e12f955ac4/AbaqusTools`（干净 `d5b661e`）已通过用户账户 1651 文件/19 worker、包内诊断、正式主机和冻结关闭检查。首包 `8e27c8c8cb26` 的队列调度状态滞留已修正，32 项相关检查通过；最终 `GPTWork/frozen-close-d76ed1a80c40/scheduler-verification.json` 确认队列 API/文件与数据库同为 CANCELED、执行身份一致，测试命令仅一次，后台正常退出且源夹具不变。原始模型与原生窗口未操作，详情见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

核对日期：2026-11-17（F020 分组出图及 F021 结果浏览）。历史测试数不与本次测试累计相加。GPTWork 是本地忽略目录，新机器不会随 Git 自动获得其中的样本和报告。

11 月 18 日继续 F004/F005 原生统一调度：Release 0 警告/0 错误，修正后扩展回归 **299 项通过**（`GPTWork/native-scheduler-regression2-20261118.xml`）；最新专项、适配器和文档 **67 项通过**，正式 C# HTTP 关闭 **5 项通过**。首轮损坏队列阻断服务启动的失败已保留并修正。覆盖优先级/CPU/绝对内存/目录约束、两次重启观察、未知保护、线程启动失败、保存失败继续监控/只重试保存、迟到回调与 Core 未知记账；重叠检查不累计求和。最新完整包仍属前阶段，原生业务、动态内存学习与真实负载未验收；命令及证据见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

## 当前证据矩阵

11 月 18 日关闭流程新增后台继续/合作停止/取消、原始输入草稿与固定实例提交。最终全控制面 + 正式 C# HTTP 客户端 **222 项通过**（`GPTWork/close-full-final-20261118.xml`），包括活动传输保留；11 项辅助进程生命周期、1 项创建竞争、2 项丢回执与 7 项纯草稿存储检查通过。文档、八页输入绑定和壳层最终 75 项通过，Release 0 警告/0 错误。第一轮 2 失败/218 通过的 Windows 拒绝请求断连已修正，失败证据保留。上述证明程序/协议与存储边界，不证明原生八页关闭重开或真实远端。

新完整目录 `GPTWork/release-win-x64-60ea97c39143/AbaqusTools` 为干净来源 `d4d70e5`；用户账户核对 1649 文件/19 worker、包内依赖诊断、正式主机启动/API/退出通过。冻结关闭 `GPTWork/frozen-close-f5d19765bc11/verification.json` 证明后台继续/取消保留测试作业，合作停止后线程清理、后台自行退出 0、连接文件消失、源夹具摘要未变。没有执行 Abaqus；首次夹具未处理终止参数的失败已保留，两个自有后台均结束。下面 `b53b0f4ca2b4` 是前一阶段候选。

本轮完整目录 `GPTWork/release-win-x64-b53b0f4ca2b4/AbaqusTools`（干净 `aa0420f`）在用户账户核对 1648 文件/19 worker、启动/API/退出与依赖自检通过；`GPTWork/frozen-shutdown-a5b9765a96ec/verification.json` 证明运行/调度停止后仍活动时拒绝退出，全部收尾后允许退出并拒绝新启动。使用等待测试命令而非 Abaqus，进程和描述文件均已清理；前两次辅助脚本失败在任务记录中保留，不计为通过。

F012 新增真实批量验证 `GPTWork/real-result-batch-750883913dd9/verification.json`：正式 C# HTTP 客户端 + 冻结后台，GJB-15 两个兄弟目标分别 8 步/70 帧、12 步/63 帧，均核对历史输出，后一目标保留 4 个空步骤提示。两次冷启动的任务与子操作身份、两个结果和回执的完整摘要相同，三份源副本摘要未变，中文含空格输出通过。43108 退出 0，两个自有后台已结束；未启动求解。三层连续链、原生 UI 与本轮新退出改动不在该证据覆盖范围。

11 月 18 日新增 F001 全受管后台退出保护：208 项控制面回归通过（含 10 项退出专项），回执 `GPTWork/control-shutdown-regression-20261118.xml`；10 项 C# 实际辅助进程生命周期检查通过，Release 0 警告/0 错误。检查覆盖活动本机作业、终态后的队列持久化、停止调度竞争、后处理取消清理、文件传输、五类 Future 收尾及关闭后任务准入。仅使用隔离执行器与自有辅助进程，没有启动求解或实际 SSH；全应用关闭选择/页面草稿/原生窗口流程仍未验收。详情见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

| 功能 | 可定位证据 | 已证明 | 尚未证明 |
|---|---|---|---|
| F012/F026 冻结批量恢复及目录候选（11-18） | `GPTWork/release-win-x64-6cbfd68f63f6/inventory-verification.json`、`GPTWork/frozen-batch-recovery-001fad0945b9/verification.json` | 用户账户核对 1647 文件/19 worker；2 次冻结后台启动恢复同一批任务、测试命令只执行 1 次、首阶段失败不启动后续阶段；正式主机与包内依赖诊断通过 | 原生页面、真实多阶段模型、目标机器；未发布本轮 ZIP/二进制 Release |
| F012 后台批量与恢复（11-18） | `GPTWork/control-batch-regression-20261118.xml`、`GPTWork/result-batches-final-20261118.xml`、`tests/control_plane/test_odb_result_batches.py` | 完整控制面 198 项及最后的批量/单步恢复专项 33 项通过（重叠不相加）；隔离进程真实退出、子任务去重与已发布结果续接、祖先共享、来源/中间结果变化拒绝、停止等待、部分结果保留、记录损坏与联合退出；C# 批量契约 6 项、Release 0 警告/0 错误 | 真实多阶段工程 ODB、原生读取/继续/停止；不代表全应用持久恢复 |
| F026 最终包用户账户访问和恢复（11-18） | `GPTWork/release-win-x64-c39d9688d751/archive-verification.json`、`GPTWork/frozen-merge-recovery-658jvpc7/verification.json` | 用户账户逐项核对 1645 文件/19 worker，ZIP CRC、正式主机启动/API/退出、两次冻结后台启动和请求去重通过；修正临时发布目录仅构建账户可读的问题 | 原生页面、真实外部进程崩溃、无开发环境目标机器 |
| F013 持久记录和恢复（11-18） | `GPTWork/control-history-regression-20261118.xml`、`tests/control_plane/test_odb_merge_recovery.py` | 178 项控制面回归，含测试进程真实终止、HTTP 重建、请求去重、损坏/磁盘失败、已提交结果保护、日志节流和联合退出；C# 3 项恢复信息检查通过 | 外部 Abaqus 实际运行中崩溃、原生页面恢复；F012 新证据见本表 |
| F026 含 F013 的目录候选（11-18） | `GPTWork/release-win-x64-g_asfnjp/archive-verification.json`、`GPTWork/package-merge-probe/bundle-probe-xb9j82ur/verification.json` | 干净 16859c4 提交构建、1644 文件与 19 worker 核对、包内诊断、正式主机启动/API/退出及 ZIP CRC 通过 | 原生窗口、无开发环境机器、安装和二进制发布 |
| F013 合并内容校验（11-18） | `GPTWork/merge-real-fv8_supj/verification.json`、`GPTWork/merge-regression-20261118.xml` | V20D 8 步/70 帧场值及历史一致；U100D 12 步/63 帧、四个无结果帧步骤如实保留，历史关闭/压缩/额外副本与发布通过，原始三份 ODB 全文件摘要不变；99 项相关回归及 C# 批量执行器 10 项通过 | 真实多节点、原生操作、进程崩溃恢复仍待验收 |
| 全项目自动化基线（11-18） | `GPTWork/migration-tests-20261118.xml` | 648 测试和 9 子检查通过，测试发现范围固定为 tests | 八页全部原生交互、真实 SSH 和无开发环境发布 |
| F021 查询性能（11-18） | `GPTWork/result-list-performance-20261118.json` | 同一真实目录 797 条、每页 500 条，十次交替测量中位耗时 51.18 → 30.32 ms，响应相同 | 不同存储介质与更大目录下的收益 |
| F021 结果清理（11-18） | `tests/winui_results/Program.cs`、Release 候选 | 清理路径校验、已有异步生命周期与表格测试、原生构建通过 | 系统回收站、部分失败、关闭等待与最终布局的原生点击 |
| F020/F022 GIF 双模式（11-17） | `GPTWork/gif-timing-s9udw0t8/verification.json`、`tests/postprocessor/test_animation.py` | 逐像素和逐帧延时核对四份真实模型动画。25 帧/秒对应 4.04 / 1.64 秒，统一 4 秒对应 25.25 / 10.25 平均帧率。两模式的请求、格式计时、工作区兼容及 WinUI 构建均通过 | 原生业务页切换与点击导出，播放器实际显示节奏 |
| F020 完整时程 GIF（11-17） | `GPTWork/group-full-gifs-ri_g396m/verification.json` | 在相同分组色标下，完整时间轴与混凝土 Mises 的逐帧 PNG 序号、分析步和帧号匹配。成品逐帧解码，GJA 101 帧 / 20.2 秒，GJB 41 帧 / 8.2 秒，均为 1500×1000、5 帧/秒 | WinUI 点击导出、其他用户模型和参数组合 |
| F020 命名组固定色标与 WinUI 编辑（11-17） | `GPTWork/group-render-check-c62b13k0/verification.json`、`tests/postprocessor/test_group_render_limits.py`、`tests/winui_postprocess/Program.cs` | GJA/GJB 实际预扫描按 101 / 41 帧算范围，两份 ODB 副本各取中间帧和末帧渲染；60 张自动范围 PNG，Mises 静态图与抽查动画帧色标区域分别逐像素一致。整组缺范围、单成员漏扫均报错，手动修复后 GJB 27 张 PNG。WinUI 构建与编辑数值边界检查通过 | 完整时程重新出图、所有模型/变量的成图像素对照、业务窗口鼠标及键盘纠错体验 |
| F021 WinUI 翻页与表格预览（11-17） | `GPTWork/result-browser-verification-20261117/verification.json`、`tests/winui_host/test_results_api.py`、`tests/winui_results/ResultBrowser.Tests.csproj` | WinUI 使用的 C# 客户端经 HTTP 读取 GJB-15 的 797 条匹配记录（500+297、无跨页重叠、返回第一页顺序一致）；CSV 18×24 和 Excel 10×6 逐格匹配；独立模型检查覆盖跨列组复制、制表符/引号/换行与空值 | 原生业务页的布局、鼠标选区、横纵滚动、系统剪贴板及粘贴目标 |
| F017 GJB 原基础流程 | `GPTWork/real-odb-validation/GJB-15-full-pipeline/acceptance-result.json` | 正式批处理返回结果目录；旧验收说明另记录 41 帧/100 截面及渲染产物 | 全部 GJA/GJB 工况、所有灌注桩对照、独立力学精度、原生操作 |
| F021 GJB 结果链 | `GPTWork/real-odb-validation/GJB-15-full-pipeline/result-api-acceptance.json` | 771 索引记录、7 范围节点、CSV 预览 | 所有 UI 预览布局和干净机器部署 |
| F018 GJA 钢筋 | `GPTWork/real-odb-validation/region-api-20261028/verification.json` | MR-1 末帧 2688 条，真实 HTTP/Abaqus，源大小与修改时间未变 | 参考面积的几何独立核对、有限变形当前面积轴力 |
| F019 GJA 实体 | `GPTWork/real-odb-validation/solid-api-20261028/verification.json` | 3 次实际提取，每次 36 行；两帧两切面；集合/整实例一致；参考点平移关系误差最大 0.06245（模型力矩单位） | 独立解析数值基准、所有实体族、所有法向与复杂切面 |
| F019/F021 GJB 混凝土与钢管 | `GPTWork/real-odb-validation/gjb-region-api-20261028/verification.json` | 两个集合各 18 行；常用结果可见、HTTP CSV 预览成功；源大小与修改时间未变 | 用户原生点击验收、全部工况数值正确性 |
| F018/F019 回归 | `tests/postprocessor/test_region_extraction.py`、`tests/postprocessor/test_region_worker.py`、`tests/postprocessor/test_solid_sections.py`、`tests/control_plane/test_region_extraction_api.py` | 2026-10-28 本线程实际运行：45 passed；覆盖校验、输出保护、模拟 CAE 和 API | 这些模拟测试本身不能证明 Abaqus 的截面积分精度 |
| F018 人工梁读取 | `GPTWork/real-odb-validation/known-region-8mgx32gk/beam_all/manifest.json`、`GPTWork/real-odb-validation/known-region-8mgx32gk/beam_local_set/manifest.json` | 两帧的已知 SF/SM 值经生产 worker 读取；校核程序通过梁断言后在实体步骤失败 | 不是用户梁模型（用户没有梁）；整个校核未通过 |
| F019 人工实体解析校核 | `GPTWork/real-odb-validation/known-region-fumxjvn1/verification.json` | 真实 Abaqus 生产 worker；实例集合、装配集合、反向、横向、倾斜切面及形心参考点六组通过；两帧共 198 行，最大绝对误差约 2.0143e-5，源 SHA256 未变 | 均匀应力 C3D8 人工样例，不是所有实体族或真实工程局部应力误差的证明 |
| F025 数字控件与参数说明 | `tests/winui_numberbox/NumberBox.Tests.csproj`、`GPTWork/winui-numberbox-preview-checks/verification-preview-matched.json`、同名 .exit.txt | 生产控件自身原生窗口 35 项通过且 exit 0；完整模板几何、主题切换、占位/焦点/帮助 Header、数值语义；15 处 Inline 入口与说明已构建 | 帮助弹层实际鼠标悬停与业务页布局、完整操作链 |
| F001/F003/F004 窗口与表单 | `tests/winui_layout/WindowLayout.Tests.csproj`、`tests/winui/test_shell_contract.py` | 13 项生产尺寸计算检查；两列布局/响应式入口、导航快捷键保留与容器提示关闭契约；最新 app 构建成功 | 业务页视觉、原生缩小/跨屏/恢复、小屏工作区裁剪后布局 |

2026-10-28 文档交付后的扩大回归：`pytest tests/postprocessor tests/control_plane tests/winui tests/winui_host/test_region_api.py tests/common/test_documentation_navigation.py`，历史记录 **449 passed in 77.54s**。包含旧参数对等、无纵筋、通用提取/失败保护、原生客户端 HTTP 和文档导航；不等同实际原生点击验收。本次文档导航检查发现这条旧命令被写成单一路径，已补命令前缀，不修改路径校验规则。

上一开发阶段记录了 238 项扩大回归、C# 状态测试和 Debug 构建成功；本轮文档工作不把这些视作刚重跑的结果。可执行文件时间此前核对为 2026-10-28 15:09:36；后续应重新构建，不能只按时间认定最新源码已全部编译。

## 当前问题清单

2026-10-28 界面交互最新实现：15 处 `WorkbenchNumberBox` 均为 Inline，右侧并排下/上折线、数值居中、最小宽度 160。完整模板按认可预览统一 40 DIP 高、每按钮 40 DIP、竖分隔线和 5 DIP 圆角；保留原生命名部件和数值处理。15 处说明悬停 180ms 打开、按钮/整个提示区内保持、离开两区 240ms 关闭，保留点击/键盘，无“知道了”；小圆问号 14 DIP、热区 28 DIP。资源表单两列对齐/窄屏换行、队列设置垂直居中、裸 Ctrl+7 提示关闭及窗口限制已纳入。**最新构建通过，业务页视觉/鼠标及跨屏仍待验收。**

此前数字控件自身原生测试窗口完成 **18 项检查**，回执 `GPTWork/winui-numberbox-native-checks/verification.json`；覆盖按钮常显、顺序与折线、数值居中、原生增减各一次、先提交编辑值再步进、硬件上限收缩、0 与 -1 哨兵、禁用、可选参考面积空值/小数、容差 0.0001 步长及普通小数格式。同期 `tests/winui/test_shell_contract.py` **33 passed**；`tests/winui_logs/RuntimeLog.Tests.csproj` **9 项行为检查通过**。这些测试数量各自独立，不累计为业务页验收数量，也不证明后续视觉调整已经验证。

最新候选 `GPTWork/ui-interaction-preview-matched-20261028/AbaqusTools.WinUI.exe` 构建 **0 warnings / 0 errors，11.86 秒**。数字控件完整检查 **35 项、exit 0**，回执在 GPTWork/winui-numberbox-preview-checks；新模板空白/有值正常关窗对照 **2 项、exit 0**，stock NumberBox UIA/聚焦禁用对照 **3 项、exit 0**。曾发生检查完成后测试窗口退出 C0000005，原回执及退出码保留为 verification-before-teardown-fix.json/.exit.txt；调整测试程序释放自身控件、等待 UI 队列、再正常退出后通过，未强制退出或忽略错误。窗口尺寸生产计算 **13 项通过**，故意失败检查按预期 exit 1。

最终项目 `.venv` 执行文档导航 **29 passed**、WinUI shell 契约 **33 passed**，包括本次新路径和资源布局/快捷键提示契约；与上述 C# 检查分别报告，不相加为真实业务页验收数量。

阶段 restored 候选的 8.59 秒构建保留为历史。该阶段启动后窗口出现，但用户按 Esc 停止 Computer Use，随后未继续 UI 操作；未确认其窗口/进程已退出。最新 preview-matched 候选只构建，未替换正在运行的旧窗口。实际业务页日志拖选、复制、滚动、帮助悬停、跨显示器尺寸与完整操作链仍待验证。详见 [TASK-004](../08-handoff/ACTIVE_TASKS/TASK-004-ui-interaction.md)。

2026-10-28 结果提取恢复续验：`GPTWork/real-odb-validation/region-delivery-zfmk0ni6/verification-resumed-2.json` 记录 GJA 钢筋 2688 行、GJB 混凝土/钢管各 18 行实际 HTTP + Abaqus + 索引 + CSV 预览通过；数值与之前成功产物一致，两个测试副本完整 SHA256 前后相同。比较时显式兼容旧 CSV 空实体列及 section_point → cut_index 迁移，原始失败检查和旧结果保留。来源保护/失败发布相关扩大回归 73 passed in 7.07s；这不替代原生点击验收或新的力学精度验证。

恢复版界面验证：C# 对象方法判定 63 项、状态恢复 34 项及既有后处理检查通过；结果浏览异步生命周期 10 项通过；WinUI shell 契约 32 passed。新增晚到进度检查防止新请求尚未获得操作号时，旧回调误入新请求并抛出未处理异常。最终 WinUI Debug 构建 0 warnings / 0 errors（12.43s），输出 `GPTWork/result-extraction-restored-20261028/AbaqusTools.WinUI.exe`。前一候选已实际启动并读取到原生窗口/控制面连接，测试窗口随后正常关闭；最后一次仅增加旧进度归属保护后重建，没有重新完整点击。

原生旧窗口可以读取后处理控件，但点击报 `coordinate input geometry is unavailable`，恢复截图报 `FrameArrived timed out: timed out waiting on channel`；因此 ISSUE-004 仍待验证。已有用户窗口与用户 Abaqus 进程不自动关闭。首次仅指定 OutDir 的构建因默认目录 XBF 被占用失败；同时指定 OutputPath 和 OutDir 后独立构建成功。

| ID | 问题 / 影响 | 复现与下一步 | 状态 |
|---|---|---|---|
| ISSUE-001 | 人工实体 ODB 缺必要截面配置，截面报告只有表头 | 原失败产物保留；补材料/截面并正确指派后六组实体生产提取吻合解析值，不需要修改生产积分算法 | 已解决于人工样例；真实模型仍按适用性验收 |
| ISSUE-002 | 人工样例使用不存在的 `OdbInstance.SectionAssignment`，退出码 0 掩盖异常 | 按 ODB API 改用 `assignSection(region, section)`；保存关闭后生成带 SHA256 的 `.created.json`，新建样例必须校验回执；新增假退出 0 的回归检查 | 已解决 |
| ISSUE-003 | 通用 manifest 对实体积分的 aggregation 描述不准确 | 按 method 区分，先失败后修复；`test_manifest_distinguishes_section_integration_from_point_values` 覆盖两种口径，六组真实实体输出也检查清单 | 已解决 |
| ISSUE-004 | 原生完整点击、布局、关闭重开及取消尚未完成验收 | 历史桌面工具报超时及几何不可用；阶段候选窗口出现后用户 Esc 停止 Computer Use；最新构建和控件自身窗口 35 项不能替代业务页验收 | 最新构建已完成，业务页验收待完成 |
| ISSUE-005 | 通用实体任意对象/法向的独立精度与适用性未完成 | 钢筋参考面积法有明确有限变形边界；实体需解析基准和真实工程对照 | 待验证 |
| ISSUE-006 | 剩余迁移不能沿用历史“全部完成”描述 | 原生升级真实旧版本、重启动/结果批量链、远程/调度持久恢复等按原迁移合同逐项审查 | 待逐项验收，不断言均有缺陷 |
| ISSUE-007 | 通用提取未检测源变化，关闭失败/最后取消可能留下已发布结果 | 源指纹分阶段核对；先关闭再写回执；管理器锁内取消检查后释放批次隔离标记；6 项新增失败复现转绿，含索引隔离回归及真实三组样本 | 已修复并验证；生产为采样变化检测，真实验收另做全文件哈希 |
| ISSUE-008 | 结构对象选择将未知/壳/混合类型默认归入梁 | 根据实际类型匹配 worker 方法，类型不完整时要求重扫，不能提交不支持对象；63 条 C# 方法判定检查通过 | 已修复；原生点击待验证 |
| ISSUE-009 | 目录刷新/索引成功时仍 busy，记录加载被跳过；晚到响应回填旧状态 | 新增 ResultBrowserLoadCoordinator，明确解除忙状态后加载、清空失败残留、请求与索引归属保护；10 项 C# 异步生命周期检查通过 | 已修复；原生点击待验证 |
| ISSUE-010 | 提交/轮询超时被显示为取消，丢失原任务跟踪 | 会话内保留请求/操作号、禁止重复提交、单次只读恢复；正在取消时禁止重按停止；恢复状态行为检查通过 | 已修复；后端重启后的未确认记录持久化不在本次实现范围 |
| ISSUE-011 | 作业概览每次轮询重新赋值日志，清除文字选择 | 同作业相同文本不写；选择/拖选冻结当前文本并合并最新快照，清选后刷新；9 项状态测试通过，已进入合并候选 | 已修复并构建；业务页复制/拖选/滚动待验证 |
| ISSUE-012 | 数字输入原隐藏/Compact，局部改原生模板仍与预览不同 | 15 处统一完整模板和说明；原生自身窗口 35 项与最新构建通过，保持值解析、步进和边界语义 | 已实现/构建，业务页视觉及帮助悬停待验收 |
| ISSUE-013 | 资源表单固定宽度挤左、队列设置行垂直不齐、窗口可缩至内容不可用 | 资源两等宽列/窄屏换行，队列控件居中；客户区最小 1250×690 DIP 按 DPI/非客户区/屏幕工作区计算，13 项检查通过 | 已实现/构建，原生布局与跨屏待验收 |
| ISSUE-014 | 页面表格附近悬浮出无关 Ctrl+7 | 快捷键绑定的 ShellNavigation 包含整个页面，默认自动生成快捷键 ToolTip；关闭其自动提示，Ctrl+7/Ctrl+8 绑定保留 | 已修复/构建，业务页原生悬停待验收 |

## 发布门槛

1. 用户实际模型按真实单元类型、集合、分析步和输出完成正确提取；GJA/GJB 与对应对照案例不得用人工梁替代。
2. 源文件保护、失败结果隔离、取消、重试、配置恢复获得相应层级证据。
3. CSV/图表/云图/动画和结果浏览分别验收，不以某一 CSV 成功覆盖全部功能。
4. 原生入口操作和当前构建在用户环境验证，记录缺陷或限制。
5. 功能、代码、测试、说明和交接状态同步；未验证条件不标完成。

## 怎样更新本页

每完成一个功能填写日期、命令/脚本、数据集或人工样例、证据路径、结果、验证边界。问题解决后保留原因和回归指针，再移入对应任务历史；不能简单删掉失败记录。当前状态只引用本页，不复制整份历史。
