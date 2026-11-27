# 验收记录与已知缺口

## 2026-11-28 · 程序发布、性能与页面操作

本轮全量离屏回归 1164 项与 9 项子检查通过，旧 Qt 启动另测 1 项。Windows 安装向导逐文件弹错已实际复现并修复。直接浏览在 12,000 个文件的目录中完成 24 页正向与 23 页反向核对；另有结果导出取消、关窗、系统回收与重建索引的原生记录。两份工程日志的重放、三台同缩放显示器和重启动图谱八节点验收各有独立边界。[应用与安装](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md) · [结果浏览](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md) · [工程日志与显示器](../08-handoff/ACTIVE_TASKS/TASK-004-ui-interaction.md) · [待验条件](COMPLETION_AUDIT.md)

## 2026-11-27 · Windows 候选和工程出图

提交 `98d1bc7` 的 1131 项自动回归与 9 项子检查通过，另一次 Windows 实际启动检查通过。1692 个目录包文件逐项核对通过，专用测试身份从 `1fc22fd` 升级、卸载的 8 项检查通过。F022 的真实加载步按 B、A 两组先后发布，静态与动画各自使用预设色标。[安装与回归记录](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md) · [工程输入与输出](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md)

## 2026-11-24 至 25 日 · 分项验收

11 月 24 日至 25 日，真实 GJA 的 B 组分别从静态和动画视口读回手动范围 1–31，仅 B 组发布了 1 个模型。结果浏览页随后用 508 个 CSV 验证第二页搜索在提交前保留原范围，提交后清空旧选区，前后两次共导出 4 个正确文件。[F021/F022 工程和页面回执](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md)

指定运行范围已用 GJA/GJB 的三份页面请求验证。单组只派发该组内已勾选的成员，独立模型使用自己的色标，默认批量保留各组顺序与手动范围。实际 HTTP 队列核对了入队、追加及重复请求；未生成产物的检查正确记录零输出。空工作区的 11 项离屏检查另覆盖组名粘贴、图例失败后重试以及删除确认。[F022 详细记录](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md)

F022 的多模型对照已使用 GJA/GJB 工程 ODB 的实际扫描结构，验证不可用的复制步骤会指出目标模型，纠正后能保持各自的配筋、集合和帧配置。保存重开后的生产解析分别取到 GJA 的末帧 100 及 GJB 手选的 6 帧。原生控件联合回归 148 项通过，覆盖 64 模型分页、选中字段跨页复制及单格撤回。参数校验 38 项及草稿恢复 40 项通过，其中包含 300 模型差异草稿。空组建立、改名、成员分配、删除和工作区持久化已通过服务测试。当前桌面锁定，完整工作台的鼠标操作另待实测。各层的产物及运行范围见 [TASK-001](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md)。

F022 分组取消和续行已用 G 盘已有的 GJB-15 工程 ODB 验证。第一组取消，第二组发布九份 480 × 320 动画，每份为 41 帧、1.64 秒。客户端三组调度、过期命令、缓存结果和条件轮询的接口测试与原生窗口范围分别记录在 [TASK-001](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md)。

新建作业原生进入实际队列后仍为待运行，Core=4，内存 63%。三级链的错误依赖已在窗口内修复，再试自引用被拒绝；已保存的结果图执行了 1 个目标、2 个真实合并阶段，最终 ODB 有 3 步、15 帧。单元集 PICK 的截面结果为 36 行 × 24 列，与既有 CSV 摘要相同。从此结果目录切入 GJB 后再进 GJA，重用结果页时实际读取的范围数从 4 变为 16、20。跨模块自动回归 125 项通过，记录为 `GPTWork/cross-module-regression-20261124-r1/regression-receipt.json`。各页面证据与待验内容见[原生验收表](NATIVE_ACCEPTANCE.md)。

