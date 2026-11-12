# 需求

V1 建立一个不依赖 Studio 的推理 API，供 Studio 和其他 Agent 调用本机 MiniMax H3 图片与视频能力。

## 范围内

- `MiniMax-H3-Image`：`1024x1024` 与 `2048x2048`
- `MiniMax-H3` 视频：文生视频、首帧图生视频、首末帧视频
- 独立 SQLite 任务和素材记录
- 图片 Worker 与视频 Worker 分离，默认各 1 个
- API Key、CIDR、HMAC 下载链接
- 结果文件保存在本服务 `data/` 目录

## 范围外

- Music3 或其他音频模型的实际推理
- 修改 ComfyUI、模型权重或已验证工作流参数
- 连接、停止或替换 104 上的 8089、8189、8190
- 任务列表、取消、回调、远程图片 URL、`mm_file://`
- 按用户隔离的多租户权限

## 状态

`queued`、`submitting`、`running`、`succeeded`、`failed`、`needs_review`。

`needs_review` 表示无法确认 ComfyUI 是否已接受任务。它不是成功，也不是失败，服务不会自动再次提交。

## 分辨率

图片结果必须能解码为 PNG，且像素等于请求尺寸。

视频请求可以写 `768P`，实际基线是 `608x352`。未打开降级开关时返回 422。
