# 运行日志阅读与数字输入交互

更新：2026-11-18。关联 F001、F005、F025，以及数字输入涉及的 F003/F004/F007/F008/F022。任务状态见 [TASK-004](../08-handoff/ACTIVE_TASKS/TASK-004-ui-interaction.md)。

## 关闭、后台继续与草稿（F001/F003/F004/F009）

结果图现已通过`RegisterCheckpoint`接入独立JSON检查点，和普通输入一起定期/限时保存；恢复待确认或损坏原件不被覆盖。基线匹配后只恢复编辑，保存正式图仍需原接口的版本检查。操作、冲突和保留副本见[结果图草稿说明](ODB_RESULT_BATCH.md)。后处理输出、工作区及四类未确认弹窗也已接入独立检查点，详见[后处理说明](POSTPROCESSING.md)；原生恢复尚未验收。

「读取目录」与后处理页「发现 ODB」的加载圆环在空闲时完全收起、不占布局宽度；读取时显示并跟随按钮文字颜色。按钮内容水平/垂直居中。前者修正已在既有候选，本轮补齐后者；构建检查不代表真实主题和显示比例已验收。

2026-11-18 源码新增日常草稿检查点和系统会话结束入口：每两秒读取一次已恢复页面的登记字段，内容变化时在后台串行保存；未变化时不重复写盘。后台只接收已经序列化的快照，不读取界面控件。损坏原文件仍保留；普通写入失败显示独立的「工作台草稿未能保存」提示，后续成功后关闭提示，不被控制面连接提示覆盖。此变更已有独立检查和构建，尚未进入既有6d5279845a23目录包/cfa638b65fa8安装候选。

Windows 关机/注销查询立即同意；用户取消注销时继续正常编辑和保存。收到确认结束消息后，捕获下文登记字段和已注册的独立草稿，并最多等待后台写入两秒，不弹出关闭选择、不调用需要等待网络的页面保存回调、不额外发送停止任务请求。超时或失败不算保存成功，恢复基线仍是最后成功的检查点。定时器可能受界面忙碌影响；此机制不能保证突然断电或系统立即终止前的最后一次编辑落盘。结果图已接入；后处理详细工作区及尚未确认的模态编辑，其完整崩溃草稿恢复尚待补齐。实现及边界见 [ADR 0017](../submitter/adr/0017-periodic-drafts-and-system-session-end.md)。

F027 在八页共用的顶部显示非阻塞作业提醒，未读可恢复；点击仅定位同一次执行，相同轮询不重建列表。保存确认后才标为已读，任务栏提示不抢焦点。具体使用及原生验收边界见 [提醒说明](JOB_NOTIFICATIONS.md)。

窗口关闭按钮与「文件 → 退出」统一进入关闭流程，重复点击共用同一次处理。先暂停页面轮询并保存编辑内容，等待当前提交、设置保存、结果文件清理和图编辑保存；保存失败则保留窗口、恢复交互并显示原因。结果图无效、修订冲突、草稿原文件损坏或操作未在等待期限内结束，均不会静默丢弃后退出。

准备关闭会检查九类后台工作及待保存的作业提醒：本机队列与作业、后处理、兼容性检查、索引、远端传输/作业，以及批量结果、单步合并和升级。任务终态后的线程保存/清理仍计为活动。准备期间暂停新 POST 请求，并等待已接收的同步请求结束；60 秒准备租约由窗口续期，取消或窗口失联到期后恢复操作入口。

- **后台继续**：关闭窗口，保留原后台、队列调度和任务，不发送隐式取消。重新打开连接同一后台；计算资源页会接回活动文件传输进度。
- **停止任务并关闭**：停止调度，向管理器请求停止，等线程保存和清理完成后由后台自行退出。清理等待最多 60 秒；超时或错误保留窗口。用户取消关闭不能撤回已经发出的停止请求。
- **取消关闭**：释放准备状态，恢复界面与轮询。没有选择停止时，不取消任务。

无活动任务时直接提交空闲退出。后台不可达或旧版不支持协议时，仅在编辑内容已保存后提供「保留后台并关闭」选择。提交回执丢失只查询原实例，不重发停止、不启动另一后台解释旧决定、不按进程名称强杀。实现与兼容边界见 [ADR 0009](../submitter/adr/0009-reversible-workbench-close.md)；旧主机释放逻辑继续使用 [ADR 0008](../submitter/adr/0008-all-worker-shutdown-fence.md) 的保护。

草稿文件为 `%LOCALAPPDATA%/AbaqusTools/workbench-session.json`。保存最近页面、正常窗口位置/尺寸、最大化状态、新建作业输入、队列目录/过滤/下一次调度参数、合并输入/选项、后处理目录和结果浏览目录/内部结果开关。原始输入字符串可保留未完成文本；实际 WinUI 数字控件失焦处理仍须原生验收。后处理详细参数继续用既有工作区，结果图用后台保存接口。运行状态、密码与令牌不写入草稿。保存使用同目录临时文件后替换；损坏/未知版本原文件不覆盖，关闭报错提示其路径。后台进程崩溃/机器重启后的所有任务持久恢复不在此功能承诺范围。