桌面截图和输入已恢复。F021实际通过：未读取的目录草稿在索引/侧栏刷新及内部开关后保持，操作仍指向已加载目录；原生文件夹选择器导出CSV与来源摘要一致；显式读取切换；非法目录清空并禁用旧文件动作；真实Excel中文预览与完整剪贴板；空闲正常关闭。证据GPTWork/native-result-context-desktop-20261119/native-result-acceptance-20261124.json，准确过程见[TASK-001](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md)。

F004 候选与正式两张表共用列定义，新增浅色行列分隔线。110 项生产控件通过。候选行实际点击、等待/刷新保持、最小宽度和横向滚动见 TASK-004。最新的完整目录包 7857f4955208 和未签名安装候选 898e84573199 已包含本次改动。

11月24日原生补验覆盖运行日志选区跨刷新、三行精确复制、切换作业、添加/编辑服务器的单行对齐和取消。508 条结果成功翻页，24 列宽表复制得到含表头 456 格，逐格及文件摘要一致。两个本地模拟作业跨窗口关闭保留并被完整包接回，停止关闭后均记录为已终止。详见[日志与表单](../08-handoff/ACTIVE_TASKS/TASK-004-ui-interaction.md)及[结果浏览](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md)。

完整包在本机打开 40 个候选和 40 个暂停调度的正式作业。两表长名称及长路径在本列省略，序号居中，浅色行列线与表头对齐。两表各选中前两行，再勾选第二个候选，入队勾选从 20 变为 21。两表纵向滚至候选第 29 行、正式第 26 行时刷新，位置保持；滚回首行仍可见四个原行高亮及正式表的两个勾选。回执 `GPTWork/native-formal-candidates-20261124/native-queue-acceptance.json`。使用隔离测试输入，未启动队列。

本轮专项复核有 55 项 pytest 通过，耗时 48.87 秒，另有 110 项原生控件、9 项日志检查及结果宽表、异步加载和导出检查通过。原始命令与报告位于 `GPTWork/table-result-regression-20261124-221603`。

以下11月20日及之前记录保留历史时点；其“当前受阻/当前进程”不能覆盖本段新事实。完整八页与目标机验收未完成。

2026-11-20恢复后阻塞复核：用户输入准备轮及两次续接均出现相同点击错误；当前cua_repl重新绑定7078082可读取999，但截图超时、点击已选CSV仍报coordinate input geometry is unavailable，焦点不变。没有新增原生通过项；不撤销下方有效的人工截图证据。前台234192/后台219004/227524身份和四份源摘要保持，resumed-blocked-audit-20261120.json保留在GPTWork/native-result-context-desktop-20261119。既有人工问题、八页其余业务与目标机仍待，准确续接见TASK-001/TASK-002顶部。

2026-11-20新增人工证据：用户明确最新999截图是在点击“读取目录”之后，根目录为“待读取结果”、提示消失，N08步骤4的正常切换部分通过；非法目录处理仍未验。后台任务ce1bbd5ccfd04cd49e568bd144c7a80b于00:05:26（UTC+8）成功，实际请求根目录为“当前结果”。索引刷新时是否保留123和草稿提示尚待确认，不把随后显式读取的999当作误切换。截图/回执manual-read-root-20261120保存在GPTWork/native-result-context-desktop-20261119，四份源摘要不变，前台234192及后台219004/227524仍为原身份。最新待反馈问题见TASK-001顶部，下段反向输入属于此前观察。

追加原生输入证据：现有7078082窗口实际加载“待读取结果”并预览CSV=999，桌面set_value成功将输入改成“当前结果”而不读取；提示保持实际目录“待读取结果”，CSV仍为999。点击刷新索引仍报coordinate input geometry is unavailable，Tab后焦点未变化，不计点击/键盘导航通过。native-index-draft-reverse.json记录此反向草稿检查，人工索引刷新仍待，未修改生产代码或重新启动。

