# Abaqus Tools 本地控制面 API v1

本文件记录 WinUI 3 前端与 Python 3.14 控制面的 v1 合同及后续扩展；基础切片和新增业务约定并列保留。准确入口见[功能索引](03-features/FUNCTION_INDEX.md)，功能完成状态与运行证据见[当前状态](08-handoff/CURRENT_STATUS.md)，不以协议存在证明迁移已验收。控制面只监听 IPv4 回环地址，不导入 Qt，也不允许前端直接提交 shell 命令。

## 启动与就绪

### 外部扫描响应补充（2026-11-18，F004/F005）

队列快照新增 `externalScanActive` 布尔字段，旧后台缺省 false。包括 `GET /api/v1/job-queues`、`GET /api/v1/local-queue-runtime` 的 queue 及队列命令响应的 snapshot；扫描期间读取最近保存状态。`scanExternalJobs` 命令保持同步返回最终结果，同一后台重复手动扫描返回 409 `EXTERNAL_SCAN_BUSY`；关闭后拒绝开始/合并，返回 503 `CONTROL_PLANE_SHUTTING_DOWN`。

成功响应的 `added`、`updated`、`statusOnlyUpdates` 按实际合并条数统计；有过期或本机执行器管理记录时新增可选 `stats.staleResultsSkipped`，不会覆盖扫描期间的新状态。扫描失败不发布部分结果。目录输入和原状态证据规则不变，详见 [本机扫描说明](03-features/LOCAL_SCHEDULING.md)。

### 连接状态响应补充（2026-11-18，F008）

`GET /api/v1/remote-servers` 的 `connection` 新增可选 `busy`（布尔，旧后台缺省 false）和 `activity`（可读状态文本，空闲为空）。远端 I/O 执行期间返回最近完整发布的状态，不等待连接锁；资源值沿用原采样时间，并明确为上次读取。连接切换时 `status=connecting`、`resource=null`，不沿用旧机器资源。操作完成/失败/需确认指纹后发布对应状态并清除 busy。服务器命令 POST 返回本次操作的最终快照，仍遵守身份/指纹/活动任务校验。只读返回值与内部资源独立，事件游标随对应完整快照发布。

`POST /api/v1/remote-server-commands` 的 `refresh` / `disconnect` 可附已有结构的非敏感 `profile`，含主机、端口、用户名、指纹、计算目录、Abaqus命令与允许目录。后台在同一通信锁内用server_identity核对当前连接，再执行动作；不匹配返回409 `REMOTE_CONNECTION_CHANGED`，不刷新/断开其他服务器。WinUI新入口携带发起时身份；旧客户端省略profile的调用保持兼容。配置名称不是身份替代，密码或私钥内容不随此请求发送。

### GPU 与精度补充（2026-11-18，F028）

本机草稿/入队 draft、远端预览/创建增加可选 `gpuCount`（null 或 0–1024 整数）、`explicitPrecision`（default/off/explicit/both/constraint）、`outputPrecision`（default/single/full）。缺省均沿用环境，GPU=0 明确关闭；拒绝布尔、小数 GPU 及未知/null 精度。错误 400 `INVALID_EXECUTION_OPTIONS`。Explicit 双精度配单个用户子程序 .obj/.o 同样在启动前拒绝。

队列更新省略字段保持原值；gpuCount:null 和精度 default 撤销覆盖。队列投影与远端 request 快照公开三字段；远端恢复缺字段的旧记录取默认。同请求 ID 改变任一选项为请求冲突。三项进入非默认内存历史键，但不构成 GPU 独占调度；详见 [F028](03-features/EXECUTION_OPTIONS.md)。

### 作业结束提醒补充（2026-11-18，F027）

健康能力 `job.notifications-v1`。`GET /api/v1/job-notifications` 返回 `schemaVersion=1`、`unreadCount`、最多 50 条未读 `items`、可空的 `persistenceWarning`；每条含 `id/source/executionId/jobId/jobName/status/message/workDirectory/observedAt/read`，按记录时间倒序。`observedAt` 是记录/恢复观察时间。`status` 仅为 succeeded/failed/cancelled；未知、断线和活动状态不作为结束。

`POST /api/v1/job-notification-acknowledgements` 只接受 `{schemaVersion:1, ids:[...]}`，1–50 个已知 ID。重复确认幂等，逐条持久保存后返回当前快照；批量后续项失败时先前已保存项不回滚。错误为 400 `INVALID_JOB_NOTIFICATION_ACK`、404 `JOB_NOTIFICATION_NOT_FOUND`、503 `JOB_NOTIFICATION_HISTORY_UNAVAILABLE` / `JOB_NOTIFICATION_STORAGE_UNAVAILABLE`。遵循普通 POST 关闭准入，准备关闭/已预留退出时拒绝修改。

