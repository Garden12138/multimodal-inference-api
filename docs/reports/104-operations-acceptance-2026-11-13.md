# 104 运维验收

日期：2026-11-13。结论：**READY_FOR_V1_PRODUCTION**。

阶段 A、B、C 由操作人员在 104 上执行并回报。阶段 D 由本机通过 HTTP 独立完成。本文把两类证据分开记录。本机没有 SSH，没有重启服务，没有修改 ComfyUI、模型或工作流，没有提交新的生成请求，也没有读取 API Key 到本文。

下载文件在 `.local/104-operations-acceptance/`。该目录已被 `.gitignore` 忽略。

## 人工服务器证据

以下内容来自操作人员对阶段 A、B、C 的回报。本机 HTTP 没有读取进程、Git 修订、备份目录或端口监听，因此这些项不记为本机独立验证。

| 项 | 操作人员回报 |
|---|---|
| API | `http://192.168.10.104:8090` |
| 部署 Commit | `6e021ac9b35169198fd2bd03261f7c1fa26c0b0f` |
| Conda 环境 | `multimodal-inference-api` |
| Python | 3.11.18 |
| 重启前 PID | 3923209 |
| 重启后 PID | 1788121 |
| 重启后身份 | PID 文件与进程一致，工作目录和 Python 路径正确 |
| 备份目录 | `/home/bj-ai/inference-api-backups/20261113_152231` |
| SQLite Backup API | 完整性检查 ok |
| 备份大小 | 约 17 MB |
| 重启前 Active Tasks | 0 |
| 重启后 `/healthz` | 200 |
| 重启后 `/v1/health` | `status=ok`，两个 Provider 正常 |
| 重启后 `/v2/health` | `status=ok`，`backend_connected=true`，`studio_dependency=false` |
| 其他端口 | 8088、8089、8189、8190 保持监听 |

仓库里的 systemd 模板仍调用检出目录的 `.venv/bin/python`。操作人员回报的运行解释器是 Conda 环境 `multimodal-inference-api`。模板没有按这次回报改成 Conda。

## 本机 HTTP 独立验证

检查时间：2026-11-13T15:51:05+08:00。地址：`http://192.168.10.104:8090`。密钥只从执行该脚本的本机 shell 环境变量读取。

全部 15 次调用都是 GET。生成接口调用次数为 0。五个任务的第一次签名下载都返回 200，没有因为过期而重新查询，也没有重新生成素材。

健康检查：

| 请求 | HTTP | 结果 |
|---|---|---|
| `GET /healthz` | 200 | `status=ok` |
| `GET /v1/health`，无密钥 | 401 | `UNAUTHORIZED` |
| `GET /v2/health`，无密钥 | 401 | `authorized_error` |
| `GET /v1/health` | 200 | `status=ok`；图片 `comfyui_h3_image` 与视频 `comfyui_h3_video` 均为 `ok`，五个工作流标记均为 true |
| `GET /v2/health` | 200 | `status=ok`，`backend_connected=true`，`studio_dependency=false`，`native_resolution=608x352` |

五个历史任务均为 `succeeded`。下载后的 SHA-256 与 [104 远程真实验收](104-remote-acceptance-2026-11-13.md) 完全一致。

| 用例 | task_id | 下载 | 字节 | SHA-256 | 媒体 |
|---|---|---|---|---|---|
| RT-01 | `8ee57c5ba2734d568d8164a356b28b7e` | `GET /v1/files/ca1f5721772544c3b210499339fca20d`，200，`image/png` | 1,331,417 | `bc7a331b3a82b7ef31fda0c71873eccf6a6f53003cbbd05f99e392c8412d4e2d` | Pillow：PNG，RGB，1024×1024 |
| RT-02 | `1fec809daca3470eb51b78b92f92090a` | `GET /v1/files/f2bb8af392604dd480d8db43f467f4ef`，200，`image/png` | 6,232,643 | `dfae1ec88303ba8c392ed96743f0055bd6ab734838bf8a87ba767e36bea3dfbb` | Pillow：PNG，RGB，2048×2048 |
| RT-03 | `b67b99f5e4cf48098fc54840530302e2` | `GET /v2/files/b67b99f5e4cf48098fc54840530302e2`，200，`video/mp4` | 389,809 | `f96479df9ebaacabfeca6e53c723b2c18029d831feab994d9822dc99f88e9e2b` | ffprobe：h264，608×352，视频流 5.166667 秒，容器 5.166688 秒 |
| RT-04 | `7085e033c01e4b9e912584a01aeebc1b` | `GET /v2/files/7085e033c01e4b9e912584a01aeebc1b`，200，`video/mp4` | 305,571 | `f8f151c4d3eef4ba09bdad70f523e47ac277ed5d9c988bb71ba939b3d155d4fb` | ffprobe：h264，608×352，视频流 5.166667 秒，容器 5.166688 秒 |
| RT-05 | `aa70f2657bfa41c693da438141308661` | `GET /v2/files/aa70f2657bfa41c693da438141308661`，200，`video/mp4` | 505,432 | `cfc2bff8f5b94e6e973a2061118aadd8b87d3399cfcf77d7d6e7f0a7a09efa9b` | ffprobe：h264，608×352，视频流 5.166667 秒，容器 5.166688 秒 |

脚本使用仓库 `.venv` 的 Pillow 11.3.0。归档前又用本机 `ffprobe` 8.0.1 和 Pillow 对这五个文件重新计算，哈希、尺寸和时长与上表相同。签名查询串没有写入本文。

## 对照

操作人员回报的重启后健康结果，与本机 15:51 的 `/healthz`、`/v1/health`、`/v2/health` 一致。五个文件的哈希、字节数和像素与最初真实验收一致，说明重启后仍能取回同一批素材。

本机没有核实 PID、Conda 路径、Git 修订、备份目录或 8088、8089、8189、8190 的监听。这些仍以操作人员回报为准。

## 结论

阶段 D 的五项恢复检查通过：五个任务为 `succeeded`，五份文件 SHA-256 一致，图片尺寸正确，视频为 608×352 且约 5.167 秒，下载过程没有提交新的 GPU 任务。结合操作人员完成的阶段 A、B、C，API 运维验收结论为 **READY_FOR_V1_PRODUCTION**。

8089 仍未切换。Music3 仍未实现。`v1.0.0` 标签和合并 `main` 不在本次执行范围内。
