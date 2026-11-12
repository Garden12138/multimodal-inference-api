# 本地开发

开发服务只监听 `127.0.0.1:8090`。这和以后在 104 上使用 `0.0.0.0:8089` 不是同一次操作。本版本的启动代码拒绝 `INFERENCE_PORT=8089`。

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

| 项目 | 本地开发 | 以后的 104 正式切换 |
|---|---|---|
| 地址 | `127.0.0.1:8090` | 计划为 `0.0.0.0:8089`，本次不执行 |
| 数据 | 仓库内 `data/` | 部署目录自己的 `data/`，不使用 Studio SQLite |
| CIDR | 默认仅 loopback | 必须显式写成 104 所在内网 |
| 降级开关 | 默认 `0` | 若要兼容现有 `768P` 客户端，设为 `1`，响应仍声明 `608x352` |
