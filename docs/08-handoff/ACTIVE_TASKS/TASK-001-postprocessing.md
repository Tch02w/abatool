# TASK-001：数据提取与后处理应用交付

## 2026-11-20 · 显式读取新目录通过，索引界面保持待确认

用户提供最新完整截图并明确回复“点过‘读取目录’后截的图”：根目录已变为“待读取结果”，load_point_raw.csv显示time=0、force=999，未读取目录提示消失。此为N08步骤4的正常目录切换部分通过，不能扩大为同一步的非法目录处理。截图副本、摘要和用户确认保存在GPTWork/native-result-context-desktop-20261119/manual-read-root-20261120.json及manual-read-root-20261120-loaded-root.png；标题栏小截图另存titlebar副本。四份源CSV/XLSX摘要与launch.json一致。

只读查询同一后台得到索引任务ce1bbd5ccfd04cd49e568bd144c7a80b，2026-11-20 00:05:25至00:05:26（UTC+8）成功，request.root及timeDirectory均指向“当前结果”。最新截图是随后显式读取另一个目录的状态，因此999不是已复现的索引误切换；该任务成功也不能独自证明刷新期间保留了目录草稿和提示。

准确续接：只待用户确认“在点击读取目录之前，刷新索引后是否仍显示123，并提示实际操作目录为当前结果”。不再修改窗口输入或要求重复往返操作，以免与用户操作交错。下面的反向999准备状态是此前观察，不是最新窗口状态。前台234192（创建1795102917.6079493）、后台219004/227524经身份核对仍在，保持现有窗口；37319是原退出观察会话，不是索引计算。没有生产代码修改、重新构建、求解或ODB移动。完整迁移仍未完成。

本轮文档导航52项通过（1.62秒，GPTWork/manual-read-root-docs-20261120.xml），git diff --check通过；未重复既有全量回归或构建。仅更新验收事实，不新增功能或改变实现边界，因此功能索引和算法说明无需改动。

## 2026-11-19 · 用户实际确认未提交目录保持原结果

用户在重开的0aba窗口完成操作并提供截图：顶部RootTextBox为native-result-context-desktop-20261119/待读取结果，路径下明确显示“输入的目录尚未读取；当前显示及操作目录：…/当前结果”；模型甲/load_point_raw.csv保持选中，预览1行2列，time=0、force=123。这是用户实际操作及截图证据，N08步骤1通过，不再将此项列为无人确认。截图原文件codex-clipboard-b8a72941-dd5a-46b8-948c-7d9bb3c9b64a.png，副本和观察回执保存至GPTWork/native-result-context-desktop-20261119/manual-root-draft-20261119.png及同名.json。两目录的四个源文件摘要重新核对不变，CSV分别为123和999。

后续用户最初称实例意外关闭并要求重开；随后明确澄清“是我不小心手动关闭的”。因此前台32412的这次关闭改记为用户手动关闭，不是已复现的应用崩溃或索引失败。N08步骤2仍未完成，不能由步骤1截图推定通过。此前日志为空、Application无1000/1001/1026事件和后台0条索引任务的观察仍保留，旧unexpected-close-20261119-2341.json属于澄清前记录，不再作为崩溃证据；补充回执manual-close-confirmed-20261119.json记录用户更正。

按用户要求于23:41重开前台234192（创建1795102917.6079493），窗口7078082经桌面工具确认结果浏览、4范围节点、控制面已连接。保留原profile中的用户草稿，故启动自动读取的是保存的“待读取结果”，没有强行改回“当前结果”。退出观察会话37319仍运行，只等待此自有前台并将退出码写入reopen-20261119-234157.json；这不是正在执行的索引或求解。异常现场unexpected-close-20261119-2341.json保留，后台219004/227524未终止。

此前输入操作观察：234192/窗口7078082和退出观察会话37319当时均在。读取界面发现已加载“待读取结果”、CSV预览999，较早查询的后台索引任务列表为空。桌面set_value成功将输入末尾改成“当前结果”，没有读取；界面提示仍以“待读取结果”为实际操作目录，预览保持999。输入设置部分可用，但点击“刷新索引”仍报coordinate input geometry is unavailable；Tab调用虽无错误，观察焦点仍在侧栏搜索框，不计键盘导航通过。最新任务查询已有一条成功记录，见上节，不沿用此前空列表作为当前状态。

当时人工问题曾改为只点“刷新索引”并核对999及操作目录“待读取结果”；随后用户截图显示已经显式读取另一个目录，该问题现由顶部的操作顺序确认替代。N08步骤1保留原123截图及反向999观察，不把输入可设置扩大成点击恢复。native-index-draft-reverse.json保留当时输入/实际目录、999预览和工具失败范围，不覆盖历史回执。

