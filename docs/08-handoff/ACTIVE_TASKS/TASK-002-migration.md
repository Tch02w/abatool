# TASK-002：后续迁移、完善与整理

## 范围与前置条件

后处理交付后继续，不以现有八个页面存在证明迁移完成。范围来自本线程用户要求和 [迁移合同](../../winui-migration.md)。功能入口均可由 [功能索引](../../03-features/FUNCTION_INDEX.md) 定位。

## 接续顺序

1. TASK-001 后处理和结果浏览验收，保留现有 PySide6 基准。
2. 目录整理：保留有效源码/文档/测试/证据；梳理 GPTWork 大型样本、历史构建和临时输出引用，先形成可恢复移动清单，不凭文件名删除。用户数据和原始模型不属于清理对象。
3. F011–F013：计算重启动与结果合并图分离、空节点有效性、分支祖先路径、点击目标生成完整结果、链式批量实际执行、取消和失败传播。
4. F003–F010：新建作业、候选/正式队列、外部作业纳管、监控选择不丢失、CPU 策略、远程连接/传输/提交；按真实流程验收，不只测按钮存在。
5. 类 Slurm 目标：软件内统一队列、资源分配、后台常驻调度。现有 `LocalQueueRuntimeManager` 等是起点，不能直接称已实现 Slurm 等价架构；常驻生命周期、持久恢复、资源记账和跨节点调度边界需单独核对/设计。
6. F001/F002/F023：浏览器、布局、进程生命周期、安全关闭、重连、配置兼容；Release 及目标机器验证。

## 2026-11-18 F004/F005 原生统一调度（当前轮）

修改前已说明改进：将原生派发接入旧版已经使用的纯 Python 调度核心，统一优先级、CPU/绝对内存、依赖和目录互斥，同时保存执行批次身份。实现定位和完整边界见 [本机调度说明](../../03-features/LOCAL_SCHEDULING.md) 与 [ADR 0010](../../submitter/adr/0010-native-shared-local-scheduler.md)。

已实现 `LocalQueueScheduling`，派发前写入队列和 SQLite；后台重启后仅观察原任务，不自动重放。未知记录不再被清理/删除/直接重排；第二次重启仍登记观察目录。运行进度保存失败保持监控，最终结果保存失败只重试保存；线程启动失败释放分配；相同状态与队列内容不重复写入。修正旧 ODB 存在时绕过活动父作业、同名父目录判断及迟到进度回调。队列页面增加调度提示。原始 G:\Job 未写入，未启动求解。

本轮检查记录：

- 初步专项 13 项、适配器组合 20 项通过；新增专项首轮 10 项、后续加边界后 22 项通过。记录 `GPTWork/scheduler-initial-20261118.xml`、`scheduler-second-20261118.xml`、`native-scheduler-20261118.xml`、`native-scheduler-final-20261118.xml`；这些覆盖重叠，不相加。
- 扩展回归首次 **296 通过/1 失败**，117.57 秒，22531 已退出 1：`GPTWork/native-scheduler-regression-20261118.xml`。失败为 `test_running_items_are_protected_and_corrupt_state_is_not_overwritten`，损坏队列在调度恢复构造期间异常退出，阻断整个服务。已改为保留原文件并让其他 API 启动，修复队列后重试恢复。
- WinUI Release 已构建成功，0 警告/0 错误，22.91 秒，40282 退出 0；`GPTWork/native-scheduler-winui-20261118.log`。不是原生业务页验收。
- 修正后扩展回归 **299 项通过**，369.23 秒，76369 退出 0，`GPTWork/native-scheduler-regression2-20261118.xml`，覆盖全控制面、共享调度/存储/适配器、队列存储、实际本机执行器和壳层契约。该轮后补的未知外部 Core 保守记账由最终专项覆盖。
- 最终专项、适配器与文档导航 **67 项通过**，31.49 秒，33278 退出 0，`GPTWork/native-scheduler-docs-final-20261118.xml`。覆盖第二次重启、未知执行结局、进度保存失败继续监控、损坏队列修复后启动、外部 Core 未知不记作零和文档路径。与 299 项存在重叠，不相加。
- 正式 C# HTTP 关闭客户端 **5 项通过**，8.29 秒，`GPTWork/native-scheduler-close-api-20261118.xml`；真实 loopback 后台配隔离执行器，无求解/SSH。Ruff 与 `git diff --check` 通过。

准确续接点：本轮测试与构建均已结束，首轮失败保留。最终完整包与冻结执行/关闭已经通过，见下一节；旧原生窗口未操作。下一项审查动态内存学习、自有作业持续 RSS，并继续真实 CPU/内存负载、原生业务和真实远程验收。既有“读取目录”居中/加载指示修正和 GIF 两种计时模式保留；不能把构建和模拟派发当作界面或求解验收。GitHub 仍等待此前具体远端确认。

### 本轮完整包与状态投影修正

代码与文档已本地提交 `39541e2ced173cf89174f0a9a85e8125da4b1052`。首个本轮完整包 `GPTWork/release-win-x64-8e27c8c8cb26/AbaqusTools` 构建 85384 退出 0，干净来源；用户账户逐项核对 **1651 文件/19 worker**。包内诊断 `GPTWork/scheduler-bundle-probe-20261118/bundle-probe-dsej4mos/verification.json`、正式主机启动/API/退出均通过，32620 已退出 0。

