# 104 远程真实验收

日期：2026-11-13。结论：**PASS**。

本次从 Mac 通过 HTTP 调用 `http://192.168.10.104:8090`。生成使用远端 ComfyUI Provider，没有使用 Mock Provider。API Key 只从运行进程的环境变量读取，本报告、日志和结果 JSON 都不包含密钥。

## 基线

| 项 | 值 |
|---|---|
| 分支 | `feature/native-api-v1` |
| Commit | `6e021ac9b35169198fd2bd03261f7c1fa26c0b0f` |
| 开始 | 2026-11-13T10:49:28+08:00 |
| 结束 | 2026-11-13T11:10:14+08:00 |
| Pillow | 12.2.0 |
| ffprobe | ffprobe version 8.0.1 Copyright (c) 2007-2025 the FFmpeg developers |
| .gitignore | `.gitignore:9:.local/	.local/104-acceptance` |

## 执行前检查

| 检查 | 结果 |
|---|---|
| /healthz | 200 |
| /v1/health 无密钥 | 401 |
| /v2/health 无密钥 | 401 |
| /v1/health | 200 |
| /v2/health | 200 |
| Image Provider | True |
| Video Provider | True |
| 后端可继续生成 | True |

认证健康响应：

```json
{
  "v1": {
    "service": "multimodal-inference-api",
    "status": "ok",
    "providers": {
      "image": {
        "provider": "comfyui_h3_image",
        "status": "ok",
        "reachable": true,
        "workflows": {
          "t2i_1mp": true,
          "t2i_4mp": true
        }
      },
      "video": {
        "provider": "comfyui_h3_video",
        "status": "ok",
        "reachable": true,
        "workflows": {
          "t2v": true,
          "i2v": true,
          "flf": true
        }
      }
    },
    "reserved_providers": {
      "music": {
        "provider": "music_reserved",
        "status": "not_implemented"
      }
    }
  },
  "v2": {
    "service": "h3-minimax-v2",
    "implementation": "multimodal-inference-api",
    "status": "ok",
    "backend_connected": true,
    "native_resolution": "608x352",
    "degraded_resolution_compat": true,
    "studio_dependency": false
  }
}
```

## RT-01：图片 1024×1024

| 项 | 值 |
|---|---|
| task_id | `8ee57c5ba2734d568d8164a356b28b7e` |
| 创建 HTTP 状态码 | 202 |
| 查询 HTTP 状态码 | 200 |
| 下载 HTTP 状态码 | 200 |
| 创建时间（客户端，UTC+8） | 2026-11-13T10:49:28+08:00 |
| 完成时间（客户端，UTC+8） | 2026-11-13T10:50:07+08:00 |
| 服务端 created_at | 图片接口不返回 |
| 服务端 updated_at | 图片接口不返回 |
| 实际耗时 | 39.172 秒（39s） |
| 最终任务状态 | succeeded |
| 文件 | `.local/104-acceptance/rt01-1024.png` |
| 文件大小 | 1331417 |
| MIME 类型 | image/png |
| Content-Type | image/png |
| 实际分辨率 | 1024x1024 |
| SHA-256 | `bc7a331b3a82b7ef31fda0c71873eccf6a6f53003cbbd05f99e392c8412d4e2d` |
| 验收 | 通过 |

第一次下载发生在 2026-11-13T10:50:07+08:00。验收脚本在请求前把签名替换成了占位文本，服务端返回 403，消息是“下载链接无效或已过期”。生成任务没有重新提交。2026-11-13T10:54:50+08:00 对同一个 task_id 再次查询并下载，HTTP 200。


首次下载错误（未重新提交生成）：

```json
{
  "http_status": 403,
  "headers": {
    "date": "Fri, 13 Nov 2026 02:50:06 GMT",
    "server": "uvicorn",
    "content-length": "102",
    "content-type": "application/json"
  },
  "body_prefix": "{\"error\":{\"code\":\"FORBIDDEN\",\"message\":\"下载链接无效或已过期。\",\"type\":\"authorized_error\"}}"
}
```

## RT-02：图片 2048×2048

| 项 | 值 |
|---|---|
| task_id | `1fec809daca3470eb51b78b92f92090a` |
| 创建 HTTP 状态码 | 202 |
| 查询 HTTP 状态码 | 200 |
| 下载 HTTP 状态码 | 200 |
| 创建时间（客户端，UTC+8） | 2026-11-13T10:54:50+08:00 |
| 完成时间（客户端，UTC+8） | 2026-11-13T10:56:11+08:00 |
| 服务端 created_at | 图片接口不返回 |
| 服务端 updated_at | 图片接口不返回 |
| 实际耗时 | 81.323 秒（1m 21s） |
| 最终任务状态 | succeeded |
| 文件 | `.local/104-acceptance/rt02-2048.png` |
| 文件大小 | 6232643 |
| MIME 类型 | image/png |
| Content-Type | image/png |
| 实际分辨率 | 2048x2048 |
| SHA-256 | `dfae1ec88303ba8c392ed96743f0055bd6ab734838bf8a87ba767e36bea3dfbb` |
| 验收 | 通过 |

