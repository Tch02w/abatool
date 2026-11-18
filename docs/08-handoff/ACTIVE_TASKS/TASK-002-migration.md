# TASK-002：后续迁移、完善与整理

## 2026-11-18 · F001/F003 显式新建与草稿保护

从干净25b9d18继续，上一轮分类为实际进展（发布验证、文档与本地提交）。先核对PySide6的open_submission_wizard/reset_for_new_job并说明方案，再实现独立菜单动作；不将普通导航变成清空。新增NewJobDraftReset确认/独立快照/先保存后发布；WorkbenchSession协调日常/系统结束写入，避免旧控件值排到重置写入后。MainWindow取消不切页，提交/预览忙碌和重复点击拒绝，普通关闭等待用户完成确认或保存；保存失败保持原草稿，空页/未访问页面也支持。清任务名称/INP/oldjob/Fortran，保留资源设置和独立ODB合并草稿，成功清旧预览并定位输入框。新建页登记顺序改为执行方式先于文件路径，修复远端恢复时路径被清除。

16项生产状态/真实JSON检查通过：`GPTWork/new-job-reset-checks-20261118.log`，证据目录同名无.log；取消、忙碌、确认期间结束会话、保存延迟/重复、保存失败/损坏原件、重试、空页/仅名称、资源原文/其他页/窗口和不可变快照。测试仅字符串ODB路径，未创建ODB。既有7项持久化+15项系统会话检查通过（new-job-reset-session-checks-20261118.log），未执行OS关闭。主机编译0警告/错误3.15秒；WinUI构建40168退出0，0警告/错误27.65秒，日志new-job-reset-winui-build-20261118.log，输出 `GPTWork/winui-new-job-reset-20261118`（开发构建，非完整发布包）。

相关Python回归99项通过29.10秒，97989退出0，回执 `GPTWork/new-job-reset-regression-20261118.log` / `.xml`：实际HTTP关闭/图恢复、16项新建专项包装、页面登记顺序、壳层、作业草稿API/领域及49文档。补充导航入口忙碌保护，防快捷键或回调在确认/保存期间切页。最终WinUI构建20552退出0，0警告/错误15.24秒，日志 `GPTWork/new-job-reset-winui-build-final-20261118.log`；全部构建与相关回归句柄结束。所有测试TEMP/TMP、数据和输出在G:项目GPTWork，未创建C:ODB或移动用户ODB。

收尾85项通过0.24秒（49文档、35壳层、1页面登记，与99项重叠不累计），`GPTWork/new-job-reset-docs-final-20261118.log`；Ruff和差异空白检查通过。代码/测试/功能说明/Wiki/候选日志/索引一起本地提交，提交号以实际Git为准；没有未收回的测试或构建句柄。

准确续接点：下一步继续合同第3节菜单与页面共用可用状态：现有菜单开始/停止/刷新/断开无状态绑定，页面自身分别在JobQueuePage.ApplyRuntime和ComputeResourcesPage.UpdateButtons设置可用性，DisconnectAsync直接调用远端命令。需共享同一状态源并核对未连接、忙碌和页面未加载时的行为；已向用户说明方案。原生操作暂停、具体GitHub远端确认仍未收到，不打开桌面、不推送；7c874d3完整包不包含本轮菜单改动。整体目标继续active，不以本项补齐代表八页验收完成。

## 2026-11-18 · 草稿恢复后的完整候选与安装验证

收尾：完整回归979项/9子检查通过；最终文档导航49项通过0.19秒，回执 `GPTWork/draft-release-verification-20261118/docs-delivery.log` / `.xml`。首次文档检查48通过/1失败（docs-final.log/xml）是把pytest节点标识写成源码路径，已拆分准确文件与函数名，没有放宽检查。README及Wiki补齐安装版/源码版启动区别，开发验证使用G:隔离目录，发布说明去掉过期“无卸载程序”描述并禁止沿用历史C:ODB目标。Ruff与差异空白检查通过；本轮仅测试和文档变更，不重建相同产品负载，不重跑已通过整套测试。最终本地提交号以实际Git为准，未推送。

本轮起点为干净7c874d33c405ad7ff07fadfce03ef74020ebb41e；上一轮为实际代码/测试/文档提交进展。使用项目解释器、G:测试TEMP/TMP运行 `packaging/build_release.py --no-restore`，95809退出0，生成 `GPTWork/release-win-x64-c245b91545d7/AbaqusTools`。清单列1669文件（清单本身另计）、19 worker，含清单总字节354939886；来源7c874d3、sourceDirty=false。相比旧6d5279845a23新增5份文档、无删除路径，30文件变化。完整核对回执 `GPTWork/draft-release-verification-20261118/inventory.json`，核对4f135a7/3d9ab94均为来源祖先，无模型/Qt/虚拟环境混入。

包内 `--check-bundle` 退出0，回执 `bundle-probe-nnsq4uhj/verification.json`（位于上述验证目录），验证默认配置、全部worker、GIF、Agg图表、工作簿预览、SSH加密导入和Qt-free。正式C#客户端 `--launch-bundle` 指向新包及独立G:运行目录，启动、资源/队列API、正常退出通过（`frozen-host.log`），descriptor已移除；未使用`--odb`，未调用Abaqus或SSH。

正式标识安装候选 `GPTWork/installer-win-x64-c513706de2c4/AbaqusTools-0.1.0-win-x64-setup.exe`，14206退出0，125568327字节，SHA256 `eda00152065f40dfce3ff7d0688e8d3535d69cd011276ec6ae15ebac905baf38`。负载与安装器源码均为干净7c874d3；1670项安装文件校验包含release-manifest。`installer-artifact.json`核对摘要、来源、安装引导器0x14c/应用和后台0x8664；`installer-signature.json`为NotSigned。两份回执在验证目录。编译器签名复核Valid。正式标识未实际安装、未发布GitHub。

新负载另编译独立测试身份 `AbaqusTools.Workbench.WinUI3.Test.202611180002`，候选b7f81001e859，96170退出0；与既有旧测试包8a79e216e0c5（负载b2cfd57）验证升级。首个普通上下文命令在读取 `HKCU/Software/Microsoft/Windows/CurrentVersion/Explorer/Shell Folders` 时WinError 2退出1，发生在创建验证目录/安装之前，非产品失败。随后经审批在正常用户上下文运行同一隔离验证，26689退出0：`GPTWork/installer-lifecycle-4d8a268bb72f/verification.json` verified。

生命周期覆盖陌生目录拒绝、链接祖先拒绝、中文空格首次安装与全摘要、活动自有后台拒绝升级/卸载而不被终止、正常退出后升级且保留旧版本/用户文件、开始菜单旧/新目标、安装后正式主机启动/API/退出、卸载清除测试登记/菜单且保留用户文件。forcedCleanupPids和remainingOwnedPids均为空，registrationRemaining=null；没有剩余自有进程或测试登记，没有原生业务窗口/求解。只移除本次安装器登记的测试程序；历史包、日志和用户ODB未移动或清理。

首轮完整无桌面回归：70460已退出1，978通过、1失败、9子检查通过，640.28秒，回执 `GPTWork/draft-release-verification-20261118/full-suite.log` / `.xml`。命令 `python -X utf8 -m pytest tests -q --ignore=tests/submitter/test_native_window_startup.py --tb=short --basetemp=GPTWork/pytest-draft-release-full-20261118 --junitxml=GPTWork/draft-release-verification-20261118/full-suite.xml`。TEMP/TMP及两类数据目录位于 `GPTWork/draft-release-full-temp-20261118`，QT_QPA_PLATFORM=offscreen；已核查测试中C: ODB字符串只用于命令/界面数据断言，不作为写入目标。必须开窗口的测试明确排除。