2026-11-19新增人工原生证据：用户在最新0aba结果浏览截图中将输入改为“待读取结果”，没有读取，提示明确保留实际操作目录“当前结果”；所选load_point_raw.csv预览time=0、force=123。N08步骤1通过，源CSV/XLSX四份摘要不变；截图及回执位于GPTWork/native-result-context-desktop-20261119/manual-root-draft-20261119.png/.json。用户随后澄清关闭为手动误操作，不计崩溃或索引失败；旧unexpected-close-20261119-2341.json保留最初报告，manual-close-confirmed-20261119.json记录更正。现有234192及37319仍在，N08步骤2尚未完成。首项证据不扩大为索引、导出或全页通过，下一问题见TASK-001顶部。

2026-11-19阻塞复核与独立回滚启动：当前源码真实Qt主窗口构造/退出1项通过（9.25秒，会话85097退出0，GPTWork/native-rollback-current-20261119/results.xml），使用独立G盘TEMP/TMP和应用数据。现有WinUI窗口9249544仍可读但点击报coordinate input geometry is unavailable，重新定位激活报failed to activate captured window，远端未连接；同一输入障碍已连续至少三轮。212240消失没有可用应用日志/对应Windows错误事件，关闭原因仍未知，未补记正常退出。完整验收受阻，不等于后台功能失败或迁移完成；恢复条件见TASK-002顶部。

2026-11-19最新全量自动回归：干净2343765（应用负载1d3c981）1085项及9项子检查通过，840.76秒，JUnit共1094项且0失败/错误/跳过。Qt offscreen，TEMP/TMP、应用数据及缓存均G盘隔离；本轮排除单独原生Qt启动。原会话98987退出0、166852/155748已结束；GPTWork/result-full-regression-20261119/tests.log和results.xml为实际回执。生产队列增量逻辑已复核，不能以自动通过代替业务页多选等待、鼠标或像素验收。准确命令见[TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)顶部。

结束后进程核对：新前台212240已不存在，后台219004及子进程227524仍在，旧9528仍在。未观察关闭过程，不计正常关闭通过，未终止或重开；下段“保留窗口”仅为先前时间点。

最新原生补充（2026-11-19）：0aba完整包窗口2164996实际出现在当前桌面，结果浏览加载4范围节点、控制面连接；仅为初始加载文字观察。点击模型geometry unavailable，编辑目录及重新绑定Raise均activation失败；用户CSV/目录提示核对尚待。回执GPTWork/native-result-context-desktop-20261119/native-observation.json；前台212240/后台219004及旧9528保留。下方不可定位/收尾记录对应前一次178864，不能混淆。完整步骤见[原生验收](NATIVE_ACCEPTANCE.md)。

2026-11-19 F021新源码：预览/真实工作簿HTTP26项、界面接线/正式C#客户端真实HTTP40项、目录身份及同名异内容文件导出11项、既有生命周期和WinUI构建通过。10万共享文本合成预览Python分配峰值约68.7MiB降至0.35/0.38MiB（早/晚引用），不是应用RSS或完整工程性能。错误基线、全部回执与未验范围见[TASK-001](../08-handoff/ACTIVE_TASKS/TASK-001-postprocessing.md)顶部。新源码1d3c981完整0aba和安装9a已生成；全摘要/依赖及11项冻结HTTP通过，原生窗口不可定位且已收尾，不能声称原生布局通过。

此前候选为干净6b4ade1完整e658a77e8d53/安装候选1fff69dedb9b，包含队列局部刷新及传输观察修复；全摘要和包内探针通过。相同负载独立测试身份安装生命周期aa87c2237002完成8步，活动后台保护、升级保留旧版本/用户文件、安装后正式主机API与退出、卸载14个数据文件摘要保留及测试登记清除通过，无强制收尾/残留。首轮196971a98c8c因检查器私有目录权限失败，失败及仅卸载测试程序的收尾回执保留，不能计完整通过；预检已前移，缺工具负向检查通过。汇总GPTWork/queue-release-lifecycle-20261119/verification-summary.json。正式标识未安装、NotSigned；原生完整业务和无SDK目标机仍待，历史记录不当作本包原生复测。

