# 原生浏览侧栏选择回归

直接编译生产 `WorkbenchExplorerHost` XAML、代码和数据契约，在测试自身的离屏窗口中运行；不启动工作台、控制面或求解器，不读取用户配置或模型。原有54项检查中，18项为深浅主题添加/编辑/连接服务器表单的等高、对齐、无横向溢出和无端口步进按钮，13项为真实ListView与侧栏可见字段变化判定的100次相同刷新、字段通知、容器/勾选/多选/滚动保持与重排删除；其余23项中，4项测量标题刷新/收起按钮在副标题与主操作显示/隐藏组合下的实际边界，6项检查深浅主题下六级缩进、文件夹/文件图标绑定以及折叠再展开后的选择，4项用真实InfoBar复现24 DIP顶部空白，验证关闭释放边距、打开与再关闭恢复；其余9项覆盖选择回调同步发布新快照、连续100次更新、节点移除/返回、上下文恢复和下一次真实TreeView选择事件。它不代表业务页鼠标、截图、CSV预览或导出验收。

2026-11-24新增56项生产QueueTableView/QueueTableRow检查，总计110项：深浅主题、两表、900/1600/2300 DIP下列边界、数值居中、选中不偏移、长文本约束、浅色行列线、表头/表体同步横向滚动，以及正式勾选与ListView选择双向同步。直接编译生产控件，不复制表格模板；实际工作台候选页的鼠标与截图证据另见TASK-004。

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

项目路径有空格时应将传入程序的完整回执路径作为一个带引号的参数。只在进程退出0、回执status为passed且110项齐全时算通过。受限环境可使用已经验证的NuGet缓存；当前工作站缓存为GPTWork/nuget-release-packages，构建时可同时传RestorePackagesPath/RestoreSources指向它。构建或无新回执的异常退出均不得写成通过，保留原失败产物。
