# Abaqus Tools 本地控制面 API v1

本文件定义 WinUI 3 前端与 Python 3.14 控制面在“ODB 发现与只读兼容性检查”切片中的 v1 边界。Python 控制面已经提供发现、异步兼容性操作、取消、幂等、活动操作枚举和事件重放；WinUI 客户端已接入发现、任务创建、快照轮询、取消，并可在控制面实例仍存活时重新接管未完成检查。阶段 1 仍需补足控制面自身重启后的持久恢复、有效与跨版本真实 ODB 证据及后续升级/读取入口，不能据此宣称整个后处理页面已迁移。控制面只监听 IPv4 回环地址，不导入 Qt，也不允许前端直接提交 shell 命令。

## 启动与就绪

开发环境启动命令：

```powershell
python -m modules.control_plane --port 0 --descriptor "<absolute-path>"
```

`--port 0` 让操作系统选择空闲端口。控制面绑定成功后，在目标目录中以临时文件加 `os.replace` 的方式原子发布 descriptor：

```json
{
  "schemaVersion": 1,
  "apiVersion": "v1",
  "instanceId": "opaque-uuid",
  "pid": 1234,
  "host": "127.0.0.1",
  "port": 54321,
  "baseUrl": "http://127.0.0.1:54321",
  "token": "random-bearer-token",
  "startedAt": "2026-08-20T12:00:00.000Z",
  "launchToken": "cold-start-correlation-nonce"
}
```

`launchToken` 不是鉴权凭据，只用于把 WinUI 发起的一次冷启动与 venv
redirector 创建的实际 Python 子进程关联。Windows 虚拟环境启动器的 PID
可能不同于最终控制面进程 PID，因此冷启动不得用 PID 相等作为唯一归属判断；
已有健康实例仍以 bearer token、`instanceId` 与 `/healthz` 共同验证。

descriptor 出现不等于服务已经就绪。前端必须读取它，然后发送带鉴权的 `GET /healthz`；只有响应为 `200`、`status` 为 `ok` 且 `instanceId` 与 descriptor 相同时才算就绪。

控制面正常退出时仅删除仍属于自身 `instanceId` 的 descriptor，避免旧进程删除新实例的连接信息。

## 鉴权与编码

所有已定义的业务端点（包括 `/healthz`）都要求：

```http
Authorization: Bearer <descriptor.token>
```

JSON 使用 UTF-8，路径保持原始 Unicode 文本。错误响应具有统一结构：

```json
{
  "schemaVersion": 1,
  "error": {
    "code": "ROOT_NOT_FOUND",
    "message": "ODB 根目录不存在或无法解析",
    "retryable": false,
    "traceId": "opaque-uuid",
    "details": {}
  }
}
```

## 健康检查

```http
GET /healthz
```

成功响应：

```json
{
  "schemaVersion": 1,
  "apiVersion": "v1",
  "status": "ok",
  "instanceId": "opaque-uuid",
  "pid": 1234,
  "startedAt": "2026-08-20T12:00:00.000Z",
  "eventCursor": 0
}
```

## ODB 发现

```http
POST /api/v1/odb-discoveries
Content-Type: application/json; charset=utf-8
```

请求：

```json
{
  "schemaVersion": 1,
  "root": "G:\\计算工程",
  "recursive": true
}
```

`recursive` 可省略，默认为 `true`。v1 拒绝未知请求字段。根目录必须存在且可解析。

发现规则：

- 扩展名 `.odb` 不区分大小写；
- 文件按相对路径自然排序，因此 `case-2.odb` 位于 `case-10.odb` 前；
- 递归时不进入 `.git`、`.venv`、`AbaqusODBPostProcessor_Results` 和 `_AbaqusODBPostProcessor_Results`；
- 忽略名称以 `-old` 结尾、包含 `-old-` 或包含 `-upgrading-` 的迁移/备份 ODB；
- 单个文件无法读取时写入 `warnings`，不会破坏其他发现结果。

成功响应：

```json
{
  "schemaVersion": 1,
  "discoveryId": "opaque-uuid",
  "root": "G:\\计算工程",
  "recursive": true,
  "odbs": [
    {
      "path": "G:\\计算工程\\case-2.odb",
      "relativePath": "case-2.odb",
      "name": "case-2.odb",
      "sizeBytes": 1024,
      "modifiedAt": "2026-08-20T12:00:00.000Z"
    }
  ],
  "count": 1,
  "warnings": [],
  "eventCursor": 2
}
```