失败为 `tests/control_plane/test_remote_jobs_api.py` 中 `test_active_remote_job_prevents_accidental_session_disconnect` 的固定3秒等待。只读检查其 `runtime/remote-jobs.sqlite3`：createdAt为08:31:29.845Z、updatedAt为08:31:34.836Z，最终running/tracking、launchState=started、error=null；并非已证实断开保护失效。原用例独立复测1项通过2.19秒（remote-repro.log/xml）。随后只改测试，用启动/监测Event而非持续HTTP轮询等待；显式暂停模拟启动，分别在starting与running阶段核对409/REMOTE_SESSION_BUSY及连接保留，finally释放测试门闩。该模块4项通过7.54秒（remote-gated.log/xml），Ruff通过，产品源码和发布物未改。

最终完整回归99701已退出0：**979项及9子检查通过，579.98秒**。新TEMP/TMP为 `GPTWork/draft-release-full2-temp-20261118`、basetemp为 `GPTWork/pytest-draft-release-full2-20261118`，回执 `GPTWork/draft-release-verification-20261118/full-suite-final.log` / `.xml`。排除原生窗口启动测试，不计为通过；没有启动求解。普通WMI进程探针因隔离账户权限拒绝；随后只读psutil探针48697已正常退出，原pytest进程终态由70460确认，未因探针失败重启原任务。全部本轮构建、安装和完整回归句柄已结束。

合同核对发现下一独立实现项：`MainWindow.xaml.cs:339`的`OnNewJobMenuClicked`仅SelectRoute。PySide6基线 `modules/submitter/main.py` / `open_submission_wizard` 会先确认当前INP/oldjob/Fortran草稿；`workbench_ui.py` / `reset_for_new_job`清空任务文件/名称、回本地执行并保留通用资源值。WinUI缺这个动作，不能将整体剩余事项只归为环境。已向用户说明将区分普通切页和明确新建，下一步补确认/重置/忙碌及恢复保护，再独立测试与文档；本轮不在完整回归过程中修改业务源码。

准确续接点：本轮最终完整回归已经收回，不重跑。文档收尾后一起本地提交；下一独立实现为上述F001/F003新建动作，需等待页面草稿恢复后重置，确认取消不清除，提交/预览忙碌时拒绝，持久化失败明确保留草稿，并保留通用资源配置。现有新包来源7c874d3，本轮仅测试及文档变更，包内文档是构建时快照；后续菜单改动不冒充已经在该包中，旧包保留。原生操作与具体GitHub main远端确认未收到，未启动桌面、未推送；整体目标active，仍缺真实环境/三级工程链/目标机/签名及原生验收。16:49实际查询周额度剩余24%，未达用户此前15%暂停线。

## 2026-11-18 · F001/F022 后处理工作区及未确认弹窗草稿

从3d9ab94继续本轮草稿实现，保留既有改动。新增 `OdbPostprocessDraftRecovery`、`OdbPostprocessingPage.Drafts.cs`、`OdbPostprocessingPage.DialogDrafts.cs`；正式工作区保存复用捕获函数，结果图与后处理共用 `RecoveryDraftFile<T>` 串行磁盘写入。原始输出字符串及四类弹窗（提取参数、图例、分组管理、组内顺序）接入日常和会话结束检查点。未确认填写不转为业务提交；根目录、正式配置及最近发现的源身份不符时只能查看/保留副本。恢复准备新行且清除结构有效性；输入恢复异常尝试回滚，保留原件及副本；弹窗保留/恢复期间阻止关闭竞态。切换目录前等待旧草稿写盘。

用户追加按钮问题已核实：ResultBrowser的「读取目录」已有空闲Collapsed、颜色绑定和内容居中；本轮将相同规则应用到后处理「发现 ODB」，消除闲置圆环占位。没有启动原生窗口或用旧候选冒充本轮渲染验收。

实际失败与修复：初次构建 `GPTWork/postprocess-draft-build-20261118.log`（35919退出1）发现StackPanel没有IsEnabled，改为待恢复时收起正文、禁用确认；第二次构建 `postprocess-draft-build-20261118-02.log` 及首次专项编译发现只读显示属性被赋值，改为从基础元数据计算。最终构建 `postprocess-draft-build-20261118-03.log`，92660退出0，18.33秒、0警告/错误，输出 `GPTWork/winui-postprocess-draft-20261118`；不是完整发布包。

专项 `GPTWork/postprocess-draft-checks-20261118-02.log`：38项通过，实际JSON证据目录同名无.log；验证原文、不可变捕获、正式配置不变、目录/配置/文件大小/mtime/列表冲突、结构失效、损坏/超限/占用保护、逐字节副本、串行清除和重试。该专项只使用ODB路径元数据，没有创建ODB。`postprocess-draft-existing-checks-20261118.log`：174项既有后处理检查通过；`postprocess-shared-graph-checks-20261118.log`：16项既有结果图草稿检查通过。

初次相关Python回归 `GPTWork/postprocess-draft-regression-20261118.log`：41通过、1失败，31505退出1。失败为壳层静态检查仍查找直接ShowAsync，已同步到恢复包装入口；业务验证条件不放宽。最终相关回归含文档 `GPTWork/postprocess-draft-regression-final-20261118.log` / `.xml`：91项通过24.24秒，9657退出0；包含正式客户端真实HTTP关闭及结果图检查。所有测试TEMP/TMP、basetemp、输出均位于G:项目GPTWork，无用户ODB移动、无Abaqus求解、无原生或实际关机操作。

最终审阅补充数值回填原文/有限数值核对、发现目录首个await前锁定按钮和缺失组内顺序拒绝，避免控件归一化丢失半填文字及等待磁盘时重入。最终构建回执 `GPTWork/postprocess-draft-build-delivery-20261118.log`，81301退出0，0警告/错误；旧构建/失败记录保留。Ruff和差异空白检查通过；当前全部构建和相关回归句柄已结束。

收尾检查 `GPTWork/postprocess-draft-docs-final-20261118.log`：85项通过0.22秒（49项文档、35项壳层及1项页面登记，与前述91项重叠，不累计）。最终构建耗时12.93秒；全部句柄已结束，无待收回进程。

准确续接点：本轮代码、测试和文档一起本地提交，提交号以实际Git为准；之后从干净提交更新完整目录和安装候选。旧6d5279845a23目录包和cfa638b65fa8安装器不含4f135a7/3d9ab94及本轮源码；保留旧包。原生恢复/主题/显示比例及四类弹窗交互待验，完整迁移不标完成。原生恢复和具体GitHub远端确认仍未收到，不操作/推送。

## 2026-11-18 · F001/F012 结果图独立草稿恢复

开始于干净4f135a7。上一轮是实际源码/测试/文档提交进展，继续从复杂草稿缺口推进，未重复已通过按钮/GIF或安装验收。先说明独立草稿、匹配基线后恢复编辑、正式保存继续版本检查的方案。新增`OdbResultGraphDraftStore`/`OdbResultGraphDraft`、`OdbResultGraphEditor.Recovery.cs`和三种恢复入口；`WorkbenchSession.RegisterCheckpoint`让基本草稿与独立草稿分别尝试写入。捕获在UI线程同步完成，后续仅磁盘任务，不调用后台提交。

