# 运行日志阅读与数字输入交互

更新：2026-10-28。关联 F005、F025，以及数字输入涉及的 F003/F004/F007/F008/F022。任务状态见 [TASK-004](../08-handoff/ACTIVE_TASKS/TASK-004-ui-interaction.md)。

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

用户最终选择右侧并排的下/上折线箭头、数字居中。16 处输入统一使用 `winui/AbaqusTools.WinUI/Controls/WorkbenchNumberBox.cs`，常驻 Inline，不使用 Compact 或 Hidden。修复前为 8 Hidden、5 Compact、2 Inline；后续发现只改原生模板图标仍与预览不同，现已通过 `winui/AbaqusTools.WinUI/Controls/WorkbenchNumberBoxResources.xaml` 统一完整外观。模板保留原生命名部件和状态，数值逻辑不重写。

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

`winui/AbaqusTools.WinUI/Controls/ParameterHelpButton.cs` 在参数标签旁提供 14 DIP 问号，保留最小 28 DIP 悬停/点击区域。`winui/AbaqusTools.WinUI/Services/ParameterHelpText.cs` 为 16 处数字输入提供 13 类说明。悬停 180 ms 打开；停留在按钮或整个提示区（含内边距）时保持；离开两者 240 ms 后关闭，避免跨越间隙时闪退。不显示“知道了”按钮。点击和 Enter 仍可打开，Escape 可关闭；键盘打开时不因鼠标不在附近而立即消失。提示正文可选取；无重复原生 ToolTip。卸载页面清理计时器，修改说明时重置旧弹层状态，自动关闭动画中重新进入可恢复，显式 Escape 不自动重开。

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