冻结后台关闭验证 84238 退出 0，`GPTWork/frozen-close-fd075271b206/verification.json` 确认后台继续/取消保留同一任务，停止后正常退出、连接文件移除、测试命令只执行一次、源测试文件未变。PID 193576 已确认结束。只读核对同目录 `scheduler-verification.json` 确认运行记录、队列存储和 SQLite 的执行身份一致，SQLite 为 CANCELED；但随后发现队列 `scheduler_state` 仍为 DISPATCHED。人类状态已经是“已终止”，问题在持久化调度状态投影。已补充每次执行事件同步该字段的修正及完成/未知状态断言，**32 项调度/运行/退出专项通过**，211.09 秒，34248 退出 0，`GPTWork/scheduler-projection-20261118.xml`。命令：`.\.venv\Scripts\python.exe -m pytest tests/control_plane/test_local_scheduling.py tests/control_plane/test_local_queue_runtime_api.py tests/control_plane/test_shutdown_guard.py -q --basetemp=GPTWork/pytest-scheduler-projection --junitxml=GPTWork/scheduler-projection-20261118.xml`。将重建候选后再验收投影一致性。

辅助检查脚本第一次误把内部 `attempt_id` 当成队列 API 的字段，出现 KeyError；改为读取队列存储后身份检查通过，没有为脚本增加多余 API 字段。首包及失败过程保留。未调用 Abaqus、SSH 或操作原生窗口；周额度最近剩余 61%。

### 最终候选与准确续接点

投影修正已本地提交 **`d5b661e91a65fd2ec45a05d27d2dc0d618147ad9`**。完整构建 88507 退出 0；最终目录 **`GPTWork/release-win-x64-b0e12f955ac4/AbaqusTools`**，来源干净。用户账户 `inventory-verification.json` 核对全部 **1651 文件/19 worker**。包内诊断 `GPTWork/scheduler-final-probe-20261118/bundle-probe-0x1kq3mj/verification.json`、正式 C# 主机启动/资源与队列 API/退出均通过（`GPTWork/scheduler-final-host-20261118.log`）。

最终冻结关闭 6679 退出 0，回执 `GPTWork/frozen-close-d76ed1a80c40/verification.json`：后台继续/取消保留同一任务，合作停止后后台自行退出 0、连接文件移除、命令仅一次、源测试文件不变。`scheduler-verification.json` 进一步核对运行记录、队列文件和 SQLite 的执行身份一致，队列 API、队列文件及数据库状态均为 CANCELED。后台 PID 200552 已确认结束。复现命令：`.\.venv\Scripts\python.exe GPTWork/verify_frozen_close_20261118.py GPTWork/release-win-x64-b0e12f955ac4/AbaqusTools GPTWork/release-win-x64-8e27c8c8cb26/host-check-client/ControlPlaneHost.Tests.dll`，只读投影核对为 `.\.venv\Scripts\python.exe GPTWork/verify_scheduler_execution_20261118.py GPTWork/frozen-close-d76ed1a80c40`。C# 客户端是本轮正式源码构建，无本轮代码未包含的旧客户端行为。

所有本轮测试和自有后台已结束，没有启动 Abaqus 求解。最终文档导航 40 项通过；包内文档是构建时快照，本段回执与最终状态在仓库补记。本轮没有新 ZIP、安装程序或 GitHub Release，未替换正在运行的旧原生窗口，未推送。周额度最终剩余 61%，目标保持进行中。下一项按上面的续接点审查内存学习和观察能力，再推进原生与真实场景，不重跑已通过样本。

## 2026-11-18 F001 可撤销关闭、页面草稿与后台继续

修改前已说明改进方案：保存先于关闭决定，提供后台继续/停止并关闭/取消，失败恢复交互；由后台执行已确认退出，避免前端拿旧空闲回执结束整个进程树。实现见 [ADR 0009](../../submitter/adr/0009-reversible-workbench-close.md) 和 [交互说明](../../03-features/UI_INTERACTION.md)。

实际改动：

- `ShutdownProtocol` 为普通 POST 增加在途计数、60 秒准备租约和有限幂等回执；准备、续期、放弃、合作停止、提交统一鉴权。后台继续不取消工作，idle/stop 由后台自身关闭 HTTP 服务并等待清理。
- `ControlPlaneHost.Shutdown` 排空正在创建的操作再确认后台身份；关闭请求固定在该实例。提交断连只查原回执，无法确认不强杀；显式分离路径不发送自动取消。窗口关闭与菜单退出共用流程，重复关闭合并处理。
- 八页登记编辑字段，`WorkbenchSessionStore` 原子保存最近路由、正常窗口位置/大小与最大化状态、原始输入。后处理复用既有工作区，图修改必须成功保存，结果回收站操作必须完成。不可读原草稿保留；失败恢复界面和计时器。队列空闲时的参数编辑不再被轮询覆盖，运行中仍显示后台真实参数。
- 计算资源重新打开时接回同一后台的活动文件传输；没有新增全任务跨后台重启恢复。关闭对话框使用中文任务类型，原生视觉和交互仍未验收。

实际检查：

- 最终全控制面和正式 C# HTTP 客户端 **222 项通过，108.71 秒**，65060 退出 0，`GPTWork/close-full-final-20261118.xml`。包含五种正式客户端场景（后台继续、取消、停止、空闲以及活动传输），使用受控任务/模拟远端，不运行 Abaqus 或真实 SSH。
- 最终关闭协议/退出保护/客户端专项此前 **22 项通过，15.16 秒**，12776 退出 0，`GPTWork/close-final-20261118.xml`；与完整回归重叠，不累计。
- C# 主机 **11 项辅助进程生命周期、1 项创建中关闭竞争、2 项固定实例丢回执、7 项草稿存储**通过；同时保留此前升级 9、合并展示 3、批量恢复 6 和启动选择 11 项。577aa3 退出 0，日志 `GPTWork/close-host-final-20261118.log`。这些是程序/存储检查，不是原生页面验收。
- 输入绑定与壳层 **36 项通过**，八页白名单均指向支持的 XAML 控件。Release 67748 退出 0，0 警告/0 错误，11.17 秒；后续中文显示改动将由完整包再次构建覆盖。相关 lint 通过。
- 文档导航、壳层和草稿绑定最终 **75 项通过**，`GPTWork/close-docs-20261118.xml`，ab4c69 退出 0。

