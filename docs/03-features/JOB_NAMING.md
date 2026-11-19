# Abaqus 作业名称（F003/F004/F010）

校验依据为 Dassault Systèmes 的 Abaqus 2025 文档 [Using basic dialog box components → Text fields](https://docs.software.vt.edu/abaqusv2025/English/SIMACAECAERefMap/simacae-c-intdialogbasic.htm)（Virginia Tech 托管的原厂文档）。Job 对象要求有效的 Abaqus/CAE 对象名，见 [ModelJob](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEKERRefMap/simaker-c-modeljobpyc.htm)。不使用 Python 标识符规则代替作业命名规则。

- 作业名称非空，最多80个字符；作业名可以以数字开头。
- 不能以短横线或下划线开头，不能以下划线结尾；不能包含空白。
- 不能包含文档列出的 `$ & * ~ ! ( ) [ ] { } | : ; '`、反引号、双引号、右双引号、逗号、句点、问号、正反斜杠、大小于号。
- `Assembly` 为保留名称，按文档的对象名不区分大小写约定检查。
- `+` 不在禁用清单，`GJA-8+2_U40D_V20D` 和 `GJA-8+2_U100D` 均通过名称检查。命名合法不代表前置ODB、CPU、输入文件或其他提交条件已经满足。

输入文本还拒绝控制字符和换行，避免将其作为路径或命令分隔符；这属于输入/平台保护，不声称是额外的 Abaqus 字母白名单。不会改名、移动或改写原始INP/ODB。具体非法字符、长度或首尾原因分别显示，不再统称只能使用英文字母等四类字符。

`modules/submitter/command.py` / `validate_job_name` 为共享校验，候选、新建、Qt对照与远端请求及oldjob依赖名复用。`constants.py` 中保存长度与禁用字符及来源。允许的百分号、插入号等不能被 Windows 命令解释器改写；本机与远端传参保持字面值，命令预览仍显示原名。命名校验不等于实际求解成功。

测试为 `tests/submitter/test_job_names.py`：文档规则边界、用户两个名称、候选及依赖名、实际 Windows 本机和远端启动脚本的参数记录器；记录器不调用Abaqus。`tests/control_plane/test_job_queue_commands_api.py` 和 `test_remote_jobs_api.py` 覆盖既有提交约定。取消和失败规则不变。

Qt对照入口调用cmd时使用[QProcess官方建议的setNativeArguments](https://doc.qt.io/qt-6/qprocess.html#setNativeArguments)，避免把带空格的命令路径错误转义。51项命名/实际传参检查通过（job-names-fixed-20261119.xml），包含本机、远端启动及控制脚本、Qt分离进程；不以此声称任意作业已真实求解。