八页输入绑定与纯存储、正式 C# HTTP 关闭选择、自有辅助进程保留和断连处理已有测试；真实业务页关闭/取消/重开、跨屏位置恢复与真实 SSH 仍待验收。队列轮询现在保留用户改过的并行数/同名结果策略，避免恢复草稿后立即被后台快照覆盖。

## 作业概览运行日志（F005）

入口为 `winui/AbaqusTools.WinUI/Pages/JobOverviewPage.xaml` 和 `winui/AbaqusTools.WinUI/Pages/JobOverviewPage.xaml.cs`。轮询仍为 1.5 秒，来源为本地运行快照与远端作业快照；不修改求解器或日志文件。

`winui/AbaqusTools.WinUI/Services/RuntimeLogUpdateState.cs` 的 `SetSnapshot` / `Flush` 管理显示快照：

- 同作业文本未变化时不重新赋值，避免清除选区。
- 鼠标拖选中或仍有文字被选中时保留当前文本，只保存最新完整快照；新日志到达显示“有新日志，取消文字选择后显示”。松开鼠标而文字仍选中时不会替换文本，可以继续复制。
- 取消选择后应用最新快照一次；包括日志尾窗裁剪及状态前缀改变，不拼接已经被来源裁剪的旧行。
- 用户切换作业时清除旧选区和旧待更新快照，显示新作业。相同文本但不同作业也重新建立阅读位置。
- 同作业更新时保留水平和垂直滚动偏移；原先位于底部时跟随新内容，阅读上方内容时不主动跳到底部。窗口裁剪后不保证旧行的语义位置仍存在。

普通轮询读取等待结束后的当前作业选择；程序更新下拉框的事件与用户选择分开。页面卸载后旧轮询不得回写。暂停/终止的失败提示有独立动作归属，不能被下一轮普通轮询吞掉；文件下载回调只更新所属页面和作业，切换页面不取消已经发起的下载。

测试入口：`tests/winui_logs/RuntimeLog.Tests.csproj`。其 9 项行为检查直接链接生产状态类，覆盖选中、新日志、中文日志裁剪、拖选起点、多次快照合并、作业切换、相同文本不同作业、快照恢复和底部跟随判定。它不代替 WinUI 原生鼠标、右键复制或滚动布局验收。

## 数字步进与参数说明（F025）

用户最终选择右侧并排的下/上折线箭头、数字居中。原有 16 处输入及 GPU 编辑区两个入口统一使用 `winui/AbaqusTools.WinUI/Controls/WorkbenchNumberBox.cs`，常驻 Inline，不使用 Compact 或 Hidden。修复前为 8 Hidden、5 Compact、2 Inline；后续发现只改原生模板图标仍与预览不同，现已通过 `winui/AbaqusTools.WinUI/Controls/WorkbenchNumberBoxResources.xaml` 统一完整外观。模板保留原生命名部件和状态，数值逻辑不重写。

| 文件 | 控件 | 修复前模式 |
|---|---|---|
| `winui/AbaqusTools.WinUI/Pages/NewJobPage.xaml` | CPU；最大并行 | Hidden；Compact |
| `winui/AbaqusTools.WinUI/Pages/JobQueuePage.xaml` | 队列并行上限 | Compact |
| `winui/AbaqusTools.WinUI/Pages/JobQueuePage.xaml.cs` | 编辑作业 Core、优先级 | Inline × 2 |
| `winui/AbaqusTools.WinUI/Pages/ComputeResourcesPage.xaml.cs` | SSH 端口 | Compact |
| `winui/AbaqusTools.WinUI/Pages/OdbPostprocessingPage.xaml` | 后处理并行、预期纵筋数、帧率、GIF 单轮时长、宽、高、容差 | Hidden × 6，单轮时长为新增 |
| `winui/AbaqusTools.WinUI/Pages/OdbPostprocessingPage.xaml.cs` | 钢筋直径、断裂前帧 | Compact × 2 |
| `winui/AbaqusTools.WinUI/Pages/OdbPostprocessingPage.StructureBrowser.cs` | 统一参考截面积 | Hidden |

NumberBox 继续负责解析、验证、步进、自动化和上下限，保留 0/−1 的自动值语义、参考截面积空值（NaN，使用 ODB 面积）、容差 0.0001 步长与 `winui/AbaqusTools.WinUI/Controls/PlainDecimalFormatter.cs`、运行期 CPU 上限及毫米/像素范围切换。输入最小宽度 160 DIP，数字居中，减少在左、增加在右；输入框高度 40 DIP、两个按钮各 40 DIP，共用 5 DIP 圆角边框，按钮间有竖分隔线。按钮同步禁用状态和上下限，点击前提交正在编辑的文字。

`tests/winui/test_shell_contract.py` 已移除旧 Hidden/Compact 契约。`tests/winui_numberbox/NumberBox.Tests.csproj` 在自身离屏 WinUI 窗口加载实际生产控件，检查原生步进、未提交文字、动态 CPU 限制、0/−1、空值、分数面积和 0.0001 小数；实际检查数和最新外观验证见任务记录。图例范围、内存和切面表达式仍是 TextBox，不自动改为普通步进数值。