失败与修正保留：首轮旧退出保护 1 失败/12 通过，原因是已封闭后台仍返回准备中错误码，已区分。首轮 C# 草稿测试未捕获 `InvalidDataException`，修正测试异常分类后通过。第一次完整回归 **2 失败/218 通过**（30473 退出 1，`GPTWork/close-full-20261118.xml`），401/503 在 Windows 因未读取的 POST 正文偶发连接重置；服务端仅限时排空受限正文再返回错误，最终完整回归已通过。另补充提交响应连接丢失测试，确保已封闭后台仍自行退出，不悬挂等待客户端。

准确续接点：上述自有测试/构建已结束。新完整目录和冻结后台关闭验收已完成，见下一节；旧 `b53b0f4ca2b4` 保留。旧原生窗口未被操作；下一项是原生八页关闭/取消/重开、草稿保存失败、跨屏窗口恢复及剩余功能迁移审查。真实 SSH、三层连续 ODB 链和无开发环境目标机器仍待验收。周额度最终读取剩余 64%，未触及 15% 暂停阈值。具体 GitHub 远端确认仍未收到，不重新推送。

### 本轮完整目录与冻结关闭验收

运行代码、测试、README 与 Wiki 已本地提交 **`d4d70e5f08530442470e0958396079dd682af61a`**。干净来源完整目录为 `GPTWork/release-win-x64-60ea97c39143/AbaqusTools`；4346 已退出 0，包含中文关闭提示和此前“读取目录”按钮修正。用户账户逐项读取并核对 **1649 文件/19 worker** 的大小与 SHA256，`sourceDirty=false`，回执 `GPTWork/release-win-x64-60ea97c39143/inventory-verification.json`。

- 包内依赖诊断通过，回执 `GPTWork/package-close-user-probe-20261118/bundle-probe-foju9nh1/verification.json`；覆盖默认配置、worker、GIF、绘图、工作簿预览、SSH 加密依赖及不导入 Qt。
- 正式 C# 主机启动包内后台、资源/队列 API 和旧兼容路径空闲安全退出通过，独立目录 `GPTWork/package-close-user-host-20261118`。最新 C# 主机全检查也再次通过。
- `GPTWork/verify_frozen_close_20261118.py` 的最终 49509 退出 0，回执 `GPTWork/frozen-close-f5d19765bc11/verification.json`：正式 C# 客户端选择后台继续、取消关闭后同一后台和本机测试任务仍在运行；随后通过新协议停止，线程清理结束再提交，后台自行退出 0、描述文件由后台移除，测试命令仅启动一次，源测试文件摘要不变。PID 3716 已确认不存在。没有调用 Abaqus、真实 SSH或操作原生 UI。
- 首次辅助脚本 5855 退出 1，证据目录 `GPTWork/frozen-close-44142eb272c6`。测试等待命令没有处理 `terminate` 参数，第二次调用同样等待释放，导致 90 秒清理检查失败；只修改 GPTWork 中的测试命令支持终止释放，没有为测试修改产品代码。已释放该测试夹具，PID 204540 确认结束、描述文件不存在；历史失败目录保留。

新包未覆盖旧运行窗口，未生成本轮 ZIP、安装程序或 GitHub 二进制 Release，未完成原生交互和无开发环境机器验收。包附带构建时文档快照，以上验收回执和最新续接状态在源码仓库补记；不据这些测试宣布整体迁移完成。

## 2026-11-18 F001 全受管后台退出保护（前一阶段）

源代码审查发现旧退出预留仅覆盖批量/合并/升级，但主机会结束整个自有后台进程树，尚在运行的本机作业、后处理和传输未受完整保护。修改前已向用户说明改进：联合检查所有受管工作，确认空闲后同时关闭任务准入；状态不明时保留后台。

已实现九类管理器固定顺序检查与全有或全无预留。五类内存任务共用 `OperationShutdownGuard`，不只检查终态，还检查 Future 已结束；本机队列同时检查调度周期、活动作业和终态后的持久化线程。修复停止调度与已选待启动作业间的竞争；启动登记、队列 STARTING 写入和线程启动由同一锁保护。主机只接受 `all-workers-v1` 回执；旧响应/损坏响应/断连不授权终止后台。实现与保留边界见 [ADR 0008](../../submitter/adr/0008-all-worker-shutdown-fence.md)。这不是完整关闭交互、同步文件/设置操作协调或全任务持久恢复。

已执行：

- 首轮退出专项 9 项通过（52153 已结束）；补充兼容性/索引/远端提交的关闭后准入检查，最终 10 项通过，15.09 秒，20390 退出 0，`GPTWork/shutdown-guard-final-20261118.xml`。
- 全控制面 **208 项通过**，207.72 秒，2004 退出 0，`GPTWork/control-shutdown-regression-20261118.xml`，包含上述 10 项，不能相加当作 218 项。
- C# 测试单独输出至 `GPTWork/host-shutdown-check-20261118`，避免覆盖真实批量验证正在加载的旧测试程序；10 项实际自有辅助进程生命周期、9 升级、3 合并展示、6 批量恢复和 11 启动选择检查通过。仅终止本测试创建的辅助程序，没有终止用户进程。
- WinUI Release 构建 40782 已结束，0 警告/0 错误，42.49 秒；相关 Python lint 通过。文档导航与壳层契约 74 项通过，`GPTWork/shutdown-docs-20261118.xml`。最终完整包在本节后续补记。