保存正式基线、原始输入、当前节点与目标；256节点/4MiB边界、运行descriptor路径及规范化内容/修订核对。冲突不能直接恢复，可查看复制或保留JSON副本并忽略。损坏原件不自动覆盖；保留副本成功并flush后才清活动检查点。确认重新读取期间锁住编辑并暂停定期捕获，避免归档后等待网络时旧草稿被重新写回。正式保存失败或修订冲突不清草稿，已保存但清检查点失败另行提示。

首轮`--graph-draft-checks`16项通过（`GPTWork/graph-draft-checks-20261118-01.log`），覆盖原文/不可变捕获、版本/同版本内容/环境冲突、节点序列规范化、循环拒绝、256节点、占用导致副本失败、正常/损坏文件逐字节保留、重试及不重复写盘。首次WinUI构建0警告/错误，75611退出0。补充重新读取并发保护和实际HTTP检查后，最终WinUI构建0警告/错误、17.40秒，96728退出0（`GPTWork/winui-graph-draft-build-final-20261118.log`）；Debug目录`GPTWork/winui-graph-draft-20261118`，不是完整发布包。

相关Python回归65项通过13.41秒，53749退出0（`GPTWork/graph-draft-regression-20261118.log`及`.xml`）：后台图23、正式客户端关闭/图恢复6、页面登记1、壳层35。其中新增真实HTTP用生产C#客户端完成4项检查：本地检查点不发布图、其他编辑后不能匹配、旧修订保存被拒绝且新图保留、原草稿仍在。无原生窗口/实际关机/求解；本轮JSON、测试占位ODB和测试TEMP/TMP均在G:项目GPTWork。

用户本轮追加完整目标约束：验证禁止向C:盘放置任何ODB（含测试/占位/复制件），可直接只读使用其他盘已授权目录，未经明确同意不得移动用户ODB。已写入AGENTS、维护工作流、当前状态与交付清单。没有移动用户ODB；历史C:跨卷回执只作既有证据，不授权重跑原目标。当前回归在新的G:basetemp与`graph-draft-temp-20261118`执行。

最终16项源码复核通过（`GPTWork/graph-draft-checks-20261118-02.log`，证据目录同名无.log），文档49项通过0.11秒（`GPTWork/graph-draft-docs-20261118.log`）；Ruff和差异空白检查通过。所有本轮测试/构建句柄均已结束，包括53749/96728。没有启动原生业务窗口，没有向C:写ODB，没有移动用户ODB。

准确续接点：代码和文档随后一起本地提交，提交号以实际Git日志为准；结果图恢复原生按钮/键盘/重开未验收，完整目录/安装器尚不含4f135a7及本轮源码。下一独立项为后处理详细工作区与未确认弹窗：`OdbPostprocessingPage.xaml.cs`的SaveWorkspace/CaptureOutputOptions/ShowJobConfigurationDialogAsync及分组图例/顺序弹窗。需按根目录与ODB身份保存独立原始输入，扫描或正式配置变化后再决定恢复，不能在OS回调同步执行业务保存或把未确认编辑自动提交。原生恢复及具体远端确认未收到，不操作/推送；整体目标继续active。

## 2026-11-18 · F001 日常草稿与系统会话结束

开始于干净92bd8fd；确认读取目录按钮和GIF双模式已在已有源码/候选中，未重复修改。按上一轮准确续接点补专用会话结束入口，先说明定期保存、限时非交互收尾方案。`WorkbenchSession.SaveDraftAsync`仅捕获已恢复页面的登记字段；`WorkbenchSessionStore.SaveAsync`先序列化快照再串行后台写入，成功内容不变时跳过，文件丢失时重建，失败不阻止下次重试。临时文件flush后替换，损坏原文件不覆盖。

`MainWindow.Session.cs`每两秒触发，无重叠采样；失败通过独立InfoBar提示。`SystemSessionEndHook`在UI线程注册/注销HWND子类回调；`SystemSessionEndState`对查询立即返回true，取消无副作用，确认结束最多等待磁盘任务两秒并对重复消息幂等。确认OS结束后不走普通关闭的对话框/网络/任务取消；普通关闭仍等待原页面保存回调。仅登记字段进入本机制，后处理详细工作区、结果图和未确认弹窗的完整崩溃草稿恢复尚待实现/核对，不能称全部草稿已覆盖。

初次独立检查7项既有持久化+14项新增检查通过（`GPTWork/session-end-checks-20261118-01.log`，15902退出0）。发现已成功文件被移走后相同内容会跳过保存，补存在性检查与真实移走/重建用例；最终7+15项通过（`GPTWork/session-end-checks-20261118-02.log`，退出0），覆盖查询/取消/重复、同步及异步错误、超时、不可变快照、64次写入顺序、无变化不写、缺失重建、失败后重试，证据文件保留在同名无.log目录。无原生窗口或系统关机。首次WinUI构建0警告0错误（63708退出0）；最终构建亦0警告0错误，18.44秒，24257退出0，日志`GPTWork/winui-session-end-build-final-20261118.log`，候选`GPTWork/winui-session-end-20261118`仅Debug构建。

相关回归98项通过22.58秒，37799退出0，回执`GPTWork/session-end-regression-20261118.log`及`.xml`：页面登记1、壳层35、正式关闭客户端HTTP5、后台关闭协议8、文档49。普通关闭保留后台/取消/停止/空闲仍通过，测试期间没有原生业务窗口或求解。差异空白检查通过；未重跑不相关整套966项，未将新Debug构建称为完整安装包。

文档同步ADR0017、界面说明、Wiki、版本日志、功能索引及当前/任务/验收状态。首次文档补丁有一处完整行匹配失败，确认无文件写入后修正重试；源码检查时误用Windows通配符路径和两个不存在的猜测文件名，均改为实际目录/索引路径，无产品失败。准确续接点：测试/构建句柄均已结束；下一项是复杂草稿独立检查点：`OdbPostprocessingPage.xaml.cs`的SaveWorkspace及CaptureOutputOptions、`OdbResultGraphEditor.xaml.cs`的Snapshot/HasUnsavedChanges/SaveForCloseAsync；不得在OS回调同步调用这些网络/业务保存，不自动把未确认模态编辑提交成业务配置。先明确本地草稿与用户确认保存的区分再实现，核对修订冲突、损坏原件、忙碌状态及恢复范围。既有完整目录6d5279845a23与安装器cfa638b65fa8不含本次源码，不覆盖或冒充新候选。原生暂停/具体远端确认未答复，未操作/推送；整体目标继续开发。

## 2026-11-18 · F026 安装、升级与卸载

开始于干净45aa392，产品负载仍使用已验证b2cfd57/6d5279845a23，不修改业务代码。先给出按用户安装、独立版本目录、保留数据、活动任务拒绝的实现方案，再新增build_installer.py、installer.iss.in、verify_installer.py及11项清单测试。正式标识构建要求干净源码；负载和安装器源码分别记账。新增安装说明、ADR0016及Wiki/README/功能索引。测试标识产物不得交付用户。

官方 Inno 7.1.1 x64 来自官方链接，Authenticode有效、发布者Pyrsys B.V.，下载SHA256为8a5a6711c3766a6e5fb74f280ba0e3551e719ce94538d901fdbd1f8f9920b3f0。便携编译器位于GPTWork/inno-setup-7.1.1/compiler；初次普通运行因SHGetFolderPath 0x80070005拒绝读取autodesktop而退出1，未部署应用；正常账户便携释放退出0，不创建编译器快捷方式/卸载项。日志extract.log/extract-allowed.log均保留。

