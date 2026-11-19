# 当前状态与接续点

更新于2026-11-19。真实SSH传输修复及10项操作通过；用户新增服务器表单与队列刷新/选区/名称问题已实现，54项生产控件和211项相关回归通过，正进行业务确认和收尾。整体WinUI迁移仍未完成；源码、实际回执及用户确认优先。

## 当前版本

| 项目 | 当前事实 |
|---|---|
| 已提交完整包源码 | e78fa5e53288dea95e21e5e36eb200554257eae9，干净构建且已推送。 |
| 最新完整目录 | GPTWork/release-win-x64-2c18c11259b2/AbaqusTools：1688清单文件、19worker、15应用资源，全摘要与包内依赖通过；含SSH修复，尚不含本轮表单/队列修改。 |
| 安装候选 | GPTWork/installer-win-x64-967f065cfdd7/AbaqusTools-0.1.0-win-x64-setup.exe，126137963字节，未签名、未安装；此次负载未重做生命周期。 |
| 当前开发输出 | GPTWork/queue-dialog-final-native-20261119，服务器表单、队列定向更新及原生列表保持；生产构建0警告/0错误。当前名称及命令规则使用项目Python源码。 |
| 文档 | README、RepoWiki、功能索引、说明和交接持续同步；未另发GitHub Wiki网站。 |

旧c6999a8e1c8e下载故障已证实，不能作为最新候选。完整发布及真实传输回执见GPTWork/ssh-fixed-delivery-20261119/verification-summary.json和[TASK-002](ACTIVE_TASKS/TASK-002-migration.md)。

## 已有实际证据

- 三级简单实体链实际求解、串联合并最终3步/15帧、全场/历史/解析值、源摘要及正常后台恢复通过，sequential-result-batch-0983d4f23773/verification.json。
- 真实合并校验worker取消/意外退出通过，real-merge-interruption-74bb9bec2c53/verification.json；不等于后台崩溃留下活worker已验收。
- 用户在新包完成SSH登录；中文空格路径两向传输/覆盖/禁止覆盖、去重、上传/下载取消、范围外拒绝共10项通过，ssh-transfer-fixed-8bd4b86f8d98两份verification回执。测试文件保留，不触碰服务器已有计算。
- 用户此前已确认顶部空白消失、密度合适、侧栏展开收起、按钮对齐和树缩进。最终14号刷新图标的像素与所有业务交互未冒称通过。
- 新表单32 DIP等高/同行对齐/固定宽度内完整显示与无端口箭头、真实ListView连续100次更新、选中/勾选/滚动及重排/删除共54项控件检查通过。业务窗口鼠标与截图仍受工具限制，不能将控件证据等同全页验收。

## 准确续接点

1. 当前在处理用户追加的服务器表单、队列增量刷新与Abaqus命名规则，见[TASK-004](ACTIVE_TASKS/TASK-004-ui-interaction.md)顶部；开发及测试代码、文档尚待最终收尾提交。待确认的新窗口9249544（前台9528，创建时间1795060504.5837119）使用GPTWork/native-queue-dialog-desktop-20261119/compute-resources独立配置；两个合成加号名称候选已通过正式API加入，无异常、无求解。processes.json和queue-fixture.json有精确身份/结果；已请用户核对表单和等待15秒后的候选选择。
2. 已登录旧SSH窗口5379070及前台227820/后台135288/197572保留，不擅自关闭或转移密码。其profile为native-ssh-fixed-20261119/compute-resources，显示与传输检查使用该版本，不冒称其含新界面修复。旧203708已结束、后台194292/190748经idle协议结束，不能称原生正常关闭；回执在native-ssh-20261119。
3. 首次受限桌面测试218736及其后台已按身份/独立profile确认结束，无残留；其不在CUA清单的失败现场保留于native-server-dialog-20261119/compute-resources/unlisted-launch-cleanup.json。当前CUA仍报coordinate input geometry is unavailable、window capture timed out和failed to activate captured window，已重新定位重试，未绕过工具操作。
4. 当前测试句柄以TASK-004后续记录为准。当前54项控件PID220820退出0（原51项205080也已退出0）；此前41项224740退出0；开发构建均终态。只对新变更和失败做定向回归，不重复求解三级链或已通过SSH传输；先核对原句柄再启动长任务。

## 完整迁移范围与约束

完整范围见[交付核对](../06-testing/COMPLETION_AUDIT.md)、[功能索引](../03-features/FUNCTION_INDEX.md)。真实SSH异常/远端任务、GPU/MPI、原生分组/图例/取消/大文件/回收站及复杂草稿、目标机/正式向导与负责人对等确认仍待。用户暂无无Python/.NET SDK目标机。保留PySide6对照和回滚入口，不切换默认入口。

禁止向C盘放任何ODB，TEMP/TMP、basetemp与产物使用G盘GPTWork。原始G:\Job模型只读，不修改集成仓库，不删除日常配置或历史验收；控制面使用项目.venv，worker使用Abaqus解释器。每完成一个功能，立即同步维护功能索引、文档、测试与交接，局部通过不称整体完成。