2026-11-19：本轮服务器表单、队列定向更新及命名修复已进入干净9a09972完整555b572ccbfe和未签名安装候选9f4880b493e0。54项原生控件、211项相关回归、全摘要/包内依赖与冻结API检查通过；实际窗口确认待用户反馈，安装器未安装。汇总GPTWork/queue-dialog-delivery-20261119/verification-summary.json。此前10项真实SSH传输对应旧2c18包，旧安装生命周期9dce03ed6016仅代表历史负载。准确当前版本见[当前状态](../08-handoff/CURRENT_STATUS.md)；以下各段保留各自历史范围。

2026-11-19补验同一555b包：真实GJB单步合并在82%校验阶段中断自有后台，真实SMAPython仍存活；新后台恢复中断记录、同请求不重放、不发布结果，第三次启动记录不变，旧目标和来源全摘要不变。校验进程被短暂停住固定时序，恢复后退出120，不计校验成功；所有本次进程结束，中断工作区保留。回执GPTWork/real-merge-backend-crash-9597d1bc621d/verification.json。此项不修改生产代码、不重建包，也不替代原生操作或真实批量后续阶段的异常验收。

同轮另补真实三级小模型批量：第一阶段82%后台崩溃，恢复为等待继续；显式继续后因原子任务中断而失败，完成0/2、第二阶段未提交、无结果。原SMAPython保持存活直到上述核对完成，再恢复执行并退出120。第三次后台启动仍恢复同一失败批次，无重放，来源摘要不变、所有本次进程结束。回执GPTWork/real-batch-backend-crash-453005f06383/verification.json；首次未命中故障时序的7217cd20dc0d回执及安全收尾保留，不能计通过。没有重新求解或修改原始工程。

历史完整758f1cc/5497f45cfec3、安装候选b4ca03cbe0c8的1687文件/19worker/15资源、依赖及同负载安装生命周期7818c66a5988通过。两旧密度窗口及197448已正常结束；227408前端结束后，其闲置后台经核对身份及正式idle协议收尾，未强杀。所有日常配置摘要保留。旧完整候选不含本轮侧栏细节，不能作为本轮最终输出。

本轮界面密度追加：InfoBar关闭仍占24 DIP的根因已原生复现，生产布局修复后13项控件及正常退出、16项尺寸、39项相关回归通过。更新后业务窗口尚待确认；完整包/安装器仍待纳入新密度与侧栏位置。此前1008+9全量回归对应4cb源码，不算本轮新代码全量复测。精确日志、临时窗口与失败见TASK-002顶部。

当前源码4cb0503包含侧栏状态和结果选择递归修复。真实旧窗口70244的栈溢出说明：旧d4fc4c7完整包的启动、摘要和安装证据不能证明结果业务可用。修复后9项生产侧栏控件、39项相关回归通过；开发输出winui-explorer-fixed-20261118已读取4范围，用户操作和CUA确认模型甲/CSV前50行3列预览正常，实际导出全部80行1408字节与源摘要一致，198808/51160及子进程正常退出；原生取消/部分失败/大文件/回收站仍待。准确活动进程、候选限制和下一步以[当前状态](../08-handoff/CURRENT_STATUS.md)为准。

## 历史阶段记录

下面带候选编号、PID或“最新”的文字描述记录时的状态，不代表当前运行入口；旧证据保留原验证范围。结果选择崩溃及修复过程见[TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)顶部。

2026-11-18 最新完整包：干净d4fc4c7目录ddd54a85dcf8、安装候选3fcfb102d9d4；1687文件/19worker/15应用资源、依赖探针、实际新包资源/合并页首次加载与正常退出、同身份完整旧负载升级卸载c80065c565a3均通过。未签名、正式身份未安装。`GPTWork/firstload-release-verification-20261118/verification-summary.json` 记录准确范围，并注明保留的结果浏览窗口70244等待用户确认CSV预览；原生记录预览/导出仍未通过。下方“尚不含两项修复”是早期候选状态，新包已纳入。

