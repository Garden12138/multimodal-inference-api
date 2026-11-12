# 实现报告

日期：2026-11-12。仓库是独立的 `multimodal-inference-api`，不是 Studio 的子模块。

## 结果

本机已经有一个不依赖 Studio 的 FastAPI 服务。图片和视频任务进入自己的 SQLite，由各自的 Worker 直接调用 ComfyUI。Mock 测试 23 项通过。`127.0.0.1:8090` 已启动并完成不产生推理的 HTTP 验收，随后已停止。

真实 GPU 生成没有执行。验收时 `GET /system_stats` 对 `127.0.0.1:8190` 和 `127.0.0.1:8189` 均不可达。

## 目录

```text
app.py
deploy/inference-api.user.service
docs/implementation-inventory.md
docs/spec/01-requirements.md
docs/spec/02-architecture.md
docs/spec/03-api-contract.md
docs/spec/04-implementation-plan.md
docs/deployment/local-development.md
docs/deployment/server-104.md
docs/integration/agent-integration.md
docs/integration/curl-examples.md
docs/operations/security.md
docs/operations/troubleshooting.md
docs/reports/automated-test-report.md
docs/reports/implementation-report.md
inference/
scripts/install.sh
scripts/start.sh
scripts/status.sh
scripts/stop.sh
tests/
workflows/image/t2i_1mp_api.json
workflows/image/t2i_4mp_api.json
workflows/video/t2v_api.json
workflows/video/i2v_api.json
workflows/video/flf_api.json
requirements.txt
requirements-dev.txt
.env.example
```

`.venv/`、`data/` 和 `.env` 不进入版本库。本次没有创建 `.env`。

## 已实现 API

| 方法 | 路径 |
|---|---|
| GET | `/healthz` |
| GET | `/v1/health` |
| POST | `/v1/images/generations` |
| GET | `/v1/images/generations/{task_id}` |
| GET | `/v1/files/{asset_id}` |
| GET | `/v2/health` |
| POST | `/v2/video_generation` |
| GET | `/v2/query/video_generation/{task_id}` |
| GET | `/v2/files/{task_id}` |

没有音乐生成接口。

## 本地 HTTP 验收

监听 `127.0.0.1:8090`，`VIDEO_ALLOW_RESOLUTION_FALLBACK=0`。没有发送会被 Worker 提交给 ComfyUI 的有效生成请求。

| 检查 | 结果 |
|---|---|
| `GET /healthz` | 200 `{"status":"ok"}` |
| 无密钥访问 `/v1/health` | 401 |
| `GET /v1/health` | 200，图片和视频 `reachable: false`，五份工作流均为 `true`，音乐 `not_implemented` |
| `GET /v2/health` | `degraded`，`backend_connected: false`，`native_resolution: 608x352`，`studio_dependency: false` |
| 图片 `size=512x512` | 422 |
| 无密钥创建图片 | 401 |
| 视频 `768P` 且未打开降级 | 422，消息说明实际输出是 `608x352` |
| 视频 `2K` | 422 |
| 远程图片 URL | 422 |
| 日志 | 不含本次使用的 API Key |
| `scripts/stop.sh` | 只停止记录的 pid |

## 与原始代码的差异

- 视频创建不再调用 Studio 的 `/api/tasks`。参考图直接 `POST` 到视频 ComfyUI `/upload/image`，然后提交对应工作流。
- 工作流字节与 Studio 已验证文件一致。提交时只替换提示词、输出前缀和图片 seed。前缀改为 `inference_{task_id}` / `video/inference_{task_id}`。
- 视频文件从 `workflows/*.json` 移到 `workflows/video/`，内容不变。
- 不确定的 `/prompt` 结果记为 `needs_review`，不再伪装成失败，也不会自动重试。
- 新增独立图片 API 和独立 SQLite。
- 开发端口是 8090。配置或脚本遇到 8089 会拒绝启动。
- 密钥以 `INFERENCE_API_KEY` 为唯一优先项。

## 安全检查

- 无效密钥返回 401，响应和日志都不含密钥。
- 默认 CIDR 之外返回 403，由单元测试覆盖。
- `storage_key` 中的 `..` 和绝对路径被拒绝。
- ComfyUI 的 `requests.Session.trust_env` 为 `False`。
- 视频下载必须带 HMAC。过期签名返回 403。
- 服务代码中没有 Studio 任务 API 客户端。
- 单密钥模型没有按 Agent 分权。知道任务编号的持钥调用方可以读取该任务。

## 尚未完成

- 104 上的真实图片和视频验收：BLOCKED。
- 本机真实 GPU 验收：BLOCKED，8190 和 8189 在本次验收中不可达。
- 切换或停止现有 8089 服务：明确不做。
- Music3 推理：明确不做。

## 后续和 Studio 对接

Studio 仍应保留自己的页面和数据库。对接时让 Studio 作为客户端调用本服务的 `/v1/images/generations` 和 `/v2/video_generation`，不要再让 Native API 回调 Studio，也不要让 Studio 和本服务同时向同一个 ComfyUI 提交同一条用户请求。

在 8090 完成真实样本验收之前，不要把现有 8089 流量切过来。
