# Abaqus Tools 架构

## 分层

```text
main.py                            唯一 GUI 入口
modules/
├── workspace.py                   单一 Qt 主窗口与功能页切换
├── common/                        Qt、路径与 JSON 基础设施
├── submitter/                     本地资源、队列和运行监控
└── postprocessor/                 ODB 批处理、渲染与结果浏览
```

## 依赖方向

领域模块可以依赖 `modules.common` 的稳定基础设施；根级壳层可以组合两个领域模块。两个领域模块不得直接互相导入。

```text
Submitter ─────┐
               ├──> modules.common 基础设施
PostProcessor ─┘
       ▲
       └──────── modules.workspace 负责组合，不承载领域规则
```

## 共享与隔离准则

适合下沉到 `modules/common/` 的代码：Qt 兼容性、文件与路径原语、JSON 持久化、无领域状态的 UI 壳层和通用诊断工具。

必须保留在领域模块的代码：提交器的调度状态机、远程连接和运行记录；后处理器的 ODB 脚本、缓存语义、图例计算、结果索引及渲染流程。它们的资源模型和失败恢复策略不同，不能因“共享”而互相依赖。