2026-11-18 首次加载续验：07ccd1e06113其余五页实测，队列/概览/重启动链空状态正常，资源与合并各发现一项初始化缺陷。修复发布输出winui-firstload-fixed-20261118已实测资源无误报、图自动读取/目录编辑/正常关闭保存revision=1；名称/CPU=4及Ctrl+7/8复核通过。81项相关回归通过，所有本轮自有窗口/后台结束；汇总 `GPTWork/native-firstload-fixed-20261118/verification-summary.json`。八页已有跨候选版本的有限加载观察，不等于完整业务/视觉验收。下面4787f0f完整包和安装器尚不含这两项修复，准确失败/命令见[TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)顶部。

上一完整发布候选：干净4787f0f目录07ccd1e06113、正式标识安装器10f24dcc8dc8。1687清单文件/19worker/15项应用资源、包内依赖及实际完整包原生名称/CPU=4恢复、后处理/结果页有限状态和空闲退出通过，`GPTWork/resource-release-verification-20261118/native-verification.json`。新负载同身份旧→新安装生命周期0d5a9b4b803e通过，旧库存兼容读取不代表旧包可运行，新负载严格验资源；无残留测试进程/登记。正式身份未安装，NotSigned，全部八页/目标机仍待。

2026-11-18 发布验收更正：a52c480 完整包73c34ceec193虽然清单/后台/安装生命周期通过，实际原生启动却因缺少应用 XBF/PRI 退出0xc000027b。129b257等同流程旧包也不能据此前后台检查认定可运行，保留追溯并撤出可运行候选。已修复publish资源收集和双门槛，20项发布检查通过；修复发布输出原生名称/CPU=4恢复、新建/后处理/结果页加载及正常退出通过，包内后台路径已核对。精确失败、进程终态及最终干净候选见[TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)顶部。

2026-11-18 已获授权恢复原生验收。新增独立配置的 14 项生产检查通过；CPU/结果初态修复后 72 项相关回归通过，22.59 秒，最终开发构建 0 警告/错误，11.88 秒。真实窗口观察和磁盘核对确认名称/CPU=4 保存及恢复、同配置单实例、目录选择/读取、结果目录重开恢复、Ctrl+7/8、后处理空目录无错误以及空闲正常退出。记录的两份日常 JSON 摘要不变，没有创建/移动 ODB 或启动求解。精确阶段/最后追加检查见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md) 顶部。

回执 `GPTWork/native-acceptance-20261118-a/verification-final.json` 为 partial-native-acceptance；最终自有窗口/后台/子进程均退出。普通工具启动窗口不可发现的实例只作失败清理；同一二进制从已授权可见桌面启动后可发现。截图/鼠标定位和选文工具仍不可用，因此不认定八业务页视觉、日志拖选、悬停、原生导出或跨屏验收通过。最新开发目录 `GPTWork/winui-native-startup-final-20261118`，下述 129b257 完整目录和安装包尚不含本轮改动。

2026-11-18结果导出修复已进入129b257完整候选：此前源码24项生产文件检查、46项相关回归及构建通过；本轮另直接引用完整包DLL执行24项导出检查，核对DLL摘要一致，取消/部分失败/重名不覆盖等通过。未调用原生选择器/回收站；所有数据仅G: GPTWork。额外探针最初NuGet还原/本地DLL加载失败及最终修正回执均保留，见TASK-002顶部。

最新完整候选为干净129b257：目录bbb1a83a8997、正式标识安装候选b1639b2aeb30，1671文件/19worker摘要、依赖及正式主机通过。相同负载的独立测试身份生命周期e2b22336049c通过，覆盖初装、升级保留、活动后台拒绝、开始菜单、安装后API和卸载保留用户文件，无残留测试进程/登记。正式身份未实际安装，NotSigned。准确路径见[当前状态](../08-handoff/CURRENT_STATUS.md)，下方旧候选和未打包语句仅描述各历史阶段。

