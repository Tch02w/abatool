# Windows 发布构建（F026）

本页说明如何构建和验证完整目录包。**当前候选路径与准确源码提交只以 [当前状态](../08-handoff/CURRENT_STATUS.md) 为准**；正式交付需要复制整个目录，不能单独复制exe。无开发环境目标机、原生业务页面、真实SSH/MPI及工程负载仍有待验项，候选包不等于正式安装版。Abaqus及许可证由目标机提供，不随软件分发。

实际进程验收工具均在GPTWork创建隔离夹具，仅操作自有进程，不启动Abaqus求解。运行前查看各工具说明，失败后先确认原句柄及进程状态，不因超时重复启动：

| 范围 | 验证入口 |
|---|---|
| 多作业资源准入与261行队列状态响应 | `packaging/verify_scheduler_load.py <完整目录或--source> <ControlPlaneHost.Tests.exe>` |
| 外部扫描期间读取、实际发现与自动完成监测 | `packaging/verify_external_scan.py <完整目录或--source> <ControlPlaneHost.Tests.exe>` |
| 归档中断后同一执行恢复 | `packaging/verify_archive_recovery.py <完整目录或--source> <ControlPlaneHost.Tests.exe>` |
| 归档完成回调丢失后的提醒补发 | `packaging/verify_archive_notifications.py <完整目录或--source> <ControlPlaneHost.Tests.exe>` |
| 内存采样、持久历史与结束提醒 | `packaging/verify_local_memory.py --bundle <完整目录> --notifications --host-client <当前C#主机测试DLL>` |

跨卷验收在归档恢复命令后追加 `--destination-root <已存在的不同卷GPTWork目录> --payload-mib 128`，每个合成ODB为128MiB，实际复制8MiB时中断自有生产者。只用新建隔离目录，不选择工程结果目录；保留目标副本、中断现场和回执。工具核对真实设备号不同，源目录清理只涉及本次生成的文件。当前G:→C:结果见TASK-002，不代表断电事务或工程多GiB负载。

需要覆盖独立文件路径时，为资源准入命令追加 `--distinct-held`；需要覆盖归档单槽位竞争时，为归档命令追加 `--parallel-recovery` 并使用当前主机测试客户端。后者只对明确未受理的忙碌409等待，不重试超时/未知受理结果，不能通过增加客户端超时掩盖状态读取问题。

资源准入夹具声明CPU/内存请求，但helper仅使用少量内存等待；它不能证明真实Abaqus/MPI满载或网络目录性能。成功回执必须核对范围、原输入摘要和自有进程结束。源代码检查、打包依赖和正式客户端通过也不能代替原生业务操作。最终回执与保留的失败见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md) 与 [验收记录](../06-testing/VALIDATION.md)。

## 开发者构建

在 Windows 上使用本项目 Python 3.14 `.venv` 和 .NET 10 SDK：

```powershell
.\.venv\Scripts\python.exe packaging/build_release.py
```

命令每次在 `GPTWork/release-win-x64-*` 创建新目录，保留旧产物。先冻结 Qt-free 控制面，再用 Release、win-x64、SelfContained=true 发布 WinUI；同时带上 Windows App SDK 运行文件。构建日志分别为 `control-plane-build.log` 和 `winui-publish.log`。首次还原需要访问 NuGet；已用相同参数还原后，可附加 `--no-restore`。

发布目录使用随机唯一名称并继承项目目录权限。Windows Python 3.14 的 `tempfile.mkdtemp` 使用仅创建者可访问的权限，因此不用于最终发布目录；构建账户与使用账户不同时，交付前必须从使用账户读取清单及程序文件。已有候选的权限不被自动更改。

产物 `AbaqusTools` 包含：

- `AbaqusTools.WinUI.exe`、.NET 与 Windows App SDK 运行库。
- `control-plane/AbaqusTools.ControlPlane.exe` 及 `_internal` 依赖目录；保留后处理默认配置和全部 Abaqus worker 脚本的相对目录。
- README、Wiki 与交接文档；`release-manifest.json` 记录文件大小/SHA256、源提交及构建时工作区是否有未提交修改。
- `THIRD_PARTY_NOTICES` 保留 Python 及主要 Python 运行依赖的许可证/声明文件和版本清单；.NET 的声明随官方发布文件保留。

不打包 PySide6、项目虚拟环境、模型、队列数据库、凭证或用户配置。文件清单只证明产物内容，不能替代运行验收。

## 启动与配置

在目标目录运行 `AbaqusTools.WinUI.exe`。默认优先使用同目录的 `control-plane`；缺失该目录内的可执行文件会明确报错，不应悄悄使用上层源码环境。开发构建仍向上定位项目 `.venv`。显式 `ABAQUS_TOOLS_ROOT` 优先；如设置 `ABAQUS_TOOLS_PYTHON`，它应与有效源码根目录配套，纯目录包不支持借用外部 Python 执行隐藏源码。