此前拟加前台诊断日志的补丁在tests/winui_host/Program.cs上下文校验阶段未应用；实查Git无源码变化、新诊断文件不存在。用户澄清手动关闭后停止该补丁，不按误报继续改异常处理。本轮无生产源码修改、无构建或求解；源数据保持原值。

2026-11-19 23:31用户要求重新启动：用户截图实际是旧native-result-records-20261118/fixture，故未见本次“待读取结果”（它是文件夹名，不是按钮）。确认旧前台9528/212240均已不存在后，按用户要求仅重开最新0aba前台，复用既有G盘独立profile及后台，不重建夹具或改源文件。新前台32412（创建1795102317.6668468）、窗口1706436已由桌面工具实查：结果浏览、RootTextBox末尾“当前结果”、4范围节点、模型甲可见、控制面已连接，预览尚未选文件。准确回执GPTWork/native-result-context-desktop-20261119/reopen-20261119-233157.json。下一步先点模型甲/load_point_raw.csv核对123，再只把顶部路径末尾改为“待读取结果”而不点读取，核对原表格和目录提示；本轮未尝试点击，不声称桌面输入已恢复。

2026-11-19后续进程核对：全量回归结束后，新前台212240已不存在；后台219004及子进程227524仍为原创建时间，旧前台9528仍在。没有观察到关闭动作/结果，不计正常关闭通过，也未主动终止或重开。CSV人工问题尚未答复；后续操作先重新核对窗口身份，不能直接复用下文2164996。当前源码1085项及9项子检查自动回归通过，详见[TASK-002](TASK-002-migration.md)顶部。

## 2026-11-19 · 最新完整包已进入用户桌面，等待实际交互反馈

前一目标轮已完成实现、测试、打包与推送，属于进展。本轮没有再次构建或重复后台验收；确认旧隔离178864/226488已结束且清理回执有效后，通过已有授权的桌面执行上下文启动同一完整0aba包，使用全新G盘profile。新窗口2164996实际出现在CUA清单；前台212240（创建1795068999.333954），后台219004（1795069000.5883832）及子进程227524有身份记录。路径GPTWork/native-result-context-desktop-20261119，launch.json含精确路径和摘要。

CUA实际读取结果浏览：加载“当前结果”根目录、4个范围节点、模型甲目录、控制面已连接、正式队列0，初始预览提示选择文件。点击模型仍报coordinate input geometry is unavailable；目录setValue报failed to activate captured window，重新绑定后Raise同样失败。未改变目录输入，未选中记录，不将初始文字观察计为预览/鼠标/布局通过。普通受限启动不可定位的旧失败记录与本次可定位但不可输入分别保留，不再重复启动同一场景。

已发出一个待反馈问题：点模型甲/load_point_raw.csv，输入根目录末尾“待读取结果”但不读取，核对荷载123及“当前结果”操作目录提示。窗口有两个内容不同的同名CSV/XLSX，准备好export-acceptance；同一profile通过正式API加入两个合成GJA-8+2候选（candidateCount=2、invalid=0、queueCount=0），仅Heading夹具不得求解。queue-fixture.json保存响应。native-observation.json记录CUA观察、失败输入、当前进程/环境核对及源摘要不变；所有临时/数据位置均在G盘，未启动求解或移动ODB。

补齐[原生验收步骤](../../06-testing/NATIVE_ACCEPTANCE.md)，逐页列输入、操作、通过条件与数据前提；修正使用手册结果图草稿“尚未进入安装候选”的过期说明及功能索引旧最新版本。文档不替代执行证据。

文档导航52项通过（0.29秒，GPTWork/native-acceptance-guide-20261119.xml），git diff --check通过；本轮仅文档和验收准备，不重复构建0aba应用或安装器。

准确续接：前台212240/后台219004有意保留供用户检查，旧9528也保留；没有本轮长构建或索引任务等待。先接收该单一问题的反馈，再做索引/导出/读取新目录及队列15秒选择保持，不重复提问或要求SSH登录。用户未反馈时，不能将聊天等待称为活跃计算等待，也不能把当前初始目录观察计为整页验收。完整迁移仍需八页原生业务和目标机等既定门槛。

## 2026-11-19 · XLSX预览性能与已加载目录身份

上一轮队列答复主要复核既有修复，未新增实现；本轮收尾已有未提交XLSX优化，并修复目录草稿混入当前结果操作。Git起点54a4c484，保留原修改，未操作G:\Job或启动求解。