## ODB 兼容性检查

创建只读检查操作：

```http
POST /api/v1/odb-compatibility-checks
Content-Type: application/json; charset=utf-8
```

请求的五个字段均为必填，v1 拒绝未知字段：

```json
{
  "schemaVersion": 1,
  "clientRequestId": "client-generated-stable-id",
  "root": "G:\\计算工程",
  "paths": [
    "G:\\计算工程\\case-2.odb",
    "子目录\\case-10.odb"
  ],
  "forceRescan": false
}
```

约束：

- `clientRequestId` 是客户端生成的非空稳定 ID，最长 128 个字符且不得包含控制字符；
- `root` 必须是可解析的现有目录；
- `paths` 包含 1–256 个互不重复的路径；相对路径按 `root` 解析，绝对路径也必须位于解析后的 `root` 内；
- 每个路径的扩展名必须是大小写不敏感的 `.odb`；创建操作时不强制文件仍存在，以便把发现后删除的文件稳定报告为 `missing`；
- `forceRescan=true` 跳过已有兼容性缓存读取，但仍按旧版语义写入新的稳定缓存。

服务端从 `modules/postprocessor/defaults.json` 读取 Abaqus 命令和发行版。可分别使用 `ABAQUS_TOOLS_ABAQUS_COMMAND` 与 `ABAQUS_TOOLS_ABAQUS_RELEASE` 覆盖；客户端不能提交命令、worker 路径或 cache 目录。检查通过配置的 Abaqus 命令启动其自带 Python worker，缓存继续位于 `<root>\cache`，缓存版本保持“发行版 + 命令路径”的旧版语义。由于旧 runner 的 request/report 文件名固定，控制面 v1 串行执行兼容性操作，避免同一缓存报告互相覆盖。

同一控制面实例内，`clientRequestId` 是幂等键：规范化后的 `root`、`paths` 与 `forceRescan` 全部相同时，重复 POST 返回原操作且不会再次启动 worker；同一 ID 对应不同请求时返回 `409 IDEMPOTENCY_CONFLICT`。控制面重启后内存操作与幂等表会清空。

创建成功返回 `202 Accepted` 和操作快照。后台线程可能在响应前已经推进状态，因此首次快照不保证仍为 `queued`：

```json
{
  "schemaVersion": 1,
  "operationId": "opaque-operation-id",
  "attemptId": "opaque-attempt-id",
  "kind": "odb.compatibility.check",
  "status": "running",
  "createdAt": "2026-08-20T12:00:00.000Z",
  "updatedAt": "2026-08-20T12:00:00.100Z",
  "version": 3,
  "progress": {
    "completed": 0,
    "total": 2,
    "currentItem": ""
  },
  "request": {
    "clientRequestId": "client-generated-stable-id",
    "root": "G:\\计算工程",
    "paths": ["G:\\计算工程\\case-2.odb", "G:\\计算工程\\case-10.odb"],
    "forceRescan": false
  },
  "results": [],
  "error": null,
  "eventCursor": 5
}
```

`status` 只允许以下小写值：

```text
queued → starting → running → succeeded
                         ↘ cancelling → cancelled
                         ↘ failed
```

终态只有 `succeeded`、`cancelled` 和 `failed`。`version` 随状态或可见进度单调递增；`eventCursor` 指向该操作最新事件的全局 sequence。缓存命中和 Abaqus worker 的 `ODB_CHECK` 消息都会推进 `progress.completed`，完成后 `currentItem` 复位为空字符串。

只有 runner 返回全部请求路径、没有重复/越界结果且每项状态合法时，控制面才能发布 `succeeded`。成功时 `results` 保持请求顺序：

```json
{
  "path": "G:\\计算工程\\case-2.odb",
  "status": "valid",
  "message": "可由本机 Abaqus 直接读取",
  "sizeBytes": 1048576,
  "stepCount": 3
}
```

逐文件 `status` 为 `valid`、`upgrade_required`、`newer_release`、`invalid`、`missing` 或 `empty`。无法获得步数时 `stepCount` 为 `null`。文件锁、损坏、许可证等由现有 worker 归入相应逐文件结果；worker 启动失败、非零退出、缓存/报告错误或结果协议不完整则使整个操作进入 `failed`：

