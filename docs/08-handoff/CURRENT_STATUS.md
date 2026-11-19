# 当前状态与接续点

更新于2026-11-19。侧栏完整包/安装及有限原生核验已有证据；新增用户授权的简单实体三级重启动实际计算、串联合并与后台恢复通过。用户已完成SSH登录；真实下载发现Windows文件同步缺陷，源码已修复，正在构建新包复验。整体WinUI迁移仍待完整业务和真实环境验收。实际源码、回执及用户确认优先。

## 当前版本

| 项目 | 当前事实 |
|---|---|
| 已打包源码 | `dd5fe12290d6b579ae1145dd03e6db3e8de2123d`，干净且已推送；包含8ac63ac侧栏修复及文档。 |
| 完整目录 | `GPTWork/release-win-x64-c6999a8e1c8e/AbaqusTools`，1687清单文件/19worker/15应用资源，全摘要和包内依赖通过。 |
| 正式标识安装候选 | `GPTWork/installer-win-x64-d7c766a02a78/AbaqusTools-0.1.0-win-x64-setup.exe`，126128448字节，未签名且未安装正式身份。 |
| 隔离安装验证 | 同负载测试e8cf272edafb从上一完整d597341f22be升级，`GPTWork/installer-lifecycle-9dce03ed6016/verification.json` verified；无自有进程/登记残留。 |
| 原生核验 | 完整包结果浏览/后处理加载与Ctrl+7/8往返、侧栏收起恢复和输入保留、正常退出已核对；截图/鼠标仍受工具限制，完整业务未验完。 |
| 文档 | README、RepoWiki、功能索引、说明和交接持续同步。包内为dd5fe122构建时快照，最终验收追加到仓库；未另发GitHub Wiki网站。 |

摘要、产物与失败详情见[TASK-002](ACTIVE_TASKS/TASK-002-migration.md)，机器回执`GPTWork/sidebar-release-verification-20261119/verification-summary.json`。旧5497f45cfec3/b4ca03cbe0c8保留历史追溯，不再作为最新候选。

新增三级验收回执为`GPTWork/sequential-result-batch-0983d4f23773/verification.json`及final-readonly-check.json，96项定向回归通过；该三级验收轮仅扩展C#验收入口与文档；当前SSH修复改变生产代码，需构建新完整包。当前提交/推送以同目录git-delivery.json实际记录为准。

## 当前界面证据

- 用户已确认顶部空白消失、密度合适、侧栏收起展开正常；本轮又确认按钮对齐和树缩进正常，并澄清模型甲为结果目录。
- 两按钮同一标题行，外框30×30；刷新14号、折线16号，收起保留40 DIP入口。树每级缩进16改10，目录/文件图标明确，内部目录类型换成中文说明。
- 23项生产控件、86项shell/文档检查通过，分别见sidebar-final-checks-20261119和sidebar-final-regression-fixed-20261119.log。发布验证不重复旧全量回归，不把局部检查说成八页业务通过。
- 新完整包原生4个结果范围、中文说明、包内后台连接、键盘切换/侧栏与退出均有实际证据。鼠标报coordinate input geometry is unavailable，截图报window capture timed out；最终14号图标的像素确认没有冒称通过。

## 准确续接点

1. 上一侧栏发布阶段的构建、安装和原生句柄均终态。开发205860/201772/221920与完整包227292/212816/226444已按创建时间核对结束，描述符移除，两份日常JSON摘要未变；回执分别在native-sidebar-final-20261119及native-sidebar-release-20261119/result-browser/verification.json。该侧栏阶段没有保留窗口；本轮SSH窗口另见第3项。
2. 新包的清单、依赖、隔离安装和有限原生核验已完成。不要仅因验收文档追加而重打相同包或重跑全量测试；需要复用时先确认原进程终态，再建立新的独立G盘profile，不能重复launch旧profile。
3. 192.168.1.202已由用户在应用登录，原生7096140显示在线和资源，前台203708/后台194292及190748保留。目录浏览和上传通过；旧包c699下载报Bad file descriptor。源码已修复，78项文档/连接/发布检查通过；需新包与重新登录后验收下载，不修改旧包运行态。精确现场和传输文件路径见TASK-002顶部。
4. 2026-11-19用户授权的三级算例three-restart-9ae3bd6cf4e9已完成三个求解，89086已退出0。串联合并sequential-result-batch-0983d4f23773得到3步/15帧、场/历史及解析值通过；正常后台重开未重放，源及发布摘要未变，203016/221036均正常退出。无需再求解或重复相同验收。原始G:\Job仍只读；不提前退役PySide6或切换默认入口。前次提交/推送回执仍见`GPTWork/sidebar-release-verification-20261119/git-delivery.json`。

## 完整迁移范围与约束

完整范围见[交付核对](../06-testing/COMPLETION_AUDIT.md)、[功能索引](../03-features/FUNCTION_INDEX.md)。真实合并校验进程取消和意外退出已通过（real-merge-interruption-74bb9bec2c53）；后台崩溃时真实worker仍活跃的情况及原生分组/图例/取消/大文件/回收站及复杂草稿、目标机/正式向导与负责人对等确认仍待。按用户新增授权计算连续三级简单算例；必须区分真实求解的简单模型、工程模型和原生交互，兄弟分支不算连续三级。

禁止向C盘放任何ODB；TEMP/TMP、basetemp及产物用G盘GPTWork。G:\Job原模型只读，不修改集成仓库，不删除PySide6/日常配置/历史验收。控制面用项目.venv，worker用Abaqus解释器。每完成一个功能，立即同步维护功能索引、文档、测试与交接，局部通过不称整体完成。
