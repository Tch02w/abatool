# Abaqus Tools 架构

## 分层

```text
main.py                            统一 GUI 入口
modules/
├── workspace.py                   提交器工作台主壳与工具页组合
├── routes.py                      无副作用的跨模块路径路由
├── common/                        Qt、路径与 JSON 基础设施
├── submitter/                     本地资源、队列和运行监控
└── postprocessor/                 ODB 批处理、渲染与结果浏览
```

## 依赖方向

领域模块可以依赖 `modules.common` 的稳定基础设施；根级壳层可以组合两个领域模块。两个领域模块不得直接互相导入。Qt 绑定只允许 PySide6，不再回退到 PyQt6。

```text
Submitter ─────┐
               ├──> modules.common 基础设施
PostProcessor ─┘
       ▲
       └──────── modules.workspace 负责组合，不承载领域规则
```

## 共享与隔离准则

适合下沉到 `modules/common/` 的代码：Qt 兼容性、文件与路径原语、JSON 持久化、无领域状态的 UI 壳层和通用诊断工具。

界面设计令牌（颜色、圆角、控件高度）与无领域基础的控件样式集中在 `modules/common/qt_theme.py`；两个领域模块各自在此之上叠加页面级样式（submitter 见 `ui_styles.py`，postprocessor 见 `ui_style.py` 的 `build_main_stylesheet()`），保证两个功能页视觉统一。样式表只挂在各领域主窗口上，不写入共享的 QApplication，避免页面间互相污染。

必须保留在领域模块的代码：提交器的调度状态机、远程连接和运行记录；后处理器的 ODB 脚本、缓存语义、图例计算、结果索引及渲染流程。它们的资源模型和失败恢复策略不同，不能因“共享”而互相依赖。

## 主窗口组合

统一窗口继承提交器 `MainWindow`，保留其自绘标题栏、文件/作业/服务器菜单、左侧资源区、右侧属性区和底部日志。原 6 个提交器任务页之后加入懒加载的“ODB 后处理”和“结果浏览”页；进入工具页时临时收起提交器侧栏和日志，返回时恢复。

跨模块只传递路径：当前提交作业通过 `modules.routes.odb_candidate_for_job()` 解析候选 ODB，后处理器自行负责扫描和校验。后处理器与结果浏览器共享同一个结果索引协调器。统一状态栏只读取各模块已有状态，不拥有调度或索引状态机。

关闭窗口时先请求结果浏览和后处理页安全退出；任一后台任务拒绝关闭，主窗口也必须拒绝退出。窗口显示后统一入口触发已恢复作业的外部状态复核，与提交器独立入口保持一致。
