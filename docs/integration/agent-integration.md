# Agent 接入

本服务是 V1.0.0，可以直接被没有 Studio 账号的 Agent 调用。示例里的地址是本机 `8090`。104 上的 V1 地址是 `http://192.168.10.104:8090`。密钥从环境变量读取，不要写进仓库。

契约和错误码以 [API 契约](../spec/03-api-contract.md) 为准。图片状态使用 `error.code`。视频失败对外仍是 `local_generation_failed`，`needs_review` 对外是 `submission_uncertain` 并带 `attention_required`。内部的 `submitting` 在视频查询里显示为 `running`。

```bash
export INFERENCE_API_KEY='替换为服务端密钥'
export BASE='http://127.0.0.1:8090'
```

视频示例要求服务端 `VIDEO_ALLOW_RESOLUTION_FALLBACK=1`。查询结果中的 `resolution` 应为 `608x352`，不要把它当成 768P 播放画质。

下面的 Python 使用 `requests`。创建任务成功只表示已入队。生成完成以查询状态为准。`needs_review` 时不要自动用同一输入再创建一次。

## API Key

```bash
curl -sS -o /dev/null -w '%{http_code}\n' "$BASE/v1/health"
curl -sS "$BASE/v1/health" -H "Authorization: Bearer $INFERENCE_API_KEY"
```

```python
import os
import requests

base = os.environ["BASE"]
key = os.environ["INFERENCE_API_KEY"]
headers = {"Authorization": "Bearer " + key}

missing = requests.get(base + "/v1/health", timeout=10)
print(missing.status_code)  # 401

health = requests.get(base + "/v1/health", headers=headers, timeout=10)
health.raise_for_status()
print(health.json()["status"])
```

## 图片 1024

```bash
curl -sS -X POST "$BASE/v1/images/generations" \
  -H "Authorization: Bearer $INFERENCE_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary '{"model":"MiniMax-H3-Image","prompt":"A cinematic mountain lake at sunrise","size":"1024x1024"}'
```

```python
import os
import requests

base = os.environ["BASE"]
headers = {"Authorization": "Bearer " + os.environ["INFERENCE_API_KEY"]}
response = requests.post(
    base + "/v1/images/generations",
    headers=headers,
    json={
        "model": "MiniMax-H3-Image",
        "prompt": "A cinematic mountain lake at sunrise",
        "size": "1024x1024",
    },
    timeout=30,
)
response.raise_for_status()
print(response.status_code, response.json())
```

## 图片 2048

把 `size` 换成 `2048x2048`。其余字段不变。

```bash
curl -sS -X POST "$BASE/v1/images/generations" \
  -H "Authorization: Bearer $INFERENCE_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary '{"model":"MiniMax-H3-Image","prompt":"A cinematic mountain lake at sunrise","size":"2048x2048"}'
```

## 视频文生

```bash
curl -sS -D - -X POST "$BASE/v2/video_generation" \
  -H "Authorization: Bearer $INFERENCE_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary '{"model":"MiniMax-H3","content":[{"type":"text","text":"A cinematic scene"}],"resolution":"768P","duration":5,"ratio":"16:9"}'
```

```python
import os
import requests

base = os.environ["BASE"]
headers = {"Authorization": "Bearer " + os.environ["INFERENCE_API_KEY"]}
response = requests.post(
    base + "/v2/video_generation",
    headers=headers,
    json={
        "model": "MiniMax-H3",
        "content": [{"type": "text", "text": "A cinematic scene"}],
        "resolution": "768P",
        "duration": 5,
        "ratio": "16:9",
    },
    timeout=30,
)
response.raise_for_status()
print(response.headers.get("X-H3-Native-Resolution"), response.json())
```

## 视频图生

```python
import base64
import os
from pathlib import Path

import requests

def image_item(path, role):
    path = Path(path)
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}[path.suffix.lower()]
    uri = "data:" + mime + ";base64," + base64.b64encode(path.read_bytes()).decode()
    return {"type": "image_url", "image_url": {"url": uri}, "role": role}

base = os.environ["BASE"]
headers = {"Authorization": "Bearer " + os.environ["INFERENCE_API_KEY"]}
response = requests.post(
    base + "/v2/video_generation",
    headers=headers,
    json={
        "model": "MiniMax-H3",
        "content": [
            {"type": "text", "text": "The subject turns toward the camera"},
            image_item("first.png", "first_frame"),
        ],
        "resolution": "768P",
        "duration": 5,
        "ratio": "adaptive",
    },
    timeout=60,
)
response.raise_for_status()
print(response.json())
```