`read_xlsx_preview`先收集预览行引用，`_read_preview_shared_strings`流式解析并移除已处理XML项，只保留需要的文本，找齐即停；纯数字/内嵌文本不读共享表。负编号原先误取最后一项，现明确失败。越界/非整数原本就失败，不将其记作新修复。首表关系、富文本、空行/列、公式缓存值和截断不变；有限预览不承诺校验未读取尾部。

修复前GPTWork/xlsx-preview-baseline-20261119.xml为3失败/4通过（0.69秒）：早期引用/纯数值都读完整3108860字节，负编号误成功。最初before回执4失败/3通过中越界类型断言过窄，已修正测试，原回执保留。修复后初检fixed回执25通过；加入真实openpyxl工作簿HTTP、共享文本和负/越界/非整数422检查后，GPTWork/xlsx-api-final-20261119.xml为26通过（12.64秒，会话17303退出0），ruff通过。

GPTWork/measure_xlsx_preview_20261119.py在两个10万条共享文本的合成ZIP/XML文件上分进程测量，before.json/after.json位于GPTWork/xlsx-preview-performance-20261119。早期引用Python分配峰值72059147→371179字节，读取15488967→16384字节，含tracemalloc计时1.3615→0.0045秒；晚期引用峰值72059147→403510字节，仍扫描15488967字节，1.3008→0.7825秒。返回单元格及两份源SHA256一致。此为合成预览的Python分配峰值，不是整个进程RSS、通用延时保证或真实原生页面验收。

目录问题复现路径为读取A→输入B但不提交→选A记录并导出/重建索引：旧页面分别读取RootTextBox.Text和旧scope，造成来源不一致。新增生产ResultBrowserLocation，操作统一取LoadedRoot；BeginRead/Apply保留未提交草稿，目录失败清空身份。页面显示实际操作目录提示，侧栏/内部文件/索引成功刷新沿用已加载根目录；外部目录跳转在索引忙时拒绝。ResultBrowserLocationChecks实际创建A/B同名不同内容CSV并导出，验证输出为A且两源不变，同时验证草稿/自动刷新/失败/延迟响应共11项。未实际调用系统回收站。

C#会话已退出0，GPTWork/result-context-check-20261119.log包含11项目录与实际导出、既有6项回收路径和10项异步生命周期及表格检查。界面接线和正式C#客户端→真实HTTP分页/宽表40项通过（11.82秒，会话53719，result-context-20261119.xml）。正式WinUI发布27137退出0，GPTWork/result-browser-fixed-native-20261119及同名日志，无警告/错误输出。以上不代表原生点选/布局通过。

最终文档导航与结果索引API53项通过（4.39秒，GPTWork/result-docs-verified-20261119.xml），ruff与git diff --check通过。首次命令误列不存在的tests/control_plane/test_results_paging.py，未运行任何测试（result-docs-final-20261119.xml）；已按实际索引改用test_result_index_api.py，分页由上述正式客户端HTTP覆盖，不将不存在文件计为通过。

新完整目录GPTWork/release-win-x64-0aba6269fe34/AbaqusTools来自干净1d3c981e4392c8d0730a7b2b5c9b6a03d4089756，已实际推送并核对origin/main。1689清单文件（含清单1690）、19worker、15应用资源，全摘要及包内依赖通过；清单SHA256为7983ed02a19fa59cd9fe4416a5204e910f7ecf6048eb7e695ab981b8579bb9df。正式标识安装候选GPTWork/installer-win-x64-9a463a0e6dc8/AbaqusTools-0.1.0-win-x64-setup.exe为126168153字节，SHA256为76050c577f365f5bdfacf395a640b70b49732b0c9188e89b388d833a5bdd29dd，实查NotSigned、未安装。构建61945和安装编译29406均退出0；未改安装模板，本轮没有重做生命周期，旧aa87仅证明此前6b4负载。

新包隔离前台178864（创建1795068266.2893393）、后台226488（1795068267.781207）已启动；CUA两次清单都找不到新窗口，不能验收原生布局/鼠标。冻结后台真实HTTP完成11项：CSV/实际XLSX、10万共享文本早/晚引用、三种非法引用422、错误目录拒绝、正确目录索引成功及双源摘要保留。回执GPTWork/native-result-context-20261119/verification.json，具体索引操作c32c126cee074554806e4fcbe51d3b95已成功终态。随后核对精确身份/路径，仅结束不可定位的自有隔离前台（退出15），后台经正式idle协议退出0，剩余自有进程为空、描述符移除；cleanup.json明确不计原生正常关闭通过。旧9528及其创建时间/路径保持，未操作原有窗口。

