# 自动化测试报告

日期：2026-11-12。命令：`.venv/bin/python -m pytest`。

结果：**23 passed**，1 条 Starlette 弃用警告（`TestClient` 仍使用 `httpx`）。没有失败。

这些测试使用 `FakeTransport` / `ScriptedComfy`。它们不连接 8189 或 8190，**不能**写成真实 GPU 推理成功。

| 文件 | 数量 | 覆盖 |
|---|---|---|
| `tests/test_workflows.py` | 5 | 工作流哈希、1MP/4MP 参数、视频基线、篡改 steps 被拒绝 |
| `tests/test_images.py` | 3 | 提交、查询、1024/2048 成功、失败、尺寸不符、下载、无效提示词、无效尺寸、无效密钥 |
| `tests/test_video.py` | 5 | T2V、I2V、FLF、base64、远程 URL、2K、降级开关、状态、签名、上游失败、`needs_review` |
| `tests/test_tasks.py` | 5 | 并发领取、跨模态并行、重启恢复、不确定提交、轮询超时重试、下载失败重试、任务超时、文件丢失、Worker 异常 |
| `tests/test_config_and_security.py` | 5 | 密钥优先级、拒绝 8089、`trust_env=False`、无 Studio `/api/tasks`、CIDR、路径穿越 |

警告原文：

```text
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
```

这不影响断言。生产运行使用 `uvicorn` 和 `requests`，不依赖 `TestClient`。

## 未执行

| 项目 | 状态 |
|---|---|
| 真实 1024 PNG | BLOCKED。本机验收时 `127.0.0.1:8190` 不可达，且没有提交 `/prompt` |
| 真实 2048 PNG | BLOCKED，同上 |
| 真实 T2V / I2V / FLF | BLOCKED。本机验收时 `127.0.0.1:8189` 不可达，且没有提交 `/prompt` |
| 104 部署后的端到端验收 | BLOCKED。本次没有连接 104 |
