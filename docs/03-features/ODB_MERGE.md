# ODB 安全合并（F013）

本功能服务于手工合并及 F012 结果图中的每一步。它调用 Abaqus 的 `restartjoin`，仅操作隔离副本；不会启动求解。界面步骤见 [使用手册](../repowiki/user-guide.md)，文件与测试见 [功能索引](FUNCTION_INDEX.md)。

## 输入与结果

选择具有重启动关系的原始 ODB 和重启动 ODB，选择输出路径、历史输出、压缩与命名冲突策略。后者可以自动编号，也可以明确覆盖既有目标。两个源 ODB 不允许作为目标。`copyOriginal` 控制 Abaqus 在隔离工作目录内是否再复制一份；无论开关如何，都不会原地合并用户源文件。

成功后保存合并 ODB、两份源备份和同目录的 `*.merge-validation.json` 回执。每次回执使用唯一名称，内容记录来源、最终输出和备份路径，以及每个分析步的来源、帧数与历史数据策略。HTTP 操作结果的 `validationReport` 指向回执。旧回执不会被覆盖。

**合并成功表示现有结果正确汇总，不表示模型全部求解完成。** 来源中尚无结果帧的后续分析步会保留，日志及完成状态会提示其数量；不会生成零值结果。若整个重启动 ODB 没有任何结果帧，则拒绝发布。

## 分析步与数据规则

分析步间重启动保留原始前序分析步，再接入重启动分析步。分析步中重启动使用重启动 ODB 替换重叠分析步；不会同时保留两套重叠结果或原文件中已经废弃的后续步骤。顺序依据 ODB 实际 `step.number`，不按名称猜测。此规则与 [Abaqus 2025 restartjoin 文档](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEEXCRefMap/simaexc-c-restartjoinproc.htm) 一致。

启用“历史输出”时，保留步骤的历史数据必须逐项与其来源一致。关闭时，Abaqus 会移除合并结果中**所有**历史数据，包括原始分析步的历史数据；校验确认没有残留历史输出。该行为已在本机 Abaqus 2025 实际运行中核对。

输出非空和可打开只是前置条件。发布前，Abaqus 自带 Python 只读打开两份备份和合并结果，逐项核对：

- 分析步名称、顺序、编号、域与累计时间；每个分析步的帧数。
- 每帧时间、增量号、场输出名称与分量覆盖。
- 所有已保存场值、实例与节点/单元位置标识、积分点、截面点及局部坐标数据。
- 按开关保留或省略历史输出；成功关闭全部 ODB 后才写回执和成功标记。

常规场数据按 bulk block 计算摘要，避免逐积分点创建 Python 对象；双精度或不支持 bulk 访问时回退到 FieldValue，读取实际双精度值。块分割或存储次序不一致可能保守地拒绝发布，需要保留日志排查。核对覆盖保存的数据，不代表求解质量、模型物理正确性或完整网格拓扑审计。

## 错误、停止与恢复边界

源文件在复制前后、发布前核对文件标识、大小及时间戳；发现变化时拒绝发布。该保护不是源文件全量内容摘要。任务运行期间不要另行写入源文件。真实验收另用完整 SHA256 比较原始文件和副本。

未产生合并结果、校验不一致、没有成功标记、回执缺失或路径不符、关闭 ODB 失败，都不能返回成功。失败时清理本次工作目录及尚未提交结果所对应的新备份/回执，保留用户原文件和旧目标。自动编号发布发生同名冲突时拒绝覆盖；明确覆盖只在全部校验通过后原子替换最终 ODB。

停止请求在复制、外部进程和发布前处理。最终发布是一段短暂提交过程：提交后才到达的停止请求不把已保存结果改标为“已取消”。源备份、回执、ODB 不是跨文件事务；系统崩溃可能留下部分新文件，控制面进程重启后的任务历史恢复仍待完善，不自动重跑长合并。

新增全量内容核对会增加读取时间。界面 82% 阶段显示逐分析步校验，日志按步骤更新；大文件需要等待，不因暂时没有新日志重复启动。

## 实现与验证入口

- 计划：`modules/submitter/odb_merge_core.py` / `build_merge_plan`。
- 隔离执行及发布：`modules/submitter/odb_merge_execution.py` / `execute_odb_merge`。
- Abaqus 校验：`modules/postprocessor/abaqus_scripts/validate_odb_merge.py` / `verify`、`main`。
- 控制面：`modules/control_plane/odb_merge_operations.py` / `OdbMergeOperationManager`。并发重复请求核对同一请求标识的参数，关闭后不再准入新操作。
- 回归：`tests/postprocessor/test_merge_validation.py`、`tests/submitter/test_odb_merge_execution.py`、`tests/submitter/test_odb_merge.py`、`tests/control_plane/test_odb_merge_operations_api.py`。

真实模型的路径、运行结果、失败记录及尚未完成的原生/多节点验收见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)；自动化与实际 ODB 验证不替代原生页面点击验收。
