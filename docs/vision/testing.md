# SpacemiT AI Gateway Vision 真机测试记录

> 测试环境：SpacemiT K3 开发板（RISC-V），Python 3.14，服务监听 `localhost:18790`

---

## 环境准备

### 克隆仓库并安装服务

```bash
git clone git@gitlab.dc.com:bianbu/spacemit_claw/spacemit-ai-gateway.git
cd spacemit-ai-gateway
pip install -e .
```

### 启动服务

```bash
uvicorn spacemit_ai_gateway.app.main:app --reload --host 0.0.0.0 --port 18790
```

服务启动后，Swagger 文档可访问：http://localhost:18790/docs

### 安装 model_zoo wheel 包（native 模式）

```bash
# 按实际环境替换为可用 wheel 或私有源安装命令
pip install spacemit-vision --index-url https://git.spacemit.com/api/v4/projects/33/packages/pypi/simple
```

<details>
<summary>安装输出示例</summary>

```text
Collecting spacemit-vision
  Using cached https://git.spacemit.com/api/v4/projects/33/packages/pypi/files/369a4ab205f0020d8d3b843824f21c93bbc063730d841ef4339207b6e01cd73a/spacemit_vision-0.1.0-cp314-cp314-linux_riscv64.whl (2.6 MB)
Requirement already satisfied: numpy>=1.26.0 in /home/user/vision_env/lib/python3.14/site-packages (from spacemit-vision) (2.4.4)
Requirement already satisfied: opencv-python>=4.8.0 in /home/user/vision_env/lib/python3.14/site-packages (from spacemit-vision) (4.13.0.92)
Installing collected packages: spacemit-vision
Successfully installed spacemit-vision-0.1.0

```

</details>

### 准备测试资源

```bash
# 测试图片
wget -O /tmp/vision_test.jpg \
    https://archive.spacemit.com/spacemit-ai/model_zoo/assets/image/006_test.jpg
wget -O /tmp/vision_face_test.png \
    https://archive.spacemit.com/spacemit-ai/model_zoo/assets/image/003_face0.png  

# 测试视频
wget -O /tmp/vision_test.mp4 \
    https://archive.spacemit.com/spacemit-ai/model_zoo/assets/video/003_palace.mp4
```

验证资源：

```bash
file /tmp/vision_test.jpg
file /tmp/vision_test.mp4
```

```text
/tmp/vision_test.jpg: JPEG image data, JFIF standard 1.01, resolution (DPI), density 72x72, segment length 16, baseline, precision 8, 500x375, components 3
/tmp/vision_test.mp4: ISO Media, Apple QuickTime movie, Apple QuickTime (.MOV/QT)
```

---

## 服务健康检查

```bash
curl -s localhost:18790/healthz | jq .
```

```json
{"status":"ok"}
```

---

## 模型管理测试

### 查询当前模型列表

```bash
curl -s localhost:18790/v1/vision/models | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "xxxx",
  "data": []
}

```

### 加载模型

```bash
curl -s -X POST localhost:18790/v1/vision/models/load \
    -H 'Content-Type: application/json' \
    -d '{
      "model_id":"yolov8",
      "config_path":"configs/vision/yolov8.yaml",
      "lazy_load":false
    }' | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "680b508c-12f1-4f85-b146-15e32fa9b659",
  "data": {
    "loaded": true,
    "model_id": "yolov8",
    "engine_state": {
      "backend": "native",
      "status": "ready",
      "config_path": "/home/user/code/open/spacemit-ai-gateway/configs/vision/yolov8.yaml"
    }
  }
}

```

### 切换模型（可选）

```bash
curl -s -X POST localhost:18790/v1/vision/models/switch \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"yolov8"}' | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "ff0e3066-4b6a-433a-b3b4-abd5e7e00e83",
  "data": {
    "switched": true,
    "default_model_id": "yolov8",
    "default_model_group": null,
    "effective_scope": "new_requests_only"
  }
}
```