真实 F012 验收使用上轮冻结包（来源 `9f5ff64`），不冒充本轮退出修正的验收。`GPTWork/verify_real_batch_20261118.py` 的 43108 已退出 0，`GPTWork/real-result-batch-750883913dd9/verification.json` 为 verified：正式 C# HTTP 客户端完成两目标；V20D 为 8 步/70 帧，U100D 为 12 步/63 帧，保留 4 个无结果帧提示；两者历史输出开启、压缩开启。两次冷启动后整批 ID、两个子操作 ID 及两个 ODB/两份回执的全文件 SHA256 一致，三个源副本的前后全文件摘要一致，中文含空格输出目录通过，临时工作目录已清理。后台 PID 174056/182444 已确认不存在，描述文件已清理。原 `G:\Job` 未修改、未启动求解；本轮只重新核对副本完整摘要，原文件摘要沿用此前证据。只读扫描找到 65 组存在父子 ODB 的 oldjob 关系，最长确认仅两个节点；GJB-15 两目标均为 U40D 的兄弟分支，不能人为串成三层链。

准确续接点：真实双目标与两次启动已完成，不再重复样本。含本轮退出修正的新完整目录与包内主机/冻结任务检查已经完成（如下）；下一项推进完整关闭选择与页面草稿协调。原生关闭选择、业务页交互、真实 SSH、三层连续重启动链及无开发环境机器验收仍待完成。GitHub 推送仍等待此前具体远端确认，自动目标继续不视为授权。当前周额度最近读取剩余 67%。

### 本轮候选构建与包内检查

本轮运行代码、测试、真实双目标证据及 Wiki 已本地提交 `aa0420f6169671ccb605dafa073ca449aae4a61b`；未推送，具体远端审批仍待用户回答。完整目录 `GPTWork/release-win-x64-b53b0f4ca2b4/AbaqusTools` 由该干净提交构建，38401 退出 0。用户账户核对全部 1648 文件/19 worker，回执 `GPTWork/release-win-x64-b53b0f4ca2b4/inventory-verification.json`；正式客户端包内后台启动、资源/队列 API 与安全退出通过（`GPTWork/package-shutdown-user-host-20261118`）。包内依赖检查回执 `GPTWork/package-shutdown-user-probe-20261118/bundle-probe-x_wpcje1/verification.json`，GIF、绘图、表格、SSH 加密依赖与 Qt-free 均通过；未连接真实 SSH。

冻结运行中任务退出保护采用 `GPTWork/verify_frozen_shutdown_20261118.py`，只执行新建隔离目录内的等待 `.cmd`，退出码 7，不调用 Abaqus。首轮 `GPTWork/frozen-shutdown-da47050f6af8`、40234 退出 1：脚本仅等 30 秒，恰好短于生产 launcher 的 30 秒确认期加轮询时间。生产代码未改，测试最终清理仍完成，后台 199036 已结束、描述文件已移除，失败现场保留。第二轮 `GPTWork/frozen-shutdown-5a0019d80438`、13340 退出 1：活动任务拒绝退出、结束后关闭与拒绝新准入均已执行，但辅助脚本误把本机作业中文 `status` 当成英文 `phase`，最后断言失败。持久队列显示“运行失败 / launcher 返回码 7”，是预期的测试命令退出；后台 205244 已结束且描述文件移除。修正为核对实际 `STATUS_FAILED` 与 `phase=failed`，第三轮 `GPTWork/frozen-shutdown-a5b9765a96ec`、18362 退出 0，`verification.json` 为 verified：运行/停止调度后仍有工作时均拒绝退出，任务结束且线程收尾后允许退出并拒绝新队列启动，测试命令仅调用一次，源 fixture 未变；193748 已结束且描述文件已清理。两次失败都只修改验收脚本，生产退出逻辑未改；保留全部现场。

## 2026-11-18 F012 批量执行所有权与阶段恢复

修改前已向用户说明实现思路：把前端内存中的计划、执行位置和共享前置结果移到后台持久管理；使用固定子任务标识、检查已发布结果后接续，避免重复合并和兄弟分支串入。源码入口和用户步骤见 [F012 说明](../../03-features/ODB_RESULT_BATCH.md)，架构见 [ADR 0007](../../submitter/adr/0007-durable-result-batches.md)。

已完成的实现：后台重新计算权威计划并冻结选项；批量 SQLite 保存计划、提交意图、子任务与结果摘要；同批共享祖先只执行一次；界面提交一整批、读取进度及重启后显式继续；停止等待实际子任务清理；退出按批量/单步合并/升级联合预留。来源为文件元数据和三段内容抽样，中间 ODB 与回执为全文件 SHA256。已提交但子任务记录缺失或中断时拒绝重跑。重启动计划不再从多个前置或同名前置中默认选第一个。旧 C# 批量执行器保留作对照，生产入口已切换。

UI 保留已选结果，避免每次轮询重建结果列表和不可变计划；有日志选区时暂不替换文本。恢复时同时显示整批选项及已完成目标，不把子合并当作新的手工任务。成功消息保留无结果帧提示。用户截图中的读取目录按钮此前已改为居中，非活动 ProgressRing 折叠、活动颜色绑定按钮前景；本轮重新核对源码，未重复改动该按钮。

测试过程与失败证据：

- 首轮新测试发现 Windows 同大小/同 mtime 的内容修改不能靠原元数据检查发现；增加三段源内容抽样，已完成结果仍采用完整摘要。
- 异常退出辅助程序改为读取并核对实际 Python worker PID 再终止，避免把 Windows 虚拟环境启动器 PID 当作 worker；没有启动 Abaqus 或终止用户进程。后续进程检查没有发现该测试脚本的遗留进程。
- 隔离恢复/单步回归/重启动计划 37 项通过，`GPTWork/result-batches-tests-20261118.xml`，句柄 29176 已结束；随后新增无结果帧提示恢复检查。
- 第一次全控制面回归 196 passed / 1 failed：F015 升级异常退出测试在并发轮询 JSON 时写入失败。将测试的磁盘轮询改为子进程输出“检查点完成”后再读取文件，避免 Windows 读句柄干扰原子替换；生产升级代码未改。专项 13 项通过，失败现场保留于 `GPTWork/pytest-control-batches-final/test_actual_process_crash_pres0`。
- C# 批量恢复契约 6 项、单步恢复展示 3 项、生命周期 8 项、升级契约 9 项、启动解析 11 项通过；旧批量执行器 10 项通过。
- 首次 WinUI 构建发现历史时间字段使用 string 与 DateTimeOffset 不一致，已统一并修复可空请求访问；修正后 Release 0 警告/0 错误，句柄 68513 已结束。最终构建 22310 已结束，0 警告/0 错误，19.12 秒。