准确续接：本轮检查、构建、索引和隔离进程均终态，源码已推送。下一项为新包原生目录提示/预览/分页/导出/取消及完整业务，未缩小总迁移目标；无原始模型修改、求解或C盘ODB。

2026-11-18最新：用户确认并经CUA核对，修复后模型选择/CSV前50行3列预览正常；实际导出80行/1408字节且与源摘要一致，随后窗口/后台正常结束。原198808不再活跃，详细证据见[TASK-002](TASK-002-migration.md)顶部。这只覆盖单份小CSV，取消/部分失败/回收站和八页完整交互仍待。

2026-11-18 F021最新续验：下方旧窗口70244实际栈溢出，已修复程序恢复选区与业务读取互相触发的问题；快照延期合并、相同选择去重、移除前清选。9项生产原生控件、39项shell/结果API及生命周期/预览检查通过，开发输出winui-explorer-fixed-20261118。旧d4fc4c7完整包仍含该问题；新窗口198808/后台51160保留等用户确认CSV表格，业务预览/导出尚未验收。失败日志、进程归属、命令及续接见[TASK-002](TASK-002-migration.md)顶部。

2026-11-18 F021 原生续验：G:测试CSV目录已有真实索引，4范围/全部2记录/常用1记录核对通过；实际窗口能读目录，但鼠标定位失败且Tab未观察到焦点变化，尚未选中记录。已请用户在保留窗口点“模型甲”及load_point_raw.csv确认表格，预览/导出仍待，不能把接口/目录检查当通过。活动窗口70244、后台33100，准确创建时间/路径/窗口ID与续接见[TASK-002](TASK-002-migration.md)顶部。

2026-11-18 F021：结果导出新增进度、取消、关闭等待与部分结果记录，24项生产文件检查、46项相关回归和构建通过；结果目录/索引排除本次未完成副本。数据仅G:夹具，原生文件选择器/取消/关闭未验；准确源码与记录见TASK-002顶部及ADR0021。

2026-11-18 F001/F005/F014：补齐“当前作业送入后处理”的当前选择、实际计算/已发布归档路由和页面恢复保护。30项生产路径检查及四种归档状态的正式C#客户端→真实本机HTTP→发现接口通过，111项相关回归、174项既有后处理和构建通过；只用G:路由字节夹具，不代表ODB提取或原生点击验收。准确构建/回归/提交及续接点见[TASK-002](TASK-002-migration.md)顶部。

2026-11-18 F001/F022补充：输出设置/工作区和提取参数、图例、分组管理、组内顺序的未确认填写已接入独立恢复草稿，恢复后强制重新读取结构，不自动提交弹窗。38项专项、174项既有后处理、16项共享结果图检查和构建通过；实际文件/失败记录及最终回归见[TASK-002](TASK-002-migration.md)顶部。原生恢复和新完整包仍待，不把JSON检查当作真实业务窗口验收。

## 需求与状态

进行中，未交付完成。用户要求沿用 WinUI 前的基础提取逻辑，支持两类根键基础及对应灌注桩；扩展为浏览 ODB 集合/实例后提取选定对象轴力、弯矩及钢筋轴力。当前用户模型无梁单元。2026-10-28 用户再次明确：**尽快先完成结果提取功能恢复**。优先可运行的读取、提取、结果查看主流程；剩余迁移和新增扩展后置。

功能：F014–F022。文件详见 [功能索引](../../03-features/FUNCTION_INDEX.md)，不重复复制所有路径。

## 已做工作及证据

### 2026-11-18 · GIF 双模式复核（F020/F022）

用户再次明确要求“帧率相同或时长相同”。本次核对现有源码，确认两种模式、工作区持久化、请求参数及正式合成入口均已实现，无需重复修改。功能索引补上 GIF 参数的 API 测试定位。

