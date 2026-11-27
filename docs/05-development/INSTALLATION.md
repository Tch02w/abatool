# Windows 安装、升级与卸载（F026）

当前 Windows x64 安装程序为 `GPTWork/installer-current-850f753-20261128/source/GPTWork/installer-win-x64-0edc18aea1b3/AbaqusTools-0.1.0-win-x64-setup.exe`。免安装入口为 `GPTWork/release-win-x64-d76d5340404a/AbaqusTools/AbaqusTools.WinUI.exe`。两者均来自干净提交 `850f753`。安装程序版本为 `0.1.0`，大小为 126495187 字节，SHA256 为 `ee8ad45b2464f0d9ca8c6b9c8f44f1a01ed866e9dfbb5643fdf09a8c5f68ee45`，签名状态为 NotSigned。

在 G 盘独立测试标识下，中文向导完成了目录选择、返回、安装和完成，安装后逐文件核对了 1697 项负载及发布清单。另从 `3ff3fa2` 升级至 `850f753`，8 项检查通过，覆盖运行中拒绝升级和卸载、退出后升级、从实际安装目录读取资源和队列、卸载后保留用户文件。旧版安装、新版升级和新版普通向导三份日志均为零异常、零抑制弹窗。升级前 1 个、卸载前 16 个应用数据文件的 SHA256 保持一致，测试登记和快捷方式均已移除。完整回执为 `GPTWork/installer-current-850f753-20261128/verified.json`。正式标识安装与独立无开发环境 Windows 仍待验收。[免安装包校验](RELEASE.md)

上一轮从 `c4bbe73`（构建器 `648f5b4`）升级至 `3ff3fa2` 的 8 项检查、普通向导和数据保留回执为 `GPTWork/installer-current-3ff3fa2-20261128/verified.json`。

## 上一修正版（构建器 648f5b4）

浮动通知版的 Windows x64 安装程序为 `GPTWork/installer-final-c4bbe73-20261128/source/GPTWork/installer-win-x64-1357614b12b3/AbaqusTools-0.1.0-win-x64-setup.exe`。直接启动同版本可打开项目目录下的 `GPTWork/release-win-x64-b3de1167dc27/AbaqusTools/AbaqusTools.WinUI.exe`。[免安装版发布记录](RELEASE.md)

安装程序版本为 `0.1.0`，应用标识为 `AbaqusTools.Workbench.WinUI3`。安装器构建脚本取自干净提交 `648f5b4`，应用负载取自 `c4bbe73`。文件大小为 126480996 字节，SHA256 为 `2f0a625e5a21a7dd11178f6af312fc6f372d5641a778758928fb818358eed247`，签名状态为 NotSigned。普通安装器和专用测试安装器使用相同的 1697 个文件和发布清单。汇总回执为 `GPTWork/installer-final-c4bbe73-20261128/verified-fix.json`。

本机 G 盘的测试标识已实际走过中文向导的目标位置、准备安装、上一步、安装和完成。返回时保留所选中文路径，安装文件与清单逐项一致，随后卸载并核对了快捷方式和登记的移除。向导记录为 `GPTWork/installer-final-c4bbe73-20261128/wizard-e90ae0d2e3/stages.json`。另从 `9d862b5` 旧包升级至本版，8 项检查通过，覆盖运行中阻止升级和卸载、退出后升级、已安装后台的资源与队列读取，以及正常卸载。升级前 1 个、卸载前 16 个数据文件摘要逐项一致。修正版向导和修正版静默升级日志均为 0 个异常、0 个被抑制的提示框。正式标识的实际安装和无开发环境的独立 Windows 机器仍待验收。

