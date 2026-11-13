# V1 发布验收

日期：2026-11-13。发布结论：**READY_FOR_V1_RELEASE**。

这不是 **READY_FOR_V1_PRODUCTION**。五种真实生成已经通过，但 104 上正在运行的进程修订没有读取，重启后的历史任务和文件也还没有按 [104 重启验收方案](104-restart-acceptance-plan.md) 验证。

## 版本和提交

| 项 | 值 |
|---|---|
| API 版本 | 1.0.0，来自 `inference.__version__` |
| 收尾分支 | `feature/api-v1-release` |
| 104 真实验收基线 | `6e021ac9b35169198fd2bd03261f7c1fa26c0b0f` |
| 验收文档提交 | `aa0d568a96ef5bfe7f9ab6baea2a37fb19e8f2d4` |
| 104 运行进程修订 | **DEPLOYMENT_REVISION_UNVERIFIED** |
| 相对基线的运行时代码 | `aa0d568` 只有文档变化。本次收尾也不修改 `inference/`、`app.py`、`workflows/` 或部署脚本 |

`main` 在收尾开始时比 `aa0d568` 少上述 3 个功能与文档提交，没有自己的额外提交。没有既有 Git 标签。

## 自动化测试

命令在本机 `.venv` 中执行。解释器是 Python 3.10.9。依赖为 FastAPI 0.162.5、Uvicorn 0.54.0、Pillow 11.3.0、requests 2.34.2、pytest 8.4.2。

```bash
.venv/bin/python -m pytest
.venv/bin/python -m compileall -q inference app.py
bash -n scripts/install.sh
bash -n scripts/start.sh
bash -n scripts/status.sh
bash -n scripts/stop.sh
```

结果：**36 passed，1 skipped**。skipped 是未设置 `INFERENCE_REFERENCE_WORKFLOW_DIR` 的可选工作流字节比较。没有失败。仍有一条既有的 `StarletteDeprecationWarning`，生产进程使用 uvicorn，不受它影响。

收集数：

| 文件 | 数量 |
|---|---|
| `tests/test_config_and_security.py` | 5 |
| `tests/test_images.py` | 3 |
| `tests/test_reference_race.py` | 3 |
| `tests/test_shutdown.py` | 5 |
| `tests/test_stop_script.py` | 4 |
| `tests/test_tasks.py` | 5 |
| `tests/test_video.py` | 6 |
| `tests/test_workflows.py` | 6 |

这是 Mock 测试。它覆盖不确定提交进入 `needs_review` 且不自动重试、关闭时退回队列或保留上游编号、文件校验、签名下载，以及停止脚本拒绝无关 PID。测试使用假传输层，不向 8189 或 8190 提交任务，不需要真实 GPU，也不需要 Studio 仓库。源码中的测试没有个人绝对路径。

沙箱里的一次运行曾使 `test_stop_signals_only_this_checkout` 失败，因为 `ps` 和 `lsof` 被禁止，停止脚本无法确认进程身份。取消沙箱后的完整运行通过。这不是产品失败，也不跳过该测试。

五份工作流 JSON 可以解析，SHA-256 与 `inference/workflows/manifest.py` 一致。`.env.example` 的密钥为空。`.gitignore` 忽略 `.env`、`.venv/`、`data/`、`.local/` 和 `*.log`。

11 月 12 日的 [自动化测试报告](automated-test-report.md) 写的是当时的 23 passed。同日稍后的 [预发就绪报告](104-staging-readiness.md) 写的是 36 passed、1 skipped。两份数字都保留为当时的记录。上表才是本次对当前代码的重新执行。

## 104 真实推理

记录在 [104 远程真实验收](104-remote-acceptance-2026-11-13.md)。结论 PASS。调用地址是 `http://192.168.10.104:8090`，没有使用 Mock Provider。

| 用例 | task_id | 结果 |
|---|---|---|
| 图片 1024×1024 | `8ee57c5ba2734d568d8164a356b28b7e` | PNG，39.172 秒，1,331,417 字节 |
| 图片 2048×2048 | `1fec809daca3470eb51b78b92f92090a` | PNG，81.323 秒，6,232,643 字节 |
| 文生视频 | `b67b99f5e4cf48098fc54840530302e2` | MP4，608×352，5.167 秒 |
| 图生视频 | `7085e033c01e4b9e912584a01aeebc1b` | MP4，608×352，5.167 秒，使用上一张 1024 图 |
| 首末帧 | `aa70f2657bfa41c693da438141308661` | MP4，608×352，5.167 秒 |

