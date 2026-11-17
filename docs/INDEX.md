# 项目文档与交接入口

本入口面向开发者及后续智能体。按用户提供的文档架构建立核心导航，复用现有架构、协议、RepoWiki 和 ADR，不复制一套互相冲突的百科。

## 接手顺序

1. [项目规则](../AGENTS.md)
2. [当前状态与接续点](08-handoff/CURRENT_STATUS.md)
3. [任务索引](08-handoff/TASK_INDEX.md)
4. [功能 → 代码 → 测试索引](03-features/FUNCTION_INDEX.md)
5. 对应功能说明和源码；仅索引缺失时定向搜索并补齐。

## 文档职责

| 要回答的问题 | 唯一主入口 |
|---|---|
| 项目是什么、怎样启动 | [README](../README.md) |
| 八个页面怎样操作、遇到问题怎么办 | [完整使用手册](repowiki/user-guide.md) |
| 智能体必须遵守什么、完成后更新什么 | [AGENTS](../AGENTS.md) |
| 系统分层、数据流、模块边界 | [系统架构导航](02-architecture/SYSTEM_ARCHITECTURE.md) |
| 每个功能在哪些文件、该测什么 | [功能索引](03-features/FUNCTION_INDEX.md) |
| 当前后处理怎么用、限制是什么 | [后处理功能说明](03-features/POSTPROCESSING.md) |
| 本机优先级、资源准入、后台重启与未知状态 | [本机调度说明](03-features/LOCAL_SCHEDULING.md) |
| 完整结果批量执行、共享祖先与重启继续 | [批量结果说明](03-features/ODB_RESULT_BATCH.md) |
| ODB 合并校验、历史输出、停止与部分结果 | [安全合并说明](03-features/ODB_MERGE.md) |
| 日志选择刷新、16 处数字输入及参数说明（F005/F025） | [界面交互说明](03-features/UI_INTERACTION.md) |
| 开发/测试/文件整理约定 | [维护工作流](05-development/WORKFLOW.md) |
| Windows 完整目录包、运行诊断和发布限制 | [发布构建](05-development/RELEASE.md) |
| 哪些验收已通过，证据证明什么 | [验收记录与缺口](06-testing/VALIDATION.md) |
| 接手时先做什么、目前未完成什么 | [当前状态](08-handoff/CURRENT_STATUS.md) |
| 任务过程、失败定位、后续动作 | [任务索引](08-handoff/TASK_INDEX.md) |
| 为什么这样设计 | [现有 ADR](submitter/adr/README.md) |

## 保留的参考文档

11 月 17 日候选包含结果列表翻页、CSV / Excel 预览和分组色标校验。图例窗口可按中文物理量填写上下限并就地纠错。操作步骤见[后处理说明](03-features/POSTPROCESSING.md)，现有两模型实际出图和异常路径见[验收记录](06-testing/VALIDATION.md)。数字输入、日志选区、参数说明与窗口布局的历史验收见 [TASK-004](08-handoff/ACTIVE_TASKS/TASK-004-ui-interaction.md)。

- [RepoWiki](repowiki/README.md)：提交器、原生界面、开发概述。
- [整体架构](architecture.md)：既有分层说明。
- [HTTP 契约](api-contract.md)：协议参考；新增端点以 `modules/control_plane/server.py` 和对应请求 DTO 为事实源，不把旧阶段说明视为现状。
- [迁移合同与历史记录](winui-migration.md)：完整迁移的要求及历史证据；不作为当前完成状态的唯一依据。

## 维护约定

开发完一个功能，必须同步更新功能说明、索引、验收记录和任务状态；未更新文档不算完成交付。当前状态不堆积完整历史，详细过程写入任务文件。仅记录真实路径、符号和执行证据；没有复核的模块标“待验收”，不得因文件存在标为稳定。
