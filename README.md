# Multimodal Inference API

版本 1.0.0。独立的多模态推理 API，提供 MiniMax H3 图片和 MiniMax H3 视频的异步任务接口，直接调用本机 ComfyUI，不依赖 Multimodal Creative Studio。

音乐生成只保留 Provider 扩展位，没有实现，也没有对应路由。

V1 端口是 8090。本机开发绑定 `127.0.0.1`，104 对内网服务时绑定 `0.0.0.0`。8089 留给现有旧服务，本版本拒绝绑定它，也不会迁移它。图片 ComfyUI 是 8190，视频 ComfyUI 是 8189。这两个进程不由本仓库的脚本停止。

## 本地运行

```bash
bash scripts/install.sh
bash scripts/start.sh
bash scripts/status.sh
bash scripts/stop.sh
```

开发监听地址是 `127.0.0.1:8090`。本版本拒绝绑定 `8089`，也不会停止或修改 `8189`、`8190` 上的 ComfyUI。

配置见 `.env.example`。密钥优先级：

1. 进程环境中的非空 `INFERENCE_API_KEY`
2. 仅当前者为空时，使用 `H3_MINIMAX_API_KEY`

两个变量同时有值时，只使用 `INFERENCE_API_KEY`。

视频请求里的 `resolution=768P` 需要显式设置 `VIDEO_ALLOW_RESOLUTION_FALLBACK=1`。实际输出仍是已验证的 `608x352`，接口不会把它报成 768P。

## 测试

```bash
.venv/bin/python -m pytest
```

测试使用 Mock ComfyUI，不代表真实 GPU 推理成功。

## 文档

- [实现盘点](docs/implementation-inventory.md)
- [API 契约](docs/spec/03-api-contract.md)
- [本地开发](docs/deployment/local-development.md)
- [104 部署说明](docs/deployment/server-104.md)
- [安全](docs/operations/security.md)
- [排障](docs/operations/troubleshooting.md)
- [Agent 接入](docs/integration/agent-integration.md)
- [104 远程真实验收](docs/reports/104-remote-acceptance-2026-11-13.md)
- [104 运维验收](docs/reports/104-operations-acceptance-2026-11-13.md)
- [V1 发布验收](docs/reports/v1-release-acceptance.md)

Mock 测试通过不等于 104 真实推理通过。发布状态见 V1 发布验收。API 运维验收结论是 `READY_FOR_V1_PRODUCTION`。8089 仍未切换，`v1.0.0` 标签尚未创建。