请求里的视频分辨率标签是 768P。接口和 ffprobe 的实际像素都是 608×352。RT-01 第一次下载因客户端把签名换成占位文本而返回 403，任务已是 `succeeded`，没有重新提交；随后对同一任务下载成功。

这次 HTTP 验收不能证明服务器进程加载的是哪一个 Git 提交。

## 鉴权和安全

自动化测试覆盖无效密钥 401、空 CIDR 拒绝、拒绝绑定 8089、`trust_env` 不为真、路径穿越、签名下载和视频不能从 `/v1/files` 下载。104 预检里，无密钥访问 `/v1/health` 和 `/v2/health` 返回 401，`/healthz` 返回 200。

V1 仍是单密钥。没有任务列表，也没有按 Agent 分权。Music3 没有实现。

## 部署和运维

文档已按 V1 端口改写：API 8090，图片 ComfyUI 8190，视频 ComfyUI 8189。对内网开放时使用 `INFERENCE_HOST=0.0.0.0` 和显式 CIDR。本机示例仍是 `127.0.0.1`。

`scripts/install.sh` 在本检出目录创建 `.venv`。systemd 模板因此调用 `.venv/bin/python`。104 是否实际使用这个虚拟环境，需要操作人员在服务器上确认。

停止脚本只处理本目录的 inference API。备份、恢复、升级和回退步骤写在部署文档中，都要求先进入该目录。

## CI

`.github/workflows/ci.yml` 在 Pull Request 和 `main` 推送时，于 Python 3.10、3.11、3.12 上安装两类依赖并执行 pytest、compileall、四个 shell 脚本的语法检查，以及五份工作流 JSON 与清单的比对。它不读取 API Key，不连接 104 或 GPU，不提交生成。

任一矩阵失败都会让该检查失败。仓库管理员若要阻止失败的 PR 被合并，还需要在 GitHub 上把这个检查设为必需。本次没有代为修改仓库规则。

本机已经执行过与 CI 相同的测试、编译、脚本语法和工作流检查。GitHub Actions 本身还没有跑过这次提交。

## 已知限制

- 视频实际输出是 608×352，时长只接受 5 秒。768P 只是请求标签，并且要求 `VIDEO_ALLOW_RESOLUTION_FALLBACK=1`。
- 图片尺寸只接受 1024×1024 和 2048×2048。
- `needs_review` 是终态。服务不会自动再提交，也没有接口把它改回 `running`。
- 单密钥，没有计费和多租户。
- 音乐 Provider 保持 `not_implemented`。

## 未完成

- 104 进程修订仍是 DEPLOYMENT_REVISION_UNVERIFIED。
- [重启验收](104-restart-acceptance-plan.md) 未执行。
- 不切换 8089。
- 不创建 `v1.0.0` 标签，不合并 `main`。等待人工确认。

因此当前可以准备 PR，但不能称为生产切换完成。

## V1.0.0 Release Notes

独立的多模态推理 API 1.0.0 提供 MiniMax H3 图片和视频任务。图片支持 1024 与 2048。视频支持文生、图生和首末帧；请求可以写 768P，实际像素是已验证的 608×352。

服务直接调用本机 ComfyUI，不依赖 Studio 的任务接口。V1 监听 8090，并拒绝绑定 8089。8189 和 8190 上的 ComfyUI 不由本仓库的脚本停止。

104 上的五种真实生成已在 2026-11-13 通过。重启后的持久性验收尚未执行。Music3 没有实现。

## 创建标签

合并到 `main` 并确认发布提交之后，由人工执行。不要在合并前把标签打在尚未进入 `main` 的功能分支上。

```bash
git checkout main
git pull
git tag -a v1.0.0 -m "Multimodal Inference API 1.0.0"
git push origin v1.0.0
```

本次收尾不执行以上命令。

## PR 说明

准备从 `feature/api-v1-release` 合并到 `main`。PR 应说明：

- 运行时代码相对已验收的 `6e021ac` 没有变化。
- 新增 CI、发布验收、重启方案和运维收尾。
- 104 五种生成 PASS，进程修订未核实，重启验收未做。
- 不切换 8089，不创建标签。

打开 PR 后看 GitHub Actions。检查失败时不要合并。本次不自动创建或合并 PR。
