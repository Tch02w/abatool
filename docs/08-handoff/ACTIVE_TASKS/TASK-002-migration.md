# TASK-002：后续迁移、完善与整理

## 范围与前置条件

后处理交付后继续，不以现有八个页面存在证明迁移完成。范围来自本线程用户要求和 [迁移合同](../../winui-migration.md)。功能入口均可由 [功能索引](../../03-features/FUNCTION_INDEX.md) 定位。

## 接续顺序

### 2026-11-18 F003/F005 工作目录准备保护（源码与完整包通过，归档/原生待验）

从已完成 F008 候选继续审查准备/归档边界。实际发现 `_prepare_workspace` 在当前作业 LCK 和取消策略判定前已复制输入及 Restart 文件；原 Restart 复制先删除旧目标，复制失败可使旧文件丢失。修改前已向用户说明先只读验证、再逐文件发布的方案及归档另行处理的边界。

新增 `modules/submitter/local_workspace.py`，输入/名称/父作业/路径/子程序/执行参数/已有结果策略验证先于写入，目录链接及目标链接拒绝；单文件使用独有临时路径，复核源元信息、取消和锁后替换。临时文件仅本次拥有才可清理，同文件输入直接复用；不承诺全目录回滚和完整 SHA256。保留 `RESTART_DEPENDENCY_EXTENSIONS` 兼容别名供远端模块使用。`LocalJobProcessController.start` 将已接受取消与进程创建串行；相对子程序在改 cwd 前解析。数据检查 INP 的空白和部分 shell 特殊字符加引号，普通名字保持原输出。

实际测试及失败：

- 原代码 LCK 复现 **1 失败/10 deselected，0.09 秒**，目标 INP/parent.odb/parent.res 已被改写，`GPTWork/workspace-before-20261118.xml/log`。初步修复 15 项通过；后续 NTFS junction/硬链接/源变化等 23 项通过，日志分别为 `workspace-first-20261118` 和 `workspace-edge-20261118`。
- 首轮扩展命令误写不存在的 test_command.py，未执行测试，`GPTWork/workspace-regression-20261118.log`；改用 test_job_draft.py 后 **110 项通过，137.87 秒**，`GPTWork/workspace-regression-final-20261118.xml/log`，76952 已退出 0。范围为准备、执行、草稿、CPU、GPU/精度、本机运行/调度/内存、关闭与提醒。
- 实际 Windows 回显程序复现含空格 INP 被拆成参数：**1 失败/20 deselected，0.75 秒**，`GPTWork/workspace-command-before-20261118.xml/log`。命令修正后 32 项通过（0.95 秒），`GPTWork/workspace-command-final-20261118.xml/log`。后加含 `&` 文件名、相对子程序和临时名碰撞；没有启动 Abaqus。
- HTTP 重启测试初稿错误期望仅有失败条目时返回 202，实际产品正确返回 **409 / NO_PENDING_LOCAL_JOBS**，首轮 **34 通过/1 失败，2.94 秒**，`GPTWork/workspace-delivery-20261118.xml/log`。修正断言保留防自动重试行为；最终 **35 项通过，11.45 秒**，`GPTWork/workspace-delivery-final-20261118.xml/log`，74162 已退出 0。覆盖 26 项准备边界、4 项执行、4 项草稿及 1 项真实 HTTP/持久恢复。真实 NTFS junction 和全部夹具位于 GPTWork，原工程未写入。
- Ruff 初稿导入/未使用变量和 dict 构造提示已修正，最终所改源码/测试通过；diff 空白检查通过。同步文档后，文档导航/壳层契约/真实 HTTP 最终 **81 项通过，2.59 秒**，`GPTWork/workspace-docs-20261118.xml/log`，检查已结束。完整包随后补记，当前尚未运行。

用户再次关注按钮及 GIF，复核 F021 生产代码：读取目录左侧为加载圆环，空闲 Collapsed、忙时随按钮前景，内容双向居中；F020 双模式和 1500×1000 四份实际 GIF 回执已有记录，本轮未重复改写。原生窗口仍未恢复操作，不把源码/既有包等同实际外观验收。

代码、测试和文档已本地提交 **`4f4028110a4f0cb016dab647da157c13f321b53f`**。从该干净来源运行 `.\.venv\Scripts\python.exe packaging/build_release.py --no-restore`，完整目录 **`GPTWork/release-win-x64-e3e69bc08715/AbaqusTools`** 构建成功，96980 退出 0，日志 `GPTWork/workspace-package-20261118.log`。用户账户逐文件核对 **1659 文件/19 worker**，全部大小/SHA256 一致，sourceDirty=false，回执为该发布父目录的 `inventory-verification.json`。旧包保留。

完整包实际验证：

- 包内依赖通过：`GPTWork/bundle-probe-vun0fu70/verification.json`，含默认配置、worker、GIF、Agg、工作簿、SSH 加密及 Qt-free；日志 `GPTWork/workspace-bundle-probe-20261118.log`。
- 正式 C# 客户端 `GPTWork/remote-responsive-host/ControlPlaneHost.Tests.exe --launch-bundle GPTWork/release-win-x64-e3e69bc08715/AbaqusTools GPTWork/workspace-host-e3e69bc08715` 启动、资源/队列 API 与安全退出通过，6254 退出 0，`GPTWork/workspace-frozen-host-20261118.log`；隔离描述文件清除。
- `.\.venv\Scripts\python.exe GPTWork/verify_workspace_bundle_20261118.py GPTWork/release-win-x64-e3e69bc08715/AbaqusTools` 退出 0，97328 结束，`GPTWork/frozen-workspace-1ac420a2e39b/verification.json` 为 verified。正式冻结执行器遇到已有 LCK 时拒绝，源/目标全部夹具字节不变，回显命令未启动；两次后台启动恢复同一失败 attemptId，开始请求 409、没有自动重放，正常关闭。PID 165052/214776 均退出 0。
- `.\.venv\Scripts\python.exe packaging/verify_local_memory.py --bundle GPTWork/release-win-x64-e3e69bc08715/AbaqusTools` 退出 0，44351 结束，`GPTWork/local-memory-live-c608394af626/verification.json` 为 verified。两个不同执行、实际 Windows helper 内存采样、取消/正常退出、历史恢复、无自动重放和源文件不变通过；本轮未重复提醒专项。后台 PID 130976/217912、helper 210960/216900 均确认不存在。没有启动 Abaqus 求解。

