# ODB 安全合并（F013）

本功能服务于手工合并及 F012 结果图中的每一步。它调用 Abaqus 的 `restartjoin`，仅操作隔离副本；不会启动求解。界面步骤见 [使用手册](../repowiki/user-guide.md)，文件与测试见 [功能索引](FUNCTION_INDEX.md)。

## 输入与结果

手工合并的「停止」需要本次后台操作编号，提交阶段保持禁用，收到受理回执后才可点击。发出停止请求后，按钮等待同一操作的取消结果。订阅里迟到的旧任务消息不能重新激活已结束任务的按钮。批量操作保留原有的预先请求停止流程。

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

停止请求在复制、外部进程和发布前处理。最终发布是一段短暂提交过程：提交后才到达的停止请求不把已保存结果改标为“已取消”。源备份、回执、ODB 不是跨文件事务；系统崩溃可能留下部分新文件。

控制面把单步合并记录保存在 descriptor 同目录的 `odb-merge-history.sqlite3`，重新打开合并页会显示最新任务及日志，包括失败和中断。已完成记录恢复来源、结果和回执路径；同一请求标识不会再次启动。页面加载新的结果图计划时保留新计划。

若后台在确认完成前退出，任务显示“合并中断，待核对”。先检查原任务是否仍在运行，再查看目标目录的 `*.merge-validation.json`、结果、备份及 `.abasub-odb-merge-*` 工作区。不要只凭文件存在认定成功，也不要因没有新日志重复启动。程序保留现场，不自动清理或重跑；外部 Abaqus 的运行状态须另行核实。

记录损坏或被其他后台占用时禁止新合并并保留数据库。运行中保存失败会请求停止未发布操作，界面显示保存失败提示；已发布结果仍显示实际结果。此时保留后台，处理磁盘问题并核对记录和文件。退出检查同时保护升级和合并；高频日志采用检查点节流，异常退出可能丢失最后检查点之后的日志。完整策略见 [ADR 0006](../submitter/adr/0006-durable-merge-history.md)。F012 已增加后台批量计划与阶段恢复，操作和限制见 [完整结果批量任务](ODB_RESULT_BATCH.md)，真实多步骤及原生交互仍待验收。

新增全量内容核对会增加读取时间。界面 82% 阶段显示逐分析步校验，日志按步骤更新；大文件需要等待，不因暂时没有新日志重复启动。

2026-11-19使用既有GJB工程ODB副本，通过当前完整包实际验收校验阶段取消和SMAPython进程意外退出：分别显示cancelled/failed，无成功结果，既有目标及来源摘要不变；重开后台恢复原记录，不重复执行。回执`GPTWork/real-merge-interruption-74bb9bec2c53/verification.json`。工具`packaging/verify_real_merge_interruption.py`只作用于GPTWork来源及其自有后台后代；此证据覆盖实际校验worker异常，不等于后台崩溃时遗留worker、所有求解进程或原生点击验收。

同日补验后台崩溃：干净9a09972完整555b包在真实GJB合并的82%校验阶段强制退出自有后台。已核实身份的SMAPython校验进程被短暂停住，保持存活直至新后台完成恢复检查，然后恢复执行。新后台将同一操作标为`ODB_MERGE_INTERRUPTED`、不可直接重试，无成功结果；同请求没有重放，原工作区保留，旧目标与三个来源完整摘要不变。第三次后台启动仍恢复同一中断记录。原校验进程恢复后退出码120（不计校验成功），所有本次自有进程最终结束；中断工作区保留供核对。证据`GPTWork/real-merge-backend-crash-9597d1bc621d/verification.json`。该项证明真实校验进程存活时的单步合并保守恢复，不等于任意求解/批量阶段或原生界面恢复已验收。

## 实现与验证入口

- 计划：`modules/submitter/odb_merge_core.py` / `build_merge_plan`。
- 隔离执行及发布：`modules/submitter/odb_merge_execution.py` / `execute_odb_merge`。
- Abaqus 校验：`modules/postprocessor/abaqus_scripts/validate_odb_merge.py` / `verify`、`main`。
- 控制面：`modules/control_plane/odb_merge_operations.py` / `OdbMergeOperationManager`。并发重复请求核对同一请求标识的参数，关闭后不再准入新操作。
- 持久记录：`modules/control_plane/odb_merge_journal.py` / `MergeJournal`；仅保存操作数据，不打开或修改 ODB。
- 回归：`tests/postprocessor/test_merge_validation.py`、`tests/submitter/test_odb_merge_execution.py`、`tests/submitter/test_odb_merge.py`、`tests/control_plane/test_odb_merge_operations_api.py`。
- 重启恢复与异常退出：`tests/control_plane/test_odb_merge_recovery.py`；原生 DTO/生命周期：`tests/winui_host/Program.cs`。
- 真实后台崩溃验收：`packaging/verify_real_merge_backend_crash.py` / `verify`。只接受非C盘GPTWork既有包和ODB副本，核对后代PID/创建时间/可执行文件/独立暂存路径，再暂停校验进程及中断自有后台；异常仍恢复暂停进程、保存准确身份，不因超时另开任务。不清理保留的中断现场。

真实模型的路径、运行结果、失败记录及尚未完成的原生验收见 [TASK-002](../08-handoff/ACTIVE_TASKS/TASK-002-migration.md)。2026-11-19已按用户授权完成实际求解的简单实体三级链，两级串联合并的场/历史和独立解析值核对均通过，详见[批量任务验收](ODB_RESULT_BATCH.md)。自动化与实际 ODB 验证不替代原生页面点击验收，合并功能自身仍不启动求解。
