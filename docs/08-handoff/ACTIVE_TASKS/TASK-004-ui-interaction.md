# TASK-004：日志选区稳定与数字输入样式

当前完整5497f45cfec3已以另一独立profile实际打开：187916/185836/210388，CUA窗口18423702。结果页4范围和后台连接正常，按钮已离开标题菜单区；Ctrl+B与fresh AX后Raise均激活失败，等待用户确认新窗口间距及收起/展开，未声称视觉通过。旧205808仍在但不再阻挡新实例，两个窗口后续分别正常关闭核验。详见TASK-002顶部及`GPTWork/native-density-release-20261118/result-browser/native-observations.json`。

最新版已进入干净758f1cc完整目录5497f45cfec3及正式标识安装候选b4ca03cbe0c8；清单、包内依赖和隔离安装生命周期7818c66a5988通过。布局仍待实际新窗口确认，旧205808无法激活，已请用户关闭；精确产物、进程及续接脚本见TASK-002顶部。

## 2026-11-18 · 顶部24 DIP留白、八页密度与侧栏按钮位置

用户在实际窗口反馈导航上方空白过大、整体稍松，要求适度紧凑，并授权选择侧栏按钮及收起后的内容方案。最终将按钮从标题菜单移到浏览器右上角，30 DIP按钮使用折线图标；收起保留40 DIP入口，原有页面上下文与草稿规则保持。八页边距统一20/16/20/20，卡片12，主要分组10，字体及输入按钮高度不缩小。窗口下限按此重算为展开1242、收起1002、默认高664 DIP。

第一次仅设置IsTitleBarAutoPaddingEnabled=False，用户指出空白仍在；继续定位到MainWindow三条关闭InfoBar各8 DIP外边距，实际共24 DIP。新增InfoBarLayout.Track把关闭提示和结果页提示容器真正Collapsed。原生自身窗口复现24 DIP、修复后0、重新打开仍可见、最后关闭再次0，连同既有选择刷新9项共13项通过，177532退出0；回执`GPTWork/density-control-checks-20261118/verification.json`及process.json。此为原生控件几何证明，不替代整页截图与鼠标验收。

最终发布构建成功：`GPTWork/winui-density-sidebar-20261118`，日志`GPTWork/winui-density-sidebar-publish-20261118.log`。16项尺寸通过`GPTWork/density-layout-final-20261118.log`；39项shell/结果API通过3.26秒，`GPTWork/density-regression-final-20261118.log`。失败记录保留：初次尺寸命令误写Layout.Tests.csproj，正确名称WindowLayout.Tests.csproj；随后--no-restore缺assets，缓存还原后发现一处测试旧706期望漏改，改为680后通过。生产计算未靠放宽断言规避问题。

先前干净6d45342目录cb9a79ed69bd/正式安装器46444abe6d77/测试安装器2a9ce6ea95e4已生成，清单1687、worker19、应用资源15。原生44576/后台221940/子219336启动结果页4范围并正常结束，日常JSON未改；这些包尚不含随后用户要求的密度调整，未完成新安装生命周期，保留追溯、不作为本轮最终候选。`GPTWork/explorer-release-verification-20261118/inventory.json`与`GPTWork/native-explorer-release-20261118/result-browser/verification.json`。

准确续接点：旧密度试窗205808/后台213728/子166276，窗口1573058，已记录身份于`GPTWork/native-density-20261118/result-browser/processes.json`。CUA截图超时；两次重新观察后Alt+F4激活失败，未强杀，已请用户关闭再打开修正版。发布输出winui-density-sidebar已编译但未打开；待关闭确认后检查旧进程、启动独立新配置、检查实际侧栏及提示，再打干净完整候选和安装生命周期。没有新增求解或ODB复制。

2026-11-18最新：用户确认并经CUA核对，修复后模型选择/CSV前50行3列预览正常；实际导出80行/1408字节且与源摘要一致，随后窗口/后台正常结束。原198808不再活跃，详细证据见[TASK-002](TASK-002-migration.md)顶部。这只覆盖单份小CSV，取消/部分失败/回收站和八页完整交互仍待。

## 2026-11-18 · 结果选择递归崩溃