2026-11-18最新源码补齐当前作业后处理路由：30项生产路径检查、四种归档状态的正式C#客户端/真实HTTP定位与发现、111项相关回归（含49文档）和174项既有后处理通过，最终WinUI构建0警告/错误。仅使用G:路由字节夹具且文件前后相同，不是实际ODB内容或原生菜单验收。d5f9e76完整候选尚不含本轮路由变更；精确日志和后续候选更新见[TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)顶部。

最新完整目录为 `GPTWork/release-win-x64-2c491d8001f9/AbaqusTools`（干净d5f9e76）：1670文件/19worker完整摘要、包内依赖、正式主机启动/API/正常退出通过，证据 `GPTWork/command-release-verification-20261118`。安装候选cc6a49dda23f的负载/安装器同源、摘要/PE架构核对通过，NotSigned，尚未实际安装新负载。包含新建及菜单变更；下方7c874d3候选与隔离生命周期均属前一阶段。本轮获用户明确授权并成功推送d5f9e76到GitHub main；准确回执见TASK-002顶部，整体迁移仍未完成。

F001/F004/F005/F008共享菜单状态及远端身份：26项状态检查通过（包含于正式客户端包装），20项服务器/客户端定向回归64.40秒（`GPTWork/command-target-regression-20261118.log` / `.xml`）、其余92项相关回归12.58秒含49文档（`GPTWork/command-state-regression-final-20261118.log` / `.xml`）通过。正式客户端只读观察4项、目标身份5项使用真实本机HTTP与替身SSH；不称真实远端验收。初次55通过/1后台刷新工具栏约束失败已保留，拆分后台忙碌后保持原检查；最终WinUI构建0警告/错误15.24秒（command-state-winui-build-delivery-20261118.log）。原生及新完整候选仍待，详见TASK-002顶部与ADR0020。

F001/F003最新源码：显式新建确认/重置16项生产状态及实际JSON检查通过，既有7项持久化+15项系统会话检查通过；相关Python回归99项通过29.10秒（`GPTWork/new-job-reset-regression-20261118.log` / `.xml`，含49文档、实际HTTP关闭/图恢复及新建专项包装）。首次WinUI构建0警告/错误，最终导航忙碌保护构建及收尾见TASK-002顶部。原生确认/焦点/关闭重开未验，7c874d3完整包不含本轮菜单改动。

最新完整目录 `GPTWork/release-win-x64-c245b91545d7/AbaqusTools`（干净7c874d3）：1669清单文件/19 worker完整摘要、包内依赖和正式主机启动/API/退出通过，回执 `GPTWork/draft-release-verification-20261118`。正式标识安装候选c513706de2c4来源/摘要/PE架构核对通过，NotSigned。新负载测试标识b7f81001e859与旧8a79e216e0c5的隔离生命周期 `GPTWork/installer-lifecycle-4d8a268bb72f/verification.json` verified，含中文空格路径、陌生/链接目录拒绝、活动后台拒绝、升级保留旧版本和用户文件、开始菜单更新/清除、正常卸载；无强制收尾、无残留自有进程/测试登记。

最新完整无桌面回归 **979项及9子检查通过，579.98秒**，99701退出0；`GPTWork/draft-release-verification-20261118/full-suite-final.log` / `.xml`。首轮978通过/1失败/9子检查通过，模拟远端作业固定3秒等待超时；原用例独立复测通过，改为启动/监测信号并同时覆盖starting/running断开保护后模块4项及完整回归通过。产品源码未修改。测试TEMP/TMP、数据与basetemp均在G:项目GPTWork；Qt为offscreen，原生窗口启动测试排除。准确过程及限制见TASK-002顶部。

## 分阶段验收记录

以下保留各阶段执行结果和当时缺口；已由顶部新候选补齐的打包事项不再视作当前未完成。旧回归不与本轮重复累计，原生交互仍待验收。

