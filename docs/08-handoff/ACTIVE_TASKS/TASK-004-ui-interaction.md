# TASK-004：日志选区稳定与数字输入样式

## 作业概览在远端记录写入期间更新本机日志（F005/F010）

用 G 盘隔离后台的真实 HTTP 撤回请求，在远端记录保存期间暂停。以相同脚本比较，旧版自动读远端列表等了 2893.6 毫秒，新版在 2.1 毫秒返回“正在更新”。同时读取本机状态分别用了 1.1 和 2.4 毫秒。两版手动读均等待提交后取得完整列表，用时分别为 2893.7 和 3017.1 毫秒。该测量只涵盖本地后台的锁竞争。前后回执为 `GPTWork/overview-lock-20261128/before.json` 和同目录 `after-repeat.json`。

WinUI 作业概览从没有远端缓存开始，在记录锁仍被持有时，137 毫秒内显示本机日志。第二次写入时，已有远端作业、日志文字及四字选区都保留。切回本机后能看见新日志；手动刷新期间切页，旧响应也没有改写已离开的页面。实窗测试使用生产页面和隔离的替代启动程序，未启动 Abaqus 求解。回执为 `GPTWork/overview-lock-20261128/native1/native.json` 及同目录 `verified.json`。真实远端物理断网与长期求解负载仍需另行核验。[刷新规则](../../03-features/REMOTE_JOBS.md)

## 队列工具栏的浅底增减按钮

正式版 `328ad47`、`cbe221e` 和 `c876875` 均在各自的实际队列窗口截取了 516 × 48 原像素图。三份 PNG 的 SHA-256 均为 `9b370b4de1482e1ea9b2b649ba0e09b0c62eee16449adcdfe1d0d81655776ca1`。96 DPI 下，左右两端热区各为 40 × 38 像素，浅底像素均为 `#EEEEEE`，中央输入区为 `#FEFEFE`。数字 3 的字形中心到输入区中心的水平偏差为 0 像素。当前成品截图与逐像素测量保存在 `GPTWork/native-queue-toolbar-328ad47-20261128/case1/queue-toolbar.png` 及同目录 `verification.json`。实测时使用独立空队列，验收进程均已退出。[工具栏实图](../../repowiki/images/queue-parallel-limit.png)

## 运行中队列的菜单与页面命令

2026-11-28 使用应用提交 `41c104c` 的 WinUI 源码，在单独的窗口副本中加入验收探针并连接该版本的正式冻结后台。G 盘独立配置含三个已入队作业，最大并行为 1。前台通过原生控件打开菜单、导航、确认框及页面按钮，通过已显示的 ListView 选择正式队列行。三个作业均使用有时限的 Windows 测试进程。

15 项检查通过。36 次观察包括 10 组顶栏和页面开始、停止、终止命令的启用状态，另有 11 份实际后台快照。队列页启动 A 后，从作业概览点「作业 → 停止后续调度」，A 保持原执行编号，完成后 B、C 均留在队列。单独暂停 B 后，经文件菜单进入新建作业页，再点作业菜单开始队列，C 取得空闲名额。恢复 B 时，C 仍占用名额。从队列页停止调度，C 正常结束，B 仍然等待。再次点击开始后才派发 B。最终 A、C、B 各完成一次，记录 3 个独立执行编号及 22 条调度事件。

选中运行中的 A 时，从顶栏触发终止会打开标有 A 名称的确认框。此时顶栏和页面均禁用三项命令。点击取消后，A 保留运行状态和选区。该路径验证至取消，实际终止请求未发送。窗口、后台、三个工作进程均已结束，描述符已清理。本轮未启动求解。成功回执在 `GPTWork/native-busy-queue-menu-20261128/case-53718cec` 下的 `verified.json`、`native.json` 和 `scheduler-events.json`。首次验收的选区探针未取得行容器的 SelectionItem 接口，改用真实 ListView 选区后完成。首次运行与清理记录保存在同目录上一级的 `case-ddc18d23/verified.json`。

## SSH 采集期间的菜单与跨页命令

2026-11-28 在私有桌面运行原生 WinUI，使用 `41c104c` 正式冻结后台、两台仅绑定回环地址的 SSH 服务和 G 盘独立配置。已连接 A、界面选中离线 B 时，从新建作业页点击「服务器 → 刷新远端资源」，基线返回计算资源页并停留在 B，提示“连接状态已变化，请核对服务器连接后重试。”连接和身份实际均未变化。约 10 秒后 A 收到页面定时采集。复现和五次原生提示采样分别保存在 `GPTWork/native-busy-ssh-menu-20261128/case-cf4ad760`、`case-a098c651`。

计算资源页进入时先取得连接快照，再确认现有传输。过去菜单在两次检查之间被唤醒，第二项检查正在读取空清单时，页面暂时显示忙碌，跨页命令因此中止。现在菜单等待首次传输清单的结论。查到活动传输时立即返回提示，保留用户主动重试的选择。页面切走时释放该次就绪等待。菜单在核对通过后选择原连接，向后台发送命令时仍携带点击时的目标配置。

修复后的 12 项原生检查通过，含 32 次观察。A 采集期间顶栏和所选 A 的刷新、断开按钮均禁用，切至概览仍禁用，采集返回后恢复。离线 B 的页面按钮依旧禁用。从其他页启动顶栏刷新与断开均选中 A 并作用于 A。在测试副本中暂停进入页后的首次读取，以便取证两个时序：

- 菜单捕获 A 的断开请求后，在 A 上启动真实 SFTP 下载。服务端仍持有读取时，菜单已返回“服务器操作尚未就绪”。放行后 16800 字节下载成功，摘要与原始文件相同，A 保持连接。
- 在相同窗口内改连 B 后，原断开操作提示“连接状态已变化”。B 保持连接，仅收到认证时的一次资源查询。