最终回执同步后，文档导航 **45 项通过，0.10 秒**，`GPTWork/workspace-package-docs-20261118.log`；diff 空白检查通过。Wiki 中“旧候选尚未包含关闭选择”的过期说明同步更正为当前包已包含、原生窗口流程仍待验收。

准确续接点：本节所有测试、构建、自有后台和 helper 已结束，最近已验证包为 e3e69bc08715，包内文档是构建时快照，最终回执在仓库补记。下一项处理归档：`_archive_result` 的 root.mkdir 在异常保护外、逐文件移动可能部分完成、空目录可能被记成功；归档失败字段与求解成功的界面提示尚需分开，`_dependency_odb_path` 也需避免优先使用部分归档。Qt `archive_finished_job_files` 对照保留。必须先说明新归档实现方案再变更。没有替换用户窗口，未生成安装程序/ZIP/GitHub Release；具体 GitHub main 推送与恢复原生交互确认仍未收到。最近周额度剩余 **47%**，未触及 15% 暂停线。

### 2026-11-18 F008 慢远端通信期间读取状态（源码与完整包通过，原生/真实 SSH 待验）

上一轮为有效进展：冻结后台/存活子进程中断验证和文档已提交 `b95c39b`。本轮继续完整迁移合同，审查历史远端 GET 超时与连接锁后，找到独立可复现问题：远端连接/刷新/目录/传输/脚本执行持有连接锁，读取服务器状态也等待该锁。没有证据将其等同于历史 `remote-jobs` GET 偶发超时的唯一根因。

修改前已向用户说明方案：公开最近一次完整连接视图、标明更新中和旧资源采样，同时保持身份/指纹核对与实际命令串行。`RemoteServerService` 现以独立短锁发布/复制连接视图，所有通信入口在开始和 finally 发布状态；连接切换清空旧机器资源。返回值深拷贝，HTTP 叠加受管作业数不反写服务内部资源。事件游标与对应快照一起发布，不跳过尚未公开的状态。命令校验、超时、持久恢复和停止语义保持原有边界。

WinUI 资源页和状态栏使用 `RemoteServerConnection.DisplayText/StatusBarText`；旧后台缺少 busy/activity 时正常兼容。已知忙时定时器只 GET 当前视图，连接中的状态也继续观察，避免永久停在连接中或持续排入刷新命令。页面说明“资源值为上次读取”，不把缓存数值当新采样。原生点击/布局仍未恢复验收。

实际执行与证据：

- 旧代码的阻塞场景真实 HTTP 复现失败：`GPTWork/remote-responsive-before-20261118.xml/log`，读取 Future 超过 2 秒仍未返回，1 失败/3 取消选择，3.54 秒；失败路径释放自有测试通信，未遗留线程。测试初稿随后的 JSON 取值已改为项目公共解析助手，不改变该等待失败证据。
- 初步专项 5 项通过，2.66 秒，`GPTWork/remote-responsive-after-20261118.xml/log`；随后增加目录/上传期间可读两例。
- 完整相关 **127 项通过，187.46 秒**，`GPTWork/remote-responsive-regression-20261118.xml/log`，54121 已退出 0。包含新增 7 项、远端连接/提交/监控/恢复/传输、关闭保护、通知、SSH 连接单元与壳层契约；包括真实本机 PowerShell 进程恢复，不是真实 SSH/Abaqus 求解。
- C# 新增 4 项连接视图/旧协议兼容检查及既有客户端/生命周期检查通过，`GPTWork/remote-responsive-host-20261118.log`；客户端输出 `GPTWork/remote-responsive-host`。
- WinUI Release **0 警告/0 错误，22.02 秒**，1732 已退出 0，`GPTWork/remote-responsive-winui-20261118.log`，输出 `GPTWork/remote-responsive-winui`。没有启动或替换旧原生窗口。
- 继续复查发现，页面失败提示可能与旧的已连接状态并存；新增 `ShowRemoteActionErrorAsync` 在失败后读取后台视图，无法读取时仅将界面标为连接异常并保留原错误，不改变任务/服务器。修改前已向用户说明。最终 Release 再次 **0 警告/0 错误，13.07 秒**，64607 退出 0，`GPTWork/remote-responsive-winui-final-20261118.log`。
- Python Ruff 首轮仅新测试导入顺序不符，已修正；源码与新测试复查通过。事件游标随发布值保留的最终调整后，7 项专项与文档合计 **51 项通过，11.21 秒**，`GPTWork/remote-responsive-docs-20261118.xml/log`，50448 已退出 0。完整包及回执随后补记。

代码、测试和同步文档已本地提交 **`6890ffaaec6a0e792502fd045b192461e75969cf`**。最终交接前壳层/文档 **79 项通过，0.14 秒**，`GPTWork/remote-responsive-handoff-20261118.xml/log`。从该干净来源生成完整目录 **`GPTWork/release-win-x64-f4d22485d254/AbaqusTools`**，12357 已退出 0，`GPTWork/remote-responsive-package-20261118.log`。用户账户核对 **1658 文件/19 worker** 的大小与 SHA256 全部一致，sourceDirty=false；回执为发布父目录 `inventory-verification.json`。

包内依赖通过 `GPTWork/bundle-probe-p6825n94/verification.json`（默认配置、worker、GIF、Agg、工作簿、SSH 加密依赖和 Qt-free）。正式 C# 客户端从 `GPTWork/remote-responsive-host` 启动该包、验证资源/队列 API 并安全退出，`GPTWork/remote-responsive-frozen-host-20261118.log` 退出 0，隔离数据 `GPTWork/remote-responsive-host-f4d22485d254` 的描述文件已清除。