F001/F022后处理恢复草稿：38项专项（`GPTWork/postprocess-draft-checks-20261118-02.log`）、174项既有后处理（`postprocess-draft-existing-checks-20261118.log`）、16项共享结果图（`postprocess-shared-graph-checks-20261118.log`）通过；最终WinUI构建0警告/错误（`postprocess-draft-build-delivery-20261118.log`）。相关Python初轮41通过/1静态定位失败，更新后91项通过24.24秒（`postprocess-draft-regression-final-20261118.log` / `.xml`，含49项文档）。本轮补齐工作区/四类弹窗源码，下方“尚缺”只描述历史阶段。原生数值输入/关闭恢复、按钮实际显示和新完整打包仍待验；本轮测试只在G:项目GPTWork，不移动用户ODB。详细失败和句柄结束记录见TASK-002顶部。

F001/F012结果图独立恢复：最终16项JSON/状态/文件检查通过（`GPTWork/graph-draft-checks-20261118-02.log`），65项相关回归通过13.41秒（`GPTWork/graph-draft-regression-20261118.log`、`.xml`），其中生产C#客户端对真实隔离HTTP核对本地草稿不提交、版本变化拒绝覆盖、原草稿保留；最终WinUI构建0警告/错误（`GPTWork/winui-graph-draft-build-final-20261118.log`），49项文档通过。原生恢复及完整包未验收，详细工作区/弹窗草稿尚缺。本轮仅G:测试JSON/占位ODB，不移动用户ODB；用户新约束禁止后续C:ODB验证目标，历史跨卷记录不授权复用。

F001源码新增每两秒登记字段检查点、串行后台写入、失败提示与OS会话结束专用入口。7项既有持久化及15项新状态/磁盘检查通过（`GPTWork/session-end-checks-20261118-02.log`）；真实输入快照不可变、64次顺序、未变化不写、文件丢失重建、失败重试、取消/重复/超时均覆盖。98项相关回归含49文档通过22.58秒（`GPTWork/session-end-regression-20261118.log`及`.xml`），最终WinUI构建0警告/错误；句柄均结束。模拟消息没有发送给原生窗口，没有实际关机；既有完整包/安装器尚未更新。复杂工作区/结果图草稿覆盖和原生恢复仍缺，准确回执见TASK-002顶部。

F026安装新增：11项清单检查通过；测试标识实际首次安装/升级/卸载、全摘要、活动后台拒绝及开始菜单更新/清除通过，回执installer-lifecycle-599f6e10a6fd。测试注册和自有进程全结束，无原生窗口/求解。目录链接祖先拒绝与全部生命周期/菜单回归也通过（installer-lifecycle-a1a720d99f20），60项清单/文档通过；正式标识cfa638b65fa8从干净e69192b构建，摘要/来源/架构核对通过、NotSigned，未在目标机安装，详见TASK-002顶部；本机结果不能替代无开发环境目标机。

本轮整体合同核对见[交付清单](COMPLETION_AUDIT.md)。整套无桌面首轮944通过/17失败/9子检查通过，失败为共享Qt夹具队列干扰退出判断；已隔离HTTP测试目录。另行四项真实HTTP复现指定队列的资源/链/计划/批量来源错误，源码修正后12项定向通过（scope-after.log）。完整重跑966项及9子检查通过746.54秒（final.log/final.xml），文档48项通过，所有测试句柄已结束；新完整包6d5279845a23来自干净b2cfd57，1664文件/19worker完整摘要、包内依赖和正式C#主机启动/API/退出通过，所有句柄结束，精确记录见TASK-002顶部。排除原生窗口测试，不计作通过。

冻结包补充验证（产品仍为03b4adf/75efcbf6b9f7）：独立源路径 `GPTWork/scheduler-load-live-3a1be04c8ea6/verification.json` verified，261路径/5执行、260次GET中位38.808/P95 279.41/最大446.392ms。跨卷并发恢复 `GPTWork/archive-recovery-live-4db89f22762e/verification.json` verified，128MiB文件复制8MiB中断、完整摘要/半成品保留/源清理/重启去重，以及两个正式客户端6次明确忙碌拒绝后依次完成。原默认源码小夹具回归983424f3695b通过；首次3b67843bedc9正确忙碌拒绝导致验证失败，已保留，不称产品缺陷。所有本轮自有进程结束；工具/文档更新，应用未重建。并非工程多GiB/断电、MPI压力或原生界面验收。

