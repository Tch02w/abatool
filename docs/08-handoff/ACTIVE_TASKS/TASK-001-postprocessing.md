# TASK-001：数据提取与后处理应用交付

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
