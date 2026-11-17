# Abaqus Tools RepoWiki

本目录是随源码维护的项目知识入口，描述当前 WinUI 3 前端、Python 控制面以及保留的 PySide6 兼容实现。文档只记录稳定边界和定位入口，具体字段以代码和版本化 API 契约为准。

接手开发先读 [统一文档入口](../INDEX.md)、[当前状态](../08-handoff/CURRENT_STATUS.md) 和 [功能定位索引](../03-features/FUNCTION_INDEX.md)。本目录保留既有概述和历史记录，不将其中某个日期的局部验收当作当前全项目完成状态。

## 导航

- [完整使用手册](user-guide.md)涵盖启动、八个页面、参数、失败处理和恢复。

- [整体架构](architecture.md)：进程边界、目录职责和数据流。
- [原生工作台](native-workbench.md)：WinUI 3 壳层、八个页面和交互约定。
- [作业提交与调度](submitter.md)：草稿、队列、本机执行、远程资源和重启动链。
- [作业内存与调度估计](../03-features/MEMORY_MONITORING.md)：当前占用、峰值、历史来源、失败状态及资源余量。
- [ODB 后处理](postprocessor.md)：发现、兼容性、合并、批处理和结果浏览。
- [WinUI 结果浏览操作](../03-features/POSTPROCESSING.md#winui-结果列表与表格预览f021)说明如何翻页、查看 CSV 和 Excel 宽表，以及复制预览。
- [开发、测试与发布](development.md)：环境、验证命令、生成物和安全约定。
- [HTTP API 契约](../api-contract.md)：控制面端点、鉴权、错误和异步操作模型。
- [WinUI 迁移合同](../winui-migration.md)：功能对等与验收边界。
- [架构决策记录](../submitter/adr/README.md)：影响长期维护的关键决策。

## 事实源顺序

发生冲突时按以下顺序判断：自动化测试与代码、`docs/api-contract.md`、本 RepoWiki、历史迁移说明。运行时配置和用户数据不存放在仓库中。
