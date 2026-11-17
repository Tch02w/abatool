# 远端作业与完成确认（F010）

WinUI 的「新建作业」通过已连接且已确认指纹的 Windows SSH 服务器提交；「作业概览」显示进度、日志与控制操作。输入选择上传本地文件或使用允许目录内的远端文件；请求包括作业名、INP、可选 oldjob/Fortran、CPU、内存及数据检查选项。完整入口与服务器配置见 [使用手册](../repowiki/user-guide.md)。

## 完成证据

每次作业使用新建远端目录；启动时记录 launcher PID 和创建时间，后续不把重复使用的 PID 视为本作业。极快结束的 launcher 使用明确的已退出回执。每轮读 STA/LOG/DAT/MSG 各最多 80 行，并检查文件大小和修改时间；读取期间发生变化、目录/身份/文件不可读时不授权成功，显示“远端状态暂不可读，等待重新核对”。

正常分析接受既有成功分析标记；分析和数据检查都可接受严格匹配本次作业名的 `Abaqus JOB <name> COMPLETED` 整行。仅有输入处理器结束、进程消失或空日志不能证明数据检查成功。错误和终止标记基于共享常量，但数值奇异、零主元、过度畸变等诊断词本身不判失败，须明确错误前缀/失败摘要；也不把泛化的迭代 terminated 词当作整个作业终止。已经读到的明确错误/作业终止会保留，避免滚出尾部后变成成功。

有完成输出仍保持活动，直到 launcher 不活跃、锁文件不存在且四个输出的签名连续 3 次一致。轮询间隔 1 秒，调用与网络耗时另计。输出变化、进程重新出现或探测不可读会重置确认。确认后优先错误，其次本次取消请求/终止，最后成功。连续 5 次稳定无进程/锁却没有成功证据时，返回失败 `REMOTE_JOB_EXIT_UNCONFIRMED`，不会伪装成功。

## 日志、错误与取消

- 四种日志各自保存上一段尾部，按重叠行只追加新行；未变化时不重新追加整个尾部。最多保留 250 行，轮转或重写的无重叠内容作为新片段显示；不是完整远端日志归档。
- 错误输出对应 `ABAQUS_REMOTE_ERROR`，非本次请求导致的终止对应 `REMOTE_JOB_TERMINATED`；都需要先确认进程和文件已结束。
- 取消使用 Abaqus 温和终止，保持取消中直到稳定确认，不以“命令已发出”代替“作业已结束”。关闭仍复用受管任务检查，不因收到完成文本提前释放活动任务。

## 当前边界与后续迁移

上述进程判断覆盖本次 launcher，锁文件辅助判断异步求解；尚未完成远端全部 MPI/脱离 launcher 的子进程身份核对。没有声称独立并发负载或真实 SSH/Abaqus 验收已经完成。

远端操作目前仍在后台内存内保存；后台重启后不会恢复这些记录。传输/SSH 命令异常目前使操作显示失败，但不能据此断言已经启动的远端求解也停止。连接中断后的持续跟踪、重连和持久恢复仍需完善，关闭后台不自动结束远端求解。不能因为本节完成判断修复就宣布 F010 或全迁移整体完成。

## 定位与验证

- 业务入口：`modules/control_plane/remote_jobs.py` / `RemoteJobOperationManager`，启动/状态 PowerShell 由 `_start_job_script`、`_job_status_script` 生成。
- 确认算法：`modules/control_plane/remote_job_monitoring.py` / `RemoteCompletionState.observe`、`new_tail_lines`。
- 原生入口：`winui/AbaqusTools.WinUI/Pages/NewJobPage.xaml.cs`、`winui/AbaqusTools.WinUI/Pages/JobOverviewPage.xaml.cs`，无新增 UI 布局或公共必填 DTO 字段。
- `tests/control_plane/test_remote_job_monitoring.py` 覆盖缺输出、完成但仍运行/有锁、签名变化、错误优先、不可读、数据检查、终止、日志重叠及生产 PowerShell 在本机的实际探测/快速启动。它只启动隔离 cmd 夹具，不是远端或求解验收。
- API、服务器、传输和关闭测试见 `tests/control_plane/test_remote_jobs_api.py`、`tests/control_plane/test_remote_servers_api.py`、`tests/control_plane/test_remote_transfers_api.py`、`tests/control_plane/test_shutdown_guard.py`、`tests/control_plane/test_shutdown_protocol.py`。实际结果与续接点见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。
