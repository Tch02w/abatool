# 系统架构与模块定位

基础设计沿用 [整体架构](../architecture.md) 和 [WinUI 控制面 ADR](../submitter/adr/0002-native-winui-control-plane.md)。本页补充接手时需要的入口和数据流，不重复维护所有 API 字段。

## 三个运行环境

| 层 | 入口与职责 | 禁止混用 |
|---|---|---|
| C# / .NET 10 / WinUI 3 | `winui/AbaqusTools.WinUI/App.xaml.cs`、`winui/AbaqusTools.WinUI/MainWindow.xaml.cs`；页面、编辑草稿、显示和操作跟踪 | 不在页面中实现应力积分、队列调度或直接操控 SSH |
| 项目 Python 3.14 | `modules/control_plane/__main__.py`、`modules/control_plane/server.py`；鉴权、校验、业务操作和进程管理 | 不导入 Qt 控件，不以普通 Python 直接打开 ODB |
| Abaqus 自带 Python / CAE noGUI | `modules/postprocessor/abaqus_scripts/`；读取 ODB、截面、渲染；由业务层启动 | 保持与 Abaqus 版本兼容，不能照搬 Python 3.14 专属语法 |

兼容入口：`main.py` → `modules/workspace.py`；独立旧后处理 `modules/postprocessor/app.py`。暂不删除 PySide6。

本机队列：`JobQueuePage → LocalQueueRuntimeManager → LocalQueueScheduling → SchedulerCore / SQLiteSchedulerRepository → execute_local_job`。计划先持久化再启动；后台重启保留未知条目并扫描原目录，不自动重复执行。合计 CPU、绝对内存、百分比限制和双文件提交边界见 [本机调度说明](../03-features/LOCAL_SCHEDULING.md) 与 [ADR 0010](../submitter/adr/0010-native-shared-local-scheduler.md)。

本机观测：多个执行器共用进程快照，以执行身份和 PID 创建时间约束统计；回调先聚合，再由队列线程批量保存。`LocalMemoryMonitor` 复用纯 Python 学习服务，历史写入同一 SQLite 的兼容元信息表，按 job ID 将估计交给调度核心。采样不可读与零占用不同，当前 RSS 与历史估计不同；详见 [内存说明](../03-features/MEMORY_MONITORING.md) 和 [ADR 0011](../submitter/adr/0011-native-memory-observation.md)。

作业提醒：本机/远端终态回调 → `JobNotificationManager` → 独立 SQLite → 全局 WinUI 提醒区。执行身份去重，已读必须保存确认；待保存提醒参与联合退出检查。旧作业历史补查不持有提醒锁，避免与完成回调形成反向锁顺序。原生仅负责显示和确认，不能自行推断作业成功。见 [提醒说明](../03-features/JOB_NOTIFICATIONS.md) 与 [ADR 0013](../submitter/adr/0013-durable-job-notifications.md)。

F028 提交参数由 Qt-free `execution_options.py` 统一校验和生成；WinUI 共用编辑区与契约传递 GPU/计算精度/输出精度，本机与远端使用相同枚举及默认语义。参数进入持久记录、请求幂等身份和内存历史键，原默认键不变。它尚不是 GPU 资源分配器。详见 [提交选项](../03-features/EXECUTION_OPTIONS.md)。

## 后处理数据流

远端作业：`RemoteJobOperationManager → RemoteJobJournal / RemoteJobRecovery → RemoteServerService → Windows PowerShell`。启动 intent 本地持久化，服务器独占提交回执约束单次启动；恢复仅观察原身份，凭据不入任务记录。连接锁同时保护身份核对和命令执行。实现、未确认窗口和测试边界见 [远端说明](../03-features/REMOTE_JOBS.md) 与 [ADR 0012](../submitter/adr/0012-durable-remote-tracking.md)。

F008 连接视图由 `RemoteServerService._publish_snapshot_locked` 在命令状态改变时发布完整副本，`snapshot` 仅持有独立快照锁并再次深拷贝。慢 SSH/SFTP/PowerShell 不阻塞连接视图读取；`busy/activity` 区分正在通信和上一份资源采样。网络操作与服务器身份校验继续串行使用原连接锁，不能把快照缓存用于授权命令或判定作业完成。原生资源页忙时只观察快照，避免定时器排入重复远端刷新。