- `tests/postprocessor/test_animation.py`、`tests/winui/test_shell_contract.py` 与文档导航共 80 项通过，回执 `GPTWork/gif-options-check-20261118.xml`。`tests/control_plane/test_postprocessing_api.py` 8 项通过，回执 `GPTWork/gif-api-check-20261118.xml`。最初误执行 `pytest tests/control_plane/test_postprocess_contracts.py`，该文件不存在，未执行测试；已改用上述真实文件。
- `dotnet run --project tests/winui_postprocess/OdbPostprocess.Tests.csproj --no-restore -p:BaseOutputPath=G:/PythonProject/abaqusTool/GPTWork/gif-workspace-check-20261118/` 退出 0，含 GIF 参数兼容、模式/数值保存和旧工作区恢复检查。
- 重新解码 `GPTWork/gif-timing-s9udw0t8/` 的四份成品，均为 1500×1000，保留 101 / 41 个画面；固定 25 帧/秒分别为 4.04 / 1.64 秒，统一时长均为 4 秒。当前复核回执 `GPTWork/gif-options-recheck-20261118.json`。没有启动求解或重渲染原始模型。
- 当前业务窗口来自 `GPTWork/winui-migration-20261118/AbaqusTools.WinUI.exe`，句柄 58461048。读取窗口成功，尝试 Ctrl+7 后未观察到页面切换，点击“ODB 后处理”返回 `coordinate input geometry is unavailable`。没有提交后处理任务；模式切换与业务页点击导出仍未验收。测试进程均已退出，业务窗口保留打开。准确续接点：恢复原生按钮定位后检查“输出与计算设置”的两种模式切换与实际提交。

### 2026-11-17 · GIF 统一帧率与统一时长（F020/F022）

文档导航检查通过 29 项。变更定位在 F020、F022，时长输入和悬停说明在 F025。

WinUI「输出与计算设置」支持选定统一帧率（新工作区 25 帧/秒）或统一单轮时长（初始 4 秒）。工作区分别保存两个输入和活动模式。请求保留原 `animationFps`，仅时长模式附带 `animationDurationSeconds`。编码按累计时间分配百分之一秒，校验源帧最低延时，记录各变量的实际单轮时间以及平均源帧率。沿用原有缺失变量处理及取消/未完成标记。

对 `GPTWork/group-full-gifs-ri_g396m` 的 GJA-1-R_U100D / GJB-15_V40D 混凝土 Mises 原始 PNG，分别按两种模式调用正式渲染收尾函数。四份 1500 × 1000 成品均重新解码，全部 284 个输出帧与对应源图的 GIF 调色板结果逐像素一致。25 帧/秒时每帧均为 40 ms，时长分别为 4040 / 1640 ms。统一 4 秒时每张均为 4000 ms。证据在 `GPTWork/gif-timing-s9udw0t8/verification.json`。

相关 Python 回归 120 项通过，包括旧请求、两种模式、30/60 帧计时、相同帧合并和目标过短。后处理 C# 状态测试通过，包括旧工作区 5 帧/秒恢复、模式存取和发送字段。Debug 构建零警告零错误，可执行程序在 `GPTWork/winui-gif-timing-20261117`。首次界面自动检查遇到最小化窗口，进程退出，事件记录为 Microsoft.UI.Windowing.dll / 0xe0464645。再次正常启动后，用户按 Esc 结束桌面检查。准确续接点是打开「输出与计算设置」，切换两种方式并从真实业务页提交一次。此轮使用现有渲染帧，没有新增 Abaqus 求解。

- 只读结构目录、作用域标识、帧输出元数据及 WinUI 对话框。
- 通用 region 请求/任务、梁或桁架字段读取、实体 CAE 截面积分、CSV/成功回执、失败不发布。
- 实际 GJA 钢筋、GJA 实体、GJB 混凝土/钢管分开提取，结果索引与 CSV 预览；证据及边界见 [验收矩阵](../../06-testing/VALIDATION.md)。
- 本轮相关快速回归 45 项通过。旧批处理和原生构建的历史记录不替代新的完整验收。

## 已解决的人工样例诊断（保留历史，不重复做）

新加 `tests/abaqus/create_region_fixture.py` 和 `tests/abaqus/verify_region_fixture.py`，只造人工 ODB，不调用 solver。

1. `known-region-8mgx32gk`：beam_all 和 beam_local_set 的已知数值断言通过；实体实例集合报告只有表头，`failure.json` 记录 Expected exactly one section result。
2. `known-region-xdue9k2_`：复用同一源，改为装配集合，仍只有表头，排除了“只有实例集合出错”的简单猜测。
3. `known-region-4dg2_t18`：人工样例添加材料/截面时调用了错误的 `solid_instance.SectionAssignment`，create.log 中 AttributeError；因此该次后续“帧无效”只是样例生成不完整，不能作为生产提取算法证据。

上述目录均在 `GPTWork/real-odb-validation`；调用已退出，不应继续等旧句柄。保留失败产物供对照，不覆盖重新生成。