对应 curl 需要先自己生成 data URL。不要把 `http://` 图片地址放进 `image_url.url`。

```bash
python3 - <<'PY' > /tmp/i2v.json
import base64, json
from pathlib import Path
raw = Path("first.png").read_bytes()
uri = "data:image/png;base64," + base64.b64encode(raw).decode()
json.dump({
    "model": "MiniMax-H3",
    "content": [
        {"type": "text", "text": "The subject turns toward the camera"},
        {"type": "image_url", "image_url": {"url": uri}, "role": "first_frame"},
    ],
    "resolution": "768P",
    "duration": 5,
    "ratio": "adaptive",
}, open("/dev/stdout", "w"))
PY
curl -sS -X POST "$BASE/v2/video_generation" \
  -H "Authorization: Bearer $INFERENCE_API_KEY" \
  -H 'Content-Type: application/json' \
  --data-binary @/tmp/i2v.json
```

## 视频首末帧

在图生请求的 `content` 里再加一项 `role` 为 `last_frame` 的图片。两项都要有。`ratio` 可以是 `adaptive` 或 `16:9`。

```python
content = [
    {"type": "text", "text": "The scene moves from the first frame to the last frame"},
    image_item("first.png", "first_frame"),
    image_item("last.png", "last_frame"),
]
```

`image_item` 与上一节相同。curl 同样先写成 JSON 文件再 `--data-binary`。

## 轮询

图片和视频都要轮询到终态。视频的 `submitting` 会显示成 `running`。

```python
import os
import time

import requests

base = os.environ["BASE"]
headers = {"Authorization": "Bearer " + os.environ["INFERENCE_API_KEY"]}

def wait_image(task_id, timeout=1800):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = requests.get(base + "/v1/images/generations/" + task_id, headers=headers, timeout=30).json()
        if body["status"] in {"succeeded", "failed", "needs_review"}:
            return body
        time.sleep(3)
    raise TimeoutError(task_id)

def wait_video(task_id, timeout=3600):
    deadline = time.time() + timeout
    while time.time() < deadline:
        body = requests.get(base + "/v2/query/video_generation/" + task_id, headers=headers, timeout=30).json()["task"]
        if body["status"] in {"succeeded", "failed", "needs_review"}:
            return body
        time.sleep(5)
    raise TimeoutError(task_id)
```

```bash
TASK_ID='替换为 task_id'
curl -sS "$BASE/v1/images/generations/$TASK_ID" -H "Authorization: Bearer $INFERENCE_API_KEY"
curl -sS "$BASE/v2/query/video_generation/$TASK_ID" -H "Authorization: Bearer $INFERENCE_API_KEY"
```

## 下载

图片 URL 是相对路径，视频 URL 是绝对路径。

```python
import os
from urllib.parse import urljoin

import requests

base = os.environ["BASE"]
headers = {"Authorization": "Bearer " + os.environ["INFERENCE_API_KEY"]}

def download_image(image_body, target):
    asset = image_body["assets"][0]
    response = requests.get(urljoin(base + "/", asset["url"].lstrip("/")), timeout=120)
    response.raise_for_status()
    open(target, "wb").write(response.content)
    return asset["sha256"]

def download_video(video_task, target):
    response = requests.get(video_task["content"]["url"], timeout=180)
    response.raise_for_status()
    open(target, "wb").write(response.content)
```

视频签名链接不需要 Bearer。图片签名链接同样可以不带 Bearer；带 Bearer 也可以下载。

```bash
curl -sS -L "$BASE/v1/files/<asset_id>?expires=<expires>&signature=<signature>" -o image.png
curl -sS -L "http://127.0.0.1:8090/v2/files/<task_id>?expires=<expires>&signature=<signature>" -o video.mp4
```

使用查询接口返回的 URL，不要自己拼 ComfyUI 的 `/view` 地址。