```json
{
  "code": "COMPATIBILITY_CHECK_FAILED",
  "message": "可读的失败摘要",
  "retryable": true,
  "details": {
    "exceptionType": "RuntimeError"
  }
}
```

### 查询操作

枚举操作：

```http
GET /api/v1/operations?activeOnly=true
```

`activeOnly` 可省略，默认 `false`；只接受小写 `true` 或 `false`。响应按创建时间从新到旧返回 `operations` 数组及当前全局 `eventCursor`。WinUI 页面加载时查询活动操作，利用快照中的 `request.root` 与 `request.paths` 重建列表，然后从最新版本继续轮询。操作历史和请求元数据只保存在当前控制面进程内。

```http
GET /api/v1/operations/<operationId>
```

成功返回 `200 OK` 和当前完整快照。不存在的 ID 返回 `404 OPERATION_NOT_FOUND`。客户端重启但控制面实例仍存活时，可用原 `operationId` 重新取得状态和结果。

### 取消操作

```http
POST /api/v1/operations/<operationId>/cancel
```

取消不需要请求正文，返回 `202 Accepted` 和最新快照。非终态先进入 `cancelling`；控制面调用该操作持有的 `ProcessController.cancel()`，终止已经 attach 的 Abaqus 进程树，随后进入 `cancelled`。在 attach 前取消也会让后续进程立即终止。重复取消以及对终态取消均为幂等操作，不改变已有终态；若取消先进入 `cancelling`，随后到达的 runner payload 会被丢弃，不得覆盖为 `succeeded`。

兼容性操作发布：

- `odb.compatibility.queued`
- `odb.compatibility.starting`
- `odb.compatibility.running`
- `odb.compatibility.progress`
- `odb.compatibility.cancelling`
- `odb.compatibility.succeeded`
- `odb.compatibility.cancelled`
- `odb.compatibility.failed`

事件的 `aggregateType` 为 `operation`，`aggregateId` 等于 `operationId`，并携带相同 `attemptId`、操作版本、状态和进度。

## 事件重放

控制面已提供以下有限重放端点；当前 WinUI 客户端通过 REST 快照轮询更新兼容性操作，并记录响应中的 `eventCursor`。应用重新打开时会枚举仍在同一控制面实例中执行的操作并恢复轮询，但尚未消费 SSE、执行 sequence 去重，也没有在控制面进程重启后恢复内存操作，因此这些能力仍属于后续契约工作。

```http
GET /api/v1/events?after=<non-negative-sequence>
Accept: text/event-stream
```

第一阶段采用有限 SSE：控制面按 sequence 重放当前进程内 `after` 之后的历史，然后发送 `replay-complete` 注释并关闭连接。客户端记录 `X-Event-Cursor`，以该值继续短轮询。若未传 `after`，可使用 `Last-Event-ID`；二者均未提供时从 `0` 开始。

```text
id: 2
event: odb.discovery.completed
data: {"schemaVersion":1,"sequence":2,"eventId":"...","occurredAt":"...","aggregateType":"odbDiscovery","aggregateId":"...","attemptId":"","version":2,"kind":"odb.discovery.completed","payload":{"root":"G:\\计算工程","recursive":true,"count":1,"warningCount":0}}

: replay-complete cursor=2
```

事件交付语义为至少一次。客户端必须按单调 `sequence` 去重，REST 响应仍是业务快照真相。


## 全受管后台退出预留

为兼容旧客户端，继续使用经过鉴权的 `POST /api/v1/odb-upgrade-shutdown-check`。这会在全部空闲时预留退出并拒绝新任务，因此不是普通状态轮询。当前成功响应包含：

```json
{"schemaVersion":1,"scope":"all-workers-v1","safeToStop":true,"operations":[]}
```

检查范围为批量结果、单步合并、升级、本机队列/作业、后处理、兼容性、索引、远端传输和远端作业。任何管理器活动、线程未收尾或持久记录不可确认时拒绝整体预留；返回非空 `operations` 或 `safeToStop:false`，其他管理器仍可使用。运行状态未知时可能直接返回错误，新客户端同样保留后台。新客户端必须校验 `scope`，不能将旧版只覆盖 ODB 的成功响应视为允许结束整个后台。健康能力为 `controlPlane.shutdown.all-workers-v1`。关闭交互、同步命令协调与完整 Prepare/Commit/Abort 不在本接口完成范围，见 [ADR 0008](submitter/adr/0008-all-worker-shutdown-fence.md)。