原保留结果窗口70244实际栈溢出退出，旧“窗口仍活跃”等待记录已被本段更新。侧栏恢复选区反复通知结果页读取，现已延期合并快照、屏蔽程序恢复时的业务回调、同选区去重并在移除前清选。直接加载生产侧栏的9项原生控件检查退出0，39项相关回归、结果生命周期/预览通过；源码定位见F002/F021，完整失败与恢复记录见[TASK-002](TASK-002-migration.md)顶部。

旧后台已通过idle协议正常关闭，修复开发输出winui-explorer-fixed-20261118已打开独立结果窗口198808/后台51160，等待用户在“模型甲”选择CSV确认，仍未原生预览/导出。新窗口有4范围读入证据；旧d4fc4c7完整安装候选尚含已知崩溃，不得称完整可用。

## 2026-11-18 · 侧栏收起、输入保留与同配置恢复

补齐F001/F002：标题栏“侧栏”按钮及Ctrl+B切换，隐藏原浏览器并释放列宽，不重建页面；旧配置默认显示，关闭/日常草稿保存显示偏好，新建动作保留。客户区最小宽按显示/隐藏取1250/970 DIP，重显仅扩大不足维度。54项相关回归、16项尺寸检查通过。

开发输出 `GPTWork/winui-sidebar-20261118` 实际新建页：初始隐藏/CPU4，Ctrl+B显示后原名/CPU4保留，输入6再隐藏仍保留；正常关闭后同一profile重开观察隐藏/原名/CPU6。两次原生、后台、子进程均正常结束，日常配置摘要未变化。回执 `GPTWork/native-sidebar-20261118/{first,restored}/verification.json`；准确命令、一次旧快捷键断言失败及过程归属见[TASK-002](TASK-002-migration.md)顶部。鼠标按钮、视觉和跨屏仍待，不能将这次键盘验收扩展到所有页面/后台忙碌操作。完整安装候选尚未纳入侧栏改动。

2026-11-18 续验：干净d4fc4c7完整包的资源/合并两个窗口实际首次加载与正常退出通过；结果浏览交互仍受工具鼠标定位/焦点观察限制。已保留独立CSV测试窗口供用户确认，原生70244/后台33100仍活跃；不是用户求解窗口，不应重复启动或自动关闭。准确回执、状态和待答问题见[TASK-002](TASK-002-migration.md)顶部。

## 2026-11-18 · 首次加载缺陷复核补充

已用07ccd1e06113真实窗口检查队列、概览、资源、重启动链和合并。队列并行上限1→2且关闭后保存；概览和链空状态正常。发现资源页首次恢复报“主窗口尚未创建”、合并图初次读取被后台恢复锁跳过，均已从初始化顺序修复。修复发布输出winui-firstload-fixed-20261118实际复核资源无误报、图自动读取/目录可编辑并在正常关闭时保存；新建名称/CPU=4、Ctrl+7/8也复核通过。81项相关检查通过，所有本轮自有窗口/后台已正常结束。准确PID、命令、产物和未验范围见[TASK-002](TASK-002-migration.md)顶部；这仍不是日志拖选、鼠标悬停或视觉布局验收。下方“三页”及129b257说明是前期阶段记录。

## 2026-11-18 最新原生进展

用户明确“允许恢复桌面验收”，并确认窗口可见；历史 Esc 暂停已解除。本轮使用 G: 独立配置，实际编辑名称/CPU、正常关闭重开和目录选择器/读取。发现并修复 CPU=4 重开被初始上限 1 裁剪；修复后原生显示和最终 JSON 均为 4。新建页常驻开发说明已移除；结果浏览/后处理空目录不再因自动刷新先报错，主动操作仍校验。

新建、结果浏览、后处理三个页面有范围有限的无障碍树/键盘证据；Ctrl+7/8 切页、GIF 帧率 25→30 输入、结果目录恢复和空闲正常退出已观察。未验帧率工作区持久化、记录预览/导出或全部八页。截图超时、坐标几何不可用、Windows 选文接口不可用，布局/鼠标/日志选区不能认定通过。

最终开发入口 `GPTWork/winui-native-startup-final-20261118/AbaqusTools.WinUI.exe`，构建 0 警告/错误；72 项相关回归通过，最后后处理空目录追加检查及精确回执见 [TASK-002](TASK-002-migration.md) 顶部。最终可见窗口 PID 168436、后台 219640 及其自有子进程均已结束、描述符已移除；`GPTWork/native-acceptance-20261118-a/verification-final.json` 记录部分原生通过和工具限制。普通工具启动未发现窗口的实例单独清理，不计正常退出证据。日常两份配置 JSON 摘要不变，没有创建/移动 ODB 或启动求解。