远端请求可选 `notify`，严格布尔类型，省略默认 true；进入请求幂等签名及持久恢复记录。本机沿用 `complete_notify`。队列条目增加 `attemptId`（旧条目为空）；查看本机提醒必须匹配此执行 ID，不能仅以 job ID 或名称定位。提醒规则见 [F027 说明](03-features/JOB_NOTIFICATIONS.md)。

### 远端完成确认补充（2026-11-18，F010）

持久恢复补充：快照新增可选 `trackingState`（preparing/tracking/reconnecting/submission_unknown/unverified/finished/interrupted）和 `persistenceWarning`。启动后 SSH 失败不再返回终态失败，而保持 running/cancelling；重连后核对原回执与原任务。历史错误返回 503 `REMOTE_JOB_HISTORY_UNAVAILABLE`；保存错误返回 503 `REMOTE_JOB_STORAGE_UNAVAILABLE`，不启动新计算。preparing 阶段后台重启返回 failed / `REMOTE_PREPARATION_INTERRUPTED`，明确没有自动提交；线程提交失败为 `REMOTE_JOB_DISPATCH_FAILED`。同一 `clientRequestId`、同参数跨后台返回原操作，不重新要求已上传本地源文件存在；新请求仍验证本地文件。活动作业只允许连接相同的固定服务器身份/路径范围，存在活动传输时仍拒绝切换/重连，返回 409 `REMOTE_SESSION_BUSY`。取消先持久保存，未核对时暂缓远端控制；暂停/恢复在非 tracking 状态返回 409 `REMOTE_JOB_NOT_STARTED`。细节见 [ADR 0012](submitter/adr/0012-durable-remote-tracking.md)。

`remote-jobs` 的公开 DTO 结构保持兼容。收到成功文本后仍为 running（取消请求期间 cancelling），phase 说明正在确认，须 launcher/锁已停止且四种输出签名连续 3 次稳定才终结。数据检查不再凭进程连续消失判成功；稳定 5 次无成功证据返回 failed / `REMOTE_JOB_EXIT_UNCONFIRMED`。错误与非请求终止优先于成功，代码分别为 `ABAQUS_REMOTE_ERROR`、`REMOTE_JOB_TERMINATED`；不可读探测继续活动并重置确认。内部探针增加 launcher 创建时间、probe_complete、output_signature、DAT/MSG 尾部；它们不是新增公共请求字段。细节与连接中断/重启限制见 [远端作业说明](03-features/REMOTE_JOBS.md)。

### 本机调度补充（2026-11-18，F004/F005）

`GET /api/v1/local-queue-runtime` 保留现有结构并增加可选兼容字段 `schedulerMessage`（空字符串表示无调度提示）；`operations[]` 增加 `attemptId`，每次真正分配执行生成新的身份，后台重启观察原作业时保留身份、不重放操作。

`POST /api/v1/local-queue-controls` 的 `start` 在待运行未暂停条目的 Core 未设置时返回 409 `LOCAL_QUEUE_CORE_REQUIRED`，`details.jobNames` 列出作业。队列不足或状态未核对不构成重复提交的许可。资源、依赖和目录等待显示在队列消息与 `pendingReason`；保存/派发异常暂停新派发并设置 `schedulerMessage`。队列文件损坏保留原文件，队列 API 返回 500 `JOB_QUEUE_STATE_UNREADABLE`，不阻止健康检查和其余服务启动。

`POST /api/v1/job-queue-commands` 的 `clearFinished` 保留状态未知条目；删除未知或活动条目返回 409 `ACTIVE_QUEUE_ITEMS_PROTECTED`，重新排队未知条目返回 409 `QUEUE_ITEMS_NOT_REQUEUEABLE`。扫描核对后处于待确认状态的条目允许用户明确重新排队。重启扫描及双文件持久边界见 [本机调度说明](03-features/LOCAL_SCHEDULING.md)。

### 本机内存观测补充（2026-11-18，F005/F007）

队列条目保留原 `runtimeMemoryBytes`（队列持久字段为 `rss_bytes`），新增兼容可选字段 `memoryObservationStatus`、`memoryPeakBytes`、`memoryEstimatedBytes`、`memorySampleCount`、`memoryEstimateSource`。旧客户端可忽略，旧响应在新客户端取空字符串/0 默认值。

`memoryObservationStatus` 为 `observed`（10 秒内且非未来的有效样本）、`waiting`、`unavailable`、`stale`、`ended` 或空字符串（旧记录）。非 observed 状态下旧 `runtimeMemoryBytes` 只供诊断，不应展示为新鲜占用或用于抵扣预留；结束清当前 RSS 并保留本次峰值。`memoryPeakBytes` 是该次执行的有效观测峰值；`memoryEstimatedBytes` 是带安全余量的调度参考。来源为 `observed`、`history`、`reference` 或空字符串；reference 明确指本次后台运行中其他作业的最大估计，不是该模型实测。