后续修复：依据官方 ODB API 使用 `assignSection(region=..., section=...)`。完整材料/截面配置后，实体实例集合与装配集合均能提取；原故障是人工样例配置缺失，不修改生产算法。生成器保存关闭后写 `.created.json`，校核脚本校验 SHA256；新增回归证明退出 0 但无回执时不会执行后续提取。

`known-region-fumxjvn1/verification.json`：两帧、六组（实例集合、装配集合、反向/横向/倾斜切面、形心参考点）共 198 条实际 CAE 结果，与独立均匀应力解析式吻合，最大绝对误差约 2.0143e-5，源 SHA256 未变。它不证明所有单元族或非均匀应力场精度。

生产 manifest 按 method 区分逐点输出与截面积分，新增失败回归后修复；真实实体校核也检查该字段。相关 Python/HTTP/文档扩大回归 449 项通过（77.54s）。

## 2026-10-28 继续恢复：来源保护与结果发布

- F018/F019：在请求、worker 开/关、宿主验收与最终发布阶段增加源变化检测；关闭失败不再提前发布成功回执。控制面持有批次隔离标记，在锁内确认未取消后才发布，封住 worker 已完成而操作终态尚未提交时的取消窗口。
- 实际文件：`modules/control_plane/region_extraction.py`、`modules/control_plane/postprocessing.py`、`modules/postprocessor/abaqus_scripts/extract_region.py`、`modules/postprocessor/abaqus_scripts/region_extract_core.py`。新增符号与定位见功能索引。
- 先用新增测试复现 6 个失败，再修复；相关扩大回归 73 passed in 7.07s，覆盖 region、实体、失败隔离、HTTP 与原生 C# HTTP 客户端。产物：`GPTWork/pytest-region-publication-red`、`GPTWork/pytest-region-publication-regression`。
- 实际 Abaqus/HTTP 重新提取：GJA MR-1 钢筋 2688 行，GJB 混凝土和钢管各 18 行。与原成功结果逐行对照，力/弯矩及已有元数据一致；三组均可建立索引并通过 CSV 预览。两个 GPTWork ODB 的全文件 SHA256 前后相同，未触碰 G:/Job 原始模型。
- 证据：`GPTWork/real-odb-validation/region-delivery-zfmk0ni6/verification-resumed-2.json`；执行入口 `GPTWork/real-odb-validation/check_region_delivery_20261028.py`。首次两次断言失败来自历史 CSV schema：GJA 原表少 10 个后来添加的空实体列；GJB 原表用 section_point 存切面编号，现已改为 cut_index。校核脚本显式验证这两种迁移，未修改旧产物；恢复执行复用已经成功的操作，未重复启动长任务。原失败回执仍保留。
- 这些结果证明当前保护机制能在真实跨解释器链路运行并保持旧数值，不新增独立工程精度结论。钢筋仍使用既有 32 mm 参考面积假定，有限变形/实际面积边界不变。

## 2026-10-28 界面主流程恢复

- F016/F018/F019：按实际类型提供方法，不能把壳/混合/未知对象默认作为梁。新增 OdbRegionExtractionMethods；63 条方法行为检查通过。
- F017/F018：新增 OdbPostprocessRecoveryState 与页面 Recovery 分部文件，失联保留请求/操作编号，状态未确认时锁定重复提交；“查询原操作状态”只做一次最多 15 秒的只读查询。取消中不重复发送停止；旧进度回调按请求与操作归属过滤，避免新请求启动期间被旧回调影响。34 条状态行为检查及既有 C# 检查通过。
- F021：ResultBrowserLoadCoordinator 修复目录刷新/索引完成后列表空白，失败清空旧内容，并隔离晚到的目录、记录、索引进度和恢复响应；10 项独立异步检查通过。
- 命令：`dotnet run --project tests/winui_postprocess/OdbPostprocess.Tests.csproj --artifacts-path GPTWork/winui-region-method-checks`；`dotnet run --project tests/winui_results/ResultBrowser.Tests.csproj --artifacts-path GPTWork/build-results-tests`；WinUI shell 契约 32 passed。
- 原有提取参数对等、无纵筋力矩、预检和结果 API/索引/文档定向回归：83 passed，另 1 项文档检查发现旧命令被当作单个路径；已修正旧文档命令写法，按规定单独复核文档导航。
- 最终构建命令：`dotnet build winui/AbaqusTools.WinUI/AbaqusTools.WinUI.csproj -c Debug --no-restore -p:OutputPath=G:/PythonProject/abaqusTool/GPTWork/result-extraction-restored-20261028/ -p:OutDir=G:/PythonProject/abaqusTool/GPTWork/result-extraction-restored-20261028/`，0 warnings / 0 errors，12.43s。输出 `GPTWork/result-extraction-restored-20261028/AbaqusTools.WinUI.exe`。
- 前一候选实际启动并读到原生窗口和控制面连接，随后用正常关闭结束本次测试窗口；最后的晚到进度小修后重建。未通过完整原生点击，不能宣称全部后处理交付完成。现有默认 Debug 用户窗口保留，不用强制终止来替换锁定文件。用户要使用恢复版时正常退出旧窗口，再启动上述候选；本次未自动重启用户已有控制面。
- 文档导航按规定命令复核：27 passed in 0.11s。所有本轮人工提取、测试和构建句柄均已退出，无需继续等待；没有提交/推送或清理历史数据。