准确续接点：已具备独立配置和可见桌面启动方式，继续解决截图/鼠标定位，再按下方原要求验日志拖选、提示悬停、数值外观、资源/队列对齐、最小窗口和跨屏。129b257 完整包尚不含本轮修复。下方候选/PID/未授权语句保留为历史记录，不能据此重复启动或拒绝本轮授权。

## 先前控件与布局记录

2026-11-18补充：用户所示「读取目录」左侧是加载圆环，既有ResultBrowser已在空闲时Collapsed释放占位、忙碌时随按钮Foreground显示并居中。本轮核对发现后处理「发现 ODB」仍有相同占位，已统一修正XAML与SetDiscoveryBusy；WinUI构建0警告/错误（GPTWork/postprocess-draft-build-20261118-03.log）。没有开展原生视觉操作；真实主题/缩放和实际按钮渲染仍待验收。恢复草稿实现与最终回归见[TASK-002](TASK-002-migration.md)顶部。

状态：日志修复、15 处常驻数字步进/参数说明、完整预览外观、表单对齐、快捷键悬浮误提示和最小窗口限制已实现，最新构建通过。数字原生控件 35 项、窗口计算 13 项通过；真实业务页交互待验证。

## 用户要求与范围

2026-10-28 在结果提取恢复之后追加：作业概览日志刷新不能取消文字选择；恢复数字输入增减按钮，不使用 WinUI Compact。用户最终选择右侧并排下/上折线、数字居中，并要求难懂参数有说明。说明最终要求为悬停打开、在按钮或提示区停留时保持、离开自动消失，不需要“知道了”按钮，问号要小。用户认可预览但指出实际软件不一致，因此继续统一实际外观。截图又确认新建作业资源区固定宽度挤左、队列工具栏垂直未对齐、主界面空白区出现 Ctrl+7，以及没有最小窗口尺寸限制。

## 实际修改

- `winui/AbaqusTools.WinUI/Pages/JobOverviewPage.xaml.cs` 接入日志更新状态，拖选/选中冻结、相同文本去重、清选后合并刷新；保存滚动偏移和底部跟随。
- `winui/AbaqusTools.WinUI/Pages/JobOverviewPage.xaml` 增加待更新提示。
- `winui/AbaqusTools.WinUI/Services/RuntimeLogUpdateState.cs` 负责按作业合并完整快照，切换作业清空旧快照。
- 修正轮询等待时切换作业被旧选择覆盖；动作失败显示和下载回调加所属页面/作业条件。
- 新增 `tests/winui_logs/RuntimeLog.Tests.csproj`、`tests/winui_logs/Program.cs`，直接测试生产状态类。
- 15 处数字输入改为 `winui/AbaqusTools.WinUI/Controls/WorkbenchNumberBox.cs`，最小宽度 160 DIP、常驻下/上箭头、数值居中；原生 NumberBox 继续负责值解析和步进。第一阶段只调整局部，用户发现与预览不一致，现由 `winui/AbaqusTools.WinUI/Controls/WorkbenchNumberBoxResources.xaml` 统一完整模板，保持命名部件和原生启禁状态。40 DIP 高、两个 40 DIP 按钮、竖分隔线、5 DIP 圆角；主题切换时使用常驻主题画刷层和状态透明度，避免 hover 状态固化旧主题颜色。详细清单与语义见 [交互说明](../../03-features/UI_INTERACTION.md)。
- `winui/AbaqusTools.WinUI/Controls/ParameterHelpButton.cs` 与 `winui/AbaqusTools.WinUI/Services/ParameterHelpText.cs` 接入 15 处输入的 12 类说明。14 DIP 小圆问号保留 28 DIP 热区，悬停 180 ms 打开、离开按钮及整个弹层 240 ms 关闭，支持选文、点击/键盘和 Esc；移除预览的“知道了”，生产弹层无确认按钮。修复更换说明时旧弹层状态与自动关闭动画中重新进入的竞态。
- `winui/AbaqusTools.WinUI/Pages/NewJobPage.xaml` 的资源区改为两等宽列，每列标签宽 108 DIP；宽度不足 720 DIP 时换成单列。输入高度统一 40 DIP，单位/优先级下拉框伸展填满列，CPU 问号归于标签组。
- `winui/AbaqusTools.WinUI/MainWindow.xaml` 在 ShellNavigation 关闭自动 KeyboardAccelerator 提示，保留 Ctrl+7/Ctrl+8 绑定。本机 SDK XML 明确该属性只影响提示显示。用户截图中表格附近的裸 Ctrl+7 来自包住全部页面的导航容器。
- `winui/AbaqusTools.WinUI/Pages/JobQueuePage.xaml` 将设置行、说明按钮与数字框统一垂直居中，同名结果下拉框高度 40 DIP。
- `winui/AbaqusTools.WinUI/Services/WindowLayoutConstraints.cs` 与 `winui/AbaqusTools.WinUI/MainWindow.xaml.cs` 根据源码约束计算客户区最小宽 1250 DIP、默认高 690 DIP；公式见交互说明。实际正常态非客户区和 GetDpiForWindow 加入外框物理尺寸，逐维 cap 到当前显示器 WorkArea。AppWindow 与 XamlRoot 变化时重算，关闭解除订阅；只在恢复态主动扩大过小窗口，不改变最大化/最小化/缩放能力。低分辨率高 DPI 触发 cap 后的宽表布局仍待原生检查。