```text
OdbPostprocessingPage → ControlPlaneHost → server.py
    ├─ discovery.py → ODB 路径与文件状态
    ├─ postprocessing.py → analyze_postprocess_inputs → runner.py → scan_odb_core.py
    │       → OdbScan / structureCatalog → OdbFileRow → 参数与对象选择
    ├─ 原基础流程 → execute_postprocess_plan → 预检查/缓存/提取/数值整理/渲染
    └─ 通用对象流程 → RegionExtractionRequest → execute_region_extraction
            → extract_region.py
                ├─ region_extract_core.py：梁或桁架保存字段
                └─ region_solid_core.py：CAE 截面应力积分
            → 临时 CSV → 完整性校验 → manifest → 移除未完成标记
结果浏览 → results.py / result_indexing.py → result_catalog.py / result_index.py
```

两条提取流程并存；通用对象提取不应偷偷带入基础模型的集合角色、材料尺寸或钢筋直径假设。已有 GJA/GJB 提取应继续按迁移前口径校核。

## 状态与配置的所有权

- 控制面是队列和执行操作的权威；UI 的勾选、搜索、展开及未提交草稿是编辑状态，不应被资源轮询清空。
- `modules/submitter/app_paths.py` 定义队列配置路径：默认本地应用数据下 `AbaqusSubmitter`，可通过 `ABAQUS_SUBMITTER_DATA_DIR` 为测试隔离。文件包括 `config.json`、`joblist.json`、`scheduler_state.db`。
- 后处理编辑工作区由 `winui/AbaqusTools.WinUI/Services/OdbPostprocessWorkspaceStore.cs` 保存；页面使用本地应用数据 `AbaqusTools/postprocess-workspaces`。只持久化编辑配置，不把旧结构有效性视为永远有效。
- 输出默认位于所选根目录下 `AbaqusODBPostProcessor_Results`；通用结果另分 `通用对象提取`。源 ODB 只读。
- 升级恢复专用 `modules/control_plane/odb_upgrade_journal.py`；**不能据此推断所有异步任务均有跨控制面重启恢复能力**。
- F013 合并记录在 `modules/control_plane/odb_merge_journal.py`，使用 descriptor 同目录的 SQLite 文件恢复终态和请求身份，非终态显示中断待核对。升级/合并联合退出预留见 [ADR 0006](../submitter/adr/0006-durable-merge-history.md)。
- F012 批量计划与阶段提交记录由 `modules/control_plane/odb_result_batches.py` 持久管理，WinUI 只提交和观察。批量/合并/升级按固定顺序联合退出预留；后台重启后显式检查再继续，不能重跑不明子任务。见 [ADR 0007](../submitter/adr/0007-durable-result-batches.md)。其他任务的跨后台恢复仍需分别实现与验收。
- 控制面 descriptor 含 bearer token，只供本机客户端使用，不进入文档、Git 或验收截图。
- F001 退出保护检查九类任务及线程收尾，底层固定锁顺序见 [ADR 0008](../submitter/adr/0008-all-worker-shutdown-fence.md)。窗口新增可撤销准备/提交/放弃协议，由 `shutdown_protocol.py` 持有 60 秒租约和 POST 准入计数；后台自行执行已确认的退出，客户端不按过期空闲回执杀进程。后台继续时仅分离窗口。原生验收仍待完成，见 [ADR 0009](../submitter/adr/0009-reversible-workbench-close.md)。
- `WorkbenchSession` 保存八页登记的编辑输入、最近路由和窗口位置；`WorkbenchSessionStore` 原子替换本地草稿，损坏原文件不覆盖。页面轮询不能把草稿当运行事实；凭证不持久化。该草稿机制和保留原后台不等于全任务跨进程恢复。

## 修改的影响链

| 改动 | 同时检查 |
|---|---|
| 请求字段 | C# Contracts → 页面构造 → Python 请求校验 → worker → API 和 C# HTTP 测试 |
| 扫描目录 | 扫描 worker → `models.py` → 执行层投影 → Contracts → 缓存版本 → 页面旧缓存提示 |
| 数值方法 | 输入单元族/字段/位置 → 参考系与单位 → 发布清单 → 数值基准 → 结果分类 |
| 输出格式 | worker → manifest 校验 → `result_catalog.py` → SQLite 索引 → 预览与兼容测试 |
| 节点式重启动 | 计算图与结果图分离；参考 [ADR 0004](../submitter/adr/0004-separate-restart-computation-and-result-materialization.md) |

精确功能文件见 [功能索引](../03-features/FUNCTION_INDEX.md)。本页描述架构，不证明迁移已完成。