外部刷新即使 RSS 不变也会持久更新时间，内部时间戳不作为新增公开字段。采样失败不构成求解失败；历史保存失败通过 `schedulerMessage` 提示并保留内存重试。队列保存失败仍暂停新派发，不重启求解。身份匹配、采样覆盖及 85% 当前可用内存预算见 [内存说明](03-features/MEMORY_MONITORING.md)。

### 进程启动

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

这是保留的旧主机路径。原生窗口使用下方的新关闭协议；处于关闭准备或存在已接收 POST 时，本旧接口返回 `safeToStop:false`，不抢占准备状态。

## 可撤销的窗口关闭协议

健康能力为 `controlPlane.shutdown.protocol-v1`。所有端点要求同一实例的 Bearer 鉴权，POST 正文必须有 `schemaVersion:1`，不接受未知字段。响应 `kind` 为 `controlPlane.shutdown`，包含 `requestId/state/safeToStop/pendingRequests/operations/stopBackend`；提交后还包含 `mode`。`operations` 仅提供类型、操作标识、显示名称和状态，不含凭证。

| 请求 | 正文字段（除 schemaVersion） | 行为 |
|---|---|---|
| POST `/api/v1/shutdown-requests` | `clientRequestId`：1–128 位字母、数字、下划线、点或连字符 | 建立或续期准备；相同 ID 幂等，其他活跃准备返回 409 |
| GET `/api/v1/shutdown-requests/{id}` | 无 | 查询并续期准备；已有完成回执则原样返回 |
| POST `/api/v1/shutdown-requests/{id}/abort` | 无 | 放弃准备并恢复准入；不撤回已经发出的停止 |
| POST `/api/v1/shutdown-requests/{id}/stop` | 无 | 停止调度并向管理器请求合作停止；不终止归属未知进程 |
| POST `/api/v1/shutdown-requests/{id}/commit` | `mode`：`idle`、`background` 或 `stop` | background 保留后台；idle/stop 要求所有任务、线程与已接收 POST 都结束后，由后台自行退出 |

准备租约为 60 秒，读取/停止会续期，窗口选择弹窗每 10 秒续期。租约失效返回 `SHUTDOWN_REQUEST_EXPIRED`；不会永久封锁操作。准备时新普通 POST 返回 503 `CONTROL_PLANE_CLOSE_PENDING`，已提交退出时为 `CONTROL_PLANE_SHUTTING_DOWN`。已接收请求由计数保护，仍在执行时停止/提交返回 409 `SHUTDOWN_REQUESTS_BUSY`。活动工作阻止 idle/stop 提交，返回 `SHUTDOWN_WORK_ACTIVE`；未先 stop 而提交 stop 返回 `SHUTDOWN_STOP_NOT_REQUESTED`。回执与不同提交方式冲突返回 `SHUTDOWN_COMMIT_CONFLICT`。

仅保存最近 32 个进程内完成回执，不承诺跨后台重启保存。客户端遇到提交回执丢失，只能查询原实例；不得以断连推断停止成功，或根据旧回执终止替换后台。已提交 idle/stop 后，即使响应连接丢失，后台仍完成清理退出。响应前限时读取大小受限的已声明未读正文，既覆盖解析前被拒的请求，也覆盖取消等不解析可选正文的成功命令，避免 Windows 连接重置遮蔽 200/202 或 401/503；不执行被拒请求。协议实现见 [ADR 0009](submitter/adr/0009-reversible-workbench-close.md)。

### 旧接口响应与范围

为兼容旧客户端，继续使用经过鉴权的 `POST /api/v1/odb-upgrade-shutdown-check`。这会在全部空闲时预留退出并拒绝新任务，因此不是普通状态轮询。当前成功响应包含：

```json
{"schemaVersion":1,"scope":"all-workers-v1","safeToStop":true,"operations":[]}
```

检查范围为批量结果、单步合并、升级、本机队列/作业、后处理、兼容性、索引、远端传输和远端作业，以及尚未保存的结束提醒（已保存未读不阻止退出）。任何管理器活动、线程未收尾或持久记录不可确认时拒绝整体预留；返回非空 `operations` 或 `safeToStop:false`，其他管理器仍可使用。运行状态未知时可能直接返回错误，新客户端同样保留后台。新客户端必须校验 `scope`，不能将旧版只覆盖 ODB 的成功响应视为允许结束整个后台。健康能力为 `controlPlane.shutdown.all-workers-v1`。关闭交互、同步命令协调与完整 Prepare/Commit/Abort 不在本接口完成范围，见 [ADR 0008](submitter/adr/0008-all-worker-shutdown-fence.md)。

后台能力为 `job.execution-options-v1`。正式客户端在发送这组参数前核对同一后台实例的能力；连接旧后台时明确提示安全退出旧后台后更新，不发送预览/提交/编辑 POST，不自动停止原作业或替换其后台。