最终完整控制面回归 **198 passed / 245.36 秒**，`GPTWork/control-batch-regression-20261118.xml`，句柄 55644 已退出 0；文档/壳层契约 **74 passed**，最新 C# 主机检查全部通过。随后收紧恢复子任务时的冻结配置身份校验，最新批量与单步恢复专项 **33 passed / 309.26 秒**，`GPTWork/result-batches-final-20261118.xml`，句柄 50650 已退出 0；覆盖 18 项批量和 15 项单步恢复。Ruff 全部通过。以上计数包含重叠用例，不累加成独立用例总数。功能、测试和 Wiki 已本地提交 `ef471f8`。尝试 `git push origin main` 被自动审批拒绝，命令未执行；理由为当前可信授权没有明确指名 `https://github.com/Tch02w/abatool.git`，推送仍待用户确认具体远端。

本轮最终目录候选为 `GPTWork/release-win-x64-6cbfd68f63f6/AbaqusTools`，来自干净提交 `9f5ff6447a93189a99718ed94cb0c6304620ff60`，构建 51942 已退出 0。用户账户核对全部 **1647 文件 / 19 worker**，回执 `GPTWork/release-win-x64-6cbfd68f63f6/inventory-verification.json`。本轮没有新建 ZIP，也未发布二进制 Release。

包内实际恢复证据为 `GPTWork/frozen-batch-recovery-001fad0945b9/verification.json`：2 次冻结后台启动、2 个计划阶段、仅准入 1 个子合并、测试命令只执行 1 次；首阶段失败后不启动后续阶段，重新提交相同批次返回原任务。源测试文件未变、失败隔离工作区已清理、联合退出预留通过，未启动 Abaqus。复现辅助脚本 `GPTWork/verify_frozen_result_batch_20261118.py`，运行句柄 87835 已退出 0；生成的认证 descriptor 已清除。正式 C# 主机在 `GPTWork/package-batch-user-host-20261118` 完成随包启动、资源/队列 API 及安全退出。用户账户包内诊断 `GPTWork/package-batch-probe-20261118/bundle-probe-cn1yv381/verification.json` 通过 GIF/Agg/工作簿/SSH 加密/Qt-free/defaults/worker 检查。这些都是本地隔离测试，不代表原生交互或真实多阶段模型验收。

准确续接点：本轮所有构建与测试已结束；本地功能提交 `ef471f8` 已完成，等待具体 GitHub 远端推送授权。本轮目录候选与冻结恢复验证已完成，继续真实多阶段和原生流程。原生窗口 58461048 仍来自旧候选 `GPTWork/winui-migration-20261118`；本轮重新选择窗口并两次截图均返回 `window capture timed out: timed out waiting on channel`，没有点击、关闭或启动第二个窗口。真实多阶段工程 ODB、原生恢复/继续/停止交互和无开发环境目标机器仍待验收。既有两组 F013 真实内容校验无需重跑。整体迁移目标继续进行。

## 2026-11-18 F013 持久记录、中断恢复与用户可访问候选（原生页面待验收）

上轮完成真实合并、发布候选及推送，是有效进展。本轮周额度初始剩余 73%，继续完整目标。修改前说明方案：先保存任务再启动，恢复历史与请求身份，未确认完成显示中断待核对；不自动重跑外部任务。约束见 [ADR 0006](../../submitter/adr/0006-durable-merge-history.md)。

### 实际改动

- F013 新增单写入者 SQLite 操作记录，启动前/状态边界/结束持久化，每次只更新一条记录；进度与日志按 0.5 秒检查点节流，日志尾部 200 行。保留原始请求签名，避免恢复后自动编号路径破坏去重。
- 恢复终态记录、来源、结果、回执与错误；非终态显示 `ODB_MERGE_INTERRUPTED`，保留未知状态及检查指引。损坏、未知版本、占用或保存失败均禁止新任务，保留数据库和输出。已提交结果与未保存状态分别显示。
- 升级/合并联合原子退出预留，任一不安全则均不预留；合并已预留后仍正常释放线程池与记录锁。
- 原生合并页显示最新任务，修复只显示旧成功而隐藏新失败的问题；还保留无结果帧提醒、校验回执、保存失败警告。页面新加载结果图计划不被历史草稿覆盖。两次查询间出现新活动任务时转入观察。

### 已执行检查与续接点

178 项控制面回归通过，回执 `GPTWork/control-history-regression-20261118.xml`，65885 退出 0；其中 15 项合并恢复检查包含独立测试进程真实终止后重开记录、HTTP 控制面实际重建、原始文件移走后重复请求不重跑、损坏/重复身份/非法成功、文件锁、磁盘失败、提交后状态保护与联合退出。测试进程使用模拟执行器，没有运行 Abaqus 或求解。

日志检查在 600 条连续消息下只写 4 个状态检查点，并确认最后 200 行在重启后一致。C# 3 项恢复信息检查、8 项进程生命周期、9 项升级契约和 11 项启动选择通过。原生 Release 构建 0 警告/0 错误，29122 退出 0，耗时 27.25 秒；文档和壳层契约 73 项通过。原生页面交互、真实外部 Abaqus 运行中崩溃、F012 多目标批量游标续接仍未验收。源码 lint 通过，新增 `packaging/verify_merge_restart.py` 用于完整包的两次冷启动和失败记录去重验证；下一项为候选更新和冻结验证。所有上述测试已结束，无需重跑两组已通过的真实合并模型。