## 本次实际验证

1. `dotnet run --project tests/winui_logs/RuntimeLog.Tests.csproj --artifacts-path GPTWork/build-runtime-log-tests --no-restore`：9 项通过。
2. 第一阶段 shell 契约 33 passed；较早文档+旧 shell 共 61 passed。使用项目 `.venv`，这些是阶段结果，最终回归待记录。
3. 第一阶段原生数字控件自测 18 项通过，进程 exit 0；收据 GPTWork/winui-numberbox-native-checks/verification.json。实际加载自身离屏 WinUI 窗口和生产控件，通过原生 RepeatButton 自动化对等体触发步进，覆盖未聚焦按钮、顺序、居中、输入提交、动态 CPU 限制、0/−1、空面积 NaN、分数面积、容差 0.0001。没有操作业务软件窗口。
4. 阶段构建 GPTWork/ui-interaction-restored-20261028：0 warnings / 0 errors，8.59 秒，包含此前结果提取恢复、日志修复、数字居中和悬停说明。此版本尚未包含后续统一外观、小圆问号、表单/窗口反馈，不是本轮最终版本。
5. 预览第一版三种布局实际点过整数及 0.0001 小数增减；第一种折线布局在约 320 像素窄视口查看过截图。说明最初点击打开/关闭也实际检查过。后改悬停、去确认按钮、缩小问号的版本尚未再次做鼠标视觉验收；预览仅示例数值，不连接或修改项目配置。
6. `dotnet run --project tests/winui_layout/WindowLayout.Tests.csproj --artifacts-path GPTWork/build-window-layout-tests`：13 项通过，直接测试生产尺寸计算与源码尺寸；加 `--no-build -- --verify-failure-exit` 按预期 exit 1，检查失败不会伪装为通过。1250/690 是源码约束与保留有效视口的设计计算，并非业务页运行时全面量测。
7. 最新数字控件 35 项通过、进程 exit 0：GPTWork/winui-numberbox-preview-checks/verification-preview-matched.json 与 .exit.txt。包含全部旧语义及完整几何、主题、占位、Header、UIA/焦点；新模板空白/有值正常 Window.Close 的 2 项对照与 stock NumberBox 的 3 项对照均 exit 0。
8. 最终构建命令：`dotnet build winui/AbaqusTools.WinUI/AbaqusTools.WinUI.csproj -c Debug --no-restore -p:OutputPath=G:/PythonProject/abaqusTool/GPTWork/ui-interaction-preview-matched-20261028/ -p:OutDir=G:/PythonProject/abaqusTool/GPTWork/ui-interaction-preview-matched-20261028/`：0 warnings / 0 errors，11.86 秒。构建后生产模板未再修改，最新业务 app 未自动启动。
9. 最终项目 `.venv` 验证：`pytest tests/common/test_documentation_navigation.py -q --basetemp=GPTWork/pytest-docs`：29 passed；`pytest tests/winui/test_shell_contract.py -q --basetemp=GPTWork/pytest-ui-preview-shell-final`：33 passed。包括新功能索引/文档路径、两列资源布局和 Ctrl+7/Ctrl+8 绑定保留。相关文件 git diff --check 无空白错误，仅本机 LF/CRLF 提醒。

