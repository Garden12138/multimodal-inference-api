# Multimodal Inference API

独立的多模态推理 API。V1 提供 MiniMax H3 图片和 MiniMax H3 视频的异步任务接口，直接调用本机 ComfyUI，不依赖 Multimodal Creative Studio。

音乐生成只保留 Provider 扩展位，没有实现，也没有对应路由。

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
- [Agent 接入](docs/integration/agent-integration.md)
