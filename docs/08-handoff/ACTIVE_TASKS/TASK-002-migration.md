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

已运行 `.venv/Scripts/python.exe GPTWork/verify_real_merge_acceptance.py`，59434 退出 0。`GPTWork/merge-real-fv8_supj/verification.json` 核实原始三份 ODB/输入副本完整摘要不变，源备份与输入一致，无结果帧列表、回执及失败目录清理符合预期。该副本目录由提升权限进程创建，普通读取可能拒绝访问；不要把权限问题当作文件不存在。54813/58927/15537/22343/45990/59434 均已确认结束，无须重跑两组真实样本。下一项为更新发布候选、原生点击及真实多节点批量/后台重启恢复验收。

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