### 卸载模型

```bash
curl -s -X POST localhost:18790/v1/vision/models/unload \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"yolov8"}' | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "4cdbab3c-53e3-4029-a373-b2043fd26cd4",
  "data": {
    "unloaded": true,
    "model_id": "yolov8"
  }
}

```

---

## 图像推理测试（Inference）

### multipart 上传推理

```bash
curl -s -X POST localhost:18790/v1/vision/inference \
    -F file=@/tmp/vision_test.jpg \
    -F 'tasks=["detect"]' \
    -F model_id=yolov8 \
    -F render=true \
    -F render_mode=overlay | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "91680b91-6ab4-4891-bae7-0c097839fe48",
  "data": {
    "model_id": "yolov8",
    "results": {
      "detect": [
        {
          "x1": 0.5928546190261841,
          "y1": 113.6988296508789,
          "x2": 84.99215698242188,
          "y2": 352.1162109375,
          "score": 0.916929304599762,
          "label": 0,
          "track_id": -1
        },
        {
          "x1": 230.99473571777344,
          "y1": 122.22115325927734,
          "x2": 316.2408752441406,
          "y2": 371.11322021484375,
          "score": 0.916929304599762,
          "label": 0,
          "track_id": -1
        },
        {
          "x1": 64.5499038696289,
          "y1": 169.18869018554688,
          "x2": 247.29580688476562,
          "y2": 370.5806884765625,
          "score": 0.6867536306381226,
          "label": 33,
          "track_id": -1
        }
      ],
      "classify": null,
      "pose": null,
      "segment": null,
      "emotion": null
    },
    "timing": {
      "preprocess_ms": 2.059005,
      "model_infer_ms": 18.321421,
      "postprocess_ms": 0.401292,
      "detect_ms": null,
      "track_ms": null,
      "embedding_ms": null,
      "sequence_ms": null,
      "draw_ms": null,
      "infer_ms": 20.789219
    },
    "rendered_image_url": "/artifacts/vision/render/infer_1776762507761.jpg"
  }
}

```

### JSON + handle 推理

```bash
curl -s -X POST localhost:18790/v1/vision/inference \
    -H 'Content-Type: application/json' \
    -d '{
      "tasks":["detect"],
      "model_id":"yolov8",
      "handle":"/tmp/vision_test.jpg"
    }' | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "15880a2a-c1eb-4e9e-9f9e-93d721f22d3a",
  "data": {
    "model_id": "yolov8",
    "results": {
      "detect": [
        {
          "x1": 0.5928546190261841,
          "y1": 113.6988296508789,
          "x2": 84.99215698242188,
          "y2": 352.1162109375,
          "score": 0.916929304599762,
          "label": 0,
          "track_id": -1
        },
        {
          "x1": 230.99473571777344,
          "y1": 122.22115325927734,
          "x2": 316.2408752441406,
          "y2": 371.11322021484375,
          "score": 0.916929304599762,
          "label": 0,
          "track_id": -1
        },
        {
          "x1": 64.5499038696289,
          "y1": 169.18869018554688,
          "x2": 247.29580688476562,
          "y2": 370.5806884765625,
          "score": 0.6867536306381226,
          "label": 33,
          "track_id": -1
        }
      ],
      "classify": null,
      "pose": null,
      "segment": null,
      "emotion": null
    },
    "timing": {
      "preprocess_ms": 2.454339,
      "model_infer_ms": 18.227671,
      "postprocess_ms": 0.42096,
      "detect_ms": null,
      "track_ms": null,
      "embedding_ms": null,
      "sequence_ms": null,
      "draw_ms": null,
      "infer_ms": 21.110428
    },
    "rendered_image_url": null
  }
}

```

---

## 特征提取测试（Feature）

### 加载 ArcFace 模型

