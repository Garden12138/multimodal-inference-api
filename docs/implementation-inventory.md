# 实现盘点

盘点时间：2026-11-12。只读来源：

- `.local/references/h3-minimax-native-v2.zip`（已解压到 `.local/extracted/`，未修改压缩包）
- `/Users/cengjiada/Documents/github/multimodal-creative-studio` 的图片、视频 Provider 和工作流

没有读取失败的必要参考。Studio 仓库没有被修改。

## 可以直接迁移的代码

这些内容按已验证行为迁入本仓库，工作流文件按字节复制。

| 来源 | 迁入位置 | 处理 |
|---|---|---|
| `workflows/image/t2i_1mp_api.json` | `workflows/image/t2i_1mp_api.json` | 字节相同 |
| `workflows/image/t2i_4mp_api.json` | `workflows/image/t2i_4mp_api.json` | 字节相同 |
| `workflows/t2v_api.json` | `workflows/video/t2v_api.json` | 只改路径，字节相同 |
| `workflows/i2v_api.json` | `workflows/video/i2v_api.json` | 只改路径，字节相同 |
| `workflows/flf_api.json` | `workflows/video/flf_api.json` | 只改路径，字节相同 |
| `studio/workflows_image.py` 的校验规则 | `inference/workflows/image.py` | 保留基线，不改模型参数 |
| `studio/workflows_video.py` 的标记替换 | `inference/workflows/video.py` | 额外锁定已验证节点，避免误改 |
| `studio/providers/image/comfyui_h3_image.py` 的 history/view 解析 | `inference/providers/comfyui/image.py` | 直接请求 8190 |
| `studio/providers/video/comfyui_h3_video.py` 的上传、history、view | `inference/providers/comfyui/video.py` | 直接请求 8189 |
| `studio/http_client.py` 的 `trust_env = False` | `inference/providers/comfyui/client.py` | 保留 |
| `minimax_v2_api.py` 的请求校验、签名和错误包 | `inference/api/video_minimax.py` | 去掉对 Studio 的调用 |

## 需要重写的代码

| 旧实现 | 原因 | 新实现 |
|---|---|---|
| `minimax_v2_api.py` 的 `studio()` | `POST /api/tasks` 和 `GET /api/tasks/{id}` 属于旧架构 | Worker 直接提交 ComfyUI `/prompt` |
| `install.sh`、`DEPLOY_PATH.txt` | 包含旧目录、8089 和旧服务切换 | `scripts/install.sh`，拒绝 8089 |
| Studio SQLite `tasks` 表 | 不能依赖 Studio 数据库 | 本服务 `data/inference.db` |
| Studio 把无 prompt id 的 `submitting` 记为失败 | 会把不确定提交伪装成失败 | 记为 `needs_review`，不自动重试 |
| 图片只存在于 Studio 页面 API | V1 需要独立图片 Native API | `POST /v1/images/generations` |

## 需要保留的协议

视频继续使用：

- `POST /v2/video_generation`
- `GET /v2/query/video_generation/{task_id}`
- `GET /v2/files/{task_id}?expires=&signature=`
- `GET /v2/health`

创建响应体仍只有 `{"task_id": "<32 hex>"}`。查询响应保留 `task.status`、`task.content.url`、`task.resolution`、`task.duration`、`task.error`。签名材料仍是 `task_id.expires` 的 HMAC-SHA256，密钥是服务端 API Key。

图片是新的异步协议，见 API 契约。没有任务列表、取消、回调、`mm_file://` 或远程图片 URL。

## 已验证的模型参数

图片，两份工作流除下表外，源文件还差一个导出时写死的 `KSampler.seed`。运行时会替换 seed，不改变 steps、CFG、采样器或分辨率档位。

| 项目 | 值 |
|---|---|
| DiT | `minimax_h3_image_pruned_w4a8.safetensors` |
| CLIP | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| 文本 CLIP | `qwen3.5_9b_w4a8_gptq.safetensors` |
| VAE | `minimax_h3_image_vae_fp16.safetensors` |
| Attention | `pytorch attention` |
| 提示词扩展开关 | `false` |
| Steps / CFG | `6` / `1.0` |
| Sampler / Scheduler / denoise | `euler` / `simple` / `1.0` |
| 宽高比 / multiple | `1:1 (Square)` / `32` |
| 1MP / 4MP | `megapixels` `1.0` / `4.0` |
| 已验证输出 | `1024x1024` PNG、`2048x2048` PNG |
| 提示词标记 | `__H3_IMAGE_STUDIO_PROMPT__`，只出现一次 |

