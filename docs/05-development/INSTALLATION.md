# Windows 安装、升级与卸载（F026）

当前安装器是待发布候选；应用仍有原生业务页、真实环境和无开发环境目标机验收缺口，见[交付清单](../06-testing/COMPLETION_AUDIT.md)。使用 Inno Setup 7.1.1，官方编译器数字签名已验证；应用安装包暂未签名，不能把编译成功称为已签名正式发布。

2026-11-18最新正式标识候选为fa6e79921794，负载与安装器源码均为干净22e47f6，含当前作业结果路由及此前新建/菜单/草稿/按钮修正。包内依赖、正式主机及安装器来源/摘要/架构通过，NotSigned。相同负载的独立测试身份已通过初装、活动后台拒绝、升级保留旧版本/用户数据、开始菜单更新、安装后主机API及卸载保留用户文件，回执c027e16d589d；无残留测试进程/登记。正式标识未安装到用户默认目录，不能替代无开发环境目标机或原生向导验收。完整路径见[当前状态](../08-handoff/CURRENT_STATUS.md)，旧包保留。

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

本机隔离验证不能替代无开发环境目标机。正式身份、签名/SmartScreen及安装向导原生操作仍需验收。

## 工具依据

采用[按用户安装规则](https://jrsoftware.org/inno-setup/documentation/topic_setup_privilegesrequired.htm)，关闭[自动结束应用](https://jrsoftware.org/inno-setup/documentation/topic_setup_closeapplications.htm)，利用[安装/卸载事件](https://jrsoftware.org/inno-setup/documentation/topic_scriptevents.htm)检查前置条件和[文件回调](https://jrsoftware.org/inno-setup/documentation/topic_scriptinstall.htm)验证摘要。下载遵循[官方签名校验说明](https://jrsoftware.org/inno-setup/downloads/verify)。