11 月 28 日撤回使用旧构建器生成的安装候选（包括 `069e05f63988` 和下列历史安装包）。旧版文件校验使用仍含 `{app}` 的目标路径，导致中文安装向导逐文件弹错；静默操作会抑制错误框并返回成功。重现日志为 `GPTWork/installer-final-c4bbe73-20261128/wizard-638132640b/wizard.log`。修正版将清单 SHA256 写入 Inno 的文件条目，编译时按文件核对摘要，解包写入时由 Inno 检查数据。验收同时读取安装日志并重新计算磁盘文件摘要。独立修改测试夹具的 XBF 后，真实编译器拒绝生成安装器。[Inno 文件校验说明](https://jrsoftware.org/inno-setup/documentation/topic_filessection.htm)

## 已撤回的历史安装候选

上一版 Windows x64 安装候选为 `GPTWork/installer-win-x64-3cb0dabd8612/AbaqusTools-0.1.0-win-x64-setup.exe`，版本 `0.1.0`，应用标识 `AbaqusTools.Workbench.WinUI3`。构建脚本和完整负载均取自干净提交 `9d862b58f2f6f6e1dd66909f39907721f64d2789`。文件大小 126373281 字节，SHA256 为 `2bfb23aaf9c60be85e2b8673bdc70763bd7b9626d08361b3d11850602b155b14`。[目录包与校验回执](RELEASE.md)

普通安装器当前未签名。专用测试安装器位于 `GPTWork/installer-win-x64-04eb75c80023/AbaqusTools-0.1.0-win-x64-setup.exe`，SHA256 为 `8fc70f8f4487d7879439b39dc22e25ff1425ca5d3084260033c15880e0d9e777`。其标识 `AbaqusTools.Workbench.WinUI3.Test.fa0dbad4b19e` 用于隔离验收。两份安装器均含 1694 个清单条目及发布清单自身。

历史正式候选中，`98d1bc7` 位于 `GPTWork/installer-win-x64-d7cfe7a56959`，`1fc22fd` 位于 `GPTWork/installer-win-x64-166c12194af4`，`b85c24b` 位于 `GPTWork/installer-win-x64-69f4b496676b`，`ee1f79f` 位于 `GPTWork/installer-win-x64-7f9e23f7bf10`。

上一目录包 `51cc69f` 的测试标识安装验收回执为 `GPTWork/installer-lifecycle-f59eb537070a/verification.json`。运行中的后台能阻止升级和卸载，空闲后正常升级和卸载，用户数据摘要保持一致。

## 旧版升级实测

11 月 27 日在 G 盘，用专用标识把 `98d1bc7` 升至 `9d862b5`。8 项检查全部通过，覆盖安装目标保护、首次安装、运行中阻止升级和卸载、退出后升级、升级后客户端读取及正常卸载。升级后 1 个、卸载后 16 个数据文件的 SHA256 均与操作前一致。用户文件保留，登记和快捷方式已移除，测试进程均已退出。回执为 `GPTWork/installer-lifecycle-1a53a627112c/verification.json`，复核为 `GPTWork/lifecycle-damage-9d862b5-20261127/run/complete.json`。

11 月 27 日在本机 G 盘新建的中文路径，使用专用标识从 `1fc22fd` 升级至 `98d1bc7`。8 项检查全部通过。安装器拒绝陌生目录和目录联接，首次安装后逐文件校验。后台运行时升级与卸载均被阻止，后台正常退出后升级成功，客户端从新安装目录读取资源及队列并正常关闭。升级前的 1 个、卸载前的 16 个应用数据文件逐项 SHA256 一致。正常卸载后用户文件保留，两个程序版本、测试登记及菜单快捷方式已移除，自有测试进程全部退出。原始回执为 `GPTWork/installer-lifecycle-329183fe8a13/verification.json`，独立复核为 `GPTWork/lifecycle-group-order-98d1bc7-20261127/retry/complete.json`。本次采用静默安装，交互式安装向导仍待验证。

11 月 25 日在本机 G 盘以专用测试标识从 `ee1f79f` 升级至 `1fc22fd`。测试安装器使用与上述候选相同的 1692 个负载文件。8 项检查通过，覆盖拒绝占用目录和目录联接、全文件校验、后台运行时保护升级与卸载、退出后升级、安装后的客户端访问和正常卸载。升级前的 1 个、卸载前的 16 个应用数据文件均逐项核对 SHA256。用户文件保留，程序版本、测试登记和快捷方式已移除，自有测试进程均已结束。回执为 `GPTWork/installer-lifecycle-94df87bd0361/verification.json`。

`ee1f79f` 的测试标识安装程序位于 `GPTWork/installer-win-x64-a2fc9bd03b73`。在本机 G 盘的中文路径，从同一测试标识的 `51cc69f` 升级至 `ee1f79f`。首次安装、运行中拒绝升级/卸载、正常退出后升级、安装后访问冻结后台、卸载与数据保留共 8 项通过。升级前的 1 个文件与卸载前的 14 个数据文件逐项摘要一致。测试登记及快捷方式已移除，用户文件保留。回执为 `GPTWork/installer-lifecycle-34e68d8d7ff7/verification.json`。

## 使用

1. 正常结束任务并退出工作台，再运行 `AbaqusTools-0.1.0-win-x64-setup.exe`。如果曾选择“后台继续”，先重新打开工作台，等待任务结束后正常退出。
2. 默认按用户安装到 `%LOCALAPPDATA%/Programs/AbaqusTools`，不要求管理员权限。也可选择本机空目录；拒绝磁盘根目录、网络路径、目录链接及含其他文件的陌生目录。
3. 从开始菜单打开“Abaqus Workbench”。安装后不会自动启动应用或求解。Abaqus 及许可证仍由目标机提供。
4. 升级时运行新包并选择原安装目录。该目录的程序或后台仍在运行时明确拒绝，不替用户终止计算。
5. 通过 Windows 应用列表或安装目录的 `unins000.exe` 卸载。卸载同样拒绝活动后台，只移除安装器登记的程序文件和入口；队列、配置、工程模型及结果不在卸载清单中。

## 数据与失败处理

负载安装到 `versions/<源码摘要前缀>-<清单摘要前缀>`。新文件全部写入并逐文件校验后建立开始菜单入口；升级保留旧版本，不原地混合 DLL。普通安装失败由 Inno 登记和回滚机制管理，不承诺断电时的文件系统事务。

应用继续使用既有用户数据目录，例如提交器的 `AbaqusSubmitter` 和工作台的 `AbaqusTools`。安装器没有删除这些目录或迁移数据库格式的规则。用户添加到安装目录的非程序文件不会被递归清空；不要把工程数据放在版本目录中。

提示目录已有其他文件时，选择空目录或原安装目录，不删除已有文件强行继续。无法读取运行进程时停止安装/卸载，检查 Windows 管理服务后重试。失败先保存日志，不重复启动多个安装器。用 `/LOG=<完整文件路径>` 指定日志，否则自动日志位于 Windows 临时目录。

旧版本目录是恢复材料；当前没有自动回退按钮，跨版本数据库降级兼容未验证，不把手工执行旧程序称为安全降级。

## 构建与核验

先按[发布构建](RELEASE.md)生成干净源码的完整目录，然后运行：

```powershell
.\.venv\Scripts\python.exe packaging/build_installer.py <完整目录> --compiler <ISCC.exe> --version 0.1.0
```

正式标识构建要求工作区干净。脚本检查负载清单的架构、源码状态、相对路径、大小和完整 SHA256，拒绝缺失、多余或变化的文件；编译后再次检查来源未变。新建 `GPTWork/installer-win-x64-*` 保存安装器、生成脚本、日志及 `build-report.json`，分别记录负载和安装器源码身份。`status=compiled` 只表示编译及来源校验通过，不表示目标机或原生操作通过。

隔离测试用 `--test-id <12位小写十六进制>` 创建独立卸载标识，不能把这种包交付最终用户。用前后两份负载构建后运行：

```powershell
.\.venv\Scripts\python.exe packaging/verify_installer.py <旧测试包build-report.json> <新测试包build-report.json> <ControlPlaneHost.Tests.exe>
```

验证器只接受测试标识、事先不存在的注册/快捷方式以及不同负载。在GPTWork新建中文空格目录，检查陌生目录拒绝、首次安装/全摘要、活动自有后台阻止升级/卸载、正常退出后升级、开始菜单指向、正式主机启动/API/退出、卸载保留用户文件并移除测试注册与入口。移除前核实绝对目标和归属；失败保留回执，只收回捕获的自有进程，不清理历史数据。

检查器应构建到普通GPTWork目录，如 `dotnet build tests/winui_host/ControlPlaneHost.Tests.csproj --no-restore -o GPTWork/installer-lifecycle-host`，避免不同Windows执行账户无法访问pytest创建的私有目录。验证器在任何安装前执行检查器纯状态检查；工具不可运行则直接停止，不留下新安装。后台正常退出后记录data/post-data/installed-host内实际数据库及旁文件，升级和卸载分别核对完整文件清单与SHA256；这些数据必须完整保留。该项不等于验证所有历史配置的数据库格式迁移。

测试标识的本机向导与静默安装分别验收。正式身份、签名/SmartScreen 及无开发环境目标机仍待验证。

## 工具依据

采用[按用户安装规则](https://jrsoftware.org/inno-setup/documentation/topic_setup_privilegesrequired.htm)，关闭[自动结束应用](https://jrsoftware.org/inno-setup/documentation/topic_setup_closeapplications.htm)，利用[安装/卸载事件](https://jrsoftware.org/inno-setup/documentation/topic_scriptevents.htm)检查前置条件和[文件回调](https://jrsoftware.org/inno-setup/documentation/topic_scriptinstall.htm)验证摘要。下载遵循[官方签名校验说明](https://jrsoftware.org/inno-setup/downloads/verify)。
