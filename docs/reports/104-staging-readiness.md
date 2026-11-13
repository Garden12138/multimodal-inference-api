# 104 预发就绪

> 阅读说明（2026-11-13）：本文撰写时真实生成是 NOT RUN，这个结论保留。后来的 HTTP 真实验收见 [104 远程真实验收](104-remote-acceptance-2026-11-13.md)。发布收尾见 [V1 发布验收](v1-release-acceptance.md)。104 运行进程修订是 DEPLOYMENT_REVISION_UNVERIFIED。

日期：2026-11-12。分支：`feature/native-api-v1`。审查基线：`141e1520ca2b987967bc42f6ea7a42c76c45818e`。

代码与本地生命周期结论：**READY_FOR_104_STAGING**。

真实 GPU 生成：**NOT RUN**。Mock 通过只说明队列、停止和文件边界按测试替身工作，不能当作 8189 / 8190 或 104 上的生成验收。2026-11-13 的远程真实结果另见 [104 远程真实验收](104-remote-acceptance-2026-11-13.md)，结论为 PASS。下面的 NOT RUN 仍是本报告撰写时的状态。

本次没有连接、部署或重启 104，没有修改五份已验证工作流，没有修改模型、步数、注意力后端或分辨率，没有修改 Studio 仓库，没有删除现有 SQLite 数据，也没有推送。

## 1. I2V / FLF 参考帧与入队竞态

任务编号先生成，参考帧写入 `inputs/{task_id}/` 之后才插入 `queued` 行。保存失败时删除已写入的片段，不留下可领取任务。T2V 没有参考帧，仍然直接入队。对外响应仍是 `{"task_id"}` 加原来的分辨率头。

| 项 | 内容 |
|---|---|
| 修复文件 | `inference/api/video_minimax.py`，`inference/db/repository.py` |
| 测试 | `tests/test_reference_race.py`。保存被挡住时并发 `claim_next` 看不到行；放行后参考帧路径存在且可领取。保存抛出 `OSError` 时任务数为 0，输入目录没有残留文件。 |
| 剩余风险 | 文件已落盘但数据库插入失败时，片段会被删除，调用方得到 `STORAGE_FAILED`。这不产生半成品队列任务。 |
| 部署建议 | 部署新代码后再接收 I2V / FLF。不要把旧进程和新代码同时指向同一个数据库。 |

## 2. Worker 停止事件

`process_one` 使用调用方传入的 `threading.Event`。`worker_loop` 和 `drain` 都传递应用生命周期里的同一个事件。事件已置位时不再领取。已领取但还没有上游任务编号时退回 `queued`。已经拿到上游编号时停止轮询、释放 worker，状态保持 `running`，重启后按原编号继续查询。

| 项 | 内容 |
|---|---|
| 修复文件 | `inference/jobs/worker.py`，`inference/jobs/scheduler.py`，`inference/db/models.py`，`inference/db/repository.py` |
| 测试 | `tests/test_shutdown.py`。覆盖停止后不领取、提交前退回队列、提交返回后保留 `prompt-1` 且恢复时不重复提交、轮询中停止后保留编号并在下次继续查询、`worker_loop` 在事件已置位时退出。 |
| 剩余风险 | 正在进行的 ComfyUI HTTP 调用不会被中途取消。进程退出时，守护线程会在 lifespan 的 2 秒 join 超时后随进程结束。已经写入数据库或恢复文件的上游编号会保留；提交请求还没返回时没有编号可保留，重启后进入既有的 `needs_review`，不会自动重提。 |
| 部署建议 | 使用 `scripts/stop.sh` 发送 SIGTERM。不要对这条进程使用 SIGKILL。若脚本报告 10 秒内未退出，先核对 PID 和命令行，再决定是否继续等待。 |

## 3. `scripts/stop.sh` 只停止本仓库进程

PID 必须是十进制数字。进程已退出或只剩僵尸时删除 pid 文件，不发信号。存活进程的命令行必须包含 `-m inference.runtime`，并且命令行包含本仓库路径或当前工作目录等于本仓库。否则拒绝，不删除 pid 文件。仍然只发 SIGTERM，不发 SIGKILL。