```bash
curl -s -X POST localhost:18790/v1/vision/models/load \
    -H 'Content-Type: application/json' \
    -d '{
      "model_id":"arcface",
      "config_path":"configs/vision/arcface.yaml",
      "lazy_load":false
    }' | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "cb909868-5d34-4bf0-881b-247b8ac9c3fd",
  "data": {
    "loaded": true,
    "model_id": "arcface",
    "engine_state": {
      "backend": "native",
      "status": "ready",
      "config_path": "/home/user/code/open/spacemit-ai-gateway/configs/vision/arcface.yaml"
    }
  }
}

```

```bash
curl -s -X POST localhost:18790/v1/vision/feature \
    -F file=@/tmp/vision_face_test.png \
    -F type=embedding \
    -F model_id=arcface | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "5df1465b-7e42-4610-a7d2-a4121dd3f09a",
  "data": {
    "model_id": "arcface",
    "embedding": [
      0.07495097070932388,
      0.05731545016169548,
      0.10140425711870193,
      ...
      0.03967992961406708
    ],
    "similarity": null,
    "timing": {
      "preprocess_ms": 0.350957,
      "model_infer_ms": 3.295033,
      "postprocess_ms": 0.031208,
      "detect_ms": null,
      "track_ms": null,
      "embedding_ms": 3.681407,
      "sequence_ms": null,
      "draw_ms": null,
      "infer_ms": null
    }
  }
}

```

---

## 异步任务测试（Jobs）

### 创建任务

```bash
curl -s -X POST localhost:18790/v1/vision/jobs \
    -H 'Content-Type: application/json' \
    -d '{
      "input_uri":"/tmp/vision_test.mp4",
      "tasks":["detect"],
      "model_id":"yolov8",
      "render":true,
      "render_mode":"overlay",
      "frame_sample_rate":1
    }' | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "0e5dbc1b-02cc-4eda-b9bc-dca96dc20b24",
  "data": {
    "job_id": "vision_job_53dc45af65ec",
    "status": "PENDING",
    "accepted_at": "2026-04-21T11:11:53Z"
  }
}

```

### 查询任务状态

```bash
curl -s localhost:18790/v1/vision/jobs/<job_id> | jq .
```

```json

{
  "code": 0,
  "message": "ok",
  "request_id": "c5752c46-88d8-4987-bb7b-47b7ae73d1a3",
  "data": {
    "job_id": "vision_job_53dc45af65ec",
    "status": "DONE",
    "progress": 100,
    "results_uri": "/artifacts/vision/jobs/vision_job_53dc45af65ec/result.json",
    "artifacts": {
      "rendered_uri": "/artifacts/vision/jobs/vision_job_53dc45af65ec/rendered/"
    }
  }
}

```

### 取消任务（可选）

```bash
curl -s -X DELETE localhost:18790/v1/vision/jobs/<job_id> | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "6cbb9d60-d2d9-4214-8a6b-547d3839cce5",
  "data": {
    "cancelled": true,
    "job_id": "vision_job_50bc5de5ad44"
  }
}

```

---

## 流式推理测试（WebSocket）

先安装客户端依赖：

```bash
pip install websockets opencv-python-headless
```

```bash
cat > /tmp/vision_ws.py <<'EOF'
import asyncio, json, cv2, websockets

WS_URL = "ws://localhost:18790/v1/vision/stream"
IMAGE_PATH = "/tmp/vision_test.jpg"

async def main():
    async with websockets.connect(WS_URL, max_size=50 * 1024 * 1024) as ws:
        await ws.send(json.dumps({
            "signal": "start",
            "model_id": "yolov8",
            "fps_limit": 15,
            "priority": 1
        }))
        print(await ws.recv())  # ready

        img = cv2.imread(IMAGE_PATH)
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            raise RuntimeError("encode failed")
        await ws.send(buf.tobytes())
        print(await ws.recv())  # frame result

        await ws.send(json.dumps({"signal": "end"}))
        print(await ws.recv())  # end ack

asyncio.run(main())
EOF

python /tmp/vision_ws.py
```