## RT-03：视频文生

| 项 | 值 |
|---|---|
| task_id | `b67b99f5e4cf48098fc54840530302e2` |
| 创建 HTTP 状态码 | 200 |
| 查询 HTTP 状态码 | 200 |
| 下载 HTTP 状态码 | 200 |
| 创建时间（客户端，UTC+8） | 2026-11-13T10:56:11+08:00 |
| 完成时间（客户端，UTC+8） | 2026-11-13T11:00:42+08:00 |
| 服务端 created_at | 2026-11-13T10:56:11+08:00 |
| 服务端 updated_at | 2026-11-13T11:00:37+08:00 |
| 实际耗时 | 270.615 秒（4m 31s） |
| 最终任务状态 | succeeded |
| 文件 | `.local/104-acceptance/rt03-t2v.mp4` |
| 文件大小 | 389809 |
| MIME 类型 | video/mp4 |
| Content-Type | video/mp4 |
| 实际分辨率 | 608x352 |
| SHA-256 | `f96479df9ebaacabfeca6e53c723b2c18029d831feab994d9822dc99f88e9e2b` |
| 验收 | 通过 |
| 请求分辨率标签 | 768P |
| 接口 resolution | 608x352 |
| 创建响应实际分辨率头 | 608x352 |
| ffprobe 时长 | 5.166667 |

## RT-04：视频图生

| 项 | 值 |
|---|---|
| task_id | `7085e033c01e4b9e912584a01aeebc1b` |
| 创建 HTTP 状态码 | 200 |
| 查询 HTTP 状态码 | 200 |
| 下载 HTTP 状态码 | 200 |
| 创建时间（客户端，UTC+8） | 2026-11-13T11:00:42+08:00 |
| 完成时间（客户端，UTC+8） | 2026-11-13T11:05:17+08:00 |
| 服务端 created_at | 2026-11-13T11:00:42+08:00 |
| 服务端 updated_at | 2026-11-13T11:05:17+08:00 |
| 实际耗时 | 275.715 秒（4m 36s） |
| 最终任务状态 | succeeded |
| 文件 | `.local/104-acceptance/rt04-i2v.mp4` |
| 文件大小 | 305571 |
| MIME 类型 | video/mp4 |
| Content-Type | video/mp4 |
| 实际分辨率 | 608x352 |
| SHA-256 | `f8f151c4d3eef4ba09bdad70f523e47ac277ed5d9c988bb71ba939b3d155d4fb` |
| 验收 | 通过 |
| 请求分辨率标签 | 768P |
| 接口 resolution | 608x352 |
| 创建响应实际分辨率头 | 608x352 |
| ffprobe 时长 | 5.166667 |

## RT-05：视频首末帧

| 项 | 值 |
|---|---|
| task_id | `aa70f2657bfa41c693da438141308661` |
| 创建 HTTP 状态码 | 200 |
| 查询 HTTP 状态码 | 200 |
| 下载 HTTP 状态码 | 200 |
| 创建时间（客户端，UTC+8） | 2026-11-13T11:05:18+08:00 |
| 完成时间（客户端，UTC+8） | 2026-11-13T11:10:13+08:00 |
| 服务端 created_at | 2026-11-13T11:05:18+08:00 |
| 服务端 updated_at | 2026-11-13T11:10:08+08:00 |
| 实际耗时 | 295.929 秒（4m 56s） |
| 最终任务状态 | succeeded |
| 文件 | `.local/104-acceptance/rt05-flf.mp4` |
| 文件大小 | 505432 |
| MIME 类型 | video/mp4 |
| Content-Type | video/mp4 |
| 实际分辨率 | 608x352 |
| SHA-256 | `cfc2bff8f5b94e6e973a2061118aadd8b87d3399cfcf77d7d6e7f0a7a09efa9b` |
| 验收 | 通过 |
| 请求分辨率标签 | 768P |
| 接口 resolution | 608x352 |
| 创建响应实际分辨率头 | 608x352 |
| ffprobe 时长 | 5.166667 |

## 产物

生成文件在 `.local/104-acceptance/`。该目录被 `.gitignore` 的 `.local/` 忽略，不进入提交。

## 明确没有做的事

- 没有修改 104 服务，没有 SSH，没有重启服务。
- 没有停止或修改 ComfyUI，没有改模型工作流。
- 没有操作 8089，没有修改 Studio。
- 失败任务没有自动再次提交。
- 没有 Commit，也没有 Push。

## 结论依据

总体结论是 **PASS**。成功标准是任务终态 `succeeded`，文件完成下载，图片经 Pillow 解码且尺寸与请求一致，视频经 ffprobe 确认 MP4、实际像素和时长。HTTP 200 本身不算生成成功。视频请求标签 768P 只记录为请求值；实测分辨率以 ffprobe 为准，接口返回的 `608x352` 不会写成 768P。
