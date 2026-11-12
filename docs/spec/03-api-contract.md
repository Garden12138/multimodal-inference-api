# API 契约

基础地址在开发环境为 `http://127.0.0.1:8090`。除 `GET /healthz` 外，请求需要：

```http
Authorization: Bearer <INFERENCE_API_KEY>
```

调用方还必须来自 `INFERENCE_ALLOWED_CIDRS`。下载接口在通过签名校验后可以不带 Bearer，但仍受 CIDR 限制。

认证失败使用各自协议的错误体。视频：

```json
{"type":"error","error":{"type":"authorized_error","message":"Invalid or missing API key","http_code":"401"}}
```

图片：

```json
{"error":{"code":"UNAUTHORIZED","message":"Invalid or missing API key","type":"authorized_error"}}
```

## 已实现路由

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/healthz` | 进程存活，不含上游细节 |
| GET | `/v1/health` | 图片和视频 Provider 状态；音乐为 `not_implemented` |
| POST | `/v1/images/generations` | 创建图片任务，HTTP 202 |
| GET | `/v1/images/generations/{task_id}` | 查询图片任务 |
| GET | `/v1/files/{asset_id}` | 下载已登记图片，Bearer 或签名 |
| GET | `/v2/health` | 视频协议健康检查 |
| POST | `/v2/video_generation` | 创建视频任务，HTTP 200 |
| GET | `/v2/query/video_generation/{task_id}` | 查询视频任务 |
| GET | `/v2/files/{task_id}` | 签名下载视频 |

没有 `GET /v1/music`、任务列表或取消接口。

## 图片

```json
{"model":"MiniMax-H3-Image","prompt":"A cinematic mountain lake at sunrise","size":"2048x2048"}
```

`size` 只允许 `1024x1024` 和 `2048x2048`。`prompt` 去掉首尾空白后为 1 到 4000 个字符。未知字段返回 422。

创建响应：

```json
{"task_id":"<32 hex>","model":"MiniMax-H3-Image","status":"queued","size":"2048x2048"}
```

查询响应：

```json
{
  "task_id": "<32 hex>",
  "model": "MiniMax-H3-Image",
  "status": "succeeded",
  "size": "2048x2048",
  "assets": [
    {
      "asset_id": "<32 hex>",
      "mime_type": "image/png",
      "url": "/v1/files/<asset_id>?expires=<unix>&signature=<hex>",
      "sha256": "<hex>",
      "size_bytes": 123
    }
  ]
}
```

`status` 取 `queued`、`submitting`、`running`、`succeeded`、`failed`、`needs_review`。失败和 `needs_review` 带 `error.code` 与 `error.message`。`needs_review` 同时带 `attention_required: true`。

成功图片必须是可解码 PNG，尺寸与 `size` 一致，并保存在本服务目录。不满足时任务为 `failed`，`error.code` 为 `RESULT_INVALID`。

## 视频

创建请求与原 V2 子集相同。

```json
{
  "model": "MiniMax-H3",
  "content": [{"type": "text", "text": "A cinematic scene"}],
  "resolution": "768P",
  "duration": 5,
  "ratio": "16:9"
}
```

文生视频的 `ratio` 必须是 `16:9`。图生和首末帧可以是 `adaptive`、`16:9` 或省略。图片只接受 `data:image/png`、`data:image/jpeg`、`data:image/webp` 的 base64。边长 256 到 5760，宽高比 0.4 到 2.5，单张不超过 12 MiB。`role` 只允许 `first_frame` 和 `last_frame`，不能只有末帧。

`duration` 只能是整数 `5`。`resolution` 只能是 `768P`，并且 `VIDEO_ALLOW_RESOLUTION_FALLBACK=1`。否则 422。

成功创建：

```json
{"task_id":"<32 hex>"}
```

响应头：

```text
X-H3-Native-Resolution: 608x352
X-H3-Resolution-Adjusted: true
```

查询体：

```json
{
  "task": {
    "id": "<32 hex>",
    "model": "MiniMax-H3",
    "status": "succeeded",
    "created_at": 0,
    "updated_at": 0,
    "content": {"url": "http://127.0.0.1:8090/v2/files/<task_id>?expires=<unix>&signature=<hex>"},
    "resolution": "608x352",
    "requested_resolution": "768P",
    "duration": 5,
    "ratio": "16:9",
    "task_type": "generation",
    "modality": "video",
    "resolution_source": "verified_workflow_baseline"
  }
}
```

内部 `submitting` 在视频查询里显示为 `running`。`needs_review` 保持原样，并带 `attention_required` 和 `error.code=submission_uncertain`。失败时 `error.code` 仍是 `local_generation_failed`，`detail_code` 是内部错误码。

`GET /v2/files/{task_id}` 必须带未过期签名。链接约 1 小时内有效，允许的时间窗口与原实现一致，不超过当前时间加 3700 秒。文件未完成时返回 409。

`GET /v2/health`：

```json
{
  "service": "h3-minimax-v2",
  "implementation": "multimodal-inference-api",
  "status": "ok",
  "backend_connected": true,
  "native_resolution": "608x352",
  "degraded_resolution_compat": false,
  "studio_dependency": false
}
```

`backend_connected` 只表示视频 ComfyUI 的 `GET /system_stats` 返回 200。它不表示真实生成已经成功。

## 错误码

常见图片错误码：`INPUT_INVALID`、`UNAUTHORIZED`、`NOT_FOUND`、`FILE_MISSING`、`FILE_TAMPERED`、`RESULT_INVALID`、`PROVIDER_REJECTED`、`PROVIDER_TIMEOUT`、`SUBMISSION_UNCERTAIN`。

视频协议错误仍用 `error.type` 与 `error.message`，不用图片错误码作为外部主字段。