测试包40d09cc651bf（0.0.9，负载03b4adf）和8a79e216e0c5（0.1.0，负载b2cfd57）编译通过，均使用独立身份AbaqusTools.Workbench.WinUI3.Test.202611180002。编译源码dirty为测试期如实记录；不是正式标识发布物。早期14a896056f83也保留。

实际静默生命周期 `GPTWork/installer-lifecycle-b2544857f35d/verification.json` verified（73495退出0）：陌生目录拒绝、中文空格目录首次安装、全摘要、活动自有后台拒绝升级/卸载且未被终止、正常退出后升级保留旧版本和用户样本、正式C#主机启动/API/退出、卸载清除登记程序/注册并保留用户文件。首轮NOICONS未验证菜单，后续 `GPTWork/installer-lifecycle-599f6e10a6fd/verification.json` verified（51187退出0），追加真实开始菜单首次指向/升级指向/卸载清除；old-shortcut.log/new-shortcut.log保留。均无强制收尾、无剩余自有PID/测试注册，不启动业务窗口/Abaqus。

最后追加目录链接祖先拒绝检查：`GPTWork/installer-lifecycle-a1a720d99f20/verification.json` verified，51405退出0，日志GPTWork/installer-boundaries-20261118.log。链接目标无写入，其余完整生命周期/开始菜单回归均通过；无强制收尾、无剩余PID/测试注册。11项清单及49项文档共60项通过0.21秒（GPTWork/installer-delivery-tests-20261118.log），Ruff及差异空白检查通过。正式标识候选随后完成，见下方最终回执。当前原生恢复及具体GitHub main确认仍未收到，未操作/推送。

最终候选：本地提交e69192befdffee14b412eaab9de8ed05bbae78ed，干净构建 `GPTWork/installer-win-x64-cfa638b65fa8`（65990退出0），正式AppId、非testOnly，负载仍为b2cfd57/6d5279845a23。安装器125523315字节，SHA256 b3b789e230c37b6998c1ffc01612c7d52112dfc067f98e9bf9e25020cb9ff1d1；artifact-verification.json核对文件/来源及架构，安装引导器0x14c、应用与后台0x8664；signature.json为NotSigned。正式标识没有实际安装到用户默认目录，没有发布GitHub。

准确续接点：所有本轮构建/测试/验证句柄已结束，无待回收进程/测试注册。最终文档49项通过0.11秒（installer-final-docs-20261118.log），本地提交后继续F001系统会话结束及日常草稿保存。最终审计发现MainWindow仅普通AppWindow.Closing接线，WorkbenchSession只在SaveForCloseAsync保存；当前没有WM_QUERYENDSESSION/WM_ENDSESSION专用处理。Windows官方说明系统会话结束有独立消息和有限处理时间，不能沿用可等待网络/对话框的普通关闭流程作为证明。先给出新的非交互保存/恢复方案，再实现/模拟检查；不实际注销/关机。原生恢复、真实环境和资料、目标机及具体远端确认仍未补齐，但尚有独立实现项，goal继续active，不标blocked/complete。正式标识真实安装、签名/SmartScreen、原生向导与无开发环境目标机仍待验，不移除其他整体迁移缺口。本轮只在新建GPTWork内安装/卸载自有测试程序，不递归清理历史证据。


## 2026-11-18 · 完整合同核对、队列来源与整套回归

本轮从干净bd22cd8开始，逐项核对迁移合同；新增[交付核对清单](../../06-testing/COMPLETION_AUDIT.md)，整理CURRENT_STATUS/TASK_INDEX中过时的连续“下一步”。Wiki和功能索引接入。发现正式安装/升级/卸载入口仍是开发缺口，不能把所有剩余事项归为外部阻塞。原生恢复、具体GitHub main确认均未收到，不操作/推送。

**初轮失败**：`GPTWork/migration-audit-20261118-135640/tests.log`、`results.xml`，961项中944通过/17失败/9子检查通过，580.13秒，22758退出1。显式排除会清除offscreen并打开窗口的 `tests/submitter/test_native_window_startup.py`，其他Qt检查offscreen；TEMP/TMP及basetemp均在本轮GPTWork。17项均被旧Qt测试写入共享文件的running/waiting记录干扰，退出保护正确识别“状态未知”，没有放宽产品关闭规则。HTTP夹具现默认每个tmp_path独立队列/服务器配置/结果图，重复同目录仍保留恢复语义。

**另行复现的产品问题**：`tests/control_plane/test_runtime_queue_scope.py` 四项将默认队列设为另一份文件，旧实现资源统计错、链为空、计划和批量返回404。有效失败回执 `scope-before-final.log`（60582退出1，4失败11.50秒）；更早 `scope-before.log` 的第四项是测试输出目录缺失，已修正夹具，不能当作产品失败。产品现把运行实例的JobQueueService.path传给资源、链、预览和批量重新核对，默认入口/HTTP字段/检查点/取消规则不变。代码为server.py、resources.py、restart_chains.py、restart_result_plans.py、odb_result_batches.py；测试相应更新显式路径，不通过修改全局常量伪装路由正确。

**定向通过**：`scope-after.log`，12项通过51.99秒，18711退出0，含四项来源隔离、原资源、重启动链和计划；全量Ruff范围及git diff --check通过。完整重跑 `GPTWork/migration-audit-20261118-135640/final.log` 与 `final.xml`：**966项及9子检查全部通过，746.54秒，66842退出0**。48项文档导航通过0.15秒（docs-final.log）。早期文档整理漏保留“每完成一个功能”原句导致1项导航失败（docs-first.log），已恢复该规则，不削弱测试。全部本轮测试句柄结束，没有Abaqus求解或原生窗口操作。

**新候选通过**：本地源码提交 `b2cfd57529c3dc34682e3c296ebaf9a5aa5471d4`，未推送；干净构建 `GPTWork/release-win-x64-6d5279845a23/AbaqusTools`（43843退出0）。本轮目录下 inventory.json 核对1664文件/19worker、354515136字节全摘要；bundle-probe-i2omouc1/verification.json验证包内GIF/图表/工作簿/SSH加密依赖和Qt-free；frozen-host.log确认正式C#主机启动、资源/队列读取和正常退出，三个命令均退出0。包内文档是构建时快照，最终回执在仓库；旧包保留。没有启动WinUI业务窗口或Abaqus求解。

**准确续接点**：所有本轮测试/构建/正式主机句柄已结束，无需重启检查。最终文档回执48项通过0.17秒（docs-receipt.log），本地提交后下一项给出正式安装入口实现方案并开发；原生/真实SSH/GPU/MPI/三级工程链/目标机及推送门槛仍未完成。当前goal active，周额度最后读数剩余34%，未达到用户此前15%暂停线。


## 2026-11-18 · 独立文件路径与跨卷槽位竞争验收收尾

最终文档导航 `GPTWork/archive-independent-final-docs-20261118.log` 47项通过（0.14秒），Ruff及差异空白检查通过；本轮工具/文档已可本地提交，没有待收回的测试句柄。

**产品不变**：仍使用干净03b4adf的完整包75efcbf6b9f7；只扩展验证器、主机测试客户端和文档，没有重建应用或修改用户配置。多作业验证器新增 `--distinct-held`，261行使用261个不同源路径。冻结回执 `GPTWork/scheduler-load-live-3a1be04c8ea6/verification.json` verified（64943退出0）：260次GET中位38.808ms、P95 279.41ms、最大446.392ms；5次执行、CPU/内存等待、停止/终止/失败释放额度、输入不变、5条提醒两次启动不重放通过。实际5个helper和两个后台、包装均已结束。这是独立本地路径元信息开销，不是261个工程模型或MPI满载。