后台服务继续使用原有 loopback 随机端口、随机 token、共享服务重连与安全关闭协议。应用数据保存在用户目录，替换发布目录不会主动清除队列和配置；升级前退出应用并等待后台任务结束。此处没有自动更新或卸载程序。

## 候选验证

1. 在复制/移动后的目录验证文件清单，确认没有 `.venv`、PySide6、用户数据；每次验收使用独立数据目录。
2. 调用包内诊断（输出父目录需可写）：

   ```powershell
   .\control-plane\AbaqusTools.ControlPlane.exe --check-bundle <检查输出父目录>
   ```

   它使用包内运行时验证默认配置、worker 文件、GIF、Agg 图表、工作簿预览、SSH 加密依赖与 Qt-free 导入。生成独立 `bundle-probe-*` 目录；不连接服务器、不读取 SSH 密钥、不启动求解。
3. 开发验收通过 `tests/winui_host/Program.cs` 的 `--launch-bundle <发布目录> <独立运行数据目录>` 分支，使用正式 C# 主机启动包内服务、检查资源/队列 API、验证空闲退出。不会连接用户的默认控制面。附加 `--odb <既有ODB>` 时，先将该文件复制到独立目录，再通过正式 API 调用包内 Abaqus 兼容性 worker，并核对副本 SHA256 不变；需设置 `ABAQUS_TOOLS_ABAQUS_COMMAND` 和 `ABAQUS_TOOLS_ABAQUS_RELEASE`，不执行求解。
4. 在无 Python/.NET SDK 的机器上验证原生窗口、八页业务、真实 Abaqus 只读检查及 SSH。完成后才能宣称目标环境可用；当前机器上的冻结运行不能替代此项。

归档中断恢复可用 `packaging/verify_archive_recovery.py <完整目录> <ControlPlaneHost.Tests.exe>` 验证；用 `--source` 替代完整目录先检查源码后台。它只在 GPTWork 创建非工程夹具，记录并中断自己创建的归档进程，核对原生跨进程锁、完整副本复用、部分清理恢复、正式 C# 客户端和第二次重启不重放，最后保存 `verification.json`。Windows 虚拟环境启动器可能有包装 PID，按自有父子链核对实际进程身份；不终止未知 Abaqus 进程。

合并记录的冻结运行验收可执行：

```powershell
.\.venv\Scripts\python.exe packaging/verify_merge_restart.py <完整AbaqusTools目录>
```

它在 GPTWork 创建独立用户数据和微小测试文件，使用固定返回失败的测试命令，实际启动/退出两次包内控制面，核对 SQLite 历史、重启去重、失败清理和退出预留；不调用 Abaqus、不访问真实模型。输出 `frozen-merge-recovery-*/verification.json`，不在报告中保存鉴权令牌。它不能代替真实 Abaqus 运行中断或原生页面验收。

后台突然退出、外部子进程仍存活时的批量恢复检查：

```powershell
.\.venv\Scripts\python.exe packaging/verify_batch_interruption.py <完整AbaqusTools目录>
```

该工具只创建独立测试后台与等待程序，记录其 PID/创建时间后中断自己启动的后台，保留子进程直到重启检查结束。核对原阶段中断、禁止重跑、后续阶段未提交，以及第三次启动仍恢复同一失败记录；最后释放测试子进程并确认自有进程退出。所有夹具、日志和回执保留在 `GPTWork/frozen-batch-interruption-*`，仅清除自有描述文件中的临时鉴权信息。三节点字节夹具不是真实 ODB，工具不调用 Abaqus、不启动求解，不证明真实连续三级链的数值正确性。若退出失败，应先读回执并核对原测试进程，不能重复启动测试或按程序名批量终止进程。