额外冻结接口/重启检查：`.\.venv\Scripts\python.exe GPTWork/verify_remote_snapshot_bundle_20261118.py GPTWork/release-win-x64-f4d22485d254/AbaqusTools` 退出 0，`GPTWork/frozen-remote-snapshot-7f0a7826cef3/verification.json` 为 verified。两次启动均返回 busy/activity 新字段与空闲状态，保存的隔离服务器配置重启恢复一致，无旧资源、未连接 SSH、未启动求解；后台 PID 161360/180528 已确认不存在，鉴权描述文件已清除。该冻结检查不包含慢的真实 SSH；慢 I/O 响应和错误路径由源码真实 HTTP 隔离测试覆盖。

发布回执更新后文档导航 **44 项通过，0.13 秒**，`GPTWork/remote-responsive-package-docs-20261118.log`；diff 空白检查通过。

准确续接点：本节所有测试、构建与自有后台均已结束，最近候选改为 f4d22485d254，旧包保持不动。未生成本轮 ZIP/安装程序/GitHub 二进制 Release，未替换用户旧窗口；包内文档为构建时快照，最后验收回执在仓库补记。下一项继续对照迁移合同核对工作目录准备、归档和中断处理，先读已有证据，不重复上述已通过长任务。真实 SSH、原生页面、连续三层工程链、目标机和具体 GitHub main 推送确认仍待完成；周额度最新剩余 **48%**，未触及 15% 暂停线。

### 2026-11-18 读取目录按钮复核与冻结批量进程中断（已验证隔离场景）

用户补充按钮文字偏右。重新核对 F021 生产 XAML 与状态更新：左侧为 `ScopeProgressRing`，不是常驻图标；空闲 `Collapsed`，读取时显示并绑定按钮前景色，按钮内容水平/垂直居中。该修正已经包含在当前 `release-win-x64-d1ad1556cf70`，本轮没有重复修改产品代码，也没有覆盖旧窗口或恢复被用户停止的桌面交互。实际业务窗口外观仍待验收。

连续链审查先复用已有证据：原只读扫描确认 65 组父子 ODB、最长仅两节点，GJB-15 的两个目标是兄弟分支。本轮没有再次扫描整个模型目录，也没有伪造连续三层工程链。改为补查尚缺的冻结后台突然退出、外部子进程仍活着时的恢复路径。

新增可复用工具 `packaging/verify_batch_interruption.py`，使用当前完整包、项目 `.venv` 和独立微小非 ODB 夹具。它在捕获自有进程身份后中断测试后台，保留测试子进程；重启后核对暂停批次、单步中断、继续失败、禁止重复执行与后续阶段未提交；第三次启动再次核对同一失败记录。测试清理仅操作已捕获的自有进程，释放等待程序、等待退出；保留日志/数据库/夹具，清除自有临时描述文件中的鉴权信息。

实际执行：`.\.venv\Scripts\python.exe packaging/verify_batch_interruption.py GPTWork/release-win-x64-d1ad1556cf70/AbaqusTools`，退出 0，回执 `GPTWork/frozen-batch-interruption-691d9fb533f3/verification.json`，日志 `GPTWork/batch-interruption-20261118.log`。三次启动、两阶段计划、仅一条子操作和一次测试命令；恢复状态 `suspended`，子任务错误 `ODB_MERGE_INTERRUPTED`，继续后 `failed`；没有结果发布、没有求解。三个输入全文件摘要不变。后台 PID 138308/149300/182040、后代 72384/137884/191592/216896 均确认已结束。

脚本首轮 Ruff 仅报告导入排序，已修正并复查通过；产品无变更，无需重复构建完整包。按钮相关既有壳层契约和文档导航 **79 项通过，0.22 秒**，`GPTWork/button-docs-20261118.xml/log`；同步说明与索引后文档导航 **44 项通过，0.18 秒**，`GPTWork/batch-interruption-docs-20261118.xml/log`，diff 空白检查通过。这不等于实际按钮外观通过。新增工具验证不证明真实 Abaqus 崩溃或三层链数值正确。

准确续接点：本节测试及原扫描句柄均不再运行，现有候选不变；继续推进尚未验证业务，不重复已经通过的冻结中断/兄弟双目标样本。原生交互恢复及具体 GitHub main 远端确认仍未收到，不重试桌面操作或推送。周额度本轮读取剩余 50%，未达到用户要求的 15% 暂停线。

### 2026-11-18 F028 GPU 与精度（源码与完整包通过，原生/真实求解待验）

上一轮为实质进展：F027 与 F023 已本地提交并完成完整包/真实 helper 验证。本轮对照合同补齐 GPU/精度输入；修改前向用户说明共用编辑区、默认不覆盖环境、共享预览/执行校验及持久恢复方案。依据 Abaqus 2025 执行文档，区分 GPU、Explicit 计算精度和 ODB 场输出精度，不将其合并成模糊“高精度”开关。

已写入共享模型/命令、控制面草稿/队列、远端启动/恢复/幂等签名、独立内存历史条件和 WinUI 共用编辑区；新建作业草稿保留原始输入，坏草稿必须明确恢复默认。队列设置可撤销覆盖，旧客户端省略字段不清除新值。显式双精度+单个目标文件在副本/备份前拒绝。范围与未实现 GPU 独占分配见 [F028](../../03-features/EXECUTION_OPTIONS.md)。

实际验证（集合重叠，不累计）：