**归档回归与忙碌保护**：原默认小样例首次源码回归 `GPTWork/archive-recovery-live-3b67843bedc9/verification.json` 失败（88222退出1）：第一归档已发布但线程尚在收尾，第二客户端被正确409 `LOCAL_ARCHIVE_BUSY`拒绝，全部自有进程结束。`ArchivePresentationChecks.RunApi`现只对该未受理错误在45秒总期限内核对同attempt/可恢复状态后等待重试，不重试其他错误或超时，不改变产品槽位保护。新主机 `GPTWork/archive-volume-host-build/Debug/net10.0/ControlPlaneHost.Tests.exe` 构建零警告/错误3.14秒，原主机检查通过。默认源码回归 `GPTWork/archive-recovery-live-983424f3695b/verification.json` verified，全部自有进程结束。

**真实竞争分支**：跨卷命令追加 `--parallel-recovery`，两客户端同时竞争一个槽位；回执 `GPTWork/archive-recovery-live-4db89f22762e/verification.json` verified（77477退出0），实际6次忙碌拒绝后两项依次完成，两个128MiB内容全摘要、8MiB半成品保留、完整副本复用、源清理续接、同attempt和4条提醒两次重启去重通过。目标位于C:测试根的同名子目录；源/目标设备号与上一跨卷记录一致。两个生产者按计划中断、两个后台及两个客户端正常退出，均为已捕获自有进程。首次状态读取2.1/16.8ms只是本夹具，不是性能上限。

**准确续接点**：本轮所有命令、后台、生产者和客户端均已结束。验证器Ruff、主机检查通过，最终文档检查后本地提交。下一项按完整迁移合同逐项审计剩余门槛，区分可继续实现项与必须恢复原生操作、提供真实环境/数据或确认发布目标的门槛；不反复跑同一夹具替代业务验收。原生恢复与具体GitHub main确认仍未收到回复，不重复询问或绕过。工程多GiB/断电、真实SSH/MPI、连续三层工程ODB、无开发环境目标机和原生八页仍未验收，整体目标不标完成。

## 2026-11-18 · 跨卷128MiB归档与中断恢复

在既有75efcbf6b9f7完整包（产品03b4adf）上补充跨卷证据，**没有修改产品或重建包**。扩展 `packaging/verify_archive_recovery.py`，保留原小夹具调用，新增不同卷目标及16–512MiB载荷选项；真实 `_copy_verified` 写入8MiB后在进度边界等待，由父进程仅结束已捕获的自有生产者。第二场景仍在发布后首次源文件删除后中断。正式C#客户端恢复同attempt，未启动求解。

准确命令：项目Python运行 `packaging/verify_archive_recovery.py GPTWork/release-win-x64-75efcbf6b9f7/AbaqusTools GPTWork/scheduler-load-host-build/Debug/net10.0/ControlPlaneHost.Tests.exe --destination-root C:/Users/Chiw/.codex/visualizations/2026/10/28/01a182a2-461c-76b2-b649-05a4ff044834/GPTWork --payload-mib 128`。源卷设备号15996367331267573161，目标卷3051326448021075386；写入前确认目录及空闲空间，目标只创建唯一子目录。

回执 `GPTWork/archive-recovery-live-d91a5ee5c815/verification.json` **verified**（5659退出0）。两个128MiB合成文件完整摘要、原始输入不变、8MiB不完整副本原样保留、完整INP副本inode复用、跨卷发布、部分清理续接、4条提醒两次重启保持唯一通过。目标完整副本及`.recovery-*`现场位于上述C:根的 `archive-recovery-live-d91a5ee5c815` 子目录；不清理历史。首次状态读取26.4/1.0ms只代表本夹具。实际生产者208884/181252按计划中断，后台211544/188136正常退出，包装也结束，无遗留进程。测试源码/文档/Ruff及路径检查收尾后本地提交；下一项独立模型路径的队列读取开销。真实工程多GiB、原生/SSH/MPI/三层链/目标机和发布仍待验。

## 2026-11-18 · 多作业资源准入与队列响应

最终回执补记后文档导航 `GPTWork/scheduler-load-docs-final-20261118.log` 47项通过（0.15秒），差异空白检查通过；没有原生操作、GitHub推送或新求解。

**最终完整包回执**：本地功能提交 `03b4adf014da75a714eb243190f90a1b7e3e9f23`，干净来源 `GPTWork/release-win-x64-75efcbf6b9f7/AbaqusTools`（32567退出0）。用户账户1663文件/19worker全摘要、依赖 `GPTWork/bundle-probe-asbma2v2/verification.json`、正式主机 `GPTWork/scheduler-load-frozen-host-20261118.log` 均通过。冻结完整流程 `GPTWork/scheduler-load-live-b52bd66c9cfb/verification.json` verified（77633退出0），5个helper和两个后台实际/包装进程均结束；无Abaqus求解，输入不变。233次GET中位39.94ms、P95 284.58ms、最大1137.44ms；本轮比源码多核对case3持续运行时，case2失败释放额度，内存请求编辑后memory_gate立即入场。5条不同执行的成功/终止/失败提醒及重启不重放通过。源码和冻结夹具都不代表独立工程模型/网络盘/真实MPI压力。

**实际发现与修改**：261行夹具（5个可调度作业、256条暂停记录共用第6个INP）运行后状态GET超过5秒。`scheduler-load-live-171fc499f113` 与带线程栈的 `scheduler-load-live-8c23ea54fc7a` 保留失败回执；栈显示调度锁内重复解析路径/查询文件，读取线程等待runtime锁。`local_memory.py`改为空历史不做无意义的历史文件查询，同轮相同路径共用解析/stat，下轮重新检查以保持源变化失效；不跨轮缓存，不改既有历史键。`local_scheduling.py`无活动归档时省略目录解析比较。并发实际流程还发现Datacheck失败漏提醒，补齐`LOCAL_TERMINAL`，同时覆盖回调/重启补查和已读去重。使用说明、Wiki、README和功能索引同步；发布文档只指向当前状态，旧“最新”段落归入历史区。

**源码实际进程回执**：`GPTWork/scheduler-load-live-afc4a08d44b5/verification.json` verified（41601退出0）。正式C#客户端开始/停止/终止，32逻辑线程预算下每作业声明16CPU、并行上限3，实际先启动2个，后续等待；停止派发保留活动进程，终止释放额度，非零退出保留失败，超总物理内存的声明请求保持等待、修改为64MB后放行。5个helper各仅8MiB缓冲，不执行求解/CPU压力；256暂停条目从未启动，5个attempt与5条提醒唯一，后台重启不重放，6个输入摘要不变。260次状态GET中位39.50ms、P95 266.12ms、最大1050.74ms；这是共享路径的小型夹具，不是261个不同工程模型/网络目录/MPI满载。7个实际自有进程与两个包装均已结束。

**已执行检查**：内存/调度首轮 `scheduler-load-first-20261118.xml/log` 30项通过26.31秒（77486退出0）；扩展 `scheduler-load-final-20261118.xml/log` 75项通过59.46秒（44978退出0），覆盖运行API/关闭/归档恢复/外部扫描/共享调度存储。最终 `scheduler-load-delivery-20261118.xml/log` 65项通过26.11秒（82674退出0），包含18项通知和47项文档。集合重叠不累计。正式C#主机检查、Ruff通过。Datacheck提醒修复前2项明确失败；已读断言先误把未读列表当作全部历史、再误用SQLite列名，已修正为读取实际持久记录并通过。首次错误测试文件名没有执行测试，不计通过；文档路径最初把pytest节点当文件路径，已分开路径并通过。47177等旧句柄均已结束。

