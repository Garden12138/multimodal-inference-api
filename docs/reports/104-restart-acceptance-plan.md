# 104 重启验收方案

状态：阶段 A–D 已于 2026-11-13 执行。执行记录见 [104 运维验收](104-operations-acceptance-2026-11-13.md)。下文保留执行前写好的检查步骤。

本次收尾没有 SSH 到 104，没有停止或启动正在运行的 API，没有操作 8089、8189 或 8190，也没有为了文档修改重新生成图片或视频。

写这份方案时，104 运行进程的 Git 修订尚未由本机读取。操作人员随后回报为 `6e021ac9b35169198fd2bd03261f7c1fa26c0b0f`，见 [104 运维验收](104-operations-acceptance-2026-11-13.md)。下面的命令先确认目录和进程，再决定备份和重启。部署目录用操作人员确认后的 `API_ROOT`，不要猜路径，也不要在 Studio 或 ComfyUI 目录里执行。

真实验收已经成功的任务，重启后应仍能查询和下载：

| 用例 | task_id | 期望 |
|---|---|---|
| 图片 1024 | `8ee57c5ba2734d568d8164a356b28b7e` | PNG，1,331,417 字节，SHA-256 `bc7a331b3a82b7ef31fda0c71873eccf6a6f53003cbbd05f99e392c8412d4e2d` |
| 图片 2048 | `1fec809daca3470eb51b78b92f92090a` | PNG，6,232,643 字节，SHA-256 `dfae1ec88303ba8c392ed96743f0055bd6ab734838bf8a87ba767e36bea3dfbb` |
| T2V | `b67b99f5e4cf48098fc54840530302e2` | MP4，608×352，SHA-256 `f96479df9ebaacabfeca6e53c723b2c18029d831feab994d9822dc99f88e9e2b` |
| I2V | `7085e033c01e4b9e912584a01aeebc1b` | MP4，608×352，SHA-256 `f8f151c4d3eef4ba09bdad70f523e47ac277ed5d9c988bb71ba939b3d155d4fb` |
| FLF | `aa70f2657bfa41c693da438141308661` | MP4，608×352，SHA-256 `cfc2bff8f5b94e6e973a2061118aadd8b87d3399cfcf77d7d6e7f0a7a09efa9b` |

密钥只从操作人员当前 shell 的 `INFERENCE_API_KEY` 读取。不要把密钥写进命令、日志或本文件。

## 1. 确认端口、PID 和目录

在 104 上，于已确认的 API 检出目录中执行：

```bash
cd "$API_ROOT"
pwd
git rev-parse HEAD
git status --short
ss -ltnp | awk '/:8090|:8089|:8189|:8190/'
bash scripts/status.sh
ps -p "$(tr -d '[:space:]' < data/inference.pid)" -o pid=,args=
lsof -a -p "$(tr -d '[:space:]' < data/inference.pid)" -d cwd -Fn
```

通过标准：8090 上的进程命令行包含 `-m inference.runtime`，工作目录是这个 `API_ROOT`。8089、8189、8190 的进程只记录，不发送信号。如果 pid 文件和 8090 监听进程不是同一个，停止并报告，不要继续重启。

同时记录 `python3 --version` 和 `ps` 里的解释器路径。这是确认 104 运行环境的步骤。本文不能预先填写。

## 2. 确认没有正在执行的任务

```bash
sqlite3 data/inference.db \
  "SELECT id, media_type, status FROM inference_tasks WHERE status IN ('queued','submitting','running');"
```

如果有行，不要停止进程。等任务进入 `succeeded`、`failed` 或 `needs_review`，或者另一次批准明确允许中断后，才能继续。

## 3. 备份

只复制本目录的数据。先创建备份目录，再复制数据库、输出、输入和恢复文件：

```bash
STAMP="$(date +%Y%m%d%H%M%S)"
mkdir -p "data/backups/$STAMP"
cp -a data/inference.db "data/backups/$STAMP/inference.db"
cp -a data/outputs "data/backups/$STAMP/outputs"
cp -a data/inputs "data/backups/$STAMP/inputs"
cp -a data/recovery "data/backups/$STAMP/recovery"
```

备份应在停止后立刻进行，避免复制到半写的 SQLite。如果本机有 `sqlite3`，也可以在停止前执行 `sqlite3 data/inference.db ".backup 'data/backups/$STAMP/inference.db'"`。文件目录仍要在停止后复制，或者确认当时没有任务在写文件。

## 4. 只停止本 API，然后启动

```bash
bash scripts/stop.sh
bash scripts/start.sh
bash scripts/status.sh
```

`scripts/stop.sh` 只向本目录 `data/inference.pid` 中、命令行包含 `-m inference.runtime` 且属于本检出目录的进程发送 `SIGTERM`。它不发送 `SIGKILL`。如果脚本拒绝，不要改 pid，也不要杀掉 8089、8189 或 8190。

## 5. 健康检查

从允许的内网地址执行。无密钥的两个健康检查应返回 401。带密钥的检查应返回 200，图片和视频 Provider 为 `ok`。

```bash
export BASE_URL=http://192.168.10.104:8090
curl --noproxy '*' -sS "$BASE_URL/healthz"
curl --noproxy '*' -sS -o /dev/null -w 'v1 %{http_code}\n' "$BASE_URL/v1/health"
curl --noproxy '*' -sS -o /dev/null -w 'v2 %{http_code}\n' "$BASE_URL/v2/health"
curl --noproxy '*' -sS "$BASE_URL/v1/health" -H "Authorization: Bearer $INFERENCE_API_KEY"
curl --noproxy '*' -sS "$BASE_URL/v2/health" -H "Authorization: Bearer $INFERENCE_API_KEY"
```

`/v2/health` 的 `native_resolution` 应为 `608x352`。`backend_connected: true` 只说明视频 ComfyUI 的 `/system_stats` 可达，不代替上面五个历史任务的下载核对。

## 6. 查询并重新下载

图片：

```bash
curl --noproxy '*' -sS \
  "$BASE_URL/v1/images/generations/8ee57c5ba2734d568d8164a356b28b7e" \
  -H "Authorization: Bearer $INFERENCE_API_KEY"
```

2048 任务把路径中的 id 换成 `1fec809daca3470eb51b78b92f92090a`。状态必须仍是 `succeeded`。用响应里的签名 URL 下载，不要自己拼 ComfyUI `/view`。

视频：

```bash
curl --noproxy '*' -sS \
  "$BASE_URL/v2/query/video_generation/b67b99f5e4cf48098fc54840530302e2" \
  -H "Authorization: Bearer $INFERENCE_API_KEY"
```

I2V 和 FLF 分别换成 `7085e033c01e4b9e912584a01aeebc1b`、`aa70f2657bfa41c693da438141308661`。用返回的绝对签名 URL 下载。

下载后计算 SHA-256，并与上表比较。图片再用 Pillow 核对像素，视频再用 ffprobe 核对 MP4、608×352 和约 5 秒。不一致则验收失败，不要重新提交生成，不要从备份覆盖正在使用的数据，除非另一次批准要求回退。

## 7. 通过标准

1. 停止和启动的都是本 API。
2. 健康检查和鉴权拒绝与重启前一致。
3. 五个历史任务仍是 `succeeded`。
4. 五个文件的 SHA-256 与 2026-11-13 真实验收一致。
5. 8089、8189、8190 的进程没有被这些命令停止。

执行结果已写入 [104 运维验收](104-operations-acceptance-2026-11-13.md)。API 运维验收结论为 `READY_FOR_V1_PRODUCTION`。
