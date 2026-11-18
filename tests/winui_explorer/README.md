# 原生浏览侧栏选择回归

直接编译生产 `WorkbenchExplorerHost` XAML、代码和数据契约，在测试自身的离屏窗口中运行；不启动工作台、控制面或求解器，不读取用户配置或模型。13项检查中，4项用真实InfoBar复现24 DIP顶部空白，验证关闭释放边距、打开与再关闭恢复；其余9项覆盖选择回调同步发布新快照、连续100次更新、节点移除/返回、上下文恢复和下一次真实TreeView选择事件。它不代表业务页鼠标、截图、CSV预览或导出验收。

在项目根目录执行（TEMP/TMP与产物均放GPTWork）：

```powershell
$env:TEMP = "$PWD/GPTWork/explorer-test-temp"
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force -Path $env:TEMP | Out-Null
dotnet build tests/winui_explorer/Explorer.Tests.csproj -c Release -o GPTWork/explorer-control-checks
$check = Start-Process -FilePath "$PWD/GPTWork/explorer-control-checks/WorkbenchExplorer.ControlChecks.exe" -ArgumentList "$PWD/GPTWork/explorer-control-checks/verification.json" -WindowStyle Hidden -PassThru
if (-not $check.WaitForExit(40000)) { throw "检查未结束，先核对原进程 $($check.Id)，不要重复启动" }
if ($check.ExitCode -ne 0) { throw "原生检查失败：$($check.ExitCode)" }
Get-Content GPTWork/explorer-control-checks/verification.json
```

项目路径有空格时应将传入程序的完整回执路径作为一个带引号的参数。只在进程退出0、回执status为passed且13项齐全时算通过。受限环境可使用已经验证的NuGet缓存；当前工作站缓存为GPTWork/nuget-release-packages，构建时可同时传RestorePackagesPath/RestoreSources指向它。构建或无新回执的异常退出均不得写成通过，保留原失败产物。
