# 当前状态与接续点

更新于2026-11-19。完整WinUI迁移仍待八页业务、真实工程/SSH及目标机验收；本轮只完成侧栏视觉与说明修复。实际源码、回执及用户确认优先。

## 当前改动与证据

- 用户确认此前完整5497f45cfec3顶部空白消失、密度合适、侧栏收起展开正常；本轮又确认按钮已对齐、树缩进正常，并澄清模型甲是结果文件夹。
- 刷新/收起位于同一标题Grid，外框30×30，刷新图标14、折线16；收起保留40 DIP入口和既有偏好/草稿/任务。
- 树每级缩进16改10，减少箭头及图标旁空隙。保留目录/文件图标差异，实际ODB文件使用文件图标；模型结果目录副标题改成中文，类型和路径不变。
- 23项生产原生控件检查通过：`GPTWork/sidebar-final-checks-20261119/verification.json`，PID229496退出0；六级文字X为53/63/73/83/93/103 DIP，深浅主题下展开后选择通过。源码发布日志`GPTWork/winui-sidebar-final-publish-20261119.log`成功。最终shell与文档回归86项通过：`GPTWork/sidebar-final-regression-fixed-20261119.log`。
- 旧完整包依赖/安装证据和此前单CSV预览/80行完整导出证据保留，不扩大成新版本全部业务通过。截图仍超时，最终图标比例的视觉确认与自动几何检查区分记录。

## 当前输出

| 项目 | 当前事实 |
|---|---|
| 最新开发输出 | `GPTWork/winui-sidebar-final-20261119`，包含上述修复，配套后台来自既有完整包；不是重新生成完整安装候选。 |
| 完整目录候选 | `GPTWork/release-win-x64-5497f45cfec3/AbaqusTools`，源码758f1cc，1687文件/19worker/15应用资源和依赖验证通过；尚不含本轮侧栏修复。 |
| 安装候选 | `GPTWork/installer-win-x64-b4ca03cbe0c8/AbaqusTools-0.1.0-win-x64-setup.exe`，未签名、正式身份未安装；同负载测试身份生命周期7818c66a5988通过。 |
| 文档 | README、RepoWiki、功能索引与交接已维护；包内是构建时快照，仓库记录后续验收，未另发GitHub Wiki网站。 |

## 准确续接点

1. 最新测试窗口来自winui-sidebar-final-20261119，窗口1442068，原生205860、后台201772、子221920；AX已确认中文目录说明和后台连接，窗口保留供查看。独立配置`GPTWork/native-sidebar-final-20261119/result-browser`。由`GPTWork/native_sidebar_final_20261119.py capture result-browser`记录后台身份；关闭后才能执行finish核对。不要重复启动同一profile。
2. 旧205808、187916、197448均连同自有后台核验结束；227408前端已退出，其空闲后台226912/193812经正式idle关闭协议收尾。各自verification.json确认描述符移除及两份日常JSON未改。API关闭只证明后台收尾，不算该窗口的原生关闭流程通过。
3. 本轮代码/说明提交`8ac63ac7305bcad878980d2afc98456739ff9b93`已推送GitHub main，ls-remote与本地HEAD一致、提交后工作树干净。下一步从干净源码更新完整目录与安装候选；保留旧产物。相关失败、用户反馈和回执见[TASK-002](ACTIVE_TASKS/TASK-002-migration.md)及[TASK-004](ACTIVE_TASKS/TASK-004-ui-interaction.md)。
4. 顶部留白、按钮对齐、六级缩进的局部通过不代表完整业务验收。八页业务交互、日志拖选/复制、悬停说明、跨屏、工程任务和目标机仍需逐项完成；不要重复同一已通过检查代替这些缺口。

## 未完成的完整迁移范围

真实SSH/指纹/传输、GPU/MPI及工程负载，连续三级真实工程ODB链、真实worker中断，原生分组/图例/取消/大文件/回收站及复杂草稿，正式安装向导、签名与无开发环境目标机、负责人对等确认仍待。已有ODB关系最长两节点，不用兄弟分支或新求解补造三级链。见[交付核对](../06-testing/COMPLETION_AUDIT.md)、[功能索引](../03-features/FUNCTION_INDEX.md)。

## 约束

禁止向C盘放任何ODB；TEMP/TMP、basetemp及产物均用G盘GPTWork。G:\Job原模型只读，不启动求解、不修改集成仓库、不删除PySide6/日常配置/历史验收。控制面使用项目.venv，worker用Abaqus解释器。每完成一个功能，立即同步维护功能索引、说明、测试与交接；文档、代码、测试一起交付，局部通过不称整体迁移完成。