跨卷新增证据：既有75efcbf6b9f7包、正式C#客户端、G:→C:不同设备，两种中断场景各128MiB。`GPTWork/archive-recovery-live-d91a5ee5c815/verification.json` verified，8MiB不完整副本保留并核对摘要，已完成INP复用inode、完整归档摘要、源清理续接、原始输入不变、两次重启与提醒去重通过，所有自有进程结束。具体目标根及设备号见TASK-002顶部。不是工程ODB、多GiB压力、断电或原生鼠标操作验收；产品没有修改或重新打包。

最新完整包 `GPTWork/release-win-x64-75efcbf6b9f7/AbaqusTools`（干净03b4adf）通过1663文件/19worker摘要、依赖 `bundle-probe-asbma2v2/verification.json`、正式主机启动/API/退出。冻结 `GPTWork/scheduler-load-live-b52bd66c9cfb/verification.json` verified：261行/5执行准入及停止/终止/失败、单项失败释放额度时另一作业继续、5条提醒重启不重放，输入不变、自有进程全结束。233次GET中位39.94/P95 284.58/最大1137.44ms。75项相关及65项通知/文档回归通过；下方源码阶段“待验”由本回执补齐。不是独立工程模型、MPI/CPU压力或原生操作验收，所有旧包/失败证据保留。

261行队列与5次实际非求解进程：源码 `GPTWork/scheduler-load-live-afc4a08d44b5/verification.json` verified，正式C#客户端、CPU/内存等待、停止派发、单项终止、失败、编辑后放行、5条提醒持久恢复及不重放、输入摘要和所有自有进程结束通过。260次GET中位39.50/P95 266.12/最大1050.74ms。261行中256暂停条目共用一个INP，不是工程/MPI满载或261个不同模型。修复前超时回执与线程栈保留于171fc499f113/8c23ea54fc7a；另有Datacheck失败漏提醒复现和修复。75项相关检查通过59.46秒，新完整包与通知专项最终结果待收尾；精确记录见TASK-002顶部。

外部扫描新完整包 `GPTWork/release-win-x64-5f29d9d738de/AbaqusTools`（干净a01382f）：1663文件/19worker用户账户全摘要、依赖 `bundle-probe-iqcgci8t/verification.json`、正式主机启动/API/退出通过。`GPTWork/external-scan-live-2b0fdadc1f67/verification.json` verified：扫描期间62次读取73.38–489.22ms，自动监测实际自有进程退出完成、输入不变；归档恢复回归 `GPTWork/archive-recovery-live-7ddb793bdfea/verification.json` verified。全部自有进程结束。首轮冻结验证脚本与周期扫描竞态409失败保留，验证器改为等待原扫描，产品不变；不视为工程负载或原生UI验收。下方“新完整包待验”由此最终回执补齐，旧包记录为历史。

F004/F005外部扫描并发：`GPTWork/external-scan-delivery-20261118.xml/log` 96项通过（308.37秒），追加边界 `GPTWork/external-scan-edges-20261118.xml/log` 13项通过（3.14秒，重叠不累计）；修复前两项读取阻塞复现保留。源码真实进程/正式C#客户端 `GPTWork/external-scan-live-8801618bf931/verification.json` verified，扫描期间71次读取79.37–431.06ms，退出完成、输入不变、自有进程结束；非Abaqus求解/非工程负载。首次脚本字段错误失败回执402ccde15b89保留。Release零警告/错误20.64秒，正式主机检查通过，新完整包尚待验证，原生交互仍未验收。细节及接续见TASK-002顶部。

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
