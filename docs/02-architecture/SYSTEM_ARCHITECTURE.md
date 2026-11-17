# 系统架构与模块定位

基础设计沿用 [整体架构](../architecture.md) 和 [WinUI 控制面 ADR](../submitter/adr/0002-native-winui-control-plane.md)。本页补充接手时需要的入口和数据流，不重复维护所有 API 字段。

## 三个运行环境

| 层 | 入口与职责 | 禁止混用 |
|---|---|---|
| C# / .NET 10 / WinUI 3 | `winui/AbaqusTools.WinUI/App.xaml.cs`、`winui/AbaqusTools.WinUI/MainWindow.xaml.cs`；页面、编辑草稿、显示和操作跟踪 | 不在页面中实现应力积分、队列调度或直接操控 SSH |
| 项目 Python 3.14 | `modules/control_plane/__main__.py`、`modules/control_plane/server.py`；鉴权、校验、业务操作和进程管理 | 不导入 Qt 控件，不以普通 Python 直接打开 ODB |
| Abaqus 自带 Python / CAE noGUI | `modules/postprocessor/abaqus_scripts/`；读取 ODB、截面、渲染；由业务层启动 | 保持与 Abaqus 版本兼容，不能照搬 Python 3.14 专属语法 |

兼容入口：`main.py` → `modules/workspace.py`；独立旧后处理 `modules/postprocessor/app.py`。暂不删除 PySide6。

## 后处理数据流

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
- F013 合并记录在 `modules/control_plane/odb_merge_journal.py`，使用 descriptor 同目录的 SQLite 文件恢复终态和请求身份，非终态显示中断待核对。升级/合并联合退出预留见 [ADR 0006](../submitter/adr/0006-durable-merge-history.md)；F012 批量游标及其他任务的跨后台恢复仍需分别实现与验收。
- 控制面 descriptor 含 bearer token，只供本机客户端使用，不进入文档、Git 或验收截图。

## 修改的影响链

| 改动 | 同时检查 |
|---|---|
| 请求字段 | C# Contracts → 页面构造 → Python 请求校验 → worker → API 和 C# HTTP 测试 |
| 扫描目录 | 扫描 worker → `models.py` → 执行层投影 → Contracts → 缓存版本 → 页面旧缓存提示 |
| 数值方法 | 输入单元族/字段/位置 → 参考系与单位 → 发布清单 → 数值基准 → 结果分类 |
| 输出格式 | worker → manifest 校验 → `result_catalog.py` → SQLite 索引 → 预览与兼容测试 |
| 节点式重启动 | 计算图与结果图分离；参考 [ADR 0004](../submitter/adr/0004-separate-restart-computation-and-result-materialization.md) |

精确功能文件见 [功能索引](../03-features/FUNCTION_INDEX.md)。本页描述架构，不证明迁移已完成。
