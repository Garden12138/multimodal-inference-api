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

`needs_review` 是终态。任务表不允许服务自己把它改回 `queued` 或 `running`，接口也没有恢复动作。重启不会重放已经进入 `needs_review` 的任务。

启动时只会处理仍是 `submitting` 或 `running` 的行：找到数据库里的 `provider_task_id`，或找到格式正确的 `data/recovery/{task_id}.txt`，就把该行继续设为 `running` 并接着查询。两者都没有时，这一行变成 `needs_review`，错误码是 `SUBMISSION_UNCERTAIN`。这不会自动重新提交。

处理方式：

1. 不要用同一个请求自动再创建一次。
2. 在对应的 ComfyUI 历史里按 `client_id`（等于本服务 `task_id`）查看是否已经有 `prompt_id`。查看历史不是重启 ComfyUI。
3. 如果没有这次提交，向调用方返回当前错误，并由调用方决定是否新建任务。
4. 如果确认上游已经接受，V1 没有安全的恢复接口。不要为了续跑去改 8089，也不要重启 8189 或 8190。需要人工续跑时，只修改本 API 目录的 `data/inference.db`：在停掉本 API 后，把该任务写成 `running`、填上确认过的 `provider_task_id`、清空 `worker_id`，然后只启动本 API。这一步绕过状态机，只在上游编号已经核对之后进行。不能确认时不要改行。

## 重启、升级和回退

重启本服务使用同一个检出目录里的 `scripts/stop.sh` 和 `scripts/start.sh`。升级或回退前先按 [本地开发](../deployment/local-development.md) 或 [104 部署说明](../deployment/server-104.md) 备份 `data/`。安装脚本不会改已有 `.env`，也不会停止其他端口。

## 文件 404 或 409

404 表示数据库没有这个素材，或磁盘文件已经丢失。任务状态不会被改成成功或失败。409 表示文件内容和登记的 SHA-256 不一致，响应不包含磁盘路径。

## 超时

图片默认 1800 秒，视频默认 3600 秒，从进入 `submitting` 开始计算。超时后任务为 `failed`，错误码 `PROVIDER_TIMEOUT`，不会重新提交。ComfyUI 里原任务可能仍在运行，需要人工查看后再决定是否新建。
