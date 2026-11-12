# 架构

```text
Agent / Studio
        |
        v
Multimodal Inference API :8090
        |
        +-- Image worker --> ComfyUI :8190
        +-- Video worker --> ComfyUI :8189
        +-- SQLite data/inference.db
        +-- files under data/outputs and data/inputs
```

本进程不加载模型。ComfyUI 只执行工作流。业务状态、重试边界和文件所有权都在本服务。

## 模块

| 路径 | 职责 |
|---|---|
| `app.py` | ASGI 入口 |
| `inference/config.py` | 环境变量和密钥优先级 |
| `inference/api/` | 图片、视频、健康检查和文件路由 |
| `inference/auth/middleware.py` | CIDR 与 Bearer |
| `inference/db/` | SQLite、原子领取、重启恢复 |
| `inference/jobs/` | 按模态分开的 Worker |
| `inference/providers/comfyui/` | 上传、提交、轮询、下载 |
| `inference/providers/base.py` | `health/submit/poll/fetch_assets`，以及未实现的 music provider |
| `inference/assets/` | 路径约束和 HMAC |
| `workflows/` | 已验证 API workflow |

`ReservedMusicProvider` 只出现在 `/v1/health` 的 `reserved_providers.music`，状态为 `not_implemented`。没有音乐生成路由。

## 提交边界

1. 请求只做协议校验并写入 `queued`。
2. Worker 用 `BEGIN IMMEDIATE` 把一条 `queued` 任务改为 `submitting`。
3. 参考图上传失败发生在 `/prompt` 之前，任务记为 `failed`，因为生成请求还没发出。
4. `/prompt` 超时、连接中断，或 200 响应里没有可确认的 `prompt_id`，记为 `needs_review`。
5. 收到 `prompt_id` 后先写 `data/recovery/{task_id}.txt`，再写入数据库并进入 `running`。
6. 之后只查询原来的 `prompt_id`。查询超时和下载超时会在任务总超时前重试，不会重新提交。
7. 重启时，有 `prompt_id` 或恢复文件的任务继续查询；两者都没有的 `submitting` 任务进入 `needs_review`。

图片和视频使用不同的 Worker 池，因此两种模态可以同时处于 `running`。同一模态默认串行。

## 数据表

`inference_tasks`：`id`、`media_type`、`model`、`mode`、`prompt`、`params_json`、`status`、`provider`、`provider_task_id`、`created_at`、`started_at`、`finished_at`、`error_code`、`error_message`。另有运维字段 `worker_id`，用于避免两个 Worker 同时处理同一条运行中的任务。

`inference_assets`：`id`、`task_id`、`media_type`、`mime_type`、`filename`、`storage_key`、`size_bytes`、`sha256`、`created_at`。

数据库使用 WAL。领取语句要求 `status='queued'` 仍成立，`rowcount` 必须为 1。