## 2026-11-17 F021 结果列表与表格预览

- 原 WinUI 把 CSV 和 XLSX 拼成文本，匹配记录超过 500 条时没有翻页入口。现将分页偏移与已提交的筛选条件关联，提供页间切换、页内选择和导出。原生表格每组最多 8 列，支持全预览复制、原值和嵌入换行；默认行数沿用共享的文件大小规则。
- 真实 GJB-15 的 summary.xlsx 首轮检查读出 9 行，独立读取首工作表得到 10 行。文件省略了第 2 行的 XML 节点。修复共享读取器，按工作表行号补空行；现在按需读取首张工作表，超过预览上限时停止读取后续行。损坏的工作簿返回预览错误。
- 生产 C# 客户端连接临时控制面对既有文件做只读核对。批次两页分别 500、297 条，交集为空；返回第一页顺序相同，末项可单独搜索。钢管 region_values.csv（18 行 × 24 列）、summary.xlsx（10 行 × 6 列，含空白第 2 行）与独立 CSV / openpyxl 读取逐格一致。路径、文件 SHA256、分页与预览回执在 `GPTWork/result-browser-verification-20261117/verification.json`。
- 项目 Python 定向回归覆盖结果 API、索引 API、旧版结果浏览、WinUI shell 与 C# HTTP 客户端，54 项通过。后者另用 502 条合成记录验证 500+2、1 MiB 以上 CSV 的默认 25 行、指定 2 行、稀疏工作簿和空单元格。C# 结果浏览测试运行通过，含已有 10 项异步检查和新增的宽表、复制、列组边界检查。
- 可运行候选 `GPTWork/winui-results-20261117/AbaqusTools.WinUI.exe`，Debug 最终构建耗时 17.40 秒，0 警告、0 错误。未打开原生业务窗口，实际鼠标选区、滚动和系统剪贴板待验收。下次可在 GJB 无纵筋批次翻至第 501 条，再切换到「通用对象提取」中的 GJB 钢管批次，选中 CSV、查看第 17–24 列、复制到空表对照 24 列。测试过程中未启动 Abaqus 求解。

文档导航按项目规定单独运行，29 项通过。本轮构建、定向回归、真实文件读取和临时控制面均已结束。

## 2026-11-17 F020 分组色标与 WinUI 编辑

- 改动前，缺组范围的图可使用自动色标或默认损伤范围，元数据仍标为组内固定；图例编辑框提交后才校验，输入错误就丢失草稿。现由 WinUI 在原窗口校验、聚焦错误项，展示中文物理量与变量编号。数值缓存继续复用。
- 命名组汇总有效范围后随渲染配置传递每个成员实际参与预扫描的序号。遇到有场输出、无有效预扫描的帧，不以其他成员数据顶替。渲染器读回视口范围；取消、错误回执、缺回执或过期回执均不能据此发布成员为成功。未分组可以回退自动色标，元数据会记录实际模式。显式手动上下限覆盖缺少的自动范围。
- 实际运行 `GPTWork/verify_group_legend_migration_20261117.py`，使用此前 GJA 与 GJB 原有预扫描和 ODB 副本，只读打开。两份模型先按全部扫描帧算动画范围，再各抽中间帧、末帧输出动画 PNG，静态图取末帧。混凝土 Mises 的两份静态图同为 0.01471344–16.95039558，两份动画样帧同为 0.00152124–16.95039558。GJA 有 11 个变量、GJB 无纵筋有 9 个，正常分组共 60 张 PNG。
- 复现过两种失败：删除动画组计划里的 PILE_U_MAG；保留计划但移除 GJB 的 PILE_U_MAG 成员覆盖。实际 CAE 分别返回缺范围与“序号 20 未参与计算”。随后手动指定 0–100，GJB 恢复，生成 27 张 PNG。
- 早期样图在 `GPTWork/group-render-check-hv7wnnel/`，原导出色条的刻度文字相同、色带 RGB 随每张图的 256 色调色板变化，逐像素验收未通过。命名组改用全彩 PNG，最终回执 `GPTWork/group-render-check-c62b13k0/verification.json`，静态及动画样帧的混凝土 Mises 色条与刻度均相同。60 张同尺寸 PNG 总量从 824,880 字节变为 1,051,136 字节。
- 定向 Python 回归 134 项通过；WinUI 后处理 C# 行为测试通过，含 10 项新增的数值输入检查；原生程序构建 0 警告 / 0 错误。候选 `GPTWork/winui-group-legends-20261117/AbaqusTools.WinUI.exe`。未启动求解，未对原生业务页弹窗作鼠标操作。下一步可在「图例范围」修改两个变量，刻意填反一对上下限，再核实原处纠错、草稿保留及键盘焦点。完整时程 GIF 重跑仍待验收。