- 初轮既有相关测试 **35 项通过，112.14 秒**，`GPTWork/execution-options-first-20261118.xml/log`（4280 已退出 0）。
- 首次 WinUI 构建因新编辑区 Grid.SetColumn 参数用 UIElement 而非 FrameworkElement 失败，`GPTWork/execution-options-winui-first-20261118.log`，51904 已退出 1；改正后 Release **0 警告/0 错误，15.38 秒**，`GPTWork/execution-options-winui-final-20261118.log`（2119 退出 0）。随后添加了坏草稿保留与明确重置，需再构建。
- 新专项 **17 项通过，14.35 秒**，`GPTWork/execution-options-new-20261118.xml/log`（52292 退出 0），含实际 Windows cmd/生产 PowerShell 参数传递；使用退出夹具，没有启动求解。
- C# 新增 **11 项**契约/草稿及已有主机检查通过，`GPTWork/execution-options-host-tests-20261118.log`；客户端输出 `GPTWork/execution-options-host-client`。
- 最后扩展 **138 项通过，178.86 秒**，`GPTWork/execution-options-final-20261118.xml/log`（80626 已退出 0），临时目录 `GPTWork/pytest-execution-options-final`。覆盖本轮 19 项、正式 C# HTTP 预览/入队/保留/撤销、内存键、调度、远端完成/恢复、队列、执行器和界面绑定。实际 Windows 本机/远端命令仅执行参数回显并退出，已核对自有进程退出；未调用求解或真实 SSH。

最后补充版本能力 `job.execution-options-v1`：新客户端只向支持的同一后台发送该组预览/提交/编辑参数；旧后台保留运行，新请求返回明确升级提示，不尝试自动替换或关闭。旧后台无 POST 副作用及正式客户端正向检查、文档导航 **46 项通过，4.01 秒**，`GPTWork/execution-options-capability-20261118.xml/log`（含文档 44 项）。此前末次原始字段草稿/API/文档集合 45 项通过，`GPTWork/execution-options-delivery-20261118.xml/log`。坏草稿补丁 Release 零警告/错误，14.60 秒，`GPTWork/execution-options-winui-delivery-20261118.log`；能力检查后的构建原句柄 63945。所有修改 Python 文件 Ruff 和 diff 空白检查通过。

最后能力检查后的 Release **0 警告/0 错误，13.03 秒**，`GPTWork/execution-options-winui-capability-20261118.log`（63945 退出 0）。当前正式主机测试客户端输出 `GPTWork/execution-options-host-final`，构建及全部契约/生命周期检查通过，日志 `GPTWork/execution-options-host-final-20261118.log`；包验证分支新增 `--execution-options`。最终文档导航 **44 项通过，0.15 秒**，`GPTWork/execution-options-docs-final-20261118.log`。全部自有测试和构建结束，最新周额度 **51%**。下一步是本地提交和完整包，不重复已通过测试。

准确续接点：上述全部测试句柄已结束。本轮尚未提交和构建完整包；先检查最后能力门禁的 Release、文档导航及代码审阅，再本地提交、干净来源打包，核对文件/依赖和正式客户端的包内提交参数。不要重复已通过的长测试。原生操作恢复未获答复，仍不操作旧窗口；真实 GPU/精度求解及 GPU 资源调度不能由这些测试证明。GitHub push 原自动审批拒绝未解除。周额度本轮开始 52%，未达暂停条件。

#### F028 最终完整包与准确续接点

代码、测试与 Wiki 已本地提交 **`35b2372a4b57041f5fac95919e9d959c575d603f`**；干净来源生成完整目录 **`GPTWork/release-win-x64-d1ad1556cf70/AbaqusTools`**。构建 8777 退出 0，日志 `GPTWork/execution-options-package-20261118.log`；旧包保留，原生窗口未替换。包内文档为构建快照，本回执补在仓库。

用户账户核对 **1658 文件/19 worker**，大小和完整 SHA256 一致，`sourceDirty=false`，回执 `GPTWork/release-win-x64-d1ad1556cf70/inventory-verification.json`。包内依赖探针 `bundle-probe-7617b9u5/verification.json` 通过，日志 `GPTWork/execution-options-bundle-probe-20261118.log`；不证明 SSH 连通或 GPU 实际可用。

正式客户端冻结命令：`dotnet GPTWork/execution-options-host-final/ControlPlaneHost.Tests.dll --launch-bundle GPTWork/release-win-x64-d1ad1556cf70/AbaqusTools GPTWork/execution-options-host-d1ad1556cf70 --execution-options`。退出 0，日志 `GPTWork/execution-options-frozen-host-20261118.log`。实际包内后台通过能力核对、预览、入队、旧式编辑保留与显式撤销；待运行条目没有 attempt ID，不曾启动求解。主机等待后台正常退出，描述文件移除；独立 INP 夹具内容未变。结构化回执 **`GPTWork/execution-options-host-d1ad1556cf70/verification.json`**。没有原始 G:\Job 写入、Abaqus/GPU 求解、SSH 连接或原生窗口交互。

准确续接点：本轮全部构建/测试/包内验证均已结束，无自有长任务等待。GPU/精度参数迁移和包验证已经完成，下一步继续原生/真实环境及连续三级 ODB 链验收；对照迁移合同审阅其余参数/错误路径。先只读检查现有 ODB 依赖关系，复用已有真实双目标证据；不启动新求解或重跑已通过样例代替剩余验收。GPU 独占分配/显存记账仍未实现，不将参数传递称为 GPU 调度。原生恢复问题与具体 GitHub 远端确认未获答复，不重试桌面操作或推送。周额度最后 **50%**，目标继续，未触及 15% 暂停条件。

### 2026-11-18 F027 作业结束提醒与 F023 成功响应修正（源码与完整包通过，原生待验收）

对照迁移合同发现 F003 的“结束提醒”保存到 QueueItem，但原生界面/控制面没有消费；旧 Qt 的 `notify_job_finished` 为每个作业打开消息框。改动前已说明新方案：后台确认终态后持久保存、按执行身份去重、跨页集中查看，使用非阻塞提醒，点击定位对应执行。用户此前 Esc 停止 UI 操作，本轮已询问是否可以恢复原生验收，尚未得到答复；先继续代码/后台验证。

已实现 F027：本机/远端完成回调、SQLite 提醒记录、恢复补查、已读持久确认及待保存关闭保护；远端 notify 选项保留默认兼容。全局非模态横幅可收起并从菜单重开，弹层阅读时冻结列表，本页已读只针对当前显示记录。再次运行产生新身份，查看提醒不能误定位同名新执行。详见 [提醒说明](../../03-features/JOB_NOTIFICATIONS.md) 和 [ADR 0013](../../submitter/adr/0013-durable-job-notifications.md)。

