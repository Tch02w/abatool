# 作业结束提醒（F003/F005/F010/F027）

新建作业的“结束提醒”同时适用于本机与远端。后台确认完成、失败或取消后生成提醒；“状态未知”、断线、暂停和仅收到部分完成输出都不作为结束。关闭该选项后仍正常执行作业，只不生成提醒。原 PySide6 入口保留自身消息框行为。

本机数据检查（Datacheck）失败同样生成失败提醒，包括实时完成回调和重启补查；与该次执行的成功/终止提醒使用相同的身份去重及已读持久规则。失败不会因为缺少提醒映射而静默消失。回归定位为 `tests/control_plane/test_job_notifications.py`，实际非零退出进程见 `packaging/verify_scheduler_load.py`。

## 原生界面

- 新提醒出现在应用右下角，作业菜单显示未读数量。
- 关闭右下角提示保留未读记录，可从「作业 → 结束提醒」查看。轮询到相同记录时保持静默。
- 「结束提醒」列出作业、状态、记录时间、说明与目录。最多显示 50 条；本页已读后继续显示下一批，未显示的提醒不会被顺带清除。
- “查看作业”仅定位同一执行身份。本机作业重新排队后若旧执行已不在列表，保留原提醒及目录，不跳到同名的新执行冒充原结果。
- 标为已读必须得到后台保存确认；失败时保留未读，提示重试。普通轮询不重建相同提醒列表，不打断复制和滚动。
- 提醒弹层展开时不因新提醒插入而重建当前列表；标为已读或重新打开后更新。本页已读针对实际正在显示的 ID，不误清后台新到的提醒。
- 窗口在后台时，新提醒请求任务栏闪烁，不抢焦点；重新轮询相同提醒不重复请求。依据 [Microsoft FlashWindowEx](https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-flashwindowex)。当前实现不是 Windows 系统通知中心推送；界面关闭且后台继续运行时，未读提醒在下次打开界面后展示。

提醒的“记录于”是后台记录/恢复观察时间，不伪装精确求解结束时间。求解成功但归档失败时，提醒说明归档错误，二者不混为同一种结果。

独立恢复归档的提醒标题为「本机归档」，避免把归档失败误读为求解失败。「查看作业」核对原队列ID和原求解attempt；同名作业的新执行不匹配，原队列已清除时仍保留提醒和归档目录。

## 持久化与性能

控制面连接文件旁的 `job-notifications.sqlite3` 保存记录，沿用单后台持有锁和 SQLite 事务。提醒 ID 由本机 attempt ID / 远端 operation ID 与来源共同生成；同一次执行重放不会重新变成未读，再次明确运行则生成新提醒。已读记录保留用于去重，不按内存条数自动删除用户历史。

完成回调在后台写入提醒，不依赖页面是否打开。后台重启后可补查持久作业终态；补查只覆盖首次创建提醒存储之后提交的作业，不将升级前所有已完成作业一次性弹出。补查每 30 秒最多一次，普通界面每 3 秒读取内存快照；平稳状态不反复读取全部作业历史。提醒记录不保存密码、鉴权令牌或完整求解日志。

写入失败保留内存中的待保存记录并每秒重试；共同关闭检查阻止在待保存时安全结束后台。作业执行不因提醒存储失败而重跑或停止。已读保存失败不会在后台重试中自动标成已读。损坏/占用的提醒历史返回显式错误，保留原文件；应查看作业概览并检查存储，不删除数据库来冒充空历史。在磁盘持续不可写且强制结束后台、同时删除原作业记录的情况下，无法承诺找回未落盘提醒。

### 归档操作的补发记录

启用结束提醒时，独立归档重试先在队列目录的 `archive-state/notifications/<operationId>.json` 保存身份和开始时间，再执行归档。全部文件处理完成时先保存成功回执，随后更新归档阶段和队列；失败/取消也先保存对应结果。通知回调和重启补查使用同一个 `attemptId:archive:operationId`，已读状态由既有SQLite历史去重，不依赖队列条目保留。即使完成回调丢失、随后清除了队列，重启仍能补发已落盘的提醒。

