# 104 部署说明

本次实现没有 SSH 到 104，没有修改 8089、8189 或 8190，也没有把本服务切换到 8089。下面是以后批准切换时的步骤，不是本次已经执行的操作。

## 8090 试运行和 8089 正式端口

| 阶段 | 绑定 | 作用 |
|---|---|---|
| 现在 | `127.0.0.1:8090` 或批准后的 `0.0.0.0:8090` | 与现有 Native API 并存，供联调 |
| 以后的正式切换 | `0.0.0.0:8089` | 只有在确认旧 `h3-minimax-v2` 已停止且调用方已改完之后才进行 |

当前 `load_settings()`、`scripts/install.sh` 和 `scripts/start.sh` 发现端口 `8089` 会直接退出。正式切换前要单独评审并去掉这道保护，不能靠本次脚本完成。

## 建议的并存步骤

1. 把本仓库放到 104 的独立目录，不要放进 Studio 或 ComfyUI 目录。
2. 运行 `bash scripts/install.sh`。不要设置 `INFERENCE_PORT=8089`。
3. 编辑新目录的 `.env`，至少设置：

```dotenv
INFERENCE_API_KEY=<新密钥，不要复用到日志>
INFERENCE_ALLOWED_CIDRS=127.0.0.1/32,::1/128,192.168.10.0/24
INFERENCE_PUBLIC_BASE_URL=http://192.168.10.104:8090
INFERENCE_HOST=0.0.0.0
INFERENCE_PORT=8090
VIDEO_ALLOW_RESOLUTION_FALLBACK=1
IMAGE_COMFYUI_BASE_URL=http://127.0.0.1:8190
VIDEO_COMFYUI_BASE_URL=http://127.0.0.1:8189
IMAGE_WORKERS=1
VIDEO_WORKERS=1
```

`H3_MINIMAX_API_KEY` 可以不设置。如果两个密钥变量都有值，运行中的只有 `INFERENCE_API_KEY`。

4. `chmod 600 .env` 后执行 `bash scripts/start.sh`。
5. 用 `bash scripts/status.sh` 和 `journalctl` 或 `data/logs/inference.log` 查看日志。
6. 先调用 `/healthz`、`/v1/health`、`/v2/health`。确认 `studio_dependency` 为 `false`。
7. 在维护窗口对 1024、2048、T2V、I2V、FLF 各做一次真实生成，并核对图片像素和视频实际分辨率仍是 `608x352`。2026-11-13 已在 `http://192.168.10.104:8090` 完成，结论为 PASS，记录见 [104 远程真实验收](../reports/104-remote-acceptance-2026-11-13.md)。视频实测仍是 `608x352`。
8. 只有真实结果通过后，才讨论停止旧的 8089 进程。停止旧服务不属于本仓库脚本的默认行为。本次验收没有操作 8089。

## systemd

模板是 `deploy/inference-api.user.service`。在 Linux 上可以：

```bash
INSTALL_SYSTEMD=1 bash scripts/install.sh
systemctl --user daemon-reload
```

安装脚本到这里为止，不会启动单元。确认端口是 8090 之后，才由操作者执行：

```bash
systemctl --user enable --now multimodal-inference-api.service
systemctl --user status multimodal-inference-api.service
journalctl --user -u multimodal-inference-api.service -n 80 --no-pager
```

不要对 `h3-minimax-v2.service`、ComfyUI 或 Studio 执行 `stop`、`restart` 或 `disable`，除非那是一次单独批准的切换。

## 回退

```bash
bash scripts/stop.sh
```

或 `systemctl --user stop multimodal-inference-api.service`。这只停止本服务。已有的 8089 服务如果没有被别的操作停掉，会继续提供旧协议。