功能提交 `7efd7b8bf60319c858b5f919ad3e22337ef6389c` 已推送 origin/main，返回 `21c2727..7efd7b8 main -> main`。该提交构建 `GPTWork/release-win-x64-ws1xh2gg`，71492 退出 0；1645 文件摘要、19 个 worker 和 ZIP CRC 通过。包内诊断 `GPTWork/package-history-probe/bundle-probe-scrzk38x/verification.json`、正式主机独立启动/退出均通过。`GPTWork/frozen-merge-recovery-jka6iogk/verification.json` 证明包内控制面两次冷启动、失败历史恢复和相同请求仅执行一次测试命令；不调用 Abaqus，测试输入和失败工作区核对通过，85388/24795/63339 均已结束。

交付复核发现该 `tempfile` 目录仅构建账户可读，用户账户读取程序文件被拒绝。这是目录权限问题，不是文件缺失，旧目录完整保留。已将发布目录改为唯一 UUID 名称加普通 `mkdir`，继承项目权限；两种账户对 `GPTWork/release-access-check-20261118/readable.txt` 的访问均通过，没有修改任何既有目录权限。下一步从修正后的构建脚本生成新候选，并在用户账户验证最终文件。当前周额度剩余 72%，整体目标继续 active。

### 最终候选与准确续接点

最终候选为 `GPTWork/release-win-x64-c39d9688d751/AbaqusTools`，由干净提交 `2406e8bfb9eb6516a9ce524aaddd186e0c9a05ce` 构建；63568 退出 0。已从用户账户读取并核对全部 1645 个清单文件和 19 个 worker，直接运行包内控制面成功。最终用户账户证据：`GPTWork/frozen-merge-recovery-658jvpc7/verification.json`（两次冷启动/仅一次测试命令/历史恢复/失败清理）、`GPTWork/package-history-user-probe/bundle-probe-l99g1uzi/verification.json`（包内诊断）、`GPTWork/package-history-user-host`（正式主机独立启动/资源和队列 API/安全退出）。67243/98709/94368 均退出 0。部分验收目录仍按测试进程账户私有，读取时须使用相应账户，不更改权限或把拒绝访问认作文件不存在。

同级 `AbaqusTools-win-x64-2406e8b.zip` 为 149480153 字节，SHA256=`7ab56795f62dffe921647417fdf4a552ed1a948309ba14240a2fd0f28fe31bdf`；CRC 和文件清单校核通过，`archive-verification.json` 记录用户账户验证。代码与文档已推送 origin/main，发布访问修正 push 返回 `7efd7b8..2406e8b main -> main`；构建后的最新交接记录另随文档提交同步。没有发布二进制 GitHub Release。

本轮所有自有构建、后台和测试进程已确认结束，没有操作旧原生窗口或用户求解。下一项：F012 完整结果批量计划/执行游标目前仍在前端内存，需继续迁移其执行所有权及跨后台续接，并验证真实多步骤链；同时推进可操作桌面的原生页面、真实 SSH 与目标机器验收。不要重跑已通过的两组真实单步内容核对，也不能把 F013 的单步恢复称作全应用恢复完成。

## 2026-11-18 F013 合并内容校验（两组真实内容核对通过）

上轮完成随包启动和发布候选，本轮继续真实合并验收。周额度读取剩余 74%，目标保持 active。修改前已说明改进：不能以“文件非空且有帧”作为成功依据，改为逐分析步、逐帧核对来源数据后才发布，保留校验回执。

实现位于 [F013 说明](../../03-features/ODB_MERGE.md)：按原始前序 + 重启动步骤核对顺序/帧/场值与位置/历史输出，双精度回退，全部 ODB 关闭成功后生成回执。控制面显示无结果帧的步骤数量，修复提交后迟到取消误报、并发请求标识冲突和关闭期间新请求准入。源文件标识保护是 stat/inode，不冒充全量内容摘要。进程崩溃恢复、真实多节点批量及原生点击尚未验收。

### 本轮实际证据

- 从 `G:/Job/GJB_ODB/GJB-15` 只读核对 `.com` 的 oldjob，U100D 与 U40D_V20D 都从 U40D 重启动；复制三份 ODB 到 `GPTWork/merge-real-fv8_supj/inputs`，文件完整摘要在 `source-copies.json`。未启动求解。
- Abaqus 读取 `source-structure.json`：U40D 六个分析步；V20D 两个后续步各 11 帧；U100D 实际仅 U50D 11 帧、U60D 4 帧，U70D–U100D 为无结果帧的未来步。不能称 U100D 计算完成。
- V20D 基线合并（历史开、压缩关、copyoriginal 关）54813 退出 0。其后独立运行新校验器，58927 退出 0，`baseline/content-verification.json` 为 verified，8 步/70 帧全部场值和历史数据与来源一致。基线合并执行器是修改前已加载版本，不冒充新发布流程完整验收。
- 第一次增强流程 `enhanced-partial`，15537 退出 1：Abaqus 2025 明确输出关闭历史时移除全部历史数据，旧校验规则错误要求保留 Geo 历史而拒绝发布。该失败目录只剩 `execution.log`，没有残留结果/备份。已按 [官方说明](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEEXCRefMap/simaexc-c-restartjoinproc.htm) 和实测修正为所有步骤历史均省略。新用例专门检查原始步历史删除，保留失败现场。
- 修正后的完整流程 `enhanced-partial-v2`，22343 退出 0；历史关、压缩开、copyoriginal 开。12 步/63 帧通过逐项核对，U70D–U100D 四个空步骤保留并输出提示，回执、备份及最终 ODB 正常发布，隔离工作目录已清理。
- 回归 `GPTWork/merge-regression-20261118.xml`：99 passed，包含内容不一致/双精度/关闭失败、源变化、无效回执、旧目标保护、取消提交时机、请求并发、结果图和文档；45990 退出 0。C# 批量执行器 10 项通过；上述检查不替代真实多节点/业务页操作。

### 准确续接点