**其他保留的夹具失败**：`scheduler-load-live-a2cba1d96f01`错误期待CPU已占满时显示内存限制；`8fe1d8937a6a`错误期待终止结果为“已取消”而非真实合同“已终止”；`331f9cb0e3dd`发现真实Datacheck失败提醒遗漏，修复后afc4a08d44b5全程通过。这些失败的自有进程均已核对结束，不作为新求解或测试通过证据。

**准确续接点**：源码/通知/文档回归、构建及冻结完整流程均已结束，产品已本地提交；本轮所有自有进程结束，没有长任务待收回。下一项检查归档跨卷发布/清理边界及不同模型路径下的文件查询开销，先明确受控验收条件，不能重复共享路径夹具冒充独立工程负载。原生操作恢复及具体GitHub main确认仍待回复，不重复询问或绕过；真实工程/MPI负载、跨卷、SSH、三层ODB与目标机仍未验收。

## 2026-11-18 · 外部扫描期间状态读取与条件合并

**最终完整包回执**：本地功能提交 `a01382f2617c5b41b91426b9699a17295796a5ee`，干净来源 `GPTWork/release-win-x64-5f29d9d738de/AbaqusTools`（44599退出0）。用户账户1663文件/19worker摘要、依赖 `GPTWork/bundle-probe-iqcgci8t/verification.json`、正式主机 `GPTWork/external-scan-frozen-host-20261118.log` 均通过。冻结扫描回执 `GPTWork/external-scan-live-2b0fdadc1f67/verification.json` verified（69802退出0）：正式C#客户端扫描期间62次读取73.38–489.22ms，识别实际自有进程，后台自动扫描确认完成，输入不变；实际195056/173812及包装均正常结束。归档恢复回归 `GPTWork/archive-recovery-live-7ddb793bdfea/verification.json` verified，四个实际进程及包装均结束（两生产者按计划中断、两后台正常退出），无Abaqus求解。

冻结首轮 `GPTWork/external-scan-live-3a51d24fbfd0/verification.json` 失败（72601退出1）：脚本第二次手动扫描恰好碰到后台周期扫描，被预期409保护拒绝；全部自有进程结束。仅修正验证器为等待并读取现有自动扫描结果，未改产品、未放宽重复扫描规则或状态GET超时，因此保留同一完整包验证。首次源码脚本验证的第二轮是手动扫描；最终冻结回执补上实际自动监测完成证据。产品来源仍为a01382f，后续回执/验证器修正提交不冒充产品重建。

最终回执文档检查 `GPTWork/external-scan-docs-final-20261118.log` 47项通过（0.17秒），验证器Ruff与差异空白检查通过。本轮没有原生操作或GitHub推送。

**实现**：F004/F005手动及后台扫描改为独立扫描锁，短队列事务取副本，锁外目录/进程/日志诊断，最终只合并基线仍匹配的记录。防删除复活、重执行/编辑覆盖和并发新增同目录同名重复。保留当前候选与排序，跳过本机活动/归档记录，失败及关闭不发布迟到结果。生产多目录共用一次进程枚举，兼容原双参数扩展扫描器。API/C#增加externalScanActive，WinUI按钮显示扫描中并防重复。使用说明、API、Wiki、README、功能索引及ADR0015已同步。

**已执行**：`external-scan-delivery-20261118.xml/log` 96项通过（308.37秒），覆盖并发、队列命令、调度、内存、归档恢复、关闭保护和壳层；追加冲突/失败重试后 `external-scan-edges-20261118.xml/log` 13项通过（3.14秒）。集合重叠不累计。Ruff通过；C#主机检查通过，WinUI Release `external-scan-winui-20261118.log` 零警告/错误20.64秒（52854退出0）。源码正式客户端真实进程回执 `GPTWork/external-scan-live-8801618bf931/verification.json` verified：扫描期间71次状态读取79.37–431.06ms，识别自有非求解进程及退出完成；输入摘要不变，包装213656/214848正常退出，实际209248/197620均结束（8855退出0）。时间仅代表此机器此小型夹具。没有新Abaqus求解。

**失败证据**：修复前 `external-scan-before-fixed-20261118.xml/log` 两项复现手动/自动扫描锁住读取；更早before文件中的自动案例未设置工作目录，属于夹具错误。首次真实验证 `GPTWork/external-scan-live-402ccde15b89/verification.json` 因脚本误读API不存在的pids失败（63212退出1），自有进程全部结束；后改为读取真实持久队列的进程身份，并使用生产C#客户端检查第二轮完成扫描，不调整状态GET超时掩盖响应问题。

**准确续接点**：96项原命令输出句柄因上下文截断未保留，最终XML/日志通过，已知进程202440/209696已核对不存在；其余本轮自有进程与构建均已结束。文档导航 `external-scan-docs-20261118.log` 47项通过（0.16秒）。产品已本地提交并完成新包验证，下一项按合同设计多作业资源准入/高负载及跨卷边界验收。原生业务显示、工程大队列/网络目录未验；具体GitHub main确认与原生操作恢复仍待用户答复，不重复询问或绕过。此局部不能代表完整迁移结束。

## 2026-11-18 · 归档独立提醒的崩溃补发

**最终完整包回执**：本地源码提交 `e31a3583159a3e8f1822b72977d582cb6f5ce53b`，干净来源包 `GPTWork/release-win-x64-10aba0ad350a/AbaqusTools`（构建59888退出0）；用户账户1662文件/19worker摘要、依赖 `GPTWork/bundle-probe-v7sw1_nd/verification.json`、正式主机 `GPTWork/archive-notice-frozen-host-20261118.log` 均通过。冻结提醒补发 `GPTWork/archive-notice-live-2af35a395468/verification.json` 和归档恢复回归 `GPTWork/archive-recovery-live-7e74fa0a82cd/verification.json` verified：实际中断自有生产者、队列清除、正式客户端补发与已读、第二次重启保持已读；原归档恢复、完整摘要与原输入不变继续通过。所有自有实际/包装进程均已核对结束，没有Abaqus求解。文档导航47项通过，旧候选及失败回执保留。

准确下一项：定向复现并修正外部扫描占用队列锁导致读取等待，扫描放到快照/写入锁之外时须拒绝合并过期执行结果。原生交互和具体GitHub远端确认仍未收到，不重问、不绕过；未执行push。下方“进行中/待验证”是过程记录，已由上述最终回执补齐；本轮不宣称原生业务操作或整体迁移完成。

最终相关回归 `GPTWork/archive-notice-delivery-20261118.xml/log` **86项通过（202.82秒）**，覆盖5项新补发/缓存/保护、恢复API/核心、原求解执行、通知、关闭与WinUI壳层；22623已返回0。没有Abaqus求解。当前接续改为文档检查、本地功能提交和新完整包验证，不再等待该测试。

上一轮有实质进展：归档恢复/目录观察修正与8791f815c891完整包完成验证，749d17d为交接提交。当前工作区开工时干净。本轮按用户更新后的完整迁移目标继续；目标仍包含全部功能验证、性能/界面、Wiki/README及GitHub上传，不收缩为归档局部。

