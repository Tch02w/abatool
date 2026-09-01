# 整体架构

## 运行边界

```text
WinUI 3 / .NET 10
        │  127.0.0.1 HTTP/JSON，随机端口与 bearer token
        ▼
Python 3.14 control plane
        │  Qt-free services / controlled subprocesses
        ├──────── 本机与远程作业执行
        └──────── Abaqus Python workers / ODB scripts
```

WinUI 只负责界面状态、用户输入和 DTO；业务校验、持久化、调度、SSH、文件操作和 Abaqus 进程管理由 Python 控制面承担。控制面不导入 Qt，因此可独立测试和安全关闭。

## 目录职责

| 目录 | 职责 |
|---|---|
| `winui/AbaqusTools.WinUI` | 原生窗口、通用浏览器、八个页面、DTO 与控制面宿主 |
| `modules/control_plane` | 本机鉴权 HTTP API、操作管理器、事件与服务适配 |
| `modules/submitter` | 作业模型、调度、运行证据、远程连接与 ODB 合并 |
| `modules/postprocessor` | ODB 扫描、提取、渲染、缓存和结果目录 |
| `modules/common` | 路径、JSON 等共享基础设施 |
| `tests` | Python 领域测试、控制面 API 测试和 WinUI 契约测试 |
| `docs` | 架构、协议、ADR 与 RepoWiki |

## 状态所有权

- 作业队列兼容状态由 `queue_store.py` 原子保存；本机运行时由控制面的队列运行管理器统一调度。
- 长任务由各自操作管理器持有，使用 operation ID、幂等请求、进度、日志、取消和终态快照。
- SSH 凭据只在当前连接期间驻留内存；保存的服务器配置不包含密码。
- ODB 源文件默认只读。升级、合并和后处理先写临时产物，完成后再提交结果。
- 左侧浏览器只持有界面选择、展开与筛选状态；队列、作业、远端和长任务事实仍由控制面持有。

## 兼容层

PySide6 代码暂时保留用于行为对照和回滚，但不再是原生页面的运行依赖。涉及 Qt 的适配器与 Qt-free 核心分文件放置，防止控制面间接导入 GUI。
