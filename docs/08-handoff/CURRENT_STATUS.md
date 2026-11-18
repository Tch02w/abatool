# 当前状态与接续点

更新于2026-11-18。整体WinUI迁移仍未完成验收，目标active；桌面验收已获授权。实际源码与运行回执优先；旧候选均保留追溯。

## 当前版本

| 项目 | 当前事实 |
|---|---|
| 源码 | `758f1cc06fb7c917116ef9253861dcc54a5bf29f`，已推送GitHub main并核对远端一致；包含适度紧凑、顶部24 DIP空白修复、侧栏按钮位置和此前结果选择修复。 |
| 完整目录 | `GPTWork/release-win-x64-5497f45cfec3/AbaqusTools`，干净同源，1687文件/19worker/15应用资源和全摘要、包内依赖已核对。该包尚未打开原生窗口。 |
| 安装候选 | `GPTWork/installer-win-x64-b4ca03cbe0c8/AbaqusTools-0.1.0-win-x64-setup.exe`，未签名，正式身份未安装；同负载独立测试身份安装/升级/卸载7818c66a5988通过，无自有进程/注册残留。 |
| 文档 | README、RepoWiki、28项功能索引及交接文档已建立；包内文档为构建时快照，最终验收追加到仓库。未另行发布GitHub Wiki网站，未完成默认入口切换。 |

准确摘要、失败和历史证据见[TASK-002](ACTIVE_TASKS/TASK-002-migration.md)，汇总`GPTWork/density-release-verification-20261118/verification-summary.json`。旧d4fc4c7含结果选择崩溃；6d45342的cb9a79ed69bd已含选择修复，但尚无本轮密度调整。不要用旧包替代当前候选。

## 当前界面改动与验证

- 八页页面留白统一20/16/20/20 DIP，卡片12，主要分组10，字号与输入/按钮高度保持。
- 导航上方空白实际来自三条关闭InfoBar各8 DIP边距；关闭时真正Collapsed，显示提示时恢复。仅关闭导航自动标题栏留白未解决问题，已根据用户反馈改正。
- 侧栏按钮移至右上，使用折线图标；收起保留40 DIP展开入口和页面相关内容，释放240 DIP。窗口客户区下限展开1242、收起1002、默认高664 DIP，继续按DPI/工作区换算。
- 13项原生控件检查（实际复现24 DIP、收起0、提示恢复以及选择刷新）、16项尺寸、39项相关回归、49项文档检查通过。上一轮全量1008+9和原生Qt启动1项对应4cb源码，不算新UI全量复测。
- 此前单CSV已由用户与CUA确认表格50行3列、导出全部80行1408字节且源/输出摘要一致，随后正常退出；证据`GPTWork/native-explorer-fixed-20261118/verification-summary.json`。这不自动证明本轮新包全部业务可用。

## 准确续接点

1. 旧密度试窗仍为205808，后台213728、子166276，窗口1573058；回执`GPTWork/native-density-20261118/result-browser/processes.json`。CUA截图超时、两次重新观察后激活失败，未强杀，已请用户关闭并回复“已关闭”。尚未收到回复；先核对原进程身份与窗口库存，不能重复启动或误称已退出。
2. 关闭后执行`GPTWork/native_density_20261118.py finish result-browser`核对退出/描述符/日常配置，再执行`GPTWork/native_density_release_20261118.py launch result-browser`打开当前完整5497f45cfec3包。用CUA核对新布局、侧栏收起恢复及错误提示，最后正常退出/capture/finish记录。当前没有新版本原生窗口。
3. 本轮构建90778已退出0；安装生命周期报告7818c66a5988为verified，句柄74818已确认退出0。其他检查已结束，勿重复相同构建或长任务。
4. 新包布局与鼠标仍待确认；旧试窗截图来自缺少InfoBar边距修复的版本，不能拿它代替新版本。继续八页完整业务、日志拖选/复制、悬停、主题、实际最小尺寸/跨屏及忙碌关闭验收。

## 未完成的完整迁移范围

实际SSH/指纹/传输、GPU/MPI和工程负载，连续三级真实工程ODB链、真实worker中断、原生分组/图例/取消/大文件/回收站及复杂草稿，正式安装向导、签名与无开发环境目标机、负责人对等确认仍待。已有ODB关系最长两节点，不能用兄弟分支或新求解补造三级链。完整范围见[交付核对清单](../06-testing/COMPLETION_AUDIT.md)与[功能索引](../03-features/FUNCTION_INDEX.md)，后处理与交互细节见[TASK-001](ACTIVE_TASKS/TASK-001-postprocessing.md)、[TASK-004](ACTIVE_TASKS/TASK-004-ui-interaction.md)。

## 约束

禁止向C:放置任何ODB，包括占位、临时、输出和复制件。TEMP/TMP、basetemp与生成物用G: GPTWork；G:\Job原始模型只读，不启动求解、不修改集成仓库、不删除PySide6/日常配置/历史验收。控制面用项目.venv，worker用Abaqus解释器。按真实单元类型选择算法，不由几何外形推断梁单元。每完成一个功能，立即同步维护索引、说明、测试和交接，局部通过不称整体完成。