实施前说明：独立归档先保存操作身份，终态在队列收尾/提醒回调之前保存小回执；回调和重启补查使用同一身份去重，队列清理不删除回执。已接入 `ArchiveNoticeStore`、原生锁核对、未变化终态内容读取缓存、取消/关闭提醒/损坏记录保护；界面标题区分本机归档，跳转核对原attempt。仅归档操作改变，原求解与远端通知原有路径保留。

源码真实进程 `GPTWork/archive-notice-live-5dbd1b38a22d/verification.json` verified：保存归档结果后、通知回调前终止自有生产者，清除夹具队列，新后台补发，正式C#客户端标已读，第二次重启仍已读；原INP不变、最终归档完整摘要通过，全部自有进程结束，无Abaqus求解。`archive-notice-corrected-20261118.xml/log` 4项通过（33.48秒）；随后补充终态与元数据失败一致性检查，最终相关测试正在执行，不能沿用4项数宣称最终全通过。C#14项通知检查及原有主机检查通过；WinUI Release零警告/错误、26.35秒。

失败记录：`archive-notice-before-20261118.log` 是4秒夹具等待超时，状态在done检查点，不能称为漏通知断言复现。首轮扩展 `archive-notice-final-20261118.xml/log` 46通过/3失败：两个补发调用字段大小写不匹配已修正，另一个损坏归档记录测试被真实外部进程扫描阻塞；该格式验证测试明确关闭周期扫描，未声称整个扫描性能问题解决。首个掉回调测试误替换已捕获的方法而非实际完成回调，已改为切断runtime._completion_sink。首个真实进程回执 `archive-notice-live-2ae157df9789` 因补发字段错误失败，原文件和终态保留，自有进程已结束。

准确续接点：最终相关检查句柄22623仍在执行，先收回原句柄/日志，禁止重复启动；WinUI95936已返回0。源码真实进程与C#检查已结束。继续完成文档/最终检查、本地功能提交与新完整包的提醒恢复验证。原生操作恢复、具体GitHub main确认仍未收到答复，不重新询问或绕过。最新用户编辑的目标已替换原目标文本。

## 2026-11-18 · 归档中断恢复与独立重试

**最终回执**：定向修正已本地提交 `6cb343d6e7ead730a0f00ff36169f98a448b1d4c`。干净来源新完整目录 `GPTWork/release-win-x64-8791f815c891/AbaqusTools` 构建结束（52123退出0），用户账户1662文件/19worker全摘要通过；依赖 `GPTWork/bundle-probe-ugqe389y/verification.json`、正式主机 `GPTWork/archive-observation-frozen-host-20261118.log` 均通过。冻结真实中断/恢复回执 `GPTWork/archive-recovery-live-49c8ff630a0e/verification.json` verified：两次后台启动，首次状态读取2.5/2.9ms、正式客户端恢复同attempt、完整副本inode复用、部分清理续接、全摘要、源输入不变、4条提醒恢复且不重放。实际生产者217712/207092按计划中断，后台29008/35008正常退出，包装进程也均结束。没有Abaqus求解、原生界面操作、跨卷工程负载或GitHub推送。

本功能代码/测试/使用说明及交接已同步；最终文档导航 `GPTWork/archive-recovery-docs-final-20261118.log` 47项通过（0.18秒），回执单独本地提交，不重建产品。准确下一项为F027独立归档提醒写入前崩溃的补发保护，以及可独立验证的并发/大文件边界；原生操作和具体GitHub main确认问题仍待用户答复，不重复询问或绕过。周额度复查41%，整体目标保持active。以下为本轮过程及保留的失败证据，早先“待重建”由本最终回执覆盖。

功能已本地提交 `fc7f8b82e451df2df821178648a58b8fbd3cc37a`，从干净来源构建的首包 `GPTWork/release-win-x64-89d3b6ab518e/AbaqusTools`（句柄69915退出0）通过1662文件/19worker用户账户摘要、依赖 `GPTWork/bundle-probe-05hor33e/verification.json`、正式主机启动/API/退出；但冻结恢复 `GPTWork/archive-recovery-live-e14df1f5caa0/verification.json` 首次状态请求5秒超时，句柄54957退出1，全部自有包装/实际进程已结束。不得把首包写为恢复通过。

定向回归 `archive-observation-before-20261118.log` 1项失败（62170退出1），已确认归档的旧目录仍进入恢复进程扫描。修正为恢复目录与用户显式监测目录分开，仅将活动/未知作业的恢复目录纳入扫描；保留显式外部监测。`archive-observation-final-20261118.xml/log` **79项通过（38.39秒，55080退出0）**，包含7项恢复API、调度、队列及47项文档；源码真实进程 `GPTWork/archive-recovery-live-df2804ad50e8/verification.json` verified、全部自有进程结束。与185项集合重叠不累计。接续：提交此定向修正，重新构建新目录，重复冻结归档恢复并记录首次状态读取耗时；不能仅靠增大超时或重跑首包宣布修复。

最终相关回归 `GPTWork/archive-recovery-delivery-20261118.xml/log` **185 项通过（96.09 秒）**，包含 47 项文档导航；句柄7903已返回0。只读进程核对句柄77610也已返回0，未发现此轮测试进程。下方各专项集合重叠不累计；下一步本地功能提交与新完整包验证。

实施前已说明方案：保留原求解执行身份，持久记录归档阶段，重启展示待恢复；显式恢复时核对并复用完整副本，继续复制/清理，不通过重新求解重试归档。相比只持久保存最终状态，增加了复制途中与部分清理后恢复能力。详见 [归档说明](../../03-features/LOCAL_ARCHIVE.md) 和 [ADR 0014](../../submitter/adr/0014-verified-local-archive-publication.md)。

- 新增 `ArchiveStateStore`、`resume_archive`、`LocalArchiveRecoveryMixin`、`run_archive_only`；按原 itemId/attemptId 保存阶段与文件计划，原生文件锁防重复接管。损坏/错执行记录不把未知求解改成完成。未完成副本保留在独立现场；缺失的已清理文件可续接，新内容/链接/LCK/摘要变化拒绝清理。
- 作业概览「恢复归档」连接正式 C# 客户端；取消、关闭、重复请求和队列编辑沿用运行保护，暂停/恢复不发送给已完成求解器。重叠计算目录不分配新作业。相同已完成状态重启不重复落盘。独立提醒已写入后可持久恢复；写提醒前崩溃的补发缺口如实保留。
- `archive-recovery-final-20261118.xml/log`：40 项通过，34.85 秒；`archive-recovery-regression-20261118.xml/log`：117 项通过，68.60 秒（集合重叠）。C# 11 项归档/兼容及原有主机检查通过；WinUI Release 22.42 秒、零警告/错误。源码真实进程 `GPTWork/archive-recovery-live-323ba9721d6f/verification.json` verified，所有自有进程结束；未启动求解。
- 验证脚本 `packaging/verify_archive_recovery.py --source GPTWork/archive-recovery-host-build/Debug/net10.0/ControlPlaneHost.Tests.exe` 实际终止复制中、部分清理后的夹具进程，再经新后台和正式客户端恢复。两次后台启动、原 attempt、全 SHA256、完整副本 inode 复用、空目录、原始输入不变、4 条求解/归档提醒去重通过。其后换完整包目录替代 `--source` 可验证冻结版本。
- 检查期间修正损坏 files/directories 类型导致启动异常、恢复发布前复核遗漏、重叠目录准入遗漏。验证脚本初次语法错误未启动进程；后续 `archive-recovery-live-4877895a2c41` 因 Windows 虚拟环境启动器 PID 与实际子进程不同而失败，保留回执。改为验证自有父子链和实际 PID/createTime；该失败的 205536/201676 均确认结束，后续成功回执记录全部包装/实际进程终态。非产品故障。
- 本轮复核 F021 读取目录按钮：空闲圆环 Collapsed、忙时绑定按钮前景色、内容水平/垂直居中仍在源码和旧完整包；GIF 两模式实际导出证据继续有效，不重复改动已修复入口。用户曾按 Esc 停止原生操作，未擅自恢复桌面控制。