```json
{"event":"ready","stream_id":"vision_stream_60b30c1ade09","params":{"model_group":"yolov8","fps_limit":15,"priority":"1"}}
{"event":"frame_result","stream_id":"vision_stream_60b30c1ade09","timestamp_ms":1776770106119,"detections":[{"x1":-0.00375211238861084,"y1":113.69255828857422,"x2":84.96481323242188,"y2":351.9652099609375,"score":0.916929304599762,"label":0,"track_id":-1},{"x1":231.41351318359375,"y1":122.68199920654297,"x2":315.6662902832031,"y2":371.73138427734375,"score":0.8942890763282776,"label":0,"track_id":-1},{"x1":66.40115356445312,"y1":167.8114471435547,"x2":247.86341857910156,"y2":370.876220703125,"score":0.6301530599594116,"label":33,"track_id":-1}],"timing":{"preprocess_ms":2.902962,"model_infer_ms":18.299026,"postprocess_ms":0.397126,"detect_ms":null,"track_ms":null,"embedding_ms":null,"sequence_ms":null,"draw_ms":null,"infer_ms":21.606947}}
{"event":"stream_end","stream_id":"vision_stream_60b30c1ade09"}

```

---

## 参数与引擎配置测试

### 推理参数

```bash
curl -s localhost:18790/v1/vision/params | jq .
```

```json
curl -s localhost:18790/v1/vision/params | jq .
{
  "code": 0,
  "message": "ok",
  "request_id": "f09a8b86-0d82-444d-b2a9-7608b0405f7e",
  "data": {
    "thresholds": {
      "detect": 0.25
    },
    "nms": 0.45,
    "roi_masks": [],
    "input_size": 640
  }
}

```

```bash
curl -s -X PATCH localhost:18790/v1/vision/params \
    -H 'Content-Type: application/json' \
    -d '{"thresholds":{"detect":0.35}}' | jq .
```

```bash
curl -s localhost:18790/v1/vision/params | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "73da78e4-a7be-43e5-9085-4b5cb74ff64c",
  "data": {
    "thresholds": {
      "detect": 0.35
    },
    "nms": 0.45,
    "roi_masks": [],
    "input_size": 640
  }
}
```

### 引擎配置

```bash
curl -s localhost:18790/v1/vision/engine | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "6f57f043-510c-409f-a85f-1b3587b43312",
  "data": {
    "ai_core_group": "cluster0",
    "threads": 4,
    "precision": "int8",
    "memory_limit": 1024
  }
}
```

```bash
curl -s -X PATCH localhost:18790/v1/vision/engine \
    -H 'Content-Type: application/json' \
    -d '{"threads":2}' | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "f3c9062b-52d3-432d-ab1c-c5b908d6e002",
  "data": {
    "ai_core_group": "cluster0",
    "threads": 2,
    "precision": "int8",
    "memory_limit": 1024
  }
}

```

### 性能指标

需要调用一次/v1/vision/inference

```bash
curl -s localhost:18790/v1/vision/stats | jq .
```

```json
{
  "code": 0,
  "message": "ok",
  "request_id": "6d653778-be97-438b-a6f7-120d4ca28f09",
  "data": {
    "rtf": 0.0,
    "fps": 0.0,
    "queue": 0,
    "infer_ms": 22.819229,
    "ai_temp": 0.0,
    "memory_usage": 0
  }
}

```

---

## 常见问题排查

### 报错：`tasks[] is required and must not be empty`

检查请求体是否包含 `tasks`，multipart 请求建议使用：

```bash
-F 'tasks=["detect"]'
```

### 模型状态为 `error`

优先排查：

- 配置文件路径是否正确（`config_path`）
- 模型文件与标签文件是否存在
- native 依赖是否安装成功
- `/v1/vision/models` 中的 `error_message` 内容

### 结果像 mock 数据

在 `/v1/vision/models` 中检查当前模型 `backend`：

- `mock`：降级返回，非真实模型推理
- `native`：真实模型推理
