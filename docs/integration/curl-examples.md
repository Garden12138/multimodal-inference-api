# curl 示例

先在当前 shell 设置密钥，不要把密钥写进命令历史之外的仓库文件。

```bash
export INFERENCE_API_KEY='替换为 .env 中的密钥'
export BASE='http://127.0.0.1:8090'
```

104 试运行把 `BASE` 换成 `http://192.168.10.104:8090`。在正式切换完成前，不要把 `BASE` 指到现有的 8089 服务并期望它是本仓库的实现。

## 健康检查

```bash
curl -sS "$BASE/healthz"
curl -sS "$BASE/v1/health" -H "Authorization: Bearer $INFERENCE_API_KEY"
curl -sS "$BASE/v2/health" -H "Authorization: Bearer $INFERENCE_API_KEY"
```

## 图片 1024

```bash
curl -sS -D - -o /tmp/image-task.json -X POST "$BASE/v1/images/generations" \
  -H "Authorization: Bearer $INFERENCE_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary '{"model":"MiniMax-H3-Image","prompt":"A cinematic mountain lake at sunrise","size":"1024x1024"}'
```

## 图片 2048

把上一则请求里的 `size` 换成 `2048x2048`。

## 查询图片并下载

```bash
TASK_ID="$(python3 -c 'import json; print(json.load(open("/tmp/image-task.json"))["task_id"])')"
curl -sS "$BASE/v1/images/generations/$TASK_ID" \
  -H "Authorization: Bearer $INFERENCE_API_KEY" | tee /tmp/image-status.json
URL="$(python3 -c 'import json; print(json.load(open("/tmp/image-status.json"))["assets"][0]["url"])')"
curl -sS -L "$BASE$URL" -o /tmp/image.png
```

`url` 已带签名，下载可以不带 Bearer。它是相对路径，所以要拼上 `BASE`。

## 视频文生

需要 `VIDEO_ALLOW_RESOLUTION_FALLBACK=1`。响应里的实际分辨率仍是 `608x352`。

```bash
curl -sS -D - -o /tmp/video-task.json -X POST "$BASE/v2/video_generation" \
  -H "Authorization: Bearer $INFERENCE_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary '{"model":"MiniMax-H3","content":[{"type":"text","text":"A cinematic scene"}],"resolution":"768P","duration":5,"ratio":"16:9"}'
```

## 视频查询和下载

```bash
TASK_ID="$(python3 -c 'import json; print(json.load(open("/tmp/video-task.json"))["task_id"])')"
curl -sS "$BASE/v2/query/video_generation/$TASK_ID" \
  -H "Authorization: Bearer $INFERENCE_API_KEY" | tee /tmp/video-status.json
python3 - <<'PY'
import json, urllib.request
task = json.load(open("/tmp/video-status.json"))["task"]
print(task["status"], task.get("resolution"))
if task["status"] == "succeeded":
    urllib.request.urlretrieve(task["content"]["url"], "/tmp/video.mp4")
    print("saved /tmp/video.mp4")
PY
```

视频 `content.url` 是绝对地址，并且只在 `succeeded` 时出现。

图生和首末帧的请求体见 [Agent 接入](agent-integration.md)。不要使用远程图片 URL。
