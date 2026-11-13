# 本地开发

本文件描述 Mac 或开发机上的 API 进程。它不是 104 上的 GPU 服务，也不会启动 ComfyUI。

开发服务监听 `127.0.0.1:8090`。104 上的 V1 对内网开放时才使用 `0.0.0.0:8090`。两条路径都拒绝 `INFERENCE_PORT=8089`。8089 留给现有旧服务。

本机收尾测试使用检出目录里的 `.venv`，Python 3.10.9。`scripts/install.sh` 也创建这个虚拟环境。不要把它改成 Conda，也不要假定 104 一定已经使用同一个 `.venv`。104 的解释器需要在服务器上确认。

## 安装

```bash
cd /path/to/multimodal-inference-api
bash scripts/install.sh
```

脚本会：

- 创建 `.venv` 并安装 `requirements.txt`
- 仅在 `.env` 不存在时，从 `.env.example` 复制并写入一把新的 API Key
- 把 `.env` 设为 `600`，把 `data/` 设为 `700`
- 编译检查 Python 文件

它不会覆盖已有 `.env`，不会安装 PyTorch 或模型，不会重启 ComfyUI，也不会停止旧的 Native API。

`INSTALL_SYSTEMD=1` 只在 Linux 上复制 user unit，且不会 `enable` 或 `start`。macOS 开发不需要这个变量。

## 启动

```bash
bash scripts/start.sh
bash scripts/status.sh
bash scripts/stop.sh
```

日志在 `data/logs/inference.log`。`stop.sh` 只向 `data/inference.pid` 里的进程发送 `SIGTERM`。进程没有退出时，脚本不会改用 `SIGKILL`，也不会清理其他端口。

默认 ComfyUI 地址：

```text
IMAGE_COMFYUI_BASE_URL=http://127.0.0.1:8190
VIDEO_COMFYUI_BASE_URL=http://127.0.0.1:8189
```

健康检查会读取 `/system_stats`。这不提交生成任务。如果本机没有 ComfyUI，`/v1/health` 和 `/v2/health` 会显示不可达或 degraded，进程本身仍可启动。

## 测试

```bash
.venv/bin/python -m pytest
```

通过只说明 Mock 传输层和协议符合预期。不要把这份结果写成真实推理成功。

## 配置差异

| 项目 | 本地开发 | 104 上的 V1 |
|---|---|---|
| API | `127.0.0.1:8090` | `0.0.0.0:8090`，由 CIDR 限制来源 |
| 旧 API | 不使用 8089 | 8089 保持不变，不迁移 |
| 图片 ComfyUI | 本机 `127.0.0.1:8190`，可以不存在 | GPU 机器上的 `127.0.0.1:8190` |
| 视频 ComfyUI | 本机 `127.0.0.1:8189`，可以不存在 | GPU 机器上的 `127.0.0.1:8189` |
| 数据 | 本检出目录的 `data/` | 104 上该检出目录自己的 `data/` |
| CIDR | 默认仅 loopback | 必须写成批准的内网范围 |
| 降级开关 | 默认 `0` | 兼容现有 `768P` 客户端时设为 `1`，响应仍是 `608x352` |

## 本目录内的日常操作

以下命令都先 `cd` 到本仓库。它们不停止其他目录或其他端口上的进程。

状态和日志：

```bash
bash scripts/status.sh
tail -n 80 data/logs/inference.log
```

重启只针对本 API：

```bash
bash scripts/stop.sh
bash scripts/start.sh
```

`stop.sh` 在 10 秒内等不到退出时不会发送 `SIGKILL`。不要接着去杀 8089、8189 或 8190。

备份前先停止本 API，避免复制到写了一半的 SQLite：

```bash
bash scripts/stop.sh
STAMP="$(date +%Y%m%d%H%M%S)"
mkdir -p "data/backups/$STAMP"
cp -a data/inference.db "data/backups/$STAMP/inference.db"
cp -a data/outputs data/inputs data/recovery "data/backups/$STAMP/"
bash scripts/start.sh
```

恢复使用同一次备份，并且只覆盖本目录的这些路径。先停止，再复制回去，然后启动。不要把开发机的 `data/` 拷到 104 覆盖真实任务。

升级和回退都在同一个检出目录里进行：先备份并停止，再检出目标提交，执行 `bash scripts/install.sh`。安装脚本不会覆盖已有 `.env`。确认端口仍是 8090 后执行 `bash scripts/start.sh`。没有标签之前不要执行 `git checkout v1.0.0`。

异常任务和 `needs_review` 的处理见 [排障](../operations/troubleshooting.md)。
