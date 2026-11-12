# 排障

## 服务起不来

- `API key must be set`：`.env` 里的 `INFERENCE_API_KEY` 为空，且没有可用的 `H3_MINIMAX_API_KEY`。
- `INFERENCE_PORT=8089 is refused`：这是保护行为。试运行使用 8090。
- `.env mode` 不是 `600`：`chmod 600 .env` 后重新启动。
- 端口占用：`scripts/start.sh` 不会杀掉占用者。先确认占用者不是本服务，再改本地端口。不要为了腾端口去停止 8089。

查看日志：

```bash
tail -n 80 data/logs/inference.log
bash scripts/status.sh
```

## 健康检查 degraded

`/v2/health` 的 `backend_connected: false` 表示视频 ComfyUI 没有返回 `GET /system_stats` 200。先在推理机本机检查 `8189` 是否由原有进程提供服务。不要重启它，除非那是一次单独的 ComfyUI 维护。

工作流缺失或被改动时，Provider 状态是 `degraded`，提交会失败且不会发送 `/prompt`。用测试中的 SHA-256 对比 `workflows/`。

## 视频请求 422

- 没有设置 `VIDEO_ALLOW_RESOLUTION_FALLBACK=1` 时，`768P` 会被拒绝。这是预期行为。
- `duration` 不是整数 `5`，`ratio` 不符合模式，或图片不是 data URL，都会 422。
- `2K` 和其他分辨率没有实现。

## needs_review

任务可能已经进入 ComfyUI，也可能没有。处理方式：

1. 不要用同一个请求自动重试。
2. 在 ComfyUI 历史里按 `client_id`（等于本服务 `task_id`）查看是否有 `prompt_id`。
3. 如果找到了，可以把编号写入该任务的 `provider_task_id` 并把状态改为 `running`，然后重启服务让 Worker 继续查询。这一步是人工修复。
4. 如果确认队列里没有这次提交，再创建一条新任务。

`data/recovery/*.txt` 里只有 `prompt_id`。服务重启时会读它。

## 文件 404 或 409

404 表示数据库没有这个素材，或磁盘文件已经丢失。任务状态不会被改成成功或失败。409 表示文件内容和登记的 SHA-256 不一致，响应不包含磁盘路径。

## 超时

图片默认 1800 秒，视频默认 3600 秒，从进入 `submitting` 开始计算。超时后任务为 `failed`，错误码 `PROVIDER_TIMEOUT`，不会重新提交。ComfyUI 里原任务可能仍在运行，需要人工查看后再决定是否新建。
