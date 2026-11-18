# 本机结果归档（F005/F011/F027）

归档与求解是两个独立结果。确认求解完成后，原生本机执行器按队列中的归档目录和「归档后清理」选项运行 Qt-free 归档流程。未设置归档目录则跳过；数据检查仍沿用原有不归档行为。PySide6 对照实现保留，尚未切换到本流程。

## 使用与行为变化

填写归档目录后，程序先在目标盘建立独有的 `.partial` 临时目录，复制并校验全部选定文件，再将整个目录改名发布。遇到同名旧归档使用新的唯一目录，不覆盖历史结果。**未勾选清理时保留计算目录中的原文件**；旧本机执行器即使未勾选也会逐文件移动，此行为已修正。

不清理时选择当前作业的 INP/ODB/STA/MSG/DAT/LOG/COM/PRT/SIM/RES/MDL/STT/FIL/PAC，另包含实际源 INP 对应的不同基名输入。其他作业不混入。清理时复制独立作业目录的全部普通文件、子目录和空目录，再逐项清理。原始 INP 位于该目录内、目录不匹配指定计算根目录/作业名、文件或子目录是链接、存在 LCK 时拒绝清理或归档。

复制使用 4 MiB 分块，源读取同时计算 SHA256，目标重新读取核对；源文件身份/大小/mtime 与文件列表在发布前复查。最终目录保存 `.abaqustools-archive.json`，包含执行身份、源目录、文件大小和完整 SHA256。临时目录中的清单即使写完也不代表已发布，必须同时核对最终目录位置。已有文件夹或清单不是新的求解成功证明。

发布后清理仍检查取消、锁和路径，并再次核对每个源/目标文件的摘要，只删除本次已确认的源文件，最后移除空目录；不递归删除目录，不清除新出现的文件。遇到占用、变化或取消立即停止，已经发布的完整归档可保留，尚未清理的原文件保留。检测到已发布文件内容异常则改为「归档需核对」，不能继续当作完整归档。

## 界面、错误与取消

| 归档状态 | 含义及文件位置 |
|---|---|
| 已归档 | 已复制、校验并发布；要求清理时清理也完成 |
| 归档失败 / 归档已取消 | 尚未发布，流程不删除原文件；可能保留 `.partial` 现场，路径在错误说明中 |
| 已归档，清理未完成 | 已发布完整归档，清理中断；计算目录可能只剩部分原文件 |
| 归档需核对 | 检测到已发布文件变化/不可读；停止清理，需核对归档和剩余源文件 |
| 归档待恢复 | 同一次求解已确认完成，但归档没有完整收尾；可在概览恢复 |
| 归档记录异常 | 持久记录损坏或与当前执行/路径不符；拒绝恢复，未知求解不会因此升级为完成 |

队列备注及概览状态卡独立显示归档状态，悬停或运行信息可查看原因和目录。求解已完成时，归档失败不改写成求解失败，结束提醒同时包含归档问题。归档过程中按终止/停止会合作取消归档；不再次终止已经完成的求解器。此时求解仍显示完成，归档显示取消或清理未完成。

读取输出、结束提醒目录和 Restart 前置路径只优先采用「已归档」或「已归档，清理未完成」的最终目录。旧版失败记录若包含部分移动目的地，不从任一半成品目录推断完整 Restart 文件族；依赖保持等待并提示核对。新执行会清空上一执行的归档字段，终态保存不沿用旧归档路径。

## 中断恢复与独立重试

后台确认求解完成后，在队列数据目录的 `archive-state` 保存原始 itemId/attemptId、源目录、源 INP、清理设置、文件身份与阶段；阶段包括 confirmed、prepared、ready、published、done。文件以原子替换保存，同一次归档用操作系统文件锁排除另一后台/线程接管；进程退出释放锁。重启只恢复状态，不自动复制、删除或重新求解。没有有效同次执行记录的旧任务继续走未知状态核对。

操作路径：**作业概览 → 选择本机作业 → 恢复归档**。按钮仅对具有可恢复记录的已完成求解显示；期间可按「取消归档」，不能向已结束求解器发送暂停/恢复。恢复不创建新的求解 attempt，不调用 Abaqus，不重新记录计算内存。归档结束产生独立提醒。

恢复先核对记录与当前执行/配置。未发布时检查源文件身份和清单，逐文件核对完整 SHA256；完整副本直接复用，未完成副本移入同根目录独立 `.recovery-*` 现场后重新复制，不覆盖原文件或历史现场。发布后先核对最终清单和所有文件摘要，再继续清理仍存在且未变化的源文件；上次已删除文件允许缺失，新文件、变化文件、链接、LCK 或损坏归档会中止。整个源目录已清理时，只核对最终归档并收尾。

归档中禁止编辑、重新排队、移除和清除已完成记录；占用队列槽位及退出保护，重叠计算目录也不分配给新作业。更换源目录、原始 INP 或清理选项后拒绝恢复，需还原记录对应配置；归档根目录只允许在发布准备之前更换，旧临时现场保留。已完成且状态一致的记录在启动时不重复写回队列。

真实 Windows 夹具验证已覆盖复制中、部分清理后强制结束自有进程，跨进程归档锁释放，新后台通过正式 C# 客户端恢复原 attempt，完整文件复用、完整摘要、原始输入不变和第二次重启不重放。夹具不是工程 ODB。**尚未完成**：真实跨卷/大文件负载、原生界面操作，以及断电级目录事务。外部程序在检查间修改文件的竞争没有被全目录排他锁消除；坏记录不会自动修复或清除。归档结果已持久保存但独立提醒尚未写入时崩溃，独立重试提醒不保证补发；原求解提醒仍按其执行身份恢复。

复制和完整摘要验证需要额外目标盘空间与读写时间，尤其在清理前复核时；优先保证源数据可恢复。运行进度合并到现有作业事件，复制更新最多每 0.2 秒一次。归档线程收尾前不释放队列槽位/退出保护。

源码：`modules/submitter/local_archive.py`（`archive_job_files`、`cleanup_verified`）、`local_archive_state.py`（`ArchiveStateStore`）、`local_archive_recovery.py`（`resume_archive`）；`modules/submitter/local_job_execution.py`（`run_archive_only`）、`modules/control_plane/local_archiving.py`（`LocalArchiveRecoveryMixin`）、`local_queue_runtime.py`、`local_scheduling.py`、`job_notifications.py`。HTTP 使用现有 `POST /api/v1/local-queue-controls`，`action=retryArchive` 和单个 `itemIds`；重复、冲突或无法恢复返回 409，关闭中返回 503。响应增加队列 `archiveRecoveryAvailable`、运行项 `archiveOnly`。界面：`winui/AbaqusTools.WinUI/Services/JobQueueContracts.cs`、`winui/AbaqusTools.WinUI/Pages/JobOverviewPage.xaml.cs`、`winui/AbaqusTools.WinUI/Pages/JobQueuePage.xaml`。

测试：`tests/submitter/test_local_archive.py`、`test_archive_recovery.py`；`tests/control_plane/test_local_archive_api.py`、`test_archive_recovery_api.py`、`test_local_scheduling.py`；`tests/winui_host/ArchivePresentationChecks.cs`；真实进程检查 `packaging/verify_archive_recovery.py`。证据与剩余工作见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)，决策见 [ADR 0014](../submitter/adr/0014-verified-local-archive-publication.md)。
