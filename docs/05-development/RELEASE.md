# Windows 发布构建（F026）

当前产物为 Windows x64 完整目录候选。必须复制整个目录；无开发环境机器验收和正式安装包评审仍需完成。Abaqus 本身和许可证由目标机器提供，不随本软件分发。

## 开发者构建

在 Windows 上使用本项目 Python 3.14 `.venv` 和 .NET 10 SDK：

```powershell
.\.venv\Scripts\python.exe packaging/build_release.py
```

命令每次在 `GPTWork/release-win-x64-*` 创建新目录，保留旧产物。先冻结 Qt-free 控制面，再用 Release、win-x64、SelfContained=true 发布 WinUI；同时带上 Windows App SDK 运行文件。构建日志分别为 `control-plane-build.log` 和 `winui-publish.log`。首次还原需要访问 NuGet；已用相同参数还原后，可附加 `--no-restore`。

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

实现依据：[PyInstaller 相对资源定位](https://pyinstaller.org/en/stable/runtime-information.html)、[Windows App SDK 自包含部署](https://learn.microsoft.com/en-us/windows/apps/package-and-deploy/self-contained-deploy/deploy-self-contained-apps)。Windows App SDK 自包含仍需另行启用 .NET 自包含，且发布文件必须整体分发。
