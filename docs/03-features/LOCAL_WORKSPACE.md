# 本机工作目录准备（F003/F005）

本机正式队列在启动 launcher 前准备 INP 和 Restart 前置文件。WinUI 通过控制面调用此流程；PySide6 对照入口保留。本说明只覆盖准备阶段，归档仍有下述未完成项。

## 输入与顺序

输入为队列条目的源 INP、实际 INP、作业名称、计算根目录、oldjob、用户子程序、CPU/内存/GPU/精度，以及同名结果策略 backup/overwrite/cancel。无计算根目录时使用现有 INP 所在目录；指定根目录时使用其下以作业名命名的目录。

先生成只读准备计划并验证命令，再创建目录/复制文件。校验包括源文件、作业名称、计算路径、已有目标类型、当前及前置作业 LCK、oldjob 名称冲突、子程序存在性、执行参数和同名结果策略。已知校验失败时不会先覆盖目标 INP 或前置文件。目录链接（包括 Windows junction）、目标文件链接及同名结果目录会明确拒绝，不沿链接覆盖其他目录。根目录本身按解析后的实际路径使用。

## 文件写入和命令

- 每个文件先写入同目录的独有临时文件，复核取消、LCK、源文件元信息及目标状态后，再替换目标。失败不会先删除该文件的旧目标；已有同名临时文件不会被本次操作接管或删除。
- 输入文件复制；Restart 文件沿用优先硬链接、不可用时复制的规则。源和目标本来是同一个文件时直接复用，避免 SameFileError；其他硬链接目标通过替换目录项更新，不改其原始内容。
- 同名 `.odb`/`.sta` 的备份、覆盖或取消策略保持原义。备份/覆盖发生在准备成功后、启动前。
- 相对子程序路径先转换为绝对路径，避免进入计算目录后解释成另一位置。数据检查命令的 INP 基名包含空白、`&`、括号或 `^` 时加引号；普通文件名保持兼容。本次不声称已完成所有 Windows 命令字符的通用转义。

## 取消、错误与恢复

准备前、逐文件处理间和发布前检查取消。进程启动与接受取消使用同一把控制器锁，已接受的取消不会再启动新 launcher。取消返回「终止」，普通准备错误由队列登记「失败」并保存具体原因与 attemptId。后台重启会恢复该失败记录；仅有失败作业时「开始队列」返回没有可调度作业，不自动重新执行。用户核对目录和原因后，可明确重新排队。

这是**逐文件保护，不是整个目录事务**。稍后文件失败时，先前已成功发布的文件可能保留；新建的工作目录也可能保留。只清理本次拥有的临时文件，清理失败会记录日志并保留现场。源变化比较使用设备/文件身份、大小和修改时间，不是完整内容摘要。外部进程在检查间创建 LCK 的竞争仍可能存在，本流程不代替求解器自身的锁。

## 验证与未完成范围

源码回归包括：已存在 LCK 时字节和路径保持、前置缺失、错误参数、取消、复制失败、源变化、同文件输入、真实 NTFS junction/硬链接、临时文件碰撞；实际 Windows 回显进程验证含空格/`&` 的 INP 是一个参数。真实 HTTP 测试验证拒绝原因、失败持久恢复和禁止自动重试。均使用 GPTWork 下微小夹具，未修改原始工程数据、未启动 Abaqus 求解。

归档已改为复制校验后完整发布，独立报告归档结果；崩溃恢复/独立重试、跨卷负载和实际业务验收仍待完成，详见 [归档说明](LOCAL_ARCHIVE.md)。不能把本阶段通过写成整个提交、归档或 WinUI 迁移完成。

源码入口：`modules/submitter/local_workspace.py` 的 `LocalWorkspacePlan`、`plan_workspace`、`prepare_workspace`、`check_existing_results`；`modules/submitter/local_job_execution.py` 的 `execute_local_job`、`LocalJobProcessController.start`；`modules/submitter/command.py`。

测试入口：`tests/submitter/test_local_workspace_safety.py`、`tests/submitter/test_local_job_execution.py`、`tests/submitter/test_job_draft.py`、`tests/control_plane/test_workspace_preflight_api.py`。实际命令、失败与候选包回执见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。