视频三份工作流共用：

| 项目 | 值 |
|---|---|
| UNET | `minimax_h3_fl2va_pruned_fp8_scaled.safetensors` |
| CLIP | `qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors` |
| VAE | `minimax_h3_video_vae_fp16.safetensors` |
| Audio VAE | `minimax_h3_audio_vae_fp32.safetensors` |
| LoRA | `minimax_h3_fl2v_turbo_4step_v1.0_768p_comfyui_bf16.safetensors`，strength `1` |
| Lightning 开关 | `true`，因此走 4 step，20 step 节点仍保留 |
| Sampler / Scheduler | `res_multistep` / `simple` |
| ResolutionSelector | `16:9 (Widescreen)`，`0.2` MP，multiple `32` |
| 时长节点 | `5` 秒，24 fps |
| 标记 | `__H3_STUDIO_PROMPT__`、`STUDIO_FIRST.png`、`STUDIO_LAST.png` |

ComfyUI 调用保持：

- 图片：`POST /prompt`，`GET /history/{prompt_id}`，`GET /view`
- 视频参考图：`POST /upload/image`，字段名 `image`，`overwrite=true`
- 视频生成：同上，再 `POST /prompt`
- 结果从 history 的 `outputs` 读取，不把 ComfyUI 磁盘路径返回给调用方

## 工作流 SHA-256

迁移前后哈希一致。1MP 与 4MP 源文件的差异只有：

- `ResolutionSelector.megapixels`：`1.0` 与 `4.0`
- `SaveImage.filename_prefix`：`minimax_h3_image_t2i` 与 `minimax_h3_image_t2i_4mp`
- 导出图里的 `KSampler.seed`

提交时只替换提示词、`filename_prefix` 和 seed。前缀从 Studio 的 `studio_{task_id}` 改为 `inference_{task_id}`，视频从 `video/studio_{task_id}` 改为 `video/inference_{task_id}`。这是输出文件名，不是模型参数。

| 文件 | SHA-256 |
|---|---|
| `image/t2i_1mp_api.json` | `9cba2d0222570e91e1d26c6f18dc641161e84334e6da5a04654ae3bc50e80544` |
| `image/t2i_4mp_api.json` | `101220f9a03ba2b5d83e1c795a299ba8cad79cfd4858fb82d1e2c54e231fe507` |
| `video/t2v_api.json` | `310b09f72ff148ed21cee72cf04289b78a152a3602afbe19941450ba100f67ef` |
| `video/i2v_api.json` | `8adabe278aca1225019ac643f755650540a0e7549920c1303764a342c0f40762` |
| `video/flf_api.json` | `5af09fbb706431d100f5cb008aedf742d97e03ae1a0b0d1dd3a0a00b4eeb086d` |

## 现有视频实际分辨率

Studio 验收记录和原 Native API 都写明实际输出是 **608×352**，约 0.2MP，时长约 5 秒。请求协议仍写 `resolution: "768P"`，这是兼容值。

本服务默认拒绝这种请求。只有 `VIDEO_ALLOW_RESOLUTION_FALLBACK=1` 时才接受，响应头 `X-H3-Native-Resolution: 608x352`，查询字段 `resolution` 也是 `608x352`。`resolution_source` 为 `verified_workflow_baseline`，表示该数字来自已验证工作流，不是本机对 MP4 像素的重新测量。

## 已知限制和风险

- 不确定是否已经提交到 ComfyUI 时，任务进入 `needs_review`。这时 GPU 上可能已经有一次推理，不能自动再提交。
- 进程在收到 `prompt_id` 之后、写入数据库之前崩溃时，靠 `data/recovery/{task_id}.txt` 恢复。恢复文件也不存在时保持 `needs_review`。
- V1 只有一把 API Key，知道 `task_id` 或 `asset_id` 的持钥调用方可以读取对应结果。没有按 Agent 隔离。
- 签名链接在过期前等价于下载能力，只应在允许的 CIDR 内传递。
- 图片和视频默认各一个 Worker。调高 Worker 数可能让同一张 GPU 并行，本服务不会因此改模型参数，但也不建议在未经验证时提高。
- Mock 测试不证明 104 上的真实出图或出视频。
- Music3 没有实现。