补查仍采用原先的30秒节流；未变化的终态小回执按文件身份/mtime/大小跳过内容读取，不读取归档大文件。未收尾回执先尝试取得同次归档原生锁：仍被执行线程或后台持有时不发中断提醒；锁已释放且结果仍未收尾时显示「归档已中断」，不会当作成功或启动求解。关闭提醒不生成此回执。损坏回执保留并返回补查警告，不覆盖为正常结果；清除已完成队列不删除回执或已读历史。

该机制覆盖归档结果已落盘而提醒回调/SQLite写入未发生的进程崩溃窗口；不承诺在记录盘始终不可写、记录被外部删除或断电破坏后重建未落盘事实。先前已落盘的归档成功不会因之后的队列元数据写入失败被重新标成归档失败，概览仍单独报告元数据恢复问题。

## 接口与配置

- `GET /api/v1/job-notifications`：`schemaVersion=1`、`unreadCount`、最多 50 条 `items`、可选 `persistenceWarning`。按观察时间倒序排列。单条包括 `id/source/executionId/jobId/jobName/status/message/workDirectory/observedAt/read`。
- `POST /api/v1/job-notification-acknowledgements`：`schemaVersion=1, ids=[...]`，只接受 1–50 个已知 ID；重复确认幂等。返回当前未读快照。多条确认逐条保存，后续项失败时已保存的项仍保持已读，刷新可核对。
- 原远端提交增加可选 `notify` 布尔值，省略默认 true；本机沿用已有 `complete_notify`。远端请求幂等比较包含该字段，历史恢复保留用户选项。
- 错误包括 `INVALID_JOB_NOTIFICATION_ACK`、`JOB_NOTIFICATION_NOT_FOUND`、`JOB_NOTIFICATION_HISTORY_UNAVAILABLE`、`JOB_NOTIFICATION_STORAGE_UNAVAILABLE`；接口仍要求既有本机鉴权。后端能力为 `job.notifications-v1`。

## 定位与验收

后台：`modules/control_plane/job_notifications.py` / `JobNotificationManager`；共享记录 `operation_journal.py` 增加可选 ID 字段，旧合并/结果批次/远端记录格式不变。完成入口为 `local_queue_runtime.py` / `_store_result` 和 `remote_jobs.py` / `_touch_locked`，服务与关闭集成在 `server.py`。

归档回执：`modules/submitter/archive_notifications.py` / `ArchiveNoticeStore`；`modules/control_plane/local_archiving.py` 接受重试时保存身份，`modules/submitter/local_job_execution.py` 在完成边界保存结果；`JobNotificationManager.reconcile` 补查。测试 `tests/control_plane/test_archive_notifications.py`；实际进程与正式客户端验证脚本 `packaging/verify_archive_notifications.py`，可以使用 `--source` 或完整包目录，所有夹具保存在GPTWork，不运行Abaqus。

原生：`winui/AbaqusTools.WinUI/MainWindow.Notifications.cs`、`MainWindow.xaml`；DTO/去重状态在 `Services/JobNotificationContracts.cs`，HTTP 在 `Services/ControlPlaneHost.Notifications.cs`。点击定位在 `Pages/JobOverviewPage.xaml.cs` / `SelectNotificationJobAsync`。

测试：`tests/control_plane/test_job_notifications.py`、`tests/winui_host/JobNotificationChecks.cs`。`packaging/verify_local_memory.py --notifications --host-client <当前C#测试DLL>` 用隔离 Windows helper、两次后台启动、正式 C# 客户端及 SQLite 核对取消提醒、恢复、已读及再次执行的新提醒；不运行 Abaqus 求解。准确结果见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。原生提醒展开、任务栏闪烁和真实作业仍需单独验收。