最新控件测试沿用下方构建命令的本地包缓存和中间目录，将 OutputPath/OutDir 改为 GPTWork/winui-numberbox-preview-checks，运行同目录 WorkbenchNumberBox.ControlChecks.exe，参数为该目录 verification-preview-matched.json。测试曾在完成断言后的退出阶段出现 C0000005，保留 verification-before-teardown-fix.json/.exit.txt；修复测试清理顺序（移除自身树、等待 UI 队列、释放内容、正常退出）后 exit 0，未强制退出。只加载新模板后直接正常关窗的对照也 exit 0。所有自身测试进程已确认结束。

原生控件阶段验证复现（仅自身测试窗口）：

```powershell
dotnet build tests/winui_numberbox/NumberBox.Tests.csproj -c Debug -p:NuGetAudit=false -p:RestorePackagesPath=C:/Users/Chiw/.nuget/packages -p:RestoreSources=C:/Users/Chiw/.nuget/packages -p:BaseIntermediateOutputPath=G:/PythonProject/abaqusTool/GPTWork/winui-numberbox-tests-obj/ -p:OutputPath=G:/PythonProject/abaqusTool/GPTWork/winui-numberbox-native-checks/ -p:OutDir=G:/PythonProject/abaqusTool/GPTWork/winui-numberbox-native-checks/
$verificationProcess = Start-Process -FilePath G:\PythonProject\abaqusTool\GPTWork\winui-numberbox-native-checks\WorkbenchNumberBox.ControlChecks.exe -ArgumentList G:\PythonProject\abaqusTool\GPTWork\winui-numberbox-native-checks\verification.json -WindowStyle Hidden -PassThru
if (!$verificationProcess.WaitForExit(20000)) { Write-Output "Still running own test process: $($verificationProcess.Id)" } else { Write-Output "Exit code: $($verificationProcess.ExitCode)" }
```

首次在默认中间目录执行 C# 测试且加 --no-restore，出现 NETSDK1004（默认 obj 缺 assets），没有测试执行。沿用此前成功的 GPTWork artifacts 路径后 9 项通过，未安装/混用环境。

未完成本轮业务页 WinUI 原生拖选、右键/键盘复制、滚动、远端下载、悬停与窗口尺寸实测；这些不从构建、源码或独立控件测试推定通过。曾启动本轮阶段候选，首次工具报告未及时发现窗口，随后只读确认原进程已出现，没有再次启动。用户按 Esc 停止 Computer Use，后续停止桌面/浏览器 UI 操作。原始模型、用户求解进程和旧软件窗口未改动，没有提交或推送。

## 准确续接点

1. 最新候选 GPTWork/ui-interaction-preview-matched-20261028/AbaqusTools.WinUI.exe 已构建，构建会话 84368 正常退出，未启动最新业务窗口。阶段 restored 候选最后确认 PID 51216、窗口 1923520，未确认已退出，不擅自关闭或重复启动。
2. 已完成独立控件与尺寸计算检查，最终文档导航/shell 契约结果见本记录。无需重跑真实 ODB 提取；真实业务页仍待用户允许的交互验收。仅工作区改变而窗口完全无事件时，窗口限制在下次位置/大小/XamlRoot 事件更新，未增加后台显示器监听。
3. 后续业务页验收：日志选中多行跨两个轮询并复制、新日志取消选择追赶、切换作业/页面及上滚；提示按钮到弹层/离开/键盘关闭；数字外观与预览一致；资源表单对齐/窄屏换行；队列工具栏垂直对齐；Ctrl+7 不再无端悬浮；窗口缩小与高 DPI。不要启动求解来代替验收。
4. 预览服务 http://127.0.0.1:61242/ 当前本轮 exec 会话 55572，已为用户保留；它是预览，不是生产控制面。源为当前线程可视化目录中的 number-input-help.html。缩小问号后已重启该已知服务，原浏览器页需刷新；下次先检查服务是否仍在，不重复占用端口。