已运行 `.venv/Scripts/python.exe GPTWork/verify_real_merge_acceptance.py`，59434 退出 0。`GPTWork/merge-real-fv8_supj/verification.json` 核实原始三份 ODB/输入副本完整摘要不变，源备份与输入一致，无结果帧列表、回执及失败目录清理符合预期。该副本目录由提升权限进程创建，普通读取可能拒绝访问；不要把权限问题当作文件不存在。54813/58927/15537/22343/45990/59434 均已确认结束，无须重跑两组真实样本。下一项为原生点击、真实多节点批量及后台重启恢复验收。

代码、测试和文档功能提交 `16859c4b457a084e2e78019c285a504b98242728` 已推送 GitHub origin/main，push 返回 `3192c19..16859c4 main -> main`。新完整目录 `GPTWork/release-win-x64-g_asfnjp/AbaqusTools` 从该干净提交构建，62767 退出 0。1644 个清单文件摘要全部匹配，19 个 worker 均与源码逐文件相同。包内诊断 `GPTWork/package-merge-probe/bundle-probe-xb9j82ur/verification.json` 与正式 C# 主机独立启动/资源和队列 API/安全关闭均通过；独立数据目录 `GPTWork/package-merge-host`。本轮没有启动或关闭原生窗口。

同级压缩包 `AbaqusTools-win-x64-16859c4.zip` 为 149463345 字节，SHA256=`14c915c80b05bb0e3bad30948436a60798d1b7ecbc2535cc8f72b48250c7ae75`，CRC 和清单核对通过，回执 `archive-verification.json`。目录和 ZIP 是本地候选，尚未上传二进制 Release；包内文档对应功能提交，构建后的验收记录保存在仓库当前文档。最终文档路径检查 38 passed；所有本轮自有构建、合并、检查和测试主机均已结束。周额度复查剩余 74%，整体目标保持 active。

## 2026-11-18 完整目录包与读取目录按钮（已构建，原生/目标机器待验收）

上轮 GIF 复核产出新的解码/测试证据并更新交接，属于进展。此次周额度初始剩余 77%，目标保持 active。

新增 F026：源码/随包控制面启动选择、PyInstaller Qt-free 目录包、.NET 与 Windows App SDK 自包含发布、文件摘要和包内诊断。设计先于修改说明，详见 [ADR 0005](../../submitter/adr/0005-self-contained-winui-control-plane.md) 与 [发布构建](../../05-development/RELEASE.md)。保留 PySide6 对照入口及用户数据位置。

用户补充“读取目录”按钮文字偏右。定位 F021 的 `ScopeProgressRing`：IsActive=False 仍保留布局宽度。已改为空闲 Collapsed、忙时显示并跟随按钮 Foreground；按钮内容和文字垂直居中。该修正已包含在随包构建中，实际界面检查仍待完成。

首个冻结产物 `GPTWork/release-win-x64-j9p1ui36/AbaqusTools/control-plane` 已由正式 C# 主机启动，资源/队列 API 和安全退出通过，11 项启动选择检查通过。首次 publish 因 NuGet 网络不可达失败（NU1301），构建进程 5654 已退出 1；该目录保留为失败现场，后续成功产物见下。

后续发现本机已有运行库缓存。联网 restore 38304 主动停止并确认退出 1；改用 `--source C:/Users/Chiw/.nuget/packages --packages G:/PythonProject/abaqusTool/GPTWork/nuget-release-packages -p:NuGetAudit=false` 本地还原成功，73475 退出 0。此离线还原未执行联网漏洞审计。

完整候选在 `GPTWork/release-win-x64-tq0askay/AbaqusTools`，由 `packaging/build_release.py --no-restore` 生成，63553 退出 0，发布日志没有警告/错误。补齐 Python 依赖声明后共 1642 个清单文件、353870809 字节。已复制到 `GPTWork/release-relocated-86vjsvcj/中文 路径/AbaqusTools` 并逐项核对 SHA256，全部 18 个 worker 与源码相同。回执 `GPTWork/release-relocation-20261118.json`。

包内 `--check-bundle` 在移除 PYTHONHOME/PYTHONPATH、PATH 仅保留 Windows 系统路径后通过：frozen=true、默认配置、18 个 worker、GIF、Agg 绘图、XLSX 预览、SSH 加密依赖、Qt-free 导入；证据 `GPTWork/package-probe-frozen/bundle-probe-8n8836yv/verification.json`。正式 C# 主机在独立 descriptor/用户数据目录启动该 exe，资源/队列 API 及空闲退出通过。进一步通过 `--odb` 复制既有 GJB ODB 到 `GPTWork/package-abaqus-runtime`，由包内兼容性脚本调用 Abaqus 2025 完成只读打开，状态 valid、SHA256 不变；`GPTWork/package-abaqus-runtime/abaqus-verification.json`，2507 退出 0，未启动求解。

相关 Python/文档回归 79 项通过，回执 `GPTWork/package-regression-20261118.xml`；C# 11 项启动选择、8 项主机生命周期及9项升级契约通过。发布脚本 Ruff 通过。已补充 F026 索引、发布说明、ADR 0005、依赖声明和按钮交互约定。

原生检查再次读取到旧候选窗口 58461048（队列运行 0），但两次激活均返回 `failed to activate captured window`。未关闭旧窗口，也未强行终止控制面。新目录包的窗口启动、按钮居中实际画面、干净机器、真实 SSH 和完整八页流程仍未验收。所有本轮构建/测试句柄已结束；准确续接点：恢复可操作桌面后安全关闭旧候选，从完整目录包验证原生窗口和读取目录按钮；独立继续其他业务验收。不要重复已通过的冻结诊断和 ODB 只读检查，除非相关代码变化。

