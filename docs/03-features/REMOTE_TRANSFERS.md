# 远端浏览与文件传输（F009）

在计算资源页选择已连接的服务器，通过“浏览 / 下载”读取允许目录，通过“上传文件”发送本机文件。连接、主机指纹和目录范围共用F008的已验证会话；目录外路径拒绝访问。密码只用于当前登录，不写入配置、验收夹具或日志。

## 输入、结果与发布

传输请求包含上传/下载方向、来源、目标和是否覆盖。相同请求标识及参数返回原任务，不重复传输；复用标识但改变参数报冲突。成功返回实际路径和文件大小，页面显示已传字节及进度。独立文件传输记录仅在当前后台内存中，不承诺跨后台恢复。

上传先写同目录唯一`.part-*`文件。禁止覆盖时使用标准SFTP重命名，避免并发创建的目标被POSIX重命名覆盖。允许覆盖时优先使用POSIX原子重命名；Windows OpenSSH不支持时，通过同一已验证连接调用Windows文件替换。不会先删除旧目标再尝试重命名；路径通过Base64编码的JSON传递，中文、空格、引号和特殊字符按路径处理。该适配面向Windows SSH服务器。

下载先写本地同目录临时文件，使用可写句柄同步后再发布。2026-11-19真实SSH验收发现旧版本以只读句柄调用`fsync`，在Windows上报`Bad file descriptor`；修复为`r+b`。不覆盖时发布阶段仍拒绝后来出现的同名文件；允许覆盖时原子替换。

## 取消和错误

状态观察与文件传输分开处理。进入计算资源页时，连接准备最多等待30秒，取得后台后每次只读状态请求再单独限时10秒；冷启动或排队不再提前耗尽读取限时。只有用户取消观察或应用关闭才保留取消异常；状态读取超时返回可重试的`REMOTE_STATE_TIMEOUT`，不据此判断传输失败。

切走页面只停止进度观察，不向后台发送取消传输。原操作标识保留；返回时先按标识读取，即使它已结束且不在活动列表中，也显示实际终态。短暂读取失败显示“传输状态暂未确认”，保留进度和取消入口，每10秒或主动刷新时重试只读查询；未核对前禁用上传/下载入口，不自动重新提交。后端明确拒绝创建时显示“传输未开始”和原错误；只有已取得终态才显示传输成功/失败/取消。后台已无原记录时保留“结果待核对”提示，不伪造终态，也不无限查询不存在的旧标识。

在传输及发布前检查取消；取消或未完成的发布清理本次临时文件，保留来源和已有目标。发布成功后才到达的取消不能把实际已保存文件改标“已取消”。若提交响应因断网丢失，不凭进度100%认定成功，需重新登录并核对目标。文件替换不代表整机断电或存储设备故障下的事务保证。

权限、目录不存在、目标重名、路径越界和连接中断均返回失败原因。覆盖失败不预先删除旧文件。远端安全替换的依据是[Paramiko重命名约定](https://docs.paramiko.org/en/stable/api/sftp.html)和[Windows File.Replace](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.replace?view=netframework-4.8.1)。

## 实现与验收

- `modules/submitter/remote_connection.py` / `list_directory`、`upload_file`、`download_file`、`_sftp_rename`、`_remote_replace_file_script`：实际SSH、路径和文件发布。
- `modules/control_plane/remote_transfers.py` / `RemoteTransferOperationManager`：串行传输、取消、去重和状态。
- `winui/AbaqusTools.WinUI/Services/ControlPlaneHost.cs` / `ReadRemoteStateAsync`、三个远端状态GET和`PollRemoteTransferUntilTerminalAsync`；`winui/AbaqusTools.WinUI/Pages/ComputeResourcesPage.xaml.cs` / `RecoverTransfersAsync`、`ObserveTransferAsync`、`OnPageUnloaded`：独立计时、状态重查与页面观察取消。前端输入/输出及HTTP协议未更改，不改变SSH登录或实际传输发布。
- `tests/winui_host/RemoteObservationChecks.cs` / `RunAsync`复现旧10秒预算错误并验证三个读取、超时分类、调用者取消、后续恢复；`RunApiAsync`和`tests/winui_host/test_shutdown_api.py`用生产C#客户端/真实HTTP/替身传输验证取消观察后同一任务仍运行、没有新增传输、释放后成功。该证据不等同实际SSH中断或原生切页操作；`tests/winui/test_shell_contract.py`另检查页面接线。
- `tests/submitter/test_remote_transfers.py`：实际Windows同步/替换、中文特殊路径、锁定旧文件保护、同名竞争及提交前后取消；`tests/control_plane/test_remote_transfers_api.py`、`test_remote_server_responsiveness.py`：API和资源快照。
- 本轮真实连接已获用户确认并由原生页面核对：192.168.1.202，64线程、约159.9GB内存、Abaqus命令可用。D:\Abaqus_Cal目录读取及63,488字节中文空格路径上传通过。旧完整包c6999a8e1c8e下载失败现场在`GPTWork/ssh-transfer-b1a0b0448869/operations.json`，不能视为完整传输通过。

修复通过11项专项及78项文档/连接/发布检查，已进入干净e78fa5e完整包2c18c11259b2。192.168.1.202上10项真实传输操作已通过：两向传输/覆盖/禁止覆盖、重复请求、上传与下载取消、范围外拒绝；下载取消保留旧目标，临时文件清理通过。回执GPTWork/ssh-transfer-fixed-8bd4b86f8d98/verification.json及download-cancel-verification.json，合成测试文件保留。准确源码、包及进程状态见[当前状态](../08-handoff/CURRENT_STATUS.md)和[TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。正式API传输不代替传输对话框的完整鼠标验收。
