# 安全

## 密钥

- 密钥只来自环境变量或权限为 `600` 的 `.env`。
- 优先级是进程环境覆盖 `.env`；在同一环境里，非空的 `INFERENCE_API_KEY` 覆盖 `H3_MINIMAX_API_KEY`。空字符串视为未设置。
- 密钥至少 24 个字符。
- 日志过滤器会去掉包含 Bearer 或密钥本身的消息。`Settings` 的调试字符串不包含密钥。
- 不要把 `.env`、`data/` 或恢复文件提交到 Git。

## 网络和下载

- `INFERENCE_ALLOWED_CIDRS` 默认是 loopback。空列表会拒绝所有来源。旧变量 `H3_ALLOWED_CIDRS` 不会被读取，避免两套网段策略。
- 视频下载只接受 HMAC 签名，签名材料是 `{task_id}.{expires}`。
- 图片下载接受 Bearer，或材料为 `asset.{asset_id}.{expires}` 的签名。
- 过期时间必须落在当前时间到其后 3700 秒之间。
- 下载前按数据库中的 SHA-256 重新计算文件。不一致返回 409，不把路径写进响应。
- `storage_key` 只能落在 `INFERENCE_DATA_DIR` 内。符号链接和 `..` 会被拒绝。
- 视频参考图只接受 base64 data URL。服务不会根据调用方给出的 `http`、`https` 或 `mm_file` 去拉取文件。

## 任务隔离

V1 是单密钥。持有密钥且知道任务编号的调用方可以查询该任务。签名 URL 在过期前也可以下载对应文件。服务没有任务列表，因此不能靠枚举接口扫出别人的结果；32 位十六进制编号本身不可猜测。这不是按 Agent 分权。

## 不自动重试的原因

`/prompt` 没有明确拒绝时，任务进入 `needs_review`。自动再提交可能让同一次创作消耗两次 GPU。操作者确认 ComfyUI 队列里没有对应 `client_id` 之后，才应新建任务。

## 静态检查

测试会确认服务代码没有 Studio 的 `/api/tasks` 客户端、没有 `trust_env = True`，并且工作流哈希与迁入时一致。