当前实际验证（集合重叠，不累计）：

- 首轮 7 项通过，`GPTWork/job-notices-first-20261118.xml`；后续通知与文档 53 项通过，`GPTWork/job-notices-final-20261118.xml`。
- 扩展控制面回归 **289 通过 / 2 失败，580.13 秒**，`GPTWork/job-notices-broad-20261118.xml`。一项为提取取消成功响应 Windows 10053；一项为真实远端恢复夹具在完成后读取超时（5 秒），不能记为全通过。
- F023 已定位并修正第一项：取消等不解析正文的命令接受 schemaVersion 正文，但发送成功响应前未读完，Windows 可能重置连接。成功 JSON 响应现在同错误响应一样限时排空已声明的小正文。真实 TCP 延迟正文回归用旧实现必然提前返回（`DID NOT RAISE TimeoutError`），证据 `GPTWork/optional-body-before-fix2-20261118.xml/log`；恢复实际修正后 **1 项通过，4.10 秒**，`GPTWork/optional-body-after-fix-20261118.xml/log`。旧实现仅在测试进程内替换，未回退工作区源码。
- 首次旧实现证明夹具导入顺序不当，默认调度路径指向 AppData，遇到 SQLite/权限错误，未进入目标断言。`GPTWork/optional-body-before-fix-20261118.xml/log` 保留为无效证明；改成显式 GPTWork 测试路径后才取得上面的因果证据。未清理或修改用户数据库。
- 修正后的 API、全部通用提取、真实远端恢复进程、通知和关闭协议 **48 项通过，123.57 秒**，`GPTWork/job-notices-delivery-20261118.xml/log`。包含 11 项提醒检查和两项扩展失败场景。远端超时在专项通过，没有证明其负载下超时根因已修复。
- C# 新增 **10 项**提醒契约/显示检查及既有主机测试通过，`GPTWork/job-notices-host-tests-20261118.log`；正式测试客户端输出 `GPTWork/job-notices-host-client`。最终 WinUI Release **0 警告 / 0 错误，14.26 秒**，`GPTWork/job-notices-winui-delivery-20261118.log`。修改 Python 文件 Ruff 与 diff 空白检查通过。
- 源码真实 Windows helper：`packaging/verify_local_memory.py --notifications --host-client GPTWork/job-notices-host-client/ControlPlaneHost.Tests.dll`，回执 **`GPTWork/local-memory-live-88f62b2d8635/verification.json`**。两次后台启动和 96 MiB 自有 helper，实际取消产生两条独立提醒；正式 C# 客户端读取、确认已读、重新读取为零；第二次明确运行产生新提醒。持久数据库两条记录、历史恢复、不自动重放、源夹具不变全部通过。后台 PID 187180/138308、helper 83880/136444 已检查不存在，连接文件已清理。未调用 Abaqus 或真实 SSH。

已核对用户截图：读取目录左侧为加载圆环，源码已在空闲时 Collapsed、忙时跟随按钮前景色；按钮文字水平/垂直居中，保留此前修正。GIF 两种控制模式已包含在源码及上一完整包。未操作旧原生窗口，不将构建通过写成按钮视觉验收。

另识别迁移合同中的 GPU/精度参数未出现在共享提交模型，使用手册已纠正为待迁移，不缩减原合同。原生八页、真实 SSH/MPI/负载、三层连续 ODB 链和目标机器仍待验收。

最终文档导航 **43 项通过，0.16 秒**，`GPTWork/job-notices-docs-20261118.xml/log`；包含功能索引、Wiki/README、接口、架构/ADR、任务与当前状态。读取已知 PID 均不存在；系统全进程 CIM 枚举被权限拒绝，未据此推断其他用户进程归属或结束状态。

准确续接点：上述测试与构建均已结束，无需重复启动。接着完成本轮文档导航检查、本地提交、从干净来源构建完整包，核对清单/依赖/正式主机，再用冻结后台跑提醒双启动流程。既有最新包仍为 `release-win-x64-a7e34c128937`，未包含 F027；新包通过后替换入口。周额度最新剩余 **53%**，未触及 15%。GitHub push 仍等待先前自动审批所要求的具体远端确认；本轮没有重试推送。

#### F027 最终完整包及准确续接点

功能、测试和文档已本地提交 **`2ff6740a7560c8f49a438652d152ba1978b78e4d`**。基于该干净来源生成完整目录 **`GPTWork/release-win-x64-2df945d26036/AbaqusTools`**，构建句柄 24218 退出 0，日志 `GPTWork/job-notices-package-20261118.log`。下面回执补记在仓库；包内文档是构建时快照。

- 用户账户核对 **1657 文件 / 19 worker**，大小和完整 SHA256 一致，`sourceDirty=false`；回执 `GPTWork/release-win-x64-2df945d26036/inventory-verification.json`。
- 包内依赖探针通过，回执 `GPTWork/release-win-x64-2df945d26036/bundle-probe-gflgahr1/verification.json`，包含 GIF、绘图、XLSX、SSH 加密库离线依赖及 Qt-free；不是 SSH 连通性验证。
- 本轮 C# 正式主机客户端 `GPTWork/job-notices-host-client/ControlPlaneHost.Tests.dll --launch-bundle` 启动/API/正常退出通过，日志 `GPTWork/job-notices-host-live-20261118.log`；隔离数据 `GPTWork/job-notices-host-2df945d26036`，描述文件已移除。
- 冻结提醒验证：`.venv/Scripts/python.exe packaging/verify_local_memory.py --bundle GPTWork/release-win-x64-2df945d26036/AbaqusTools --notifications --host-client GPTWork/job-notices-host-client/ControlPlaneHost.Tests.dll`；75321 退出 0。回执 **`GPTWork/local-memory-live-966282df5338/verification.json`**：两次独立执行 `cedc234a7ee34b9caf44ada74710e871` / `7554998a047448658aa5fb8282e184f7`，均确认取消；两条持久提醒、一条已读一条未读；C# 正式接口确认和重读通过。历史恢复、无自动重放、源夹具不变、后台正常退出均通过。
- 冻结 helper PID 165288/211824、后台 201948/210572 已直接检查均不存在，连接文件移除；没有 Abaqus 求解、SSH 连接或原生窗口操作。源码和冻结检查不替代原生验收。
- 最后文档检查 **43 项通过，0.15 秒**，`GPTWork/job-notices-docs-final-20261118.log`。最终回执补记后需再执行标准导航检查。