回执位于 `GPTWork/native-busy-ssh-menu-20261128/fixed-066909cc/verified.json` 和同目录 `native.json`。窗口、正式冻结后台及两台测试服务均正常退出。定向 WinUI、远端命令、传输及响应性 73 项通过，见 `GPTWork/native-busy-ssh-menu-20261128/pytest-transfer.xml`。本次使用回环 SSH 和固定资源采样响应，没有访问业务服务器。[远端操作与采集](../../03-features/REMOTE_JOBS.md)

## 2026-11-28 · 从后处理菜单和 Ctrl+8 打开当前工程结果

旧版 PySide 的「后处理 → 打开结果浏览」会进入当前 ODB 工程的结果目录。WinUI 基线能从页面按钮读入同一目录，但顶栏菜单返回了此前结果浏览器里的未读取路径。已让顶栏命令和 Ctrl+8 根据当前业务页分派。在 ODB 后处理页，两者共用页面按钮的发布目录解析和多目录选择框。其他页面的通用入口、顶部选项卡仍可直接返回之前的浏览位置。

在 G 盘隔离配置和本机发布包控制面上，实点四组原生菜单。冷启动恢复到保存的结果浏览页，文件菜单新建空白作业，作业菜单进入队列且空闲调度状态与页面按钮一致，未连接时服务器菜单进入资源页且刷新、断开均禁用。新旧后处理对照及修复后的回执如下。

- `GPTWork/native-shell-menu-parity-20261128/qt-profile/receipt.json` 记录了旧版实际菜单和目标目录。`baseline-5b6bedd6/receipt.json` 复现 WinUI 同名菜单和按钮产生不同目标。
- 同一验收目录下的 `fixed-d058d922/receipt.json` 和 `fixed-d08e0037/receipt.json` 各通过 14 项。验证单目录、未发现新工程时的提示、已发现空工程的提示、双目录取消后通过菜单或 Ctrl+8 重新选定目标，以及普通标签保留未读取草稿。键盘验证向该测试进程的 WinUI 输入子窗口发送按键，经过已注册的 XAML 加速键。
- `tests/winui/test_shell_contract.py` 新增菜单、Ctrl+8 和页面按钮的接线回归。该回归与文档导航共 53 项通过。合跑整个外壳契约及文档导航时，首轮 103 项通过，并行修改重启动链页面后复测有一项旧标题「提交顺序」断言失败。后处理 C# 的 `--scope-checks` 通过，含发布目录、嵌套路径及已移走输出校验。构建和检查日志在同一验收目录的 `build-fixed.log`、`checks-build.log`、`locations.log`。原生源码摘要与回执核验见 `verification.json`。

重启动页恢复稳定的「提交顺序」标题后，外壳、结果浏览与文档的 141 项定向检查全部通过，见 `GPTWork/index-diagnostics-20261128/final-checked.xml`。本次菜单对照使用目录与文件名夹具，未读取 ODB 内容、启动求解、连接业务服务器或发出远程命令。忙碌服务器和运行中作业命令的验收沿用各自功能记录。

### 数字输入框的成品复核

再次按所选的「布局 2、浅底按钮 3、说明图标 C」核对，原生控件复测 71 项通过。按钮模板摘要为下列同一 SHA-256。此次回执在 `GPTWork/index-diagnostics-20261128/button-combination.json`，工具栏和编辑窗口的实际外观见下方截图。

`1b899eb` 免安装目录内的数字框样式与本次复测的原生控件逐字节一致，SHA-256 为 `58592d0a249a20113f5b31ed152a8778b4fceebdc9a8c46e768374b169732cd1`。原生检查 74 项通过，覆盖左右减加、数值居中、浅色与深色主题的按键底色、悬停、按下与到达边界后变淡。回执为 `GPTWork/sort-resource-qa-20261128/number-control.json`。[作业队列实图](../../repowiki/images/job-queue-toolbar.png)

## 2026-11-28 · 本机作业的 STA 增量与固定表头