`winui/AbaqusTools.WinUI/Controls/ParameterHelpButton.cs` 在参数标签旁提供 14 DIP 问号，保留最小 28 DIP 悬停/点击区域。`winui/AbaqusTools.WinUI/Services/ParameterHelpText.cs` 原有数字输入提供 13 类说明，新增 GPU/计算精度/场输出精度三类说明。悬停 180 ms 打开；停留在按钮或整个提示区（含内边距）时保持；离开两者 240 ms 后关闭，避免跨越间隙时闪退。不显示“知道了”按钮。点击和 Enter 仍可打开，Escape 可关闭；键盘打开时不因鼠标不在附近而立即消失。提示正文可选取；无重复原生 ToolTip。卸载页面清理计时器，修改说明时重置旧弹层状态，自动关闭动画中重新进入可恢复，显式 Escape 不自动重开。

参数语义与当前源码保持一致：CPU=0 是不传 cpus 参数（Abaqus 默认值），不是全部 CPU；预期纵筋数只作核对；纵筋切面容差判断穿越/端点归属，不是切片厚度或实体积分精度；参考面积留空按单元读 ODB，手动填值覆盖选中桁架面积；钢筋直径只在缺少面积时回退；断裂前帧手动值为跨分析步拼接的总序号；毫米图片尺寸不保证固定印刷 DPI；队列优先级标记不等于当前本机调度自动按数值排序。

## 表单布局与导航提示

新建作业“执行环境与资源”使用两等宽列，各列共用 108 DIP 标签宽度和 10 DIP 标签间距，列间隔 28 DIP。命令、内存、CPU、优先级的输入高度统一为 40 DIP，优先级和单位下拉框占满各自列宽。可用表单宽度低于 720 DIP 时第二列换到下一行。CPU 提示按钮在文字右侧，与标签成组，不占用输入区。

主窗口 `winui/AbaqusTools.WinUI/MainWindow.xaml` 的 ShellNavigation 设置 KeyboardAcceleratorPlacementMode=Hidden。Ctrl+7/Ctrl+8 仍绑定后处理与结果浏览；仅关闭附着在整个导航容器的自动快捷键提示，防止在其子页面表格或空白区域冒出裸 Ctrl+7。该设置由本机 SDK API 文档确认，不删除快捷键或其他业务 ToolTip。

队列工具栏的文字、问号、同名结果下拉框与并行输入统一垂直居中，下拉框与数字框同为 40 DIP 高。

结果浏览“读取目录”按钮（F021）的加载圆环只在读取过程中显示；空闲时使用 Collapsed 释放占位，文字在按钮中水平、垂直居中。加载圆环跟随按钮 Foreground，避免浅色主题强调按钮上颜色不清楚。失败、取消或读取结束均通过既有状态刷新回到空闲布局。

## 最小窗口尺寸（F001）

`winui/AbaqusTools.WinUI/Services/WindowLayoutConstraints.cs` 计算客户区最小宽度：max(8×118 导航宽，280 目录+48 页面边距+600/310 资源列+12 列间隔，280+48+34 卡片边距+108 标签+10 间距+160 数字框)=1250 DIP。高度保留固定壳层和两个队列的可用视口，每卡片保留三行控制、一行表头及一行数据；默认客户区下限 690 DIP，不把全部可滚动内容高度当作窗口下限。

`winui/AbaqusTools.WinUI/MainWindow.xaml.cs` 使用 GetDpiForWindow/96 转物理像素，加入正常态 Size−ClientSize 测得的非客户区尺寸，向上取整后逐维限制到当前显示器 WorkArea。通过 OverlappedPresenter.PreferredMinimumWidth/Height 约束，不替换 presenter，不禁止缩放/最大化/最小化；启动或恢复态小于下限时扩大，跨显示器/缩放变化时重算，关闭时解除事件。标题栏物理 Insets 同步转 DIP。小屏高 DPI 下优先保证窗口不会大于工作区，此时宽表/固定页面是否仍需滚动另作原生验收。

`tests/winui_layout/WindowLayout.Tests.csproj` 直接测试生产尺寸计算，覆盖 100%/125%/150%/200% 缩放、独立工作区裁剪、启动钳制、有效尺寸保持、输入校验与源码布局约束。构建或独立检查不代替跨显示器拖动、窗口恢复和实际业务页视觉验收。

## GPU 与精度编辑区（F028）

新建作业与正式队列编辑共用 `winui/AbaqusTools.WinUI/Controls/ExecutionOptionsEditor.cs`，位于可展开区域。标签、问号与右侧输入按固定标签列对齐；GPU 采用相同 WorkbenchNumberBox 模板。队列长表单增加滚动容器，保存前校验失败保留对话框及当前输入。新建作业的原始数字文本与选项由 WorkbenchSession 登记保存；无效自定义草稿保留原字符串，只有明确恢复默认后才允许替换。语义和实际证据见 [提交选项说明](EXECUTION_OPTIONS.md)，原有 35 项控件自身原生证据不覆盖新增业务编辑区。
