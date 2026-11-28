# Windows 安装、升级与卸载（F026）

当前 Windows x64 安装程序为 `GPTWork/installer-legacy-workbench-20261128/source/GPTWork/installer-win-x64-d053fe8ae824/AbaqusTools-0.1.0-win-x64-setup.exe`。应用与安装程序均从干净提交 `cf58e9e` 构建，版本 0.1.0，大小 126676263 字节，SHA-256 为 `5f1caf673daaa2371c0e2477d76c8eaac4f2d4448e5ca91e046ef630abe0c0f4`，尚未签名。[免安装包与来源](RELEASE.md)

在开发机上使用独立测试标识，从 `2c06b77` 安装、升级、卸载的八项检查通过。运行中升级与卸载均被阻止，退出后台后可继续。升级前 1 份、卸载前 12 份测试数据的摘要保持一致。中文向导复核了 G 盘安装目录、1700 个负载文件、67 份文档及 967 个本地链接。卸载后测试注册项和快捷方式已移除，验收进程均已退出。

从实际安装目录打开新版时，旧 PySide 保存的作业名、3 核、17 GB 内存、Abaqus 命令、输入与归档路径均读回。修改作业名并重开后 WinUI 显示新名，同一旧配置仍可由历史版本 PySide 打开，原文件摘要一致。首次检查时测试脚本缺少哈希命令，在应用启动前失败；改用 .NET SHA-256 后，在新隔离目录重跑中文向导和两次应用启动均通过。回执为 `GPTWork/installer-legacy-workbench-20261128/verified.json` 和 `GPTWork/native-legacy-workbench-20261128/package-94b0807e/package-reopen.json`。正式标识安装及独立无开发工具 Windows 设备仍待实测。[本机设置的迁移范围](../03-features/UI_INTERACTION.md#从旧版工作台接续本机设置)

## 历史版本 2c06b77

该版 Windows x64 安装程序为 `GPTWork/installer-index-recovery-20261128/source/GPTWork/installer-win-x64-db199b3d97d0/AbaqusTools-0.1.0-win-x64-setup.exe`。应用和安装程序均从干净提交 `2c06b77` 构建，版本 0.1.0，大小 126663986 字节，SHA-256 为 `ef2ead96c44034acf716710b4875175b9355ed8ea315e99298e525a61e22ad1d`，尚未签名。

本机使用独立测试标识从 `328ad47` 升级，八项安装、升级和卸载检查通过。后台运行时安装程序会阻止升级和卸载，关闭后可继续。升级前 1 份、卸载前 12 份测试数据的摘要逐一吻合。中文向导在带空格的 G 盘目录完成安装，返回上一步时保留原路径。已核对 1700 个应用负载文件及随包清单、67 份文档和 924 个本地链接。卸载后，测试注册项、快捷方式和版本文件均已移除。三份安装日志均无异常，测试进程正常退出。

回执为 `GPTWork/installer-index-recovery-20261128/verified.json`。正式标识安装和独立无 Python、无 .NET SDK 的 Windows 环境仍待验证。

## 历史版本 328ad47

该版 Windows x64 安装程序为 `GPTWork/installer-history-preview-20261128/source/GPTWork/installer-win-x64-6cf67a992614/AbaqusTools-0.1.0-win-x64-setup.exe`。应用提交为 `328ad47`，版本 0.1.0，大小 126641061 字节，SHA-256 为 `9d7af4703cc76e6549a2f809a8a2e3fbccce7471f4ad07c11c68f47a3bd5cc9d`，签名状态为 NotSigned。

本机用独立测试标识从 `cbe221e` 升级。八项安装与卸载检查通过，包括运行中阻止升级或卸载、退出后升级，以及升级前 1 份、卸载前 12 份测试数据逐文件核对。中文向导可选带空格的 G 盘路径，点“上一步”后保留选择。已安装的 1699 个应用文件、67 份文档和 886 个本地链接通过核对。正式安装标识及单独一台没有 Python 和 .NET SDK 的 Windows 机器仍待验。

首次运行验收工具时，外层测试配置使调度数据库写到了另一个测试目录。已让验收工具显式向已安装客户端指定数据目录，并使用同一对安装包从首次安装重新跑完八项检查。独立配置中的测试文件及其摘要均得到保留，卸载后测试注册项与快捷方式已移除，所有本轮进程正常退出。完整回执为 `GPTWork/installer-history-preview-20261128/verified.json`，目录隔离复测见同目录 `profile-regression.json`。

## 历史版本 cbe221e

该版 Windows x64 安装程序为 `GPTWork/installer-remote-merge-20261128/source/GPTWork/installer-win-x64-a8b37404cc42/AbaqusTools-0.1.0-win-x64-setup.exe`，源码 `cbe221e`，版本 0.1.0，大小 126621879 字节，SHA-256 为 `8a9f6b1bbd0ceb06c49899671ceb9d13458497cfac334e3db099195760e67bb7`，签名状态为 NotSigned。

在本机用独立测试标识从 `c876875` 升级，核对了安装、运行中保护、升级、客户端连接、用户数据保留及卸载，八项通过。中文向导内的 1698 个应用文件、67 份文档和 858 个链接已经核对。升级前 1 份、卸载前 12 份测试数据文件的摘要保持一致。首次检查旧后台遇到 30 秒启动等待超时，重试在原已升级实例完成了数据保留与卸载验证。详细回执为 `GPTWork/installer-remote-merge-20261128/verified.json`。

另一份程序复制到独立中文路径后，在移除开发工具的进程 PATH 下，前台 174 个、后台 88 个已加载模块全部来自程序目录或 Windows。退出后前后台和连接描述符均已清理。回执为同目录的 `run-f9c1b754/verification.json`。独立无 SDK 目标机与正式安装标识的首次安装仍待验。

## 历史版本 c876875

该版 Windows x64 安装程序为 `GPTWork/installer-menu-gif-20261128/source/GPTWork/installer-win-x64-8b5011fbf087/AbaqusTools-0.1.0-win-x64-setup.exe`。源码提交 `c876875`，版本 0.1.0，大小 126606267 字节，SHA-256 为 `6d2ef52651ffed472404ce24bca04f5b8d64d9bda7bed5c8c6e894199897403e`，签名状态为 NotSigned。

以独立测试标识从 41c104c 升级，本机安装、运行中保护和卸载的 8 项检查已通过。升级前 1 个、卸载前 16 个数据文件的摘要均保留，快捷方式、注册项和测试进程已清理。中文向导完成后核对了 1698 个应用文件、67 份文档和其中的 825 条链接。第一次向导检测在正常写盘期间触及固定时间限制，改为依据安装写入进展等待后完整通过。回执为 `GPTWork/installer-menu-gif-20261128/verified.json` 和同目录的 `wizard-retry.json`。

开发机上另一份中文路径的免安装程序在无开发工具的 PATH 下运行。前台 174 个、后台 88 个加载模块全部来自成品或 Windows，程序正常退出。回执为 `GPTWork/installer-menu-gif-20261128/run-5cce0916/verification.json`。独立无开发工具 Windows 及正式标识的安装生命周期仍待验收。

## 历史版本 41c104c

Windows x64 安装程序为 `GPTWork/installer-queue-index-20261128/source/GPTWork/installer-win-x64-a4d196da215b/AbaqusTools-0.1.0-win-x64-setup.exe`。应用及安装器来自提交 `41c104c`，版本 `0.1.0`，大小 126589848 字节，SHA-256 为 `0da3162fcbaf3744c01219787c5a8a40640ee1ecb2a060ea51c6c2d07259c215`，签名状态为 NotSigned。免安装入口和清单摘要见[发布记录](RELEASE.md)。

使用同一负载的独立测试标识从 `827a45f` 升级，安装、运行时保护与卸载共 8 项通过。中文向导也已实际完成安装、返回和卸载。1698 个应用文件逐一匹配清单，已安装的 67 份说明中 806 个相对文件链接均可访问。升级前 1 个、卸载前 16 个应用数据文件的摘要均保留，三份安装日志无异常，测试标识、快捷方式和自有进程已清理。回执为 `GPTWork/installer-queue-index-20261128/verified.json`。独立无开发工具 Windows 及正式安装标识的生命周期仍待测试。

另将此版本放到 G 盘独立中文目录，逐一校验 1698 个应用文件和清单。在 PATH 无 Python、.NET 与 Abaqus 的独立进程环境下打开 WinUI，前台 174 个、后台 87 个加载模块全部来自程序目录或 Windows，退出码为 0，后台及连接描述文件已清理。回执为 `GPTWork/installer-queue-index-20261128/run-72e86c58/verification.json`。本机 Windows Sandbox、Hyper-V 均处于禁用状态，实际设备范围见 `GPTWork/installer-queue-index-20261128/environment.json`。

## 历史版本 827a45f

`GPTWork/installer-transfer-context-20261128/source/GPTWork/installer-win-x64-46bcbbe7d191/AbaqusTools-0.1.0-win-x64-setup.exe` 来自应用提交 `827a45f`，版本 `0.1.0`，大小 126576854 字节，SHA-256 为 `3434b2ad49720d1b225cbea08f0af62d445d1d1043fa6788a540de8b64012336`，尚未签名。

本机从 `1b899eb` 升级独立标识的安装，8 项检查全部通过。中文向导完整走过安装、返回以及卸载。1698 份负载与清单逐项一致，安装目录中 67 份文档的 778 个相对链接均可达。升级前 1 份数据文件和卸载前 16 份数据文件均保留原摘要。三份日志均无异常，无残留测试登记、快捷方式或自有进程。回执为 `GPTWork/installer-transfer-context-20261128/verified.json`。

免安装包在 G 盘独立中文路径启动，PATH 中无 Python、.NET 或 Abaqus，前台加载 174 个模块、后台加载 87 个模块，全都来自成品目录或 Windows。窗口和后台正常退出，回执为 `GPTWork/installer-transfer-context-20261128/run-71767467/verification.json`。独立无开发工具 Windows 环境和正式安装标识仍待实测。

## 历史版本 1b899eb

`GPTWork/installer-result-sort-20261128/source/GPTWork/installer-win-x64-c09329df1efe/AbaqusTools-0.1.0-win-x64-setup.exe` 对应应用提交 `1b899eb`，版本 `0.1.0`，大小 126566445 字节，SHA-256 为 `99e0dcb315735bcbb380ff8bc35d4936186af71dd3b6257504e21cc50938ff59`，尚未签名。

本机使用独立安装标识从 `5a056db` 升级，通过 8 项检查。中文向导完成安装，1698 个负载文件与清单逐项一致，67 份文档的 752 个相对文件链接均可达。升级前 1 份、卸载前 16 份数据的摘要保持一致，安装、升级和中文向导三份日志均无异常。免安装程序另在 G 盘独立中文目录启动，PATH 中无 Python、.NET 与 Abaqus，加载的 174 个前台模块和 87 个后台模块均来自程序目录或 Windows。前后台正常关闭。回执在 `GPTWork/installer-result-sort-20261128/verified.json` 和 `GPTWork/installer-result-sort-20261128/run-a65f9f13/verification.json`。独立无开发工具 Windows 上的实际安装仍待验证。

## 历史版本 5a056db

`GPTWork/installer-current-5a056db-20261128/source/GPTWork/installer-win-x64-614f8574eaba/AbaqusTools-0.1.0-win-x64-setup.exe` 对应干净提交 `5a056db`。版本 `0.1.0`，大小 126550417 字节，SHA-256 为 `83fbed26b3717249e800943721281c56a8a582b05817dc17207c5c034f765ddd`，签名状态为 NotSigned。

在 G 盘用独立安装标识完成了从 `de319eb` 到 `5a056db` 的 8 项生命周期核对，以及普通中文向导的选择目录、返回、安装和完成操作。已安装的 1698 个负载文件与清单一致，安装目录内 README 的提交号正确，4 个相对链接可打开。升级和卸载分别保留 1 份及 16 份已核对的应用数据。三份安装日志均无异常或被抑制的弹窗。回执 `GPTWork/installer-current-5a056db-20261128/verified.json`。本机未使用正式标识安装，独立无开发工具的 Windows 环境仍待验收。

## 历史版本 de319eb

`GPTWork/installer-current-de319eb-20261128/source/GPTWork/installer-win-x64-fe1496f9bb88/AbaqusTools-0.1.0-win-x64-setup.exe` 和免安装入口 `GPTWork/release-win-x64-dc388a3f01e3/AbaqusTools/AbaqusTools.WinUI.exe` 均来自干净提交 `de319eb`。安装程序版本为 `0.1.0`，大小为 126532011 字节，SHA-256 为 `91b0e57e9c908a19f3ae5d7fe89f322f7e7e63440fee2f2db6db03562856ff96`，签名状态为 NotSigned。

11 月 28 日使用同一负载的独立测试标识，从 `c847e05` 升级至 `de319eb` 的 8 项检查一次通过。后台运行中会阻止升级或卸载。正常退出后升级成功，从安装目录启动的后台可读取资源和队列并安全退出。普通中文向导也已实测，返回上一步能保留选定的 G 盘中文目录，安装后的 1697 个文件及发布清单逐项匹配。

升级前 1 个、卸载前 16 个应用数据文件的 SHA-256 保持一致，用户保留文件仍可读回。旧版安装、新版升级和新版中文向导三份日志均为零异常、零抑制弹窗，测试登记及快捷方式已移除，无残留自有进程。完整回执为 `GPTWork/installer-current-de319eb-20261128/verified.json`。正式标识安装及无 Python/.NET SDK 的独立 Windows 环境仍待验收。

## 历史版本 c847e05

`c847e05` 的 Windows x64 安装程序为 `GPTWork/installer-current-c847e05-20261128/source/GPTWork/installer-win-x64-b126d3e5d7af/AbaqusTools-0.1.0-win-x64-setup.exe`。免安装入口为 `GPTWork/release-win-x64-af10c900a70a/AbaqusTools/AbaqusTools.WinUI.exe`。安装程序版本为 `0.1.0`，大小为 126526172 字节，SHA-256 为 `c99641885bcba69db3c938ecc57a73dbec7ee40dc4ade8441bc45f8d14c76f97`，签名状态为 NotSigned。

在 G 盘独立测试标识下，从 `a20e35d` 升级至 `c847e05` 的 8 项验收通过，覆盖运行中拒绝升级和卸载、正常退出后升级、从安装目录读取资源和队列、卸载后保留数据。普通中文向导另验选择目录、返回上一步、安装与完成。安装后的 1697 项负载及发布清单逐文件匹配。升级前 1 个、卸载前 16 个应用数据文件的 SHA-256 均保留，用户文件仍在，测试登记及快捷方式均已清除。旧安装、新升级、新向导三份日志均记录成功，异常与受抑制弹框均为 0。完整回执在 `GPTWork/installer-current-c847e05-20261128/verified.json`。正式标识安装与独立无 Python/.NET SDK 的 Windows 环境仍待验收。

同一负载在整套回归运行期间曾出现两次后台启动超时。首次从已安装目录启动和在原配置重试都未能及时取得连接信息，日志从创建至最后一次写入分别为 28.12 秒与 55.04 秒。测试标识最终正常卸载，失败回执及重试记录在 `GPTWork/installer-current-c847e05-20261128/source/GPTWork/installer-lifecycle-1294727b3979`。整套运行结束并静置两分钟后，在全新 G 盘配置中以相同宿主默认时限启动免安装包，1.837 秒取得已认证的健康响应，2.213 秒完成正常退出。随后在另一个空目录执行上述 8 项检查。从安装目录启动、查询资源与队列并退出，日志跨度为 5.34 秒。冷启动记录在 `GPTWork/installer-current-c847e05-20261128/cold-f38b95c6/verification.json`。并发负载下的启动稳定性仍需跟踪。

## 历史版本 a20e35d

`a20e35d` 的 Windows x64 安装程序为 `GPTWork/installer-current-a20e35d-20261128/source/GPTWork/installer-win-x64-49d5f499d912/AbaqusTools-0.1.0-win-x64-setup.exe`。免安装入口为 `GPTWork/release-win-x64-3f6c82f499dd/AbaqusTools/AbaqusTools.WinUI.exe`。安装程序版本为 `0.1.0`，大小为 126508806 字节，SHA-256 为 `3a7a84787ce1cf99262175b9695234199180a05210e3c360fdefab32f28be79e`，签名状态为 NotSigned。

11 月 28 日使用相同负载及独立测试标识，在中文向导中选择 G 盘中文目录、返回上一步，再完成安装。安装后的 1697 个文件和发布清单均与源包一致。另从 `850f753` 升级到 `a20e35d`，8 项检查通过。后台运行中会拒绝升级和卸载，正常退出后升级成功。从新安装目录启动后，正式客户端可读取资源和队列并安全退出。

升级前的 1 个、卸载前的 16 个应用数据文件均逐项核对 SHA-256，用户自行保留的文件也可读回。测试安装登记和快捷方式已移除，无残留自有进程。旧版安装、新版升级、新版中文向导三份日志均记录了安装成功，异常和被抑制的弹窗均为 0。回执为 `GPTWork/installer-current-a20e35d-20261128/verified.json`。正式标识的安装生命周期及独立无 Python/.NET SDK 的 Windows 机器仍待验收。

## 上一版 850f753

`850f753` 的 Windows x64 安装程序为 `GPTWork/installer-current-850f753-20261128/source/GPTWork/installer-win-x64-0edc18aea1b3/AbaqusTools-0.1.0-win-x64-setup.exe`。免安装入口为 `GPTWork/release-win-x64-d76d5340404a/AbaqusTools/AbaqusTools.WinUI.exe`。安装版本为 `0.1.0`，大小为 126495187 字节，SHA256 为 `ee8ad45b2464f0d9ca8c6b9c8f44f1a01ed866e9dfbb5643fdf09a8c5f68ee45`，签名状态为 NotSigned。

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