准确续接点：本轮源码、完整包、清单/依赖/正式主机、冻结通知全部结束，无未确认的自有长任务。下一步继续迁移合同中的 GPU/精度参数设计与实现，改动前向用户说明方案；原生恢复问题仍未得到答复，暂不操作旧窗口。其余缺口为真实 SSH/MPI/并发负载、三层连续 ODB 链和无开发环境目标机。不要重复已通过的通知 helper 或真实 ODB 样例。周额度最后剩余 **52%**，目标继续，不到 15% 暂停阈值。GitHub push 仍受此前自动审批拒绝约束，未重试；没有正式安装包或 GitHub 二进制 Release。

### 2026-11-18 F008/F010 持久恢复与重连（源码与完整包通过，真实 SSH/原生待验收）

改动前已说明方案：本地保存任务阶段，服务器保存提交回执；断线或后台重启只核对原任务，不重发启动。固定服务器地址、账户、指纹及工作目录范围，记录中不保存认证秘密。已实现 `remote_job_journal.py`、`remote_job_recovery.py`，接入远端服务/HTTP 和 WinUI 状态；离线取消持久保存，写入失败不启动新任务，损坏记录不伪装空历史。功能说明、索引、使用手册、README、接口说明、架构与 ADR 0012 已同步。

当前验证：`GPTWork/remote-recovery-first-20261118.xml` 为 1 失败/31 通过，真实 PowerShell 发现 `File.Replace` 的 `$null` 备份参数绑定为空路径；已改 `[NullString]::Value`，失败目录保留，夹具 PID 217996 已检查结束。第二轮 `remote-recovery-second-20261118.xml` 32 项通过，52.78 秒。Release `remote-recovery-winui-20261118.log` 零警告/错误。扩展 `remote-recovery-broad-20261118.xml` 291 通过/1 失败，295.27 秒：`test_manager_commits_successful_worker_only_if_not_cancelled[True]` HTTP 连接被 Windows 中止；57716 已退出 1，未重复启动。下一步专项复核此失败、补未核对状态的控制禁用、真实本机 PowerShell 恢复夹具、同步文档并构建。未连接 SSH 或操作用户求解。

本轮复核“读取目录”按钮：左侧是加载圆环；已有源码空闲 Collapsed、文本居中、加载圆环跟随按钮前景色，既有修正保留。GIF 两模式已实现，真实原生页面视觉和操作继续待验收。周额度本轮读取剩余 56%，未触发用户 15% 暂停条件。

后续验证已经完成：

- `.venv/Scripts/python.exe -m pytest tests/control_plane/test_remote_job_recovery.py tests/control_plane/test_remote_job_monitoring.py tests/control_plane/test_region_extraction_api.py -q --basetemp=GPTWork/pytest-remote-recovery-final --junitxml=GPTWork/remote-recovery-final-20261118.xml`：54 项通过，57.97 秒，91551 退出 0，包含扩展中失败的提取取消路径。未复现该 Windows 连接中止，不声称为它修改过产品代码。
- `tests/control_plane/test_remote_recovery_process.py` 独立运行：1 项通过，15.83 秒，52078 退出 0。实际 PowerShell 启动独立 cmd/等待 helper，丢失启动响应后令测试后台直接退出；新后台通过原回执接回原进程，启动计数 1，最终稳定成功。证据 `GPTWork/pytest-remote-recovery-process/test_real_launcher_survives_ba0/verification.json`，两个后台 211336/209488、launcher 209732、helper 197880 已检查均不存在；未操作用户进程。属于本机传输替身下的实际脚本/进程验证，无 SSH/Abaqus。
- 最后补充未核对状态控制禁用、损坏字段保护及路径规范化后，恢复/服务器/传输/关闭/文档专项 `remote-recovery-delivery-20261118.xml` **81 项通过，127.54 秒**（53536 退出 0，含 42 项文档）。Ruff 修改文件全部通过。新 C# 恢复显示 6 项及既有主机检查通过，日志 `remote-recovery-host-tests-20261118.log`。最终 Release `remote-recovery-winui-final-20261118.log` 0 警告/错误，13.56 秒，43049 退出 0。正式主机测试客户端输出 `GPTWork/remote-recovery-host-client`，已成功生成。

代码、测试与文档已本地提交 **`7e09e1ab9da7f24df018051d23575733cfad0b25`**，基于该干净提交构建完整目录 **`GPTWork/release-win-x64-a7e34c128937/AbaqusTools`**，构建 4997 退出 0，日志 `remote-recovery-package-20261118.log`。用户账户核对 **1655 文件/19 worker**，大小及 SHA256 全一致，`sourceDirty=false`；清单回执为发布父目录 `inventory-verification.json`。包内依赖回执 `bundle-probe-13o2g9iw/verification.json`，正式当前 C# 主机日志 `GPTWork/remote-recovery-host-20261118.log`，均通过启动/接口/安全退出。独立数据 `GPTWork/remote-recovery-host-a7e34c128937`，连接文件已由后台清除。包内文档为构建快照，本回执在仓库补记。

准确续接点：本轮测试、构建、清单、包内诊断和正式主机均已结束；实际 SSH、MPI、原生页面及其他迁移缺口仍待验收。旧窗口未替换，未启动求解。下轮优先核对原生业务/剩余迁移合同；本轮恢复测试已通过，无需重复。GitHub push 仍等待先前自动审批所要求的具体远端确认，没有重试推送。周额度最后剩余 **55%**，未达到 15% 暂停条件，目标仍在进行。

