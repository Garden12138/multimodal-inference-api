# 104 部署说明

本文描述 104 上的 API 进程，不是 GPU 上的 ComfyUI，也不是 Mac 上的开发进程。图片 ComfyUI 继续使用该机器上的 `127.0.0.1:8190`，视频 ComfyUI 继续使用 `127.0.0.1:8189`。本仓库的脚本不停止、不替换这两个进程。

V1 正式端口是 **8090**。8089 留给现有旧服务，不迁移。`load_settings()`、`scripts/install.sh` 和 `scripts/start.sh` 遇到 `INFERENCE_PORT=8089` 会直接退出。

| 角色 | 地址 |
|---|---|
| 本 API | `0.0.0.0:8090`，再用 `INFERENCE_ALLOWED_CIDRS` 限制来源 |
| 旧 API | 8089，保持不变 |
| 图片 ComfyUI | `127.0.0.1:8190` |
| 视频 ComfyUI | `127.0.0.1:8189` |

`scripts/install.sh` 在检出目录创建 `.venv`，systemd 模板也调用这个解释器。2026-11-13 的收尾没有读取 104 上的进程，因此实际 Python 和虚拟环境是未确认项，运行中的 Git 修订是 **DEPLOYMENT_REVISION_UNVERIFIED**。操作人员需要在服务器上记录 `ps` 里的解释器路径和 `git rev-parse HEAD`。本机文档测试使用的是 Python 3.10.9 的 `.venv`，不能当成 104 的事实。

五种真实生成已在 2026-11-13 通过，见 [104 远程真实验收](../reports/104-remote-acceptance-2026-11-13.md)。重启验收还没有做，方案见 [104 重启验收方案](../reports/104-restart-acceptance-plan.md)。下面的安装步骤是操作手册。本次收尾没有重新执行它们，也没有 SSH。

## 首次安装

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
8. 五种真实生成已经通过。V1 仍然不停止、不替换 8089。停止旧服务不属于本仓库脚本的行为。

## 密钥、CIDR、启动和日志

`scripts/install.sh` 只在 `.env` 不存在时生成密钥，并且不把密钥打印出来。已有 `.env` 保持不变。密钥文件保持 `chmod 600`。更换密钥时编辑本目录的 `.env`，然后只重启本 API。不要把新密钥写进 Git 或日志。

内网访问使用：

```dotenv
INFERENCE_HOST=0.0.0.0
INFERENCE_PORT=8090
INFERENCE_ALLOWED_CIDRS=127.0.0.1/32,::1/128,192.168.10.0/24
```

空的 CIDR 会拒绝所有来源。不要用旧变量 `H3_ALLOWED_CIDRS`。

启动、状态、日志和停止都在这个检出目录里：

```bash
bash scripts/start.sh
bash scripts/status.sh
tail -n 80 data/logs/inference.log
bash scripts/stop.sh
```

重启就是先 `stop.sh` 再 `start.sh`。停止脚本只向本目录 pid 文件中的 inference API 发送 `SIGTERM`。超时后它不会发送 `SIGKILL`，也不会清理 8089、8189 或 8190。

## 备份和恢复

停止本 API 后复制本目录数据，再启动：

```bash
bash scripts/stop.sh
STAMP="$(date +%Y%m%d%H%M%S)"
mkdir -p "data/backups/$STAMP"
cp -a data/inference.db "data/backups/$STAMP/inference.db"
cp -a data/outputs data/inputs data/recovery "data/backups/$STAMP/"
bash scripts/start.sh
```

如果必须在运行中复制数据库，并且系统里有 `sqlite3`，可以用 `sqlite3 data/inference.db ".backup 'data/backups/$STAMP/inference.db'"`。输出目录仍应在没有任务写入时复制。

恢复只把同一次备份拷回这个 `data/`。先停止本 API，覆盖 `inference.db`、`outputs`、`inputs` 和 `recovery`，再启动。不要把这份数据恢复到旧的 8089 服务或其他目录。

有正在执行的 `queued`、`submitting` 或 `running` 任务时，不要为了备份或升级停止进程，除非这次停止已经单独批准。

## 升级和回退

在同一个检出目录：

1. 确认没有未完成任务。
2. 按上一节备份。
3. `bash scripts/stop.sh`。
4. 检出要发布或要退回的提交。V1.0.0 标签还没有创建，不要提前执行 `git checkout v1.0.0`。
5. `bash scripts/install.sh`。它不覆盖 `.env`，不安装模型，不重启 ComfyUI。
6. 确认 `INFERENCE_PORT` 仍是 8090，然后 `bash scripts/start.sh`。
7. 检查 `/healthz`、带密钥的 `/v1/health` 和 `/v2/health`。

回退使用同一步骤，把第 4 步换成上一个已批准的提交，并在需要时恢复对应备份。不要用回退命令停止其他服务。

异常任务和 `needs_review` 见 [排障](../operations/troubleshooting.md)。

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

不要对 `h3-minimax-v2.service`、ComfyUI 或 Studio 执行 `stop`、`restart` 或 `disable`。V1 不包含这次切换。

## 只停止本服务

```bash
bash scripts/stop.sh
```

或 `systemctl --user stop multimodal-inference-api.service`。这只停止本服务。已有的 8089 服务如果没有被别的操作停掉，会继续提供旧协议。版本回退用上面的“升级和回退”，不是只停进程。
