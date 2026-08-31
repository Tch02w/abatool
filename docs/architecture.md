# Abaqus Tools 架构

## 总览

项目采用原生 WinUI 3 前端与本机 Python 控制面分层。桌面客户端负责渲染和用户交互，控制面是业务状态与文件写入的唯一入口，Abaqus worker 继续使用其内置 Python 环境。

```text
WinUI 3 / .NET 10
        │  127.0.0.1 HTTP/JSON，随机端口、bearer token
        ▼
Python 3.14 control plane（禁止导入 Qt）
        │
        ├── submitter：队列、调度、本机执行、SSH、归档、ODB 合并
        └── postprocessor：ODB 兼容性、批处理、渲染、结果索引
                    │
                    ▼
          Abaqus solver / Abaqus Python workers
```

PySide6 工作台仍保留为迁移验收期的兼容和回滚入口，但 WinUI 页面不会嵌入或调用 Qt 控件。

## 分层

```text
winui/AbaqusTools.WinUI/
├── MainWindow.xaml(.cs)           原生壳层、导航、菜单、状态与关闭
├── Pages/                         八个完整业务页面
├── Models/                        页面模型
└── Services/                      控制面宿主和版本化 DTO

modules/
├── control_plane/                 本机鉴权 API、事件、操作管理器和适配器
├── submitter/                     作业提交与调度领域核心
├── postprocessor/                 ODB 后处理领域核心
├── common/                        路径与 JSON 等共享基础设施
├── workspace.py                   PySide6 兼容工作台组合器
└── routes.py                      跨模块路径路由
```

## 依赖规则

- WinUI 只依赖 DTO 和控制面协议，不读取 SQLite、作业 JSON、SSH 会话或 Abaqus 日志。
- `modules/control_plane` 不导入 PySide6/PyQt；涉及 Qt 的适配器与 Qt-free 核心分文件保存。
- `submitter` 与 `postprocessor` 不直接依赖彼此的 UI，只通过路径、DTO 或稳定核心接口协作。
- 文件写入采用原子替换或临时产物提交；源 ODB 不被隐式覆盖。

## 异步操作模型

兼容性检查、ODB 合并、后处理、结果索引、远程传输和远程作业统一使用 operation ID。操作快照包含请求、状态、进度、日志、结果和结构化错误；客户端可轮询、取消、重连和按幂等键恢复。

控制面启动时写入仅当前用户可读的 descriptor，包含随机端口、token、实例和 launch token。客户端退出时先取消或收束活动操作，再关闭服务；运行中 Abaqus 作业由各自生命周期策略处理，不因界面刷新丢失。

## 界面架构

主导航固定为新建作业、作业队列、作业概览、计算资源、重启动链、ODB 合并、ODB 后处理和结果浏览。各页面拥有自己的上下文、进度、日志和操作区；壳层不再叠加静态项目栏、属性栏或重复的全局 TabView。

详细导航见 [RepoWiki](repowiki/README.md)，API 见 [api-contract.md](api-contract.md)，迁移验收见 [winui-migration.md](winui-migration.md)。