### 2026-11-18 F010 完成证据与日志增量（源码与完整包通过，远端恢复待完善）

上一轮完成内存观测和冻结包，属于有效进展。本轮先只读观察既有 GJA-13_V40D：主进程 86340（创建时间 1794888177.9505272）及子进程 196820 被识别，三次快照均与独立 psutil 读取的进程树/创建时间一致，观测 RSS 与同一快照求和完全一致；最后 20514975744 字节。回执 `GPTWork/live-solver-memory-045301de9317/verification.json`，脚本 `GPTWork/audit_live_memory_20261118.py`，执行句柄 25063 已结束。扫描首轮 13.43 秒，后两轮 0.258/0.298 秒。未控制或终止用户作业，没有启动求解；这证明单个真实 Standard/SMP 子进程覆盖，不覆盖 MPI、并发资源准入或原生显示。

发现 F010 两处明确误判：数据检查仅凭无进程三轮就成功；完成文字先于错误、活跃进程/锁判断直接终结。改动前已向用户说明新方案：以完成证据和稳定确认共同判断，错误优先、缺证据不成功，并去除重复远端日志。实现详见 [远端作业说明](../../03-features/REMOTE_JOBS.md)。

已实现：launcher 创建时间核对；真实 PowerShell 读取四类日志及文件签名；不可读和活动状态不授权终结；三次稳定确认，五次稳定无成功证据返回未确认失败；错误/终止证据保留；取消继续活动到稳定退出；按来源尾部重叠只追加新增行。公共 DTO 兼容，未改 UI 布局。

验证：`.\.venv\Scripts\python.exe -m pytest tests/control_plane/test_remote_job_monitoring.py tests/control_plane/test_remote_jobs_api.py tests/control_plane/test_remote_servers_api.py tests/control_plane/test_remote_transfers_api.py tests/control_plane/test_shutdown_guard.py tests/control_plane/test_shutdown_protocol.py -q --basetemp=GPTWork/pytest-remote-confirm-final2 --junitxml=GPTWork/remote-confirm-final2-20261118.xml`，**47 项通过，25.88 秒**，日志同名 `.log`。覆盖生产 PowerShell 本机真实文件/PID/创建时间不匹配、缺目录、快速 cmd 启动及稳定成功；只启动隔离 cmd 夹具，无 Abaqus/SSH 求解。Ruff 全部修改 Python 文件通过。

失败保留：`GPTWork/remote-confirm-first-20261118.xml` 为 1 失败/20 通过，测试请求漏必填 cpus/memory，补齐后通过。`GPTWork/remote-confirm-final-20261118.log` 为命令误写不存在 test_workbench_close.py，未运行测试；改用实际 test_shutdown_protocol.py 后通过。所有测试句柄已结束，没有重复启动长任务。

最后审阅发现共享错误词表包含可能出现在警告中的诊断词。新增 DAT/MSG 判断须区分警告与明确失败：数值奇异/零主元/畸变本身不覆盖成功，明确 `***ERROR` 或失败摘要仍优先；泛化 iteration terminated 也不当作业终止。补充三种警告与错误配对回归后，相同六个测试文件 **50 项通过，23.81 秒**，`GPTWork/remote-confirm-final3-20261118.xml`（`--basetemp=GPTWork/pytest-remote-confirm-final3`），句柄 39347 退出 0。Ruff 通过，文档导航 42 项通过。

本轮功能、测试、README/Wiki 已本地提交 **`11ee6fff32ba38db847596493ce2d571a8101051`**。基于该干净提交生成完整目录 **`GPTWork/release-win-x64-b2bb97c3929a/AbaqusTools`**；构建句柄 40263 退出 0，日志 `GPTWork/remote-confirm-package-20261118.log`。用户账户逐项核对 **1654 文件/19 worker**，大小和 SHA256 一致，`sourceDirty=false`，回执为该发布目录的 `inventory-verification.json`。包内依赖探针 `bundle-probe-zdf35c6n/verification.json` 与正式主机 `GPTWork/remote-confirm-host-20261118.log` 均通过：后台启动、资源/队列接口、安全退出。主机使用上轮构建的 `memory-host-client-c246927`，本轮 C# 代码未变化；隔离数据为 `GPTWork/remote-confirm-host-b2bb97c3929a`。所有本轮构建/测试句柄已结束，没有打开原生业务窗口或启动求解；包内文档为构建快照，本回执补记在仓库。

只读检查现有服务器配置：有 1 份非回环服务器配置及已存指纹，认证为用户名/密码，没有配置私钥文件；未读取或保存密码，未连接服务器。真实 SSH 验收仍需安全的交互登录，不在聊天索取密码。周额度最后剩余 **57%**，继续推进目标，未触发暂停。

准确续接点：下一迁移缺口是远端连接丢失后持续跟踪、重连及后台重启持久恢复；当前远端操作仍在内存、SSH 异常使操作失败，不能据此断言求解已停止。真实 SSH、原生八页、三层 ODB 链、MPI/并发高负载及目标机器仍未完成。已有 GitHub 推送自动审批拒绝未解除，不重试推送。不要重跑本轮已通过的单作业只读内存或本机 PowerShell 夹具，除非相关代码变化；不因冷扫描较慢重复启动观察任务。

### 2026-11-18 F005/F007 自有进程内存与历史估计（源码和最终冻结包通过，原生/真实负载待验）

修改前已向用户说明方案：接入按执行身份约束的实际进程采样，以峰值和安全余量辅助资源分配，按输入与执行参数区分历史；多作业共用扫描，未知读数不当零。已实现共享快照、PID/创建时间/子进程核对、首次与最终立即保存和中间 5 秒批量保存、短时峰值保留；外部刷新保留不变数值的时间戳。内存学习复用纯 Python 服务，SQLite 兼容元信息保留历史，队列和概览提示区分当前/峰值/估计来源。资源预算使用当前可用内存的 85%，抵扣活动作业尚未由新鲜 RSS 覆盖的预留。功能、错误和限制见 [内存说明](../../03-features/MEMORY_MONITORING.md)、[ADR 0011](../../submitter/adr/0011-native-memory-observation.md)。