实现依据：[PyInstaller 相对资源定位](https://pyinstaller.org/en/stable/runtime-information.html)、[Windows App SDK 自包含部署](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/self-contained-deploy/deploy-self-contained-apps)。Windows App SDK 自包含仍需另行启用 .NET 自包含，且发布文件必须整体分发。

## 11 月 18 日批量恢复候选

上一轮本地目录为 `GPTWork/release-win-x64-6cbfd68f63f6/AbaqusTools`，来源干净提交 `9f5ff64`，含 F012 后台批量计划与恢复。用户账户完成 1647 文件/19 worker 核对、两次冻结后台启动去重、正式主机启动/API/退出及包内诊断。回执与准确边界见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。本轮尚无新 ZIP、二进制 GitHub Release 或无开发环境目标机器验收；源码推送被自动审批拦截，等待具体远端授权。旧窗口需正常退出后才可使用新目录，不能强制终止用户正在运行的任务。


### 11 月 18 日退出保护候选

前一阶段完整目录为 `GPTWork/release-win-x64-b53b0f4ca2b4/AbaqusTools`，来源干净提交 `aa0420f`，新增九类受管工作及线程收尾的退出保护，保留 GIF 两种播放模式和读取目录按钮修正。用户账户核对 1648 文件/19 worker，正式主机启动、资源/队列 API、安全退出与包内依赖检查通过。冻结任务检查使用隔离等待命令，证明运行中与停止调度后的收尾均阻止后台退出，结束后退出预留拒绝新任务；没有运行 Abaqus 或真实 SSH。准确回执与两次验收脚本失败记录见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

新包尚未完成原生业务页和无开发环境目标机器验收；没有覆盖仍打开的旧程序，也没有发布新 ZIP、安装程序或二进制 Release。GitHub 源码推送仍等待具体远端确认。

F028 提交参数的冻结验证：正式 C# 主机 `--launch-bundle <完整目录> <GPTWork隔离数据> --execution-options`，在包内后台执行预览、入队、旧式编辑保留和明确撤销参数，再核对正常退出；只保存微小 INP 夹具，不启动求解。实际本机/远端 Windows 参数回显由 `tests/control_plane/test_execution_options.py` 单独验证。

### 11 月 18 日连接状态响应候选

当前最新完整目录 `GPTWork/release-win-x64-f4d22485d254/AbaqusTools`，干净来源 `6890ffa`，包含 F008 慢通信期间的连接视图和错误显示修正。用户账户核对 1658 文件/19 worker，通过包内依赖、正式客户端启动/API/退出，以及冻结状态接口和两次启动的配置恢复。准确回执见 [验收记录](../06-testing/VALIDATION.md)；慢通信由源码隔离夹具验证，没有进行真实 SSH/原生点击。旧候选保持原样，未发布本轮 ZIP/安装程序/二进制 Release；包内文档是构建时快照，最终回执在源码仓库补记。


## 历史候选记录（仅供追溯）

以下段落保留原阶段记录；其中的“最新”只指当时阶段，不作为当前下载入口。

最新提醒补发候选为 `GPTWork/release-win-x64-10aba0ad350a/AbaqusTools`（干净e31a358），1662文件/19worker、依赖/正式主机、新提醒补发与原归档恢复真实进程验证通过。`packaging/verify_archive_notifications.py <完整目录或--source> <ControlPlaneHost.Tests.exe>` 只中断自己的微型生产者，清除夹具队列后核对正式客户端补发/已读和第二次重启，证据见[当前状态](../08-handoff/CURRENT_STATUS.md)。以下8791f815c891为前一归档恢复候选，保留原记录。

最新已验证完整目录为 `GPTWork/release-win-x64-8791f815c891/AbaqusTools`，干净源码6cb343d，1662文件/19worker、依赖、正式主机及归档中断恢复通过。前一89d3b6ab518e候选的状态读取超时和修正证据保留，详见[当前状态](../08-handoff/CURRENT_STATUS.md)及[验收记录](../06-testing/VALIDATION.md)。原生业务页面、跨卷大文件与目标机未验收，不是正式安装版。

当前产物为 Windows x64 完整目录候选。必须复制整个目录；无开发环境机器验收和正式安装包评审仍需完成。Abaqus 本身和许可证由目标机器提供，不随本软件分发。

最新已验证候选与当前开发差异以[当前状态](../08-handoff/CURRENT_STATUS.md)为准，下面有历史包回执，不应将后文每个“最新”都视为当前入口。当前 F028 新目录为 `GPTWork/release-win-x64-d1ad1556cf70/AbaqusTools`（干净 `35b2372`），1658 文件/19 worker、依赖及正式主机冻结参数流程验证通过；前一阶段 F027 的冻结通知证据保留。原生窗口和真实环境仍待验收，完整回执见 TASK-002。

提醒冻结验证使用项目解释器运行 `packaging/verify_local_memory.py --bundle <完整AbaqusTools目录> --notifications --host-client <当前C#主机测试DLL>`。它只在 GPTWork 创建隔离数据，实际启动两次包内后台及 96 MiB 等待 helper；验证两次取消提醒、已读确认、冷启动恢复和新的执行身份，不启动 Abaqus 或连接 SSH。后台、helper、连接文件必须确认结束/移除，保存 verification.json；不能以它代替原生弹层与真实求解验收。

最新目录为 **`GPTWork/release-win-x64-b2bb97c3929a/AbaqusTools`**（干净 `11ee6ff`），加入远端完成证据/稳定确认及日志去重，保留内存和此前界面修正。用户账户 1654 文件/19 worker 的完整清单、依赖探针和正式主机启动/API/退出通过。50 项相关检查含生产 PowerShell 本机夹具，不代表真实 SSH/远端求解或原生交互验收。以下是前阶段包记录，最终回执见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。

11 月 18 日本轮最新目录为 `GPTWork/release-win-x64-5a09eb59688b/AbaqusTools`，干净来源 `a4e8212`，包含本机内存观测/历史估计，以及共享调度、关闭/草稿、GIF 与读取按钮修正。用户账户核对 1653 文件/19 worker、依赖和正式主机启动/API/退出通过；冻结包实际 96 MiB helper 的两次后台启动、PID/创建时间/内存、历史恢复、明确重新排队及安全退出通过，详见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。没有调用求解，原生业务和目标机器仍未验收，旧候选保留。包内文档为构建时快照，最终验证回执补记于仓库。
