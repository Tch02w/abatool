# 远端浏览与文件传输（F009）

在计算资源页选择已连接的服务器，通过“浏览 / 下载”读取允许目录，通过“上传文件”发送本机文件。连接、主机指纹和目录范围共用F008的已验证会话；目录外路径拒绝访问。密码只用于当前登录，不写入配置、验收夹具或日志。

## 输入、结果与发布

传输请求包含上传/下载方向、来源、目标和是否覆盖。相同请求标识及参数返回原任务，不重复传输；复用标识但改变参数报冲突。成功返回实际路径和文件大小，页面显示已传字节及进度。独立文件传输记录仅在当前后台内存中，不承诺跨后台恢复。

上传先写同目录唯一`.part-*`文件。禁止覆盖时使用标准SFTP重命名，避免并发创建的目标被POSIX重命名覆盖。允许覆盖时优先使用POSIX原子重命名；Windows OpenSSH不支持时，通过同一已验证连接调用Windows文件替换。不会先删除旧目标再尝试重命名；路径通过Base64编码的JSON传递，中文、空格、引号和特殊字符按路径处理。该适配面向Windows SSH服务器。

下载先写本地同目录临时文件，使用可写句柄同步后再发布。2026-11-19真实SSH验收发现旧版本以只读句柄调用`fsync`，在Windows上报`Bad file descriptor`；修复为`r+b`。不覆盖时发布阶段仍拒绝后来出现的同名文件；允许覆盖时原子替换。

## 取消和错误

在传输及发布前检查取消；取消或未完成的发布清理本次临时文件，保留来源和已有目标。发布成功后才到达的取消不能把实际已保存文件改标“已取消”。若提交响应因断网丢失，不凭进度100%认定成功，需重新登录并核对目标。文件替换不代表整机断电或存储设备故障下的事务保证。

权限、目录不存在、目标重名、路径越界和连接中断均返回失败原因。覆盖失败不预先删除旧文件。远端安全替换的依据是[Paramiko重命名约定](https://docs.paramiko.org/en/stable/api/sftp.html)和[Windows File.Replace](https://learn.microsoft.com/en-us/dotnet/api/system.io.file.replace?view=netframework-4.8.1)。

## 实现与验收

- `modules/submitter/remote_connection.py` / `list_directory`、`upload_file`、`download_file`、`_sftp_rename`、`_remote_replace_file_script`：实际SSH、路径和文件发布。
- `modules/control_plane/remote_transfers.py` / `RemoteTransferOperationManager`：串行传输、取消、去重和状态。
- `tests/submitter/test_remote_transfers.py`：实际Windows同步/替换、中文特殊路径、锁定旧文件保护、同名竞争及提交前后取消；`tests/control_plane/test_remote_transfers_api.py`、`test_remote_server_responsiveness.py`：API和资源快照。
- 本轮真实连接已获用户确认并由原生页面核对：192.168.1.202，64线程、约159.9GB内存、Abaqus命令可用。D:\Abaqus_Cal目录读取及63,488字节中文空格路径上传通过。旧完整包c6999a8e1c8e下载失败现场在`GPTWork/ssh-transfer-b1a0b0448869/operations.json`，不能视为完整传输通过。

修复通过11项专项及78项文档/连接/发布检查；新完整包与真实上传/下载重验仍待。准确源码、包及进程状态见[当前状态](../08-handoff/CURRENT_STATUS.md)和[TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。原生登录确认不代替传输对话框的完整鼠标验收。