| 项 | 内容 |
|---|---|
| 修复文件 | `scripts/stop.sh` |
| 测试 | `tests/test_stop_script.py`。`sleep` PID 不被杀死且脚本失败；不存在的 PID 只删除 pid 文件；非法 PID 被拒绝；本仓库 `18190` 上的 runtime 可以被同一脚本停止。 |
| 本地证据 | `scripts/start.sh` 在 `127.0.0.1:8090` 启动成功，`GET /healthz` 返回 200。`scripts/stop.sh` 随后停止该进程，8090 不再监听，pid 文件被删除。日志中没有 API Key，也没有 `Bearer`。8089 未监听，本次没有操作它。 |
| 剩余风险 | 身份判断依赖命令行和 `lsof` 的 cwd。若两者都不可用，脚本会拒绝而不是猜测。这是有意的失败关闭。 |
| 部署建议 | 每个检出目录使用自己的 `data/inference.pid`。不要用这份脚本停止 8089、8189、8190 或其他目录里的推理服务。 |

## 4. 工作流测试不再依赖 Studio 绝对路径

默认测试只读取本仓库 `workflows/` 和 `inference/workflows/manifest.py` 的 SHA-256。跨仓库字节比较改为设置 `INFERENCE_REFERENCE_WORKFLOW_DIR` 后才运行。源码和文档中的个人绝对路径已去掉。五份工作流 JSON 未改。

| 项 | 内容 |
|---|---|
| 修复文件 | `tests/test_workflows.py`，`docs/implementation-inventory.md` |
| 测试 | `test_workflow_bytes_match_sha256_manifest` 在没有 Studio 仓库时通过。`test_optional_external_workflow_bytes` 本次为 skipped。 |
| 剩余风险 | 默认测试证明仓库内文件与清单一致，不证明它们与另一台机器上的 Studio 副本逐字节相同。需要这层比较时显式设置环境变量。 |
| 部署建议 | 104 上不需要检出 Studio 才能运行这组测试或启动服务。 |

## 5. `/v1/files/{asset_id}` 只提供图片

图片下载要求 `media_type=image`，并且 MIME 属于 PNG、JPEG、WebP。视频仍只走带签名的 `GET /v2/files/{task_id}`。类型不匹配返回 404。

| 项 | 内容 |
|---|---|
| 修复文件 | `inference/api/files.py`，`tests/test_video.py` |
| 测试 | 视频资产访问 `/v1/files/{asset_id}` 返回 404；同一任务的 `/v2/files/{task_id}` 签名链接仍返回 `video/mp4`。既有图片成功用例仍从 `/v1/files/` 下载 PNG。 |
| 剩余风险 | 没有新增公开状态或路由。旧的视频资产 ID 不能再从 v1 下载，这是收紧后的预期行为。 |
| 部署建议 | 调用方继续用视频查询响应里的签名 URL 下载视频。 |

## 自动化测试

命令：`.venv/bin/python -m pytest`。

结果：**36 passed，1 skipped**。skipped 是未设置 `INFERENCE_REFERENCE_WORKFLOW_DIR` 的可选跨仓库比较。没有失败。

| 文件 | 收集数 | 本次新增覆盖 |
|---|---|---|
| `tests/test_reference_race.py` | 3 | 参考帧入队竞态、失败不留任务 |
| `tests/test_shutdown.py` | 5 | 停止、退回队列、保留上游编号、恢复查询 |
| `tests/test_stop_script.py` | 4 | 拒绝无关 PID、清理死 PID、停止本仓库进程 |
| `tests/test_workflows.py` | 6 | 清单校验；跨仓库比较跳过 |
| `tests/test_video.py` | 6 | v1 拒绝视频资产，v2 签名下载仍可用 |
| 其余既有测试 | 13 | 图片、任务、配置与安全 |

仍有一条既有警告：`StarletteDeprecationWarning`，`TestClient` 使用 `httpx`。生产进程使用 uvicorn，不受这条警告影响。

## 明确未执行

| 项目 | 状态 |
|---|---|
| 真实 1024 / 2048 图片生成 | NOT RUN |
| 真实 T2V / I2V / FLF | NOT RUN |
| 104 上的部署、重启和端到端验收 | NOT RUN |

## 104 部署建议

1. 在 104 上单独部署这个仓库的新提交，绑定非 8089 端口。不要替换现有 8089、8189、8190 进程。
2. 先在 104 上跑 `.venv/bin/python -m pytest`，确认默认测试不需要 Studio。
3. 用该目录自己的 `scripts/start.sh` 和 `scripts/stop.sh` 管理进程。
4. 服务起来后只做健康检查和鉴权拒绝检查。真实生成另列验收，不把本次 Mock 结果算进去。
5. 确认调用方对视频使用 `/v2/files/{task_id}` 签名链接。