两份自动范围结果经正式整理入口另生成 60 张透明 PNG、20 个 GIF，均可解码；两份混凝土 Mises GIF 各含两个抽样帧。此轮 CAE、构建和测试进程均已结束，历史失败现场已保留。

### 从两帧样片到完整动画

上次色标验收把 GJA 的序号 50、100 和 GJB 的序号 20、40 写入临时抽样时间轴，两个混凝土 Mises GIF 均为 960×720、每帧 200 ms、一轮 0.4 秒。此次沿用该组的动画范围，改用两份既有数值结果中原始的完整时间轴，按 1500×1000 像素、5 帧/秒重新渲染到独立目录，无须求解。验证脚本为 `GPTWork/export_full_group_gifs_20261117.py`，导出位置为 `GPTWork/group-full-gifs-ri_g396m/`。GJB 的 41 张混凝土 Mises 源帧均与分析步、帧号对应，GIF 解码得到 41 个不同画面，播放一轮 8.2 秒。

GJA 的 101 张混凝土 Mises 源帧也已逐个匹配时间轴。其 1500×1000 GIF 已逐帧解码，共 101 帧，时长 20.2 秒。两份完整动画的视口上下限与原组计划一致，导出和检验进程已退出。回执在 `GPTWork/group-full-gifs-ri_g396m/verification.json`，各成员的 GIF 在同目录下该模型的 animations 文件夹内。本次复用了已有数值结果，直接运行正式渲染与 GIF 合成入口；WinUI 业务页点击仍待验收。

## 分组图例的早期检查及后续验收

2026-11-17 F020 检查：从 WinUI 所选行构造分组、组预扫描/汇总、每成员渲染配置到 Abaqus `contourOptions` 的调用均已核对。将已存的 GJA-1-R_U100D（101 帧）、GJB-15_V40D（41 帧）真实预扫描分别与原各自渲染元数据比对，再放入同一测试组走当前汇总函数。混凝土 Mises 的选定末帧组范围是 0.01471344–16.95039558，动画是 0.00152124–16.95039558。复核文件 `GPTWork/group-legend-audit-20261117/replay.json`。未重新打开原始模型、求解或将两模型合组实际渲染；单成员出图记录和双成员计算回放不能替代双成员原生出图验收。建议后续验收同时核对缺失色标的降级路径与两张实际图例。

本次项目 `.venv` 回归：`test_legends`、`test_parallel_prescan`、`test_legacy_payload_parity`、`test_unreinforced_prescan`、`test_postprocessing_api` 合计 62 passed；文档导航 29 passed。测试与回放进程均已退出，本次未改生产代码。

1. 完成原生对象选择/提取/结果浏览实际入口验收；本次能读取旧窗口的后处理页面，但点击报 `coordinate input geometry is unavailable`，重新取窗口截图报 `FrameArrived timed out: timed out waiting on channel`。不能将原生点击标为通过。
2. 回到用户真实实体根键/钢管/混凝土和钢筋，补适用性与独立数值对照；既有 GJA/GJB 实际提取证据复用，不重复所有批次。
3. 检查失败、取消、重试和配置恢复的用户流程，整理后处理交付入口。
4. 每完成一项同步文档。剩余迁移/目录整理保留 TASK-002，不扩大当前活动目标。

## 不变约束与交接

源模型只读；无纵筋显式 none；钢筋 S11×参考面积有有限变形边界；切面采用参考几何且不自动增加钢筋贡献。任务未授权改原始模型或运行求解。

每完成以上一个功能或修复，必须同步更新功能说明、路径索引、验收证据和 CURRENT_STATUS，不等整个任务完成才写。当前工作区包含大量未提交修改；本次未提交/推送。