旧界面会整理 Standard 的增量行，WinUI 原先仅显示混合运行日志。新增「STA 增量」直接读取所选本机作业对应的状态文件，显示文件名，悬停可核对完整路径。原始日志、格式缺失、文件消失和远端输出的操作见[作业概览说明](../../03-features/UI_INTERACTION.md#作业概览运行日志f005)。

使用 GJB-15、GJB-14 既有 STA 的副本，在 G 盘独立原生页面分段重放。显示的 300 条记录与原文件逐行逐字段匹配，包括未成功尝试的 `1U`。滚动数据前后表头均在 Y=333 DIP。在 385 DIP 宽的视口横移 60 DIP 后，表头和数据均左移 60 DIP。两种视图的选区均能跨追加保持；解除选区、切换作业及返回运行日志后，内容与对应文件一致。最终 10 项实测通过，前台和隔离后台均正常退出，两份原始 STA 的摘要保持一致。回执 `GPTWork/n03-sta-table-20261128/case3/verified.json`，界面抓图为同目录的 `table.png`。

另用 `tests/winui_logs/RuntimeLog.Tests.csproj` 检查原有的 9 项日志行为和文件解析，包括半行追加、Fortran 指数、可选列、不同求解器输出及文件替换；两项概览页面入口检查通过。回执为 `GPTWork/n03-sta-view-20261128/runtime-log-tests.txt` 及同目录的 `shell-tests.txt`。本次为工程日志重放；远程 STA 仍通过文件下载核对。未启动求解。

若同一 STA 在读取期间追加数据，先保留本次已读到的完整行，下一轮再显示新行，避免增量表在繁忙时闪空。五种实际文件并发情形已核对，包括追加、改写后增长、截短、等长改写和替换，回执为 `GPTWork/n03-sta-view-20261128/sta-concurrent-tests.txt`。

## 2026-11-28 · 队列写入期间的原生选区

方案 2 的布局为左减、数值居中、右加，两端使用方案 3 的浅底圆角按钮，说明图标采用 C 款。数字框原生检查 74 项通过。`de319eb`、`c847e05`、`a20e35d` 和 `850f753` 的数字框编译资源逐字节一致，SHA-256 为 `58592d0a249a20113f5b31ed152a8778b4fceebdc9a8c46e768374b169732cd1`。当前免安装包与验收记录见[发布清单](../../05-development/RELEASE.md)。[队列工具栏实图](../../repowiki/images/job-queue-toolbar.png) · [编辑作业实图](../../repowiki/images/job-queue-editor.png)

在隔离原生窗口中，第一次读取本机队列被写入阻挡时，界面显示正在读取，菜单和按钮均不能启动队列。先取得完整数据再持有写锁时，候选行和正式行保持选中。释放锁后同一行显示「运行失败」，两个选区仍在。作业概览在本机待更新时仍能显示远端进度，已选择的日志文本保持。远端观察来自本机回放，7 项检查通过。回执为 `GPTWork/queue-lock-observation-20261128/desktop-024943/native.json`。

## 2026-11-28 · 三台物理显示器的最小窗口

在两台 2560×1440 横屏和一台 1440×2560 竖屏上，实际移动 `3ff3fa2` 的独立原生队列窗口。三台显示器的有效 DPI 均为 96。分别展开和收起侧栏，从正常窗口请求缩小至 600×400，系统分别限制在外框 1258×673 和 1018×673，对应客户区 1242×664 和 1002×664。12 个状态中两张表、正式队列 11 个操作、扫描、菜单、关键输入框及状态栏均在可见边界内。未更改系统缩放比例。跨不同有效 DPI 仍待验证。数据在 `GPTWork/physical-layout-20261128/displays.json`、`native.json`。

## 2026-11-28 · 工程日志重放

用 GJB-15、GJB-14 两个工程已有的 STA / MSG 在 G 盘隔离队列重放。MSG 分别为 8,278,320 和 7,580,141 字节。选中 GJB-15 的三行进度，追加 325 行，使所选文本退出后台最近 300 行的缓冲；经过至少两次轮询后，屏幕上的文本和选区仍一致。取消选区后约 62 ms 显示最新末尾，切换作业可读到 GJB-14 自己的日志。首次载入约 164 ms。6 个源文件摘要前后相同，未启动求解。首次探针因原生换行处理有误失败，修正探针后检查通过，两次回执均保留在 `GPTWork/n03-engineering-20261128`。

另对 77,080 字节的工程 STA 和约 8.28 MB 的 MSG 检查实际读取量。首次采样耗时约 110 ms。文件未变化时，轮询读取 0 字节文件内容。50 次按原记录追加共 3,334 字节，每次还读取 64 KiB 的 STA 末尾以检查结构，单轮耗时中位数约 3.09 ms。测试覆盖工程文件重放，长期在线运行仍待核对。诊断读取回执为 `io.json`，最终原生页面回执为 `native2.json`。

## 2026-11-28 · 右下角通知、队列折叠区和数字键

已核对新版 `850f753` 与以下实窗截图所用的 `c4bbe73`。队列表单与数字框相关源码一致，两包的 `JobQueuePage.xbf` 和 `WorkbenchNumberBoxResources.xbf` 也分别逐字节相同。下图展示的左减右加、浅灰键面及居中数值适用于这两个版本。[浅色工具栏实图](../../repowiki/images/job-queue-toolbar.png) · [编辑作业实图](../../repowiki/images/job-queue-editor.png)。本次深色验证使用生产控件，已检查普通、悬停、按下和禁用状态。

最终免安装版 `c4bbe73` 已在 G 盘独立配置中打开正式队列的 `Formal_003` 编辑框。工具栏和表单均显示左减、居中数值、右加及浅底圆角按钮，右边框、折叠区箭头和保存按钮完整可见。实窗截图与启动记录见 `GPTWork/queue-edit-navigation-20261127/currentFinalC4bbe73`。该窗口已留给用户查看，40 项正式作业均处于暂停调度状态，验收期间未启动求解。另有 5 项新建作业与作业概览的原生交互检查通过，覆盖空草稿、有效命令预览、STA 文件消失以及后台轮询，见 `GPTWork/feedback-notification-menu-20261128/extra/native.json`。

最终发布包和本地免安装启动路径见[发布记录](../../05-development/RELEASE.md)。154 项原生控件检查和两次真实窗口核对的汇总为 `GPTWork/feedback-host-20261128/desktop-verification.json`。结束提醒实测覆盖一次弹出、叉号关闭后保留未读、后台重复轮询、通过作业菜单反复打开及标为已读。三次测量菜单下方导航顶缘均为 38 DIP。12 项实际界面检查及 18 项后台回归见 `GPTWork/feedback-notification-menu-20261128/verification.json`。

上一版固定了队列表单的宽度。继续展开目录和 GPU 两个可选区时仍会重算整个对话框的高度，使居中的窗口跳动。现在在弹窗首次打开时记录可见内容高度，后续折叠项在表单内部滚动。用 Formal_003 连续展开两个区域、滚动到场输出精度后再收起，在 1676 × 1044 实窗中，标题所在弹窗的上沿始终为 y=174，保存按钮为 y=814～845。截图为 `GPTWork/feedback-host-20261128/visible` 中的 06 至 12。

队列恢复消息和其他页面的操作反馈移到右下角，原生主题按程度着色，支持叉号关闭，原位保留字段校验、进度及确认。队列刷新实窗显示提示时，表格保持原位置。悬停 5.08 秒后成功提示仍可见，移开并等待 4.52 秒后消失，另一次点击叉号立即关闭。生产宿主的计时、键盘焦点、模态对话框以及明暗主题等检查见 `GPTWork/feedback-host-20261128/verified-v1.json`。计算资源、重启动链、合并和后处理四个页面分别区分用户操作与后台轮询，12 项原生页面验证见 `GPTWork/feedback-operations-20261128/native.json`。

参数说明采用用户选定的 C：16 DIP 实心圆内的反色 i，热区保持 28 DIP。数字键结合方案 2 和 3，左减右加、中央输入，两端各有内缩浅底圆角键。浅色、深色、禁用、悬停、步进、32 / 40 DIP 外框和数值居中等 71 项原生检查通过，见 `GPTWork/symbol-native-20261128/checked.json`。旧版队列证据保留在下文。

最终样式再次在 Formal_003 上检查。在队列工具栏两键的浅底均测得 RGB 237，输入区域为 254。编辑表单两键底色均为 RGB 238，输入区域为 255。五帧覆盖两个折叠项的展开、滚动与收起，窗口和保存按钮的坐标一致。[工具栏实图](../../repowiki/images/job-queue-toolbar.png) · [正式编辑实图](../../repowiki/images/job-queue-editor.png)。界面和文档导航及结束提醒后台回归共 113 项通过，应用 Release 构建 0 警告、0 错误。

## 2026-11-28 · 队列编辑表单与工具栏

原正式队列编辑窗口的 Core、优先级用 40 DIP 数字框，单行文本框为 32 DIP。旧表单给内容写死了 520 DIP 宽，右侧超过可视范围。另一处「同名结果」和「并行上限」在用户提供的 613 × 48 图中实际均占第 4 至第 43 行（起始坐标 0），底边却分别为 RGB 212 和 98。修复后，编辑表单采用 32 DIP 文本框外观，工具栏维持 40 DIP 并采用下拉框外观。两处仍显示常驻的减少、增加折线。队列目录编辑、校验和字段保留规则见[本机调度](../../03-features/LOCAL_SCHEDULING.md)。

生产数字控件与原生下拉框、单行文本框在浅色及深色主题下的 47 项检查通过。覆盖实际外框位置、宽高、填充与边框画刷、圆角、数值居中和步进。回执为 `GPTWork/queue-number-form-20261128/numberbox.json`。原版本实际页的取消、保存和跨页选区核对见 `GPTWork/queue-edit-navigation-20261127/baseline/verified.json`。

在修复后的 1676 × 1043 队列实窗中，两控件的可见外框均占第 565～604 行。在 x=1302 和 x=1538 两处取样，底边同为 RGB 212，上边同为 RGB 235。正式作业编辑窗口在 x=865 处测得 Core、内存、优先级的上下边分别为 339～370、406～437、481～512，均为 32 像素，右侧箭头完整显示。两张源图在 `GPTWork/queue-edit-navigation-20261127/fixed`，分别为 `01-queue.jpg` 和 `02-formal-edit.jpg`。浅色图的读数受截图压缩影响，明暗外框资源另由上述原生检查直接比对。

队列、目录、重启动、调度、归档、正式客户端 HTTP 和文档导航联合回归通过 110 项，包含 12 项新增检查，见 `GPTWork/queue-directory-validation-20261128/final.xml`。最终文档导航 52 项、界面接线 45 项联合通过（含队列框样式选择）。

生产窗口中，两数值框与内存框的左右边界均为 x=589～1074，每颗箭头按钮宽 32 像素。点箭头将 Core 和优先级改为 1、2，内存填写 71%，保存重开后逐项一致。候选编辑中补填前置 ODB 后，候选表显示对应的依赖作业。批量更新仅作用于 40 个候选中勾选的 2 个，填写不存在的目录时保留原表单，修正后可保存。开启归档后清理默认关闭；手动开启后，单独清空归档根目录会关闭清理并保留计算根目录。正式作业也实际保存了两个目录。操作截图与三阶段队列数据见上述 `fixed` 目录，上下边像素读数及源码摘要见 `GPTWork/queue-number-form-20261128/geometry.json`。

## 2026-11-27 · 最终目录包中的队列实窗

打开 `9d862b5` 的正式免安装版核对两张表。候选 40 行，勾选 21 行，异常 0。正式队列 40 行均暂停调度，运行 0。实窗图 `GPTWork/queue-visible-final-9d862b5-20261127/queue-official-window.jpg` 可同时查看两表的行列分隔、标题对齐和长名称省略。同目录 `verified.json` 核对进程身份、5 份队列源码和两份编译资源。已为用户保留这个独立配置的示例窗口。

## 2026-11-27 · 在 98d1bc7 发布包中核对两张队列表格

在独立配置中打开 `release-win-x64-1fcb773bec3c` 的正式程序，候选区和正式队列各有 40 行测试数据，正式作业均暂停调度。实窗可见两表序号居中、名称和 INP 路径左对齐、首行长名称在本列省略；每一行下方和相邻列之间均有分隔线。实窗图为 `GPTWork/queue-visible-98d1bc7-20261127/queue-official-window.jpg`。检查后正常关闭该实例。

同一生产页面的独立原生渲染另外生成浅色、深色整页 PNG，均为 1704 × 1051。逐像素检查候选表的 7 条、正式表的 11 条内部竖线：表头与前三行完全对齐，横线、竖线均占 1 像素。两表的首行名称和第二行路径都实际触发省略。两种主题图分别为 `GPTWork/queue-visible-98d1bc7-20261127/v1/queue-light.png` 和同目录 `queue-dark.png`。与此前候选截图及 40 行验收所用的表格实现、编译界面资源的来源核对见 `GPTWork/queue-visible-98d1bc7-20261127/verified.json`。所有测试数据均在 G 盘，未启动求解。

深色主题下使用相同控件和尺寸核对，七个表头分界与浅色版完全相同。深灰数据行上的分隔线为 RGB 71/71/71，表头分隔线为 RGB 81/81/81，均只占一个像素。深色示例图及读图检查为 `GPTWork/native-parameter-comparison-20261124/tabledark1/queue-dividers.png` 和同目录 `verified-pixels.json`。

11 月 25 日使用 WinUI 自身的 RenderTargetBitmap 将生产候选表、三行示例数据和浅色主题渲染为 1350 × 165 PNG。读图核实八列有七条内部竖线，表头和各行的分界在同一像素位置，白底上分隔线为 RGB 233/233/233、厚 1 像素。序号居中，长名称在名称列内显示省略号。图片及读图回执为 `GPTWork/native-parameter-comparison-20261124/table1/queue-dividers.png` 和同目录 `verified-pixels.json`。正式队列与 40 行滚动的实际窗口记录见下文。

11 月 24 日晚在最新完整目录包 `15bec5c3e691` 打开独立的 40 候选和 40 正式作业样例，再次目视核对两表每行下方和相邻列之间的细线。选框与序号居中，名称和路径左对齐，长名称和长路径均在列内省略。应用源码为 `ee1f79f`；保留的验收窗口和配置位置见 [TASK-002](TASK-002-migration.md)。

## 2026-11-24 · 新建作业草稿、命令预览和单作业入队（N01）

在完整包 7857f4955208 的 G 盘隔离配置中，原生文件选择器选取仅含标题的 NativeDraft.inp，名称自动填为 NativeDraft。改为 NativeDraft_Check，用输入框两颗折线按钮将 CPU 从 4 增到 5 再减回 4，内存填 75%。命令预览中可见 `abaqus.bat`、`job=NativeDraft_Check`、`cpus=4` 和 `memory=75%`。另在重启动依赖与用户子程序输入框填入 Prior.odb、UserRoutine.for，两者均只作为草稿文本。

切换到作业概览再返回、新建菜单选择「保留当前填写」，名称和三条文件路径均保留。再次选择「清空并新建」，四个字段清空，CPU 4 和内存 75% 保留。接着输入 NativeDraft_Retry，将内存改为 63%，临时加锁阻止隔离会话文件被替换。确认清空时页面显示「新建未完成 · 请检查草稿保存错误」，输入仍可编辑；释放锁后重试，成功清空。

最后选择同一 INP，填写 NativeDraft_Queued，核对命令预览后点击「提交作业（加入队列）」。正式队列显示一个待运行作业，未启动调度。窗口 3801516（进程 213420）正常关闭。只读复核隔离配置的会话与作业清单：名称、INP、4 核、63% 及完成通知与正式队列条目一致，清单无进程、尝试编号和提交时间。回执 `GPTWork/native-newjob-menu-20261124/native-draft-acceptance.json` 保存桌面观察、持久化字段及三个文件摘要。本项覆盖本机草稿和入队，远端执行及实际重启动、子程序计算另行验收。

## 2026-11-24 · 完整包候选区与正式队列表格实测

完整包在本机打开 40 个候选和 40 个暂停调度的正式作业。两表长名称及长路径在本列省略，序号居中，浅色行列线与表头对齐。两表各选中前两行，再勾选第二个候选，入队勾选从 20 变为 21。两表纵向滚至候选第 29 行、正式第 26 行时刷新，位置保持；滚回首行仍可见四个原行高亮及正式表的两个勾选。回执 `GPTWork/native-formal-candidates-20261124/native-queue-acceptance.json`。使用隔离测试输入，未启动队列。

本轮专项复核有 55 项 pytest 通过，耗时 48.87 秒，另有 110 项原生控件、9 项日志检查及结果宽表、异步加载和导出检查通过。原始命令与报告位于 `GPTWork/table-result-regression-20261124-221603`。

验收结束时，完整包 7857f4955208 的隔离窗口 23748624（进程 145024）保留在队列页首行，调度停止。在继续操作前重新核对窗口身份。

## 2026-11-24 · 作业概览日志、服务器表单及活动任务关闭

本轮用含两份独立测试日志的原生工作台完成 F005 选区验收，通过 F008 添加和编辑表单的布局、保存及取消检查，并验证 F001 的三种活动任务关闭选择。此次补充运行证据，产品实现沿用 51cc69f。综合回执为 GPTWork/native-overview-logs-20261124/desktop/native-interaction-verification.json。

**作业概览。** 开发前台 160084 的原生运行日志显示 N03_A 的五行测试输出。用鼠标拖选 FIRST、SECOND、THIRD 三行后，后台给 A、B 各追加两行。轮询显示有新日志，仍可复制原选区。粘贴内容的 59 字节文件与预期的三行逐行一致，SHA256 为 bc236e6c75d0530a53295434d7b5d6134491a38fb6a79aeda0677dd4f5f2e9df。释放选区后显示两行新增内容，切换 N03_B 后日志仅包含 B 的输出。数据来自项目控制面的本机运行接口，日志生产者使用隔离测试执行器，未启动 Abaqus 求解。证据为同目录的 ready.json、after-append.json 和 copied.txt。

**计算资源。** 在浅色桌面实际打开“添加服务器”和“编辑服务器”。两者采用实现中设定的 548 DIP 固定宽度，目测主机、端口及其他单行输入等高，文字垂直对齐，右边缘可见。端口可直接键入，无步进按钮。用“仅保存”保存名为“表单验收”的回环测试配置，端口为 2222。再次编辑为 2233 后取消，重新打开仍显示 2222，与隔离配置文件的实存值一致。打开连接面板后取消。本项覆盖表单交互，真实 SSH 登录、网络中断及指纹处理有独立验收范围。32 DIP 控件高度的测量来自此前生产控件检查。

**关闭和重开。** 两份测试任务均活动时，“取消关闭”返回原工作台。“后台继续”让开发窗口关闭，原后台 107472 和两次执行身份继续存活。切换到 51cc69f 完整目录包 7857f4955208，在相同隔离配置重开，前台 141220、窗口 7939222 重新显示 A、B 运行中及 A 的七行日志。选择“停止任务并关闭”，原生窗口消失。只读快照先记录停止调度，再记录两份同身份任务均已终止。之后后台移除描述符、进程退出，监视会话 56075 退出码 0。测试脚本的主动收尾标记不存在，确认由关闭操作触发。after-keep-running.json、stop-close-observations.json 和 ended.json 保存了上述顺序，测试目录 ODB 数为 0。

复用方式见 GPTWork/native-overview-logs-20261124/fixture.py。脚本用项目 .venv 启动，在 G 盘隔离 profile 中产生测试运行数据。先用 smoke 验证真实运行接口，再用独立 desktop 实例在鼠标拖选后触发 append。现有 desktop 实例已收尾，保留的材料供核对。后续尚需验证高频长日志裁剪与滚动、关闭期间保存失败或超时，以及其他后台任务类型的关闭交互。

## 2026-11-24 · 队列列对齐、浅色行列线与实际窗口检查

用户在原生窗口指出序号/名称/路径错位并要求浅色分隔线。源码确认原表头独立Grid，ListView默认多选区域叠加表体缩进。新增共用QueueTableView和单一列定义QueueTableRow，移除隐式选择区域，保留显式勾选、行多选、双击编辑、行虚拟化和QueueListUpdates。候选/正式两表都有主题适配行列线，序号等数值居中，文字左对齐并本列省略；统一横向视口与16 DIP滚动条预留，不再靠空格对齐。没有改后台业务规则。

实际生产控件共110项通过，其中新增56项覆盖深浅主题、候选/正式、900/1600/2300 DIP、长文本、选中前后列边界、横向滚动及正式复选框与原生选择双向同步。回执GPTWork/queue-table-20261124/controls-fixed.json，进程202072退出0；测试构建0警告/0错误。首轮编译FontWeights命名空间错误已修正；第一份控件失败是测试错误要求空文本宽度大于0，保留controls-verification.json和controls-diagnostic.json，不把失败记录删除。既有54项选择/表单等检查亦在最终110项内。

开发发布输出GPTWork/queue-table-20261124/app，发布会话83322退出0。旧0aba窗口139280/12790616经Alt+F4正常退出0（监视11331结束），再用同一G盘隔离profile启动新前台142444/窗口9575816。CUA截图和点击已恢复；候选两行标题/内容边界一致，浅色行列线、序号居中、名称/路径不串列；点击勾选由1变2，等待16秒及手动刷新后仍为2。实际把窗口缩至最小宽度并横向滚到末列，确认表头与数据同步、长路径省略、检查结果可见，最后恢复最大化。扫描按钮在观察时保持可用，没有连续录像，不能将离散观察扩大成所有运行场景无闪烁。native-verification.json保留准确范围。

正式队列仍为空；Heading-only夹具没有确认入队或求解。正式行交互仅生产控件通过，不称业务运行验收通过。旧结果目录/预览/导出已完成的实际检查见TASK-001顶部。本轮未创建/搬移ODB，TEMP/TMP都在G盘。

最终相关回归110项通过（9.36秒，GPTWork/queue-table-20261124/regression-final.xml），含文档导航52项、界面接线、候选/正式队列API和外部扫描并发；git diff --check通过。首轮57通过/1失败为旧源码接线检查仍在JobQueuePage.xaml寻找已移动的“重启动依赖”，更新至实际QueueTableRow定位后通过，原regression.xml保留。原生控件110项与此次pytest110项是不同检查集，不能误作全量回归。

准确续接：新窗口142444/9575816保留供查看，启动监视会话52656只等待退出；完整目录0aba/安装9a尚不含本次表格修复。本轮相关回归和文档校验已完成；提交推送以GPTWork/queue-table-20261124/git-delivery.json实查回执为准，之后继续未验业务与更新完整候选。运行日志拖选、服务器业务表单、正式队列操作仍未因本次局部通过而完成。

2026-11-19复核用户“只刷新需要刷新的内容”要求：当前源码已具备行身份保留、字段差异通知、页头/按钮差异更新及手动/自动扫描状态分离，本轮未重复改写。当前全量自动回归1085项及9项子检查通过，准确命令/日志见[TASK-002](TASK-002-migration.md)顶部；既有连续100次刷新、多选与滚动保持的控件回执仍有效，但不替代业务页实操。最新实查旧前台9528仍在，新前台212240已不存在，其后台219004仍在，未擅自终止或重开；下段保留先前观察时间点。

2026-11-19原生接续：最新完整0aba窗口2164996/前台212240已打开，独立G盘配置备好两个合法GJA-8+2候选供后续15秒选择保持检查。当前先等结果浏览CSV/目录提示反馈；点击和激活仍受工具限制，不能把初始加载或夹具准备记为队列交互通过。准确身份、问题和步骤见[TASK-001](TASK-001-postprocessing.md)顶部及[原生验收](../../06-testing/NATIVE_ACCEPTANCE.md)，不重复旧窗口的确认问题。

后续发布已同步：6b4ade1局部刷新现已包含于完整e658a77e8d53和正式候选1fff69dedb9b；同负载隔离安装生命周期aa87c2237002通过，见TASK-002顶部。现有两个业务窗口仍为旧输出，以下开发/控件证据不扩大为新包原生交互确认。

## 2026-11-19 · 进一步缩小队列刷新范围

用户要求只刷新必要内容。核对当前源码：此前已按ItemId保留列表对象/容器与选择，仅通知变化字段；剩余ApplyQueue每1.5秒无条件触发Changed，页头/按钮及调度选项也重复赋值。本次修改JobQueuePage.ApplySnapshot/ApplyRuntime/SetEnabledIfChanged，仅写实际变化的显示值；WorkbenchCommandState.ApplyQueue/InvalidateQueue在队列可知性、调度状态或活动编号集合变化时才通知。相同活动编号重排不通知；每次观测和失败仍递增QueueRevision，保留旧响应丢弃约定，不更改后台轮询频率、扫描互斥、勾选持久化、求解或队列命令。

先在生产C#状态类新增100次相同动作状态观测、活动编号重排/终态变化、重复失联与恢复、旧响应隔离共8项断言。修复前pytest会话99303退出1，GPTWork/queue-targeted-before-20261119.xml明确失败于Unchanged queue actions notified the toolbar on every poll。修复后34项客户端断言通过；与已有两项真实HTTP状态/目标身份检查一起，GPTWork/queue-targeted-fixed-20261119.xml为3通过/54未选（6.95秒），不是57项通过。列表逻辑本轮未改，原54项原生控件回执保留既有范围。

最终文档导航、界面/草稿接线及后台扫描并发回归103项通过（21.93秒，会话5309退出0，GPTWork/queue-targeted-regression-20261119.xml）；ruff和git diff --check通过。生产发布会话70362退出0，目标GPTWork/queue-targeted-native-20261119、日志同名.log，未报告警告/错误。汇总及Git核对写入GPTWork/queue-targeted-delivery-20261119/verification.json，提交/推送状态仅以实际核对回执为准。

准确续接：自动检查与开发构建均已终态，无本轮长任务待等待。未启动新工作台、未关闭旧窗口。Get-Process实查9528（queue-dialog-native-20261119）和227820（release-win-x64-2c18c11259b2/AbaqusTools）仍在，创建时间与既有回执一致；CIM只读查询被拒绝后改用Get-Process确认，没有改权限。旧完整e422/安装6126不含本次优化，下一项是新候选的业务页鼠标/视觉确认与后续完整打包，不能以构建或状态类检查替代。没有启动求解或访问原始模型。

## 2026-11-19 · 服务器表单、队列选区与名称修复

修复已提交并推送9a099728b97da27a5669bf550fa6edfc4a6662f2，已实际核对origin/main一致。干净完整目录release-win-x64-555b572ccbfe/AbaqusTools、安装候选installer-win-x64-9f4880b493e0已生成并核对全摘要。1689清单文件、19worker、15应用资源；清单SHA256为44f004167a0d60970858277fde3a40eb7583f61105ce35c0c3e36671bd6fb035，安装器126146312字节、SHA256为94e4e639940278210c3e9df739da77b6751ebfbb31d43f6013a5e3daaf4b6982。安装器NotSigned，未安装、未重做生命周期。包内依赖检查及冻结API的两个加号名称、手动扫描状态和候选勾选检查通过；219864后台经idle协议退出0、描述符移除，未启动求解。汇总GPTWork/queue-dialog-delivery-20261119/verification-summary.json，分项queue-dialog-frozen-6a644c79bf95/verification.json和queue-dialog-bundle-probe-20261119/bundle-probe-5t2qcr39/verification.json。

最终定向回归211项通过（40.83秒，queue-dialog-delivery-20261119.xml，会话36892退出0）；最终WinUI构建queue-dialog-final-native-20261119为0警告/0错误，会话74138退出0。54项控件和命名专项均终态。自动检查和打包已完成，业务窗口确认尚待用户反馈；不重复启动新窗口或转移旧SSH登录。


收尾新增：侧栏也只响应可见字段变化，54项控件最终通过，220820退出0，queue-dialog-final-controls-20261119/verification.json；51项命名/真实Windows传参检查通过，job-names-fixed-20261119.xml；111项界面/文档/运行控制回归通过，queue-dialog-followup-fixed-20261119.xml。Qt参数记录器曾发现带空格命令路径被QProcess二次转义，按官方setNativeArguments方式修复后通过；保留job-names-final-20261119.xml的73通过/1失败记录。source-contract旧RestoreFormalSelection和SelectedItems.Add断言已随实际入口迁移，两次旧断言失败均保留，最终111通过。

业务验收窗口9249544已在用户桌面打开并由CUA读取，前台9528、后台142020/184740/91156均有创建时间回执。独立profile中正式API添加两份合成GJA-8+2候选，异常数0；不访问原始工程、不启动求解。工具仍无法点击、截图与激活，已交用户核对添加/编辑表单和15秒候选多选保持。待回复期间保留该窗口及旧已登录窗口5379070。

用户要求固定宽度内统一添加/编辑/连接表单，主机与端口同其他单行框等高、移除端口增减按钮。已在共享方法接入ServerDialogLayout：548 DIP弹窗、32 DIP输入体、共同行/列及右侧滚动留白。原根因是560 DIP内容超过默认弹窗可用宽度，以及NumberBox帮助标题/40 DIP控件撑高同行TextBox。旧已登录SSH窗口5379070保留，未关闭或改变连接。

用户随后指出队列“扫描”闪烁、候选多选自动丢失，截图为GJA-8+2系列。原队列每1.5秒Clear全部列表，且自动扫描与手动扫描共用按钮状态。改为按ItemId保留对象和容器，只通知变化字段；同时保留候选与正式列表选择，自动监测和手动扫描显示区分。Abaqus命名按2025原厂文档修正，详见JOB_NAMING功能说明，未修改G:\Job、未启动求解。

已通过51项生产原生控件，进程205080退出0，回执queue-dialog-controls-20261119/verification.json；服务器单独41项也通过。正式WinUI开发构建queue-dialog-native-20261119成功。首轮控件构建漏引JobDraftContracts导致编译失败，补齐生产契约后通过。首轮名称/扫描63项中62通过，失败为测试使用了不存在的editCandidate命令，已改为实际updateCandidate；后续117项116通过，唯一失败为旧源码契约仍要求清空后RestoreFormalSelection，已更新为实际两表增量同步入口。最终回归及原生业务确认续记于本节。

准确续接：新完整555b包已包含本轮全部修改，当前用户可见的待确认窗口仍为queue-dialog-native-20261119开发输出（不含最后的侧栏可见字段过滤；候选列表和表单修复已包含）。首次受限桌面启动218736虽有窗口句柄但不在CUA清单，已验证其独立profile、无活动任务后结束前台并经正式idle协议关闭219644等后台；unlisted-launch-cleanup.json确认无残留，不作为原生正常关闭验收。用户可见旧SSH窗口不受影响。下一项为接收用户表单/候选等待反馈，再继续尚未通过的原生业务；相关生成物均在GPTWork，失败回执保留。

## 2026-11-19 · 完整候选原生有限复核

侧栏修复已进入干净dd5fe122完整c6999a8e1c8e与正式标识安装候选d7c766a02a78。同负载隔离安装生命周期9dce03ed6016通过。完整包实际加载4个结果范围和中文目录说明，Ctrl+7/8往返后处理/结果浏览、Ctrl+B收起恢复及目录输入保留、Alt+F4正常退出均经CUA和身份/配置回执核对；开发窗口205860及完整包227292连同各自后台均结束，无自有残留。当前没有为本轮保留的原生窗口。

鼠标定位仍失败、截图超时；键盘/AX不代表鼠标、像素或八页完整业务验收。详见TASK-002顶部和GPTWork/sidebar-release-verification-20261119/verification-summary.json。23项控件与86项相关检查沿用源修复时的有效证据，不因打包重复跑整套。

## 2026-11-19 · 侧栏按钮比例、树缩进与目录含义

提交核验：修复与说明已提交`8ac63ac7305bcad878980d2afc98456739ff9b93`并推送origin/main，远端ls-remote与本地HEAD一致；其后的本条为验收记录补充。完整目录及安装候选尚未重建，不把旧安装包称作本轮版本。

收尾核验：最终窗口1442068已实际加载4个范围并连接后台，AX确认“结果根目录/对比组目录/提取批次目录/模型结果目录”。原生205860、后台201772、子221920，身份回执`GPTWork/native-sidebar-final-20261119/result-browser/processes.json`，窗口保留供查看。最终23项控件与86项shell/文档检查通过（sidebar-final-regression-fixed-20261119.log）；初次最终文档检查85通过/1失败是CURRENT_STATUS漏写持续维护约定的原句，已补回，失败日志保留。没有将最终14号刷新图标宣称为用户视觉确认。

用户确认按钮已对齐、树缩进正常；反馈刷新图标视觉偏大，随后澄清“模型甲”也是文件夹，先前把它误认为数据库文件。最终保留文件夹/文件的图标区分，不将模型结果目录改成数据库图标。刷新图标由默认SymbolIcon改为14号FontIcon，折线16号，共用16×16内容区域与30×30按钮；展开入口同样为16号折线。

生产WorkbenchExplorerHost保留同一标题Grid，避免覆盖按钮错位。新增CompactTreeItem，仅对既有WinUI模板的MultiSelectGrid缩进绑定按10/16缩放，展开箭头左右留白14改8，图标列18改16、列间距7改5；原生选择、展开、焦点与主题模板保留。文件夹/文件显式使用系统图标字体；工作目录、后处理和合并源的实际ODB文件改为文件图标。ResultScopeNode.KindDisplay将root/group/batch/odb等内部类型显示为中文目录说明，“模型甲”下方显示“模型结果目录”，不改变路径、类型或读取算法。

最终生产控件检查23项通过，PID229496退出0，回执GPTWork/sidebar-final-checks-20261119/verification.json及process.json：4项提示留白、4种标题边界、深浅主题各3项六级缩进/图标绑定/折叠后选择、9项选择刷新。六级文字X为53/63/73/83/93/103 DIP。开发发布构建GPTWork/winui-sidebar-final-publish-20261119.log通过。前一版23项/86项shell与文档回归也通过；最后文档与源码回归另见当前状态。

失败记录保留：sidebar-polish-checks-20261119第一次228060的前10项通过，折叠再展开后尚未布局，ContainerFromNode为空；在展开后完成UpdateLayout后228136通过23项。短暂的独立矢量图标方案在用户澄清后撤回，sidebar-vector-checks只构建未运行，不作为交付证据。

197448及后台227264/223484已正常结束；227408前端退出后后台226912/193812仍在，已核对身份与空闲状态，经正式关闭协议idle提交结束，未强杀或停止任务。两处verification.json分别验证描述符移除和两份日常JSON不变；第二处另有idle-api-close.json，不把API收尾称为原生关闭验收。更早205808/187916实例也已核验结束。

准确续接：当前开发输出GPTWork/winui-sidebar-final-20261119，独立配置GPTWork/native-sidebar-final-20261119/result-browser，原生205860；用native_sidebar_final_20261119.py capture/finish核验身份，窗口关闭前不能运行finish并声称通过。旧完整5497f45cfec3/安装b4ca03cbe0c8不含本轮修复，完整包仍待重建。截图工具仍超时，用户确认范围与自动检查分别记录；禁止向C盘放ODB、未启动求解。以下为当时历史记录，当前状态以本节和CURRENT_STATUS为准。

## 2026-11-19 · 密度验收确认与侧栏按钮对齐修正

用户确认5497f45cfec3窗口“空白已消失，密度合适，收起展开正常”，这三项实际验收已补记，不能继续写成待确认。但用户随后截图指出刷新/收起按钮上下不齐，作为独立缺陷修复。根因是刷新按钮位于WorkbenchExplorerHost标题行，而收起按钮位于MainWindow覆盖层，分别按行中心与8 DIP上边距定位。

将展开状态的ExplorerCollapseButton放进生产WorkbenchExplorerHost的同一标题Grid，与ExplorerRefreshButton共用ExplorerHeaderButtonStyle：30×30 DIP，显式最小尺寸30，垂直/内容居中，列间隔6。删除为覆盖按钮保留的右侧48 padding，恢复12。CollapseRequested事件仍由主窗口统一切换；关闭/新建锁定同步禁用两处入口。主窗口只在收起时显示40 DIP窄栏的展开按钮，不再覆盖展开状态的标题区。保留Ctrl+B、偏好、页面/输入/选择和后台任务。

生产原生控件新增四种标题几何组合（有/无副标题、有/无较高的选择目录按钮），两按钮实际顶部均为11/11或13/13 DIP，尺寸均30×30。全部17项通过、39652退出0，`GPTWork/header-alignment-checks-20261119/verification-final.json`及process-final.json。初次220640退出1保留verification.json：四个几何检查通过，新增控件测试切换后旧选择检查尚未完成初始布局，未发选择事件；在该选择测试初始Attach后显式Measure/Arrange/UpdateLayout，保持原断言后全部通过。37项shell回归通过0.05秒，日志`GPTWork/header-alignment-regression-20261119.log`；发布构建`GPTWork/winui-header-alignment-publish-20261119.log`成功。新开发输出`GPTWork/winui-header-alignment-20261119`。

已通过CUA正常Alt+F4关闭两旧测试窗口：205808/213728/166276及187916/185836/210388全部按身份核验结束，描述符移除，两份日常JSON未改。原native-density与native-density-release的verification.json和用户验收说明已更新。现在只有新修复测试窗口197448，后台227264、子223484，CUA窗口2294212；`GPTWork/native-header-alignment-20261119/result-browser/processes.json`。CUA见并排刷新/收起控件、结果4范围与后台连接；截图仍超时。新实例的收起/展开与退出续验中，不能将17项几何检查说成全业务截图验收。没有求解或ODB复制。


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