源码与交接文档功能提交 `90d6608` 已推送 origin/main，push 返回 `8cdd9ac..90d6608 main -> main`。随后从该干净提交重新执行完整构建，1805 退出 0；最终目录 `GPTWork/release-win-x64-_eok77y5/AbaqusTools`，清单 sourceDirty=false、sourceCommit=90d6608，共 1642 个文件逐项 SHA256 通过。该最终目录的包内诊断和正式主机启动/API/安全关闭再次通过，诊断回执 `GPTWork/package-final-probe/bundle-probe-zzmw0g3w/verification.json`。离线分发候选为同级 `AbaqusTools-win-x64-90d6608.zip`，149452138 字节，压缩包 SHA256=`03f0d10caf730fe8f48b5b835268c7a7ade9ea058cbf2db7ab3fb18dc681f22e`；文件清单及压缩包记录见同级 `archive-verification.json`。候选仅保存在 GPTWork，GitHub 上传的是源码与文档，尚未发布二进制 Release。周额度最终读取剩余 76%，目标保持 active。

## 2026-11-18 全范围核对与结果浏览补齐

本轮重新读取八页迁移合同和 F001–F025 索引。整体目标仍包含功能对等、真实操作、性能、界面、完整使用与交接文档、README 和 GitHub 上传。用户增加周额度剩余 15% 时暂停，须等待用户确认再继续。额度工具本轮首次读取剩余 79%，该值按账户共享。

### 已完成的开发与检查

- F021 结果浏览补齐「更多 → 移到回收站」。确认所选路径后调用 Windows 文件操作，逐文件统计，部分失败保留已完成数量并刷新索引。范围校验覆盖根目录、导出文件扩展名、文件存在性与链接。F001 关闭等待当前清理和索引整理完成。原来的复制、导出移入同一菜单。
- F021 查询按批次浏览时省去重复子路径判断，分类统计合并为一遍。真实 GJB 批次 797 条、返回 500 条，优化前后各十次交替运行中位数为 51.18 / 30.32 ms，响应逐项相同。证据在 `GPTWork/result-list-performance-20261118.json`，只代表该目录上的本机查询。
- 全量 Python 基线 648 项、9 子检查通过，耗时 229.90 秒，记录 `GPTWork/migration-tests-20261118.xml` 和 `GPTWork/migration-tests-20261118-scoped.log`。包含模拟业务、真实 HTTP/C# 客户端和 Qt 启动检查，适用范围以具体测试为准。
- 修正默认测试发现范围为 `tests`，排除 GPTWork、虚拟环境和构建目录。首次未限定目录的测试在收集期间主动中断，句柄 14516 已返回退出码 1；后续正式测试句柄 91476 退出码 0。
- C# 结果浏览状态、表格检查及 6 项清理路径检查通过。Release 候选位于 `GPTWork/winui-migration-20261118`。
- 新增完整八页使用手册，README、Wiki 与文档入口均接入。

### 整体交付仍需的证据

本轮源码与使用文档已提交并推送到 origin/main，提交 `7b1f6fc`。Git push 退出码 0。周额度复查剩余 78%，目标继续 active。下一轮从上表的原生交互、真实合并/远程、发布部署检查继续推进；本轮所有测试和构建均已结束。

| 范围 | 当前证据 | 准确续接点 |
|---|---|---|
| 新建作业、队列、概览 | 全量测试覆盖命令、依赖、队列状态、外部纳管、失败和取消 | 原生页面输入、日志选区、已有长任务的跨页与恢复验收 |
| 计算资源与远程 | 本地资源及 SSH 替身测试 | 使用可连接的真实服务器核对指纹、传输、任务状态和断网 |
| 重启动链与结果合并 | 图计划、顺序执行及 API 检查 | 现有 ODB 副本的真实合并与原生交互 |
| 后处理与结果浏览 | TASK-001 的真实提取、图例、GIF、表格，以及本轮清理路径验证 | GIF 模式切换、系统回收站、复制、翻页和布局的原生验收 |
| 生命周期与发布 | 控制面测试、Release 构建 | 冷启动、意外退出、后台恢复，以及无开发环境机器安装包验证 |
| 文档与 GitHub | 使用手册、开发与交接导航已形成 | 核对本轮提交、远端回执，后续功能验收继续同步 |

上一轮 Microsoft.UI.Windowing 退出事件尚需复现定位。11 月 18 日 Release 成功启动，原生辅助功能树显示 Abaqus 2025 和控制面已连接，Ctrl+8 成功切换结果浏览，目录输入成功写入既有 GPTWork 结果路径。窗口截屏返回 `window capture timed out`，鼠标点击返回 `coordinate input geometry is unavailable`，视觉及鼠标验收继续待办。当前窗口来自 `GPTWork/winui-migration-20261118/AbaqusTools.WinUI.exe`，本轮未关闭它。系统回收站新入口未操作真实用户结果。

本轮收尾还检查 README 所列 Ruff 范围，修复既有导入顺序与字典构造告警，批次时间显式使用本地时区。升级记录和发布失败沿用既有异常契约，并在相应位置说明 lint 例外理由。Ruff 全部通过。修改后控制面与 WinUI 契约再次通过 195 项，日志 `GPTWork/control-final-20261118.log`，句柄 92236 退出码 0。结果/客户端/文档专项 67 项通过，新增 Wiki 导航检查后文档检查共 36 项通过。六个 C# 检查项目均退出 0，包括布局 13、日志 9、批处理 10、升级契约 9、控制面生命周期 8 项及后处理/结果模型检查。最终 Release 构建退出 0，零警告零错误。测试和构建句柄均已终止，桌面候选窗口仍保留。

本任务是待逐项核对的范围，不表示全部未实现。每项开始时根据当前源码和运行证据判断已完成/待修/待验收，避免重复已完成工作。按原迁移合同维护需求，不为了通过现有测试缩小交付范围。

每完成一个功能，同时写对应文档和测试记录，更新功能索引及当前状态；设计变化补 ADR。只有所有相关验收和必要文档完成后才能关闭对应任务。