实际验证（重叠集合不累计）：

- 首轮 32 项通过：`GPTWork/memory-first-20261118.xml`。扩展控制面、执行器、调度、队列及 WinUI 契约 **314 项通过**，`GPTWork/memory-regression-20261118.xml`（169.62 秒）；在末次外部时间戳/首次立即保存/85% 预算修改之前。
- 最后专项 **45 项通过，107.98 秒**，`GPTWork/memory-external-final2-20261118.xml`（日志同名 `.log`，临时目录 `GPTWork/pytest-memory-external-final2`）。
- 上一遍同集合 `GPTWork/memory-external-final-20261118.xml` 为 1 失败/44 通过：`test_observations_reach_api_queue_and_persisted_profile_without_new_scanner` 发现初始空队列保存周期会推迟首个样本 5 秒。每次执行第一次回调立即触发保存后通过，失败证据保留。
- C# 主机回归通过，新加 **6 项内存显示检查**，包括旧响应缺字段兼容；日志 `GPTWork/memory-host-20261118.log`。WinUI Release **0 警告/0 错误**，23.10 秒，`GPTWork/memory-winui-20261118.log`。Ruff 检查全部修改 Python 文件通过。
- README、Wiki、API、功能索引、架构/ADR、状态及任务同步更新后，标准文档导航检查 **41 项通过**（`tests/common/test_documentation_navigation.py`，`--basetemp=GPTWork/pytest-docs`）。
- 源码实际 Windows 进程：`.\.venv\Scripts\python.exe packaging/verify_local_memory.py`，回执 `GPTWork/local-memory-live-2bbf2fa42a36/verification.json`。两次独立后台启动，隔离 helper 各实际分配 96 MiB；观测 125173760/125001728 字节，历史估计 137691136 字节，PID/创建时间匹配，父后台未计入。重启保留估计、不自动再运行，明确重新排队产生新执行身份；关闭等待安全终态后退出 0、连接描述文件移除、源夹具不变。helper 181896/21032、包装进程 212460/211788 均已检查不存在，没有调用 Abaqus 求解。该回执在末次外部时间戳/首次立即保存/85% 预算修改之前；最终冻结验证将覆盖这些修改。

当前测试句柄均已结束（最终 60975 日志确认 45 项通过），没有遗留已知自有 helper。读取目录按钮修正仍保留；未操纵旧原生窗口，不能把内存显示逻辑通过当作悬停/布局验收。真实 Abaqus/MPI 高负载、完整原生业务、真实 SSH、三层连续 ODB 链和无开发环境目标机器仍待验。周额度本次最近剩余 59%，未触及暂停阈值。

源码阶段的续接点已执行，最终回执如下。记录失败句柄及原进程后才考虑重跑，不为验收启动求解。GitHub 推送仍等待此前具体远端确认；`b0e12f955ac4` 包属于前一阶段，不包含此内存改动。

### F005/F007 最终完整包及准确续接点

功能和文档本地提交 **`c2469272375a35713650b72376f62801f8065608`**，接口文档字段名校准提交 **`a4e8212c59035397d206c36b956f29241b60234f`**。首目录 `GPTWork/release-win-x64-e4e47d9696ae` 构建成功，但文档将公开字段误写为 rssBytes；实际接口一直是 runtimeMemoryBytes，没有功能代码变化。校准文档、41 项导航检查通过后重新生成最终目录，首目录保留但不作为本轮交付候选。

最终完整目录 **`GPTWork/release-win-x64-5a09eb59688b/AbaqusTools`**，干净来源 `a4e8212`，构建句柄 79927 退出 0，日志 `GPTWork/memory-package-final-20261118.log`。从实际用户账户逐项核对 **1653 文件/19 worker** 的大小和 SHA256，`sourceDirty=false`，回执 `GPTWork/release-win-x64-5a09eb59688b/inventory-verification.json`。

- 包内依赖探针通过：`GPTWork/release-win-x64-5a09eb59688b/bundle-probe-wqytpei7/verification.json`，包含 GIF、绘图、XLSX、SSH 加密库离线检查及 Qt-free。它不证明真实 SSH 连通。
- 使用本次构建的 `GPTWork/memory-host-client-c246927/ControlPlaneHost.Tests.exe --launch-bundle`，正式主机启动、资源/队列接口及安全退出通过，日志 `GPTWork/memory-host-live-20261118.log`；隔离数据目录 `GPTWork/memory-host-live-5a09eb59688b`。未显示或操作原生窗口。
- 冻结内存验证命令：`.\.venv\Scripts\python.exe packaging/verify_local_memory.py --bundle GPTWork/release-win-x64-5a09eb59688b/AbaqusTools`，句柄 31033 退出 0。回执 **`GPTWork/local-memory-live-aafe45770a9f/verification.json`**：两次执行身份不同，实际观测 125120512 / 125132800 字节；估计 137632563 / 137646080 字节。第二次冷启动已读到历史，明确重新排队前无操作或重复调用；总调用恰好 2 次，原夹具 SHA256 不变。结束状态、后台正常退出及描述文件移除均通过。
- helper PID 213956/203064，后台包装 PID 215904/198152 已逐项检查不存在。所有本轮构建/测试均结束，没有启动 Abaqus 求解或遗留已知自有测试后台。

准确续接点：F005/F007 内存开发与包验证已完成，下一步核对实际 Abaqus/MPI 进程覆盖及并发高负载、原生队列/概览内存悬停与读取目录居中效果；继续真实 SSH、三层连续 ODB 链和无开发环境目标机器验收。原始模型只读，不启动新求解替代验收；可操作桌面恢复前不重复激活旧候选或强制关闭窗口。全项目目标继续进行，周额度最后剩余 **58%**。GitHub 推送仍受此前自动审批拒绝约束，未推送；无新 ZIP/安装程序/GitHub Release。包内文档是构建时快照，本节最终回执补在仓库。

### 全范围顺序

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
