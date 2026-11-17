# 验收记录与已知缺口

核对日期：2026-11-17（F020 分组出图及 F021 结果浏览）。历史测试数不与本次测试累计相加。GPTWork 是本地忽略目录，新机器不会随 Git 自动获得其中的样本和报告。

## 当前证据矩阵

| 功能 | 可定位证据 | 已证明 | 尚未证明 |
|---|---|---|---|
| F026 最终包用户账户访问和恢复（11-18） | `GPTWork/release-win-x64-c39d9688d751/archive-verification.json`、`GPTWork/frozen-merge-recovery-658jvpc7/verification.json` | 用户账户逐项核对 1645 文件/19 worker，ZIP CRC、正式主机启动/API/退出、两次冻结后台启动和请求去重通过；修正临时发布目录仅构建账户可读的问题 | 原生页面、真实外部进程崩溃、无开发环境目标机器 |
| F013 持久记录和恢复（11-18） | `GPTWork/control-history-regression-20261118.xml`、`tests/control_plane/test_odb_merge_recovery.py` | 178 项控制面回归，含测试进程真实终止、HTTP 重建、请求去重、损坏/磁盘失败、已提交结果保护、日志节流和联合退出；C# 3 项恢复信息检查通过 | 外部 Abaqus 实际运行中崩溃、原生页面恢复、F012 完整批量游标续接 |
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