准确续接点：40 项检查句柄 79942 已返回 0；前轮回归117项日志终态明确，恢复 API 句柄15803已收回，Release91335此前结束。源码进程检查正常退出，新完整包尚未构建；先完成文档及最终相关回归，再本地提交、构建完整目录并运行冻结恢复/清单/依赖/正式主机检查。GitHub push 此前自动审批拒绝，具体远端 main 确认尚未收到，不重试。周额度本轮读取剩余42%，整体目标保持 active。

## 范围与前置条件

后处理交付后继续，不以现有八个页面存在证明迁移完成。范围来自本线程用户要求和 [迁移合同](../../winui-migration.md)。功能入口均可由 [功能索引](../../03-features/FUNCTION_INDEX.md) 定位。

## 接续顺序

### 2026-11-18 F005 归档发布与独立结果（源码/完整包通过；专门恢复/重试未完成）

上一轮工作目录保护及完整包为实质进展，提交 `4f40281`/`67809ed`、e3e69bc08715 候选已复核。本轮读取实际代码发现：不清理选项仍逐文件 move；归档根目录 mkdir 在异常保护外；旧失败目的地可能优先用于 Restart。修改前已向用户说明目标盘暂存、完整复制校验、一次发布、发布后可选清理及独立状态的方案，并告知额外空间和校验时间。

新增 Qt-free `local_archive.py`：4 MiB 分块复制与完整 SHA256 校验、源身份和文件集复核、清单、同目标盘目录发布、唯一目的地；发布前失败/取消不删源，发布后逐文件复核/清理，不递归删除未知内容。目录链接、LCK、原始输入清理冲突、空归档拒绝。已有结果不覆盖，未知临时现场不清理。检测到已发布内容异常与普通清理失败分为「归档需核对」和「已归档，清理未完成」。

求解成功状态独立保存，归档阶段合作取消不再调用已完成求解器的 terminate。队列、概览、日志和提醒增加归档结果；默认目录和 Restart 仅采用有效发布状态，旧部分移动记录等待核对。新执行清空旧归档字段，终态不会沿用旧目标。新的 ADR 0014、功能说明和候选版本日志已同步；PySide6 对照保留。

实际验证：

- 旧版 **2 项失败，0.14 秒**：关闭清理仍移走输入/结果；无效归档根抛出异常，`GPTWork/archive-before-20261118.xml/log`。首轮修复 **6 项通过，0.43 秒**，`GPTWork/archive-first-20261118.log`。
- 归档核心及已有执行 **29 项通过，2.86 秒**，`GPTWork/archive-edges-20261118.xml/log`。真实 HTTP/重启 **2 项通过，5.85 秒**，`GPTWork/archive-api-20261118.xml/log`。
- 扩展队列/调度/通知/关闭/准备/壳层 **105 项通过，67.07 秒**，`GPTWork/archive-regression-20261118.xml/log`，64234 已退出 0。
- 最终归档/执行/API **34 项通过，6.79 秒**，`GPTWork/archive-final-20261118.xml/log`。含真实 NTFS junction、复制/校验/发布失败、源变化、取消、清理占用和归档内容损坏；两个真实自有 Windows 子进程分别在发布前和发布后清理前终止，原文件保持、最终目录有无与边界一致。测试子进程均结束，未运行 Abaqus，未碰原始模型。
- C# 新增 6 项归档展示/旧协议兼容及既有主机测试通过，`GPTWork/archive-host-20261118.log`，输出 `GPTWork/archive-host-build`。WinUI Release **0 警告/0 错误，20.74 秒**，39371 已退出 0，`GPTWork/archive-winui-20261118.log`。未操作被用户停止验收的原生窗口。
- Ruff 初稿报告导入、异常边界、公开常量及 subprocess.check；修正为显式公开常量、记录归档异常和显式 check=False，最终通过。文档导航 **47 项通过，0.09 秒**，`GPTWork/archive-docs-20261118.log`；diff 空白检查通过。完整包待补记。

已本地提交 **`1f295df20d1aa962b7e6f0aaf621d8de7931ba6d`**，从干净来源构建完整目录 **`GPTWork/release-win-x64-2c2808add94d/AbaqusTools`**，90143 已退出 0，`GPTWork/archive-package-20261118.log`。用户账户核对 **1662 文件/19 worker**，全部大小/SHA256 一致、sourceDirty=false，回执为该发布父目录 `inventory-verification.json`。旧包保留。

完整包证据：

- 依赖/默认配置/worker/GIF/Agg/工作簿/SSH 加密/Qt-free 通过，`GPTWork/bundle-probe-p4tay3kv/verification.json`，`GPTWork/archive-bundle-probe-20261118.log`。
- 本轮正式 C# 客户端 `GPTWork/archive-host-build/Debug/net10.0/ControlPlaneHost.Tests.exe --launch-bundle GPTWork/release-win-x64-2c2808add94d/AbaqusTools GPTWork/archive-host-2c2808add94d` 启动、资源/队列 API、安全退出通过，`GPTWork/archive-frozen-host-20261118.log` 退出 0，描述文件清除。
- `.\.venv\Scripts\python.exe GPTWork/verify_archive_bundle_20261118.py GPTWork/release-win-x64-2c2808add94d/AbaqusTools` 退出 0，59586 结束，`GPTWork/frozen-archive-5538576f393c/verification.json` verified。使用非工程微小夹具和项目 Python 回显命令，正式冻结本机执行器完成两项作业：完整归档/清理成功、坏归档根失败且计算结果保留。最终清单逐文件摘要相符，两个原始 INP 摘要不变；两次后台启动恢复同一执行身份和归档状态，提醒保留问题及正确目录，开始请求 409，无自动重算。只有两次夹具命令，没有 Abaqus 求解；PID 180684/183268（后台）和 151404/192388（夹具）均确认结束，鉴权描述文件清除。此次不是归档过程中后台崩溃后自动接续的证明。

最终回执同步后，文档导航 **47 项通过，0.17 秒**，`GPTWork/archive-package-docs-20261118.log`，diff 空白检查通过。

准确续接点：本节全部检查、构建和自有进程已结束，新候选为 2c2808add94d，包内文档为构建时快照，最终回执在仓库补记。下一项处理专门的中断归档恢复与独立重试入口；不能以重算替代归档重试。目前后台在归档/清理中崩溃仍走原有状态未知/待确认流程，发布清单保留但未自动接续。真实跨卷、大文件负载及原生外观未验证。没有替换旧窗口或生成 ZIP/安装程序/GitHub Release，具体 GitHub main 推送及原生恢复确认仍未收到，不重试。周额度最新剩余 **45%**，未触及 15% 暂停线。

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

F001会话结束下一项的官方依据：[WM_QUERYENDSESSION](https://learn.microsoft.com/en-us/windows/win32/shutdown/wm-queryendsession)、[WM_ENDSESSION](https://learn.microsoft.com/en-us/windows/win32/shutdown/wm-endsession)。需及时响应查询、在实际结束时无提示地保存，并处理会话取消；本轮只核对文档/源码，尚未实现或测试该路径。
