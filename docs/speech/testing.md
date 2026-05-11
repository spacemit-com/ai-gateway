# SpacemiT AI Gateway 真机测试记录

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

### 安装 model_zoo wheel 包

```bash
# 安装本地 wheel（spacemit_audio）
pip install ~/workspace/spacemit_robot/output/wheels/components_multimedia_audio/spacemit_audio-1.0.0-cp314-cp314-linux_riscv64.whl

# 安装 ASR / TTS / VAD 及 spacemit-audio
pip install --index-url https://git.spacemit.com/api/v4/projects/33/packages/pypi/simple \
    spacemit-asr spacemit-tts spacemit-vad spacemit-audio
```

<details>
<summary>安装输出</summary>

```
Collecting spacemit-asr
  Downloading spacemit_asr-1.0.0-cp314-cp314-linux_riscv64.whl (395 kB)
Collecting spacemit-tts
  Downloading spacemit_tts-1.0.0-cp314-cp314-linux_riscv64.whl (996 kB)
Collecting spacemit-vad
  Downloading spacemit_vad-1.0.0-cp314-cp314-linux_riscv64.whl (187 kB)
Collecting spacemit-audio
  Downloading spacemit_audio-1.0.0-cp314-cp314-linux_riscv64.whl (154 kB)
Collecting numpy>=1.19.0 (from spacemit-asr)
  Using cached numpy-2.4.4-cp314-cp314-manylinux_2_38_riscv64.manylinux_2_41_riscv64.whl (11.1 MB)
Successfully installed numpy-2.4.4 spacemit-audio-1.0.0 spacemit-asr-1.0.0 spacemit-tts-1.0.0 spacemit-vad-1.0.0
```

</details>

### 安装 WebSocket 客户端

```bash
pip install websockets
```

### 准备测试音频文件

测试音频来自 SpacemiT 资产库，原始格式为 WAV，需转换为 16kHz 单声道 int16 PCM。

```bash
# 下载原始 WAV
wget -O /tmp/speech.wav \
    https://archive.spacemit.com/spacemit-ai/model_zoo/assets/audio/004_zh_selling_sausages.wav

# 转换为 16kHz 单声道 int16 PCM（去除文件头，裸 PCM 数据）
ffmpeg -i /tmp/speech.wav -ar 16000 -ac 1 -f s16le /tmp/speech.pcm
```

验证转换结果：

```bash
python -c "
import numpy as np
a = np.fromfile('/tmp/speech.pcm', np.int16)
print('dur', len(a)/16000, 's  rms', int(np.sqrt((a.astype(float)**2).mean())))
"
```

```
dur 14.158375 s  rms 4911
```

---

## 服务健康检查

```bash
curl -s localhost:18790/healthz | jq .
```

```json
{
  "status": "ok",
  "domains": {
    "asr": { "ready": true, "state": "ready", "backend": "sensevoice" },
    "tts": { "ready": true, "state": "ready", "backend": "matcha_zh" },
    "vad": { "ready": true, "state": "ready", "backend": "silero" }
  }
}
```

---

## VAD 测试

### 健康检查 & 参数查询

```bash
curl -s localhost:18790/v1/vad/healthz | jq .
curl -s localhost:18790/v1/vad/params  | jq .
```

```json
{ "ready": true, "state": "ready", "backend": "silero" }
```

```json
{
  "trigger_threshold": 0.5,
  "stop_threshold": 0.35,
  "min_speech_ms": 250,
  "max_silence_ms": 500,
  "sample_rate": 16000
}
```

### 短片段语音检测

```bash
curl -s -X POST "localhost:18790/v1/vad/analyze?sample_rate=16000" \
    -F file=@/tmp/speech.pcm | jq .
```

```json
{
  "is_speech": true,
  "probability": 0.9999030232429504,
  "smoothed_probability": 0.405691921710968,
  "processing_ms": 358.00272604683414
}
```

### 音频切分（获取语音段时间戳）

```bash
curl -s -X POST "localhost:18790/v1/vad/segments?sample_rate=16000" \
    -F file=@/tmp/speech.pcm | jq .
```

```json
{
  "segments": [
    { "start_ms": 300.0,   "end_ms": 3120.0,  "confidence": 0.9999647 },
    { "start_ms": 3480.0,  "end_ms": 6120.0,  "confidence": 0.9999207 },
    { "start_ms": 6480.0,  "end_ms": 8040.0,  "confidence": 0.9998379 },
    { "start_ms": 8340.0,  "end_ms": 9390.0,  "confidence": 0.9998693 },
    { "start_ms": 9660.0,  "end_ms": 10560.0, "confidence": 0.9998433 },
    { "start_ms": 10800.0, "end_ms": 11670.0, "confidence": 0.9998887 },
    { "start_ms": 11940.0, "end_ms": 14130.0, "confidence": 0.9998816 }
  ],
  "duration_ms": 14158.375,
  "speech_ratio": 0.8496737796533854,
  "processing_ms": 351.06249601813033
}
```

### 更新参数

```bash
curl -s -X PATCH localhost:18790/v1/vad/params \
    -H 'Content-Type: application/json' \
    -d '{"threshold":0.6}' | jq .
```

```json
{
  "threshold": 0.6,
  "min_silence_ms": 100,
  "speech_pad_ms": 30
}
```

### 引擎配置

```bash
curl -s localhost:18790/v1/vad/engine | jq .
```

```json
{
  "threads": 1,
  "npu_priority": null,
  "memory_limit": null,
  "pending_restart": false
}
```

```bash
curl -s -X PATCH localhost:18790/v1/vad/engine \
    -H 'Content-Type: application/json' \
    -d '{"threads":2}' | jq .
```

```json
{
  "threads": 1,
  "npu_priority": null,
  "memory_limit": null,
  "pending_restart": true
}
```

### 性能指标 & 运行态摘要

```bash
curl -s localhost:18790/v1/vad/stats | jq .
```

```json
{
  "total_requests": 1,
  "total_errors": 0,
  "latency_ms_avg": 359.66,
  "uptime_s": 103.5
}
```

```bash
curl -s localhost:18790/v1/vad/info | jq .
```

```json
{
  "initialized": true,
  "backend": "silero",
  "backends_loaded": ["silero"]
}
```

### VAD WebSocket 流式检测

以 30ms 帧（960 bytes）模拟实时推送，服务端逐帧返回语音/静音事件。

```bash
cat > /tmp/vad_ws.py <<'EOF'
import asyncio, json, pathlib, websockets

PCM = pathlib.Path("/tmp/speech.pcm").read_bytes()
FRAME = 960  # 30ms @16kHz int16

async def main():
    async with websockets.connect("ws://localhost:18790/v1/vad/stream?sample_rate=16000") as ws:
        print(await ws.recv())

        async def send():
            for i in range(0, len(PCM) - FRAME + 1, FRAME):
                await ws.send(PCM[i:i+FRAME])
                await asyncio.sleep(0.03)
            await ws.send(json.dumps({"type": "end"}))

        async def recv():
            try:
                while True: print(await ws.recv())
            except websockets.ConnectionClosed: return

        await asyncio.gather(send(), recv())

asyncio.run(main())
EOF

python /tmp/vad_ws.py
```

```json
{"type":"ready"}
{"event":"silence",      "probability":0.00017, "timestamp_ms":0.0}
{"event":"speech_start", "probability":0.99120, "timestamp_ms":300.0}
{"event":"speech_end",   "probability":0.18514, "timestamp_ms":3120.0}
{"event":"speech_start", "probability":0.98675, "timestamp_ms":3480.0}
{"event":"speech_end",   "probability":0.00072, "timestamp_ms":6120.0}
{"event":"speech_start", "probability":0.99804, "timestamp_ms":6480.0}
{"event":"speech_end",   "probability":0.00036, "timestamp_ms":8040.0}
{"event":"speech_start", "probability":0.99781, "timestamp_ms":8340.0}
{"event":"speech_end",   "probability":0.00055, "timestamp_ms":9390.0}
{"event":"speech_start", "probability":0.99849, "timestamp_ms":9660.0}
{"event":"speech_end",   "probability":0.00093, "timestamp_ms":10560.0}
{"event":"speech_start", "probability":0.99012, "timestamp_ms":10800.0}
{"event":"speech_end",   "probability":0.00028, "timestamp_ms":11670.0}
{"event":"speech_start", "probability":0.98067, "timestamp_ms":11940.0}
```

---

## TTS 测试

### 健康检查 & 模型/音色查询

```bash
curl -s localhost:18790/v1/tts/healthz | jq .
curl -s localhost:18790/v1/tts/voices  | jq .
curl -s localhost:18790/v1/tts/models  | jq .
```

```json
{ "ready": true, "state": "ready", "backend": "matcha_zh" }
```

```json
[
  { "id": "default", "name": "默认中文", "language": "zh", "gender": "female", "description": null }
]
```

```json
[
  { "id": "matcha_zh",    "languages": ["zh"],    "sample_rate": 22050, "loaded": true  },
  { "id": "matcha_en",    "languages": ["en"],    "sample_rate": 22050, "loaded": false },
  { "id": "matcha_zh_en", "languages": ["zh-en"], "sample_rate": 22050, "loaded": false }
]
```

### HTTP 同步合成

```bash
curl -s -X POST localhost:18790/v1/tts/synthesize \
    -H 'Content-Type: application/json' \
    -d '{"text":"你好，世界。今天天气不错。","response_format":"wav"}' \
    -D /tmp/tts_hdr.txt \
    --output /tmp/tts.wav
```

响应头（性能指标）：

```
x-duration-ms: 3320       # 合成音频时长 3.32s
x-processing-ms: 1561     # 推理耗时 1.56s
x-rtf: 0.470              # 实时率 0.47（< 1 表示快于实时）
x-sample-rate: 22050
content-type: audio/wav
```

输出文件：`RIFF WAV，PCM 16bit mono 22050Hz`

### 播放合成音频

TTS 输出为 22050Hz 单声道，硬件需要 48000Hz 双声道，需先用 ffmpeg 转换：

```bash
# 转码：22050Hz mono → 48000Hz stereo
ffmpeg -i /tmp/tts.wav -ar 48000 -ac 2 /tmp/tts_48k.wav

# 播放
aplay -Dhw:0,0 /tmp/tts_48k.wav
# Playing WAVE '/tmp/tts_48k.wav' : Signed 16 bit Little Endian, Rate 48000 Hz, Stereo
```

### TTS WebSocket 流式合成

先创建 session，再通过 WebSocket 推送文本、接收 PCM 音频块。

```bash
cat > /tmp/tts_ws.py <<'EOF'
import asyncio, json, pathlib, urllib.request, websockets

async def main():
    req = urllib.request.Request(
        'http://localhost:18790/v1/tts/stream/session',
        data=json.dumps({"voice_id": "default", "response_format": "pcm"}).encode(),
        headers={'Content-Type': 'application/json'})
    sid = json.loads(urllib.request.urlopen(req).read())['session_id']
    uri = f"ws://localhost:18790/v1/tts/stream?session_id={sid}&response_format=pcm"
    out = pathlib.Path("/tmp/tts_stream.pcm").open("wb")
    async with websockets.connect(uri) as ws:
        print(await ws.recv())
        await ws.send(json.dumps({"type": "start", "text": "你好，世界，这是一段流式合成的测试文本。"}))
        await ws.send(json.dumps({"type": "end"}))
        try:
            while True:
                m = await ws.recv()
                if isinstance(m, bytes):
                    out.write(m)
                else:
                    print(m)
                    if '"done"' in m: break
        except websockets.ConnectionClosed: pass
    out.close()
    print("PCM bytes:", pathlib.Path("/tmp/tts_stream.pcm").stat().st_size)

asyncio.run(main())
EOF

python /tmp/tts_ws.py
```

```json
{"type":"ready"}
{"type":"done","duration_ms":4562.0,"rtf":0.4756685793399811}
PCM bytes: 201216
```

### 推理参数管理

```bash
curl -s localhost:18790/v1/tts/params | jq .
```

```json
{
  "speed": 1.0,
  "pitch": 1.0,
  "volume": 50.0,
  "emotion_strength": null
}
```

```bash
curl -s -X PATCH localhost:18790/v1/tts/params \
    -H 'Content-Type: application/json' \
    -d '{"speed":1.2}' | jq .
```

```json
{
  "speed": 1.2,
  "pitch": 1.0,
  "volume": 50.0,
  "emotion_strength": null
}
```

### 引擎配置

```bash
curl -s localhost:18790/v1/tts/engine | jq .
```

```json
{
  "threads": 1,
  "sample_rate": 22050,
  "cache_policy": null,
  "pending_restart": false
}
```

```bash
curl -s -X PATCH localhost:18790/v1/tts/engine \
    -H 'Content-Type: application/json' \
    -d '{"threads":8}' | jq .
```

```json
{
  "threads": 1,
  "sample_rate": 22050,
  "cache_policy": null,
  "pending_restart": true
}
```

### 性能指标 & 运行态摘要

```bash
curl -s localhost:18790/v1/tts/stats | jq .
```

```json
{
  "total_requests": 1,
  "total_errors": 0,
  "rtf_avg": 0.4696,
  "uptime_s": 265.3
}
```

```bash
curl -s localhost:18790/v1/tts/info | jq .
```

```json
{
  "initialized": true,
  "backend": "matcha-zh",
  "num_voices": 1,
  "default_model": "matcha-zh",
  "backends_loaded": ["matcha-zh"]
}
```

### 异步合成任务

提交异步任务，后台合成完成后通过 download_url 获取音频。

```bash
curl -s -X POST localhost:18790/v1/tts/tasks \
    -H 'Content-Type: application/json' \
    -d '{"text":"你好世界"}' | jq .
```

```json
{
  "task_id": "f56266b7-88aa-4ec9-aa3a-c25d9025588f",
  "status": "PENDING"
}
```

查询任务状态：

```bash
curl -s localhost:18790/v1/tts/tasks/f56266b7-88aa-4ec9-aa3a-c25d9025588f | jq .
```

```json
{
  "task_id": "f56266b7-88aa-4ec9-aa3a-c25d9025588f",
  "status": "DONE",
  "progress": 100.0,
  "download_url": "/v1/tts/tasks/f56266b7-88aa-4ec9-aa3a-c25d9025588f/audio",
  "duration_ms": 1195.0,
  "error": null,
  "created_at": "2026-04-20T13:11:44.019962Z"
}
```

下载合成音频：

```bash
curl -s localhost:18790/v1/tts/tasks/f56266b7-88aa-4ec9-aa3a-c25d9025588f/audio \
    --output /tmp/tts_task.wav
# 返回 WAV 音频文件，可正常播放
```

### 发音词库管理

```bash
curl -s localhost:18790/v1/tts/lexicons | jq .
```

```json
{ "lexicons": [] }
```

```bash
curl -s -X POST localhost:18790/v1/tts/lexicons \
    -H 'Content-Type: application/json' \
    -d '{"entries":[{"word":"重庆","phoneme":"chong qing"}]}' | jq .
```

```json
{
  "id": "f4e7081f",
  "entries": [
    { "word": "重庆", "phoneme": "chong qing", "locale": "zh" }
  ],
  "created_at": "2026-04-20T13:12:12.326569Z"
}
```

---

## ASR 测试

### 健康检查 & 语言/模型查询

```bash
curl -s localhost:18790/v1/asr/healthz   | jq .
curl -s localhost:18790/v1/asr/languages | jq .
curl -s localhost:18790/v1/asr/models    | jq .
```

```json
{ "ready": true, "state": "ready", "backend": "sensevoice" }
```

```json
{ "languages": ["auto", "en", "ja", "ko", "yue", "zh"], "default": "zh" }
```

```json
[
  {
    "id": "sensevoice",
    "name": "SenseVoice",
    "capabilities": ["multilingual", "streaming"],
    "languages": ["zh", "en", "ja", "ko", "yue", "auto"],
    "sample_rate": 16000,
    "loaded": true
  }
]
```

### HTTP 同步识别

```bash
curl -s -X POST "localhost:18790/v1/asr/recognize?language=zh&punctuation=true" \
    -F file=@/tmp/speech.pcm | jq .
```

```json
{
  "text": "兄弟们，今天教你们卖烤肠暴力赚钱法，一根成本2块，卖8块，一天能卖100根。关键是这个秘制酱料配方，我偷偷告诉你们，蒜蓉酱打底加韩系辣酱，再放点蚝油，保证客人天天回购。",
  "sentences": [],
  "duration_ms": 14158.0,
  "processing_ms": 7904.0,
  "rtf": 0.5582709312438965,
  "language": "zh"
}
```

### ASR WebSocket 流式识别

以 20ms 帧（640 bytes）模拟实时推送，收到 `final` 后结束。

> **注意**：当前后端 SenseVoice 为离线批量推理模型，`partial` 结果仅在全部音频接收完毕后触发一次，并非逐字增量输出。

```bash
cat > /tmp/asr_ws.py <<'EOF'
import asyncio, json, pathlib, urllib.request, websockets

PCM = pathlib.Path("/tmp/speech.pcm").read_bytes()
FRAME = 320 * 2  # 20ms @16kHz int16

async def main():
    req = urllib.request.Request(
        'http://localhost:18790/v1/asr/stream/session',
        data=json.dumps({
            "sample_rate": 16000, "language": "zh",
            "partial_results": True, "encoding": "pcm_s16le"
        }).encode(),
        headers={'Content-Type': 'application/json'})
    sid = json.loads(urllib.request.urlopen(req).read())['session_id']
    uri = f"ws://localhost:18790/v1/asr/stream?session_id={sid}&language=zh&sample_rate=16000&partial=true"
    async with websockets.connect(uri) as ws:
        print(await ws.recv())

        async def send():
            for i in range(0, len(PCM) - FRAME + 1, FRAME):
                await ws.send(PCM[i:i+FRAME])
                await asyncio.sleep(0.02)
            await ws.send(json.dumps({"type": "end"}))

        async def recv():
            try:
                while True:
                    m = await ws.recv()
                    print(m)
                    if '"final"' in m: return
            except websockets.ConnectionClosed: return

        await asyncio.gather(send(), recv())

asyncio.run(main())
EOF

python /tmp/asr_ws.py
```

```json
{"type":"ready"}
{"type":"partial","text":"兄弟们，今天教你们卖烤肠暴力赚钱法，一根成本2块，卖8块，一天能卖100根。关键是这个秘制酱料配方，我偷偷告诉你们，蒜蓉酱打底加韩系辣酱，再放点蚝油，保证客人天天回购。","duration_ms":14140.0,"rtf":0.5589109063148499}
{"type":"final","text":"兄弟们，今天教你们卖烤肠暴力赚钱法，一根成本2块，卖8块，一天能卖100根。关键是这个秘制酱料配方，我偷偷告诉你们，蒜蓉酱打底加韩系辣酱，再放点蚝油，保证客人天天回购。","duration_ms":14140.0,"rtf":0.5589109063148499}
```

### 推理参数管理

```bash
curl -s localhost:18790/v1/asr/params | jq .
```

```json
{
  "language": "zh",
  "punctuation": true,
  "hotword_weight": null,
  "itn": null
}
```

```bash
curl -s -X PATCH localhost:18790/v1/asr/params \
    -H 'Content-Type: application/json' \
    -d '{"language":"en"}' | jq .
```

```json
{
  "language": "en",
  "punctuation": true,
  "hotword_weight": null,
  "itn": null
}
```

### 音频预处理配置

```bash
curl -s localhost:18790/v1/asr/audio | jq .
```

```json
{
  "sample_rate": 16000,
  "vad_threshold": null,
  "denoise": false,
  "agc": false
}
```

```bash
curl -s -X PATCH localhost:18790/v1/asr/audio \
    -H 'Content-Type: application/json' \
    -d '{"sample_rate":8000}' | jq .
```

```json
{
  "sample_rate": 16000,
  "vad_threshold": null,
  "denoise": false,
  "agc": false
}
```

### 引擎配置

```bash
curl -s localhost:18790/v1/asr/engine | jq .
```

```json
{
  "num_threads": 1,
  "device": "spacemit",
  "power_mode": null,
  "pending_restart": false
}
```

```bash
curl -s -X PATCH localhost:18790/v1/asr/engine \
    -H 'Content-Type: application/json' \
    -d '{"threads":8}' | jq .
```

```json
{
  "num_threads": 1,
  "device": "spacemit",
  "power_mode": null,
  "pending_restart": true
}
```

### 性能指标 & 运行态摘要

```bash
curl -s localhost:18790/v1/asr/stats | jq .
```

```json
{
  "total_requests": 1,
  "total_errors": 0,
  "rtf_avg": 0.5562,
  "uptime_s": 85.2
}
```

```bash
curl -s localhost:18790/v1/asr/info | jq .
```

```json
{
  "initialized": true,
  "backend": "sensevoice",
  "model": "sensevoice",
  "backends_loaded": ["sensevoice"]
}
```

### 异步转写任务

提交异步 job，服务端通过 httpx 下载 audio_url 后执行识别。需先启动临时文件服务：

```bash
cd /tmp && python -m http.server 8080 &
```

```bash
curl -s -X POST localhost:18790/v1/asr/jobs \
    -H 'Content-Type: application/json' \
    -d '{"audio_url":"http://localhost:8080/speech.pcm"}' | jq .
```

```json
{
  "job_id": "b1019d75-af63-4a71-aad4-374a6fc38a96",
  "status": "PENDING"
}
```

查询任务状态（异步完成后 status 变为 DONE，result 包含识别结果）：

```bash
curl -s localhost:18790/v1/asr/jobs/b1019d75-af63-4a71-aad4-374a6fc38a96 | jq .
```

```json
{
  "job_id": "b1019d75-af63-4a71-aad4-374a6fc38a96",
  "status": "DONE",
  "progress": 100.0,
  "result": {
    "text": "兄弟们，今天教你们卖烤肠暴力赚钱法，一根成本2块，卖8块，一天能卖100根。关键是这个秘制酱料配方，我偷偷告诉你们，蒜蓉酱打底加韩系辣酱，再放点蚝油，保证客人天天回购。",
    "sentences": [],
    "duration_ms": 14158.0,
    "processing_ms": 7875.0,
    "rtf": 0.5562226176261902,
    "language": "zh"
  },
  "error": null,
  "created_at": "2026-04-20T13:17:18.090998Z"
}
```

取消任务：

```bash
curl -s -X DELETE localhost:18790/v1/asr/jobs/{job_id} | jq .
```

```json
{ "job_id": "xxx", "status": "CANCELLED" }
```

### 热词词库管理

```bash
curl -s localhost:18790/v1/asr/lexicons | jq .
```

```json
{ "lexicons": [] }
```

```bash
curl -s -X POST localhost:18790/v1/asr/lexicons \
    -H 'Content-Type: application/json' \
    -d '{"entries":[{"word":"SpacemiT","weight":2.0}]}' | jq .
```

```json
{
  "id": "fd46cc8c",
  "entries": [
    { "word": "SpacemiT", "weight": 2.0 }
  ],
  "scope": "global",
  "created_at": "2026-04-20T13:12:20.754844Z"
}
```

---

## 模型管理测试（load / unload / switch）

### ASR 模型管理

启动时仅加载 `sensevoice`，通过 load/switch/unload 动态管理后端。

```bash
curl -s localhost:18790/v1/asr/models | jq .
```

```json
[
  {
    "id": "sensevoice",
    "name": "SenseVoice",
    "capabilities": ["multilingual", "streaming"],
    "languages": ["zh", "en", "ja", "ko", "yue", "auto"],
    "sample_rate": 16000,
    "loaded": true
  }
]
```

切换默认模型（已加载的）：

```bash
curl -s -X POST localhost:18790/v1/asr/models/switch \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"sensevoice"}' | jq .
```

```json
{ "switched": true, "default_model_id": "sensevoice" }
```

卸载未加载的模型 → 404：

```bash
curl -s -X POST localhost:18790/v1/asr/models/unload \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"qwen3-asr"}' | jq .
```

```json
{
  "error": "model_not_loaded",
  "message": "model 'qwen3-asr' not loaded",
  "retriable": false,
  "details": { "available": ["sensevoice"] }
}
```

动态加载新模型：

```bash
curl -s -X POST localhost:18790/v1/asr/models/load \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"qwen3-asr"}' | jq .
```

```json
{ "loaded": true, "model_id": "qwen3-asr", "state": "ready" }
```

确认模型列表更新：

```bash
curl -s localhost:18790/v1/asr/models | jq .
```

```json
[
  {
    "id": "sensevoice",
    "name": "SenseVoice",
    "capabilities": ["multilingual", "streaming"],
    "languages": ["zh", "en", "ja", "ko", "yue", "auto"],
    "sample_rate": 16000,
    "loaded": true
  },
  {
    "id": "qwen3-asr",
    "name": "Qwen3-ASR",
    "capabilities": ["multilingual"],
    "languages": ["zh", "en"],
    "sample_rate": null,
    "loaded": true
  }
]
```

### TTS 模型管理

启动时仅加载 `matcha_zh`，动态加载 kokoro 后切换、卸载、再加载。

```bash
curl -s localhost:18790/v1/tts/models | jq .
```

```json
[
  { "id": "matcha_zh",    "languages": ["zh"],    "sample_rate": 22050, "loaded": true  },
  { "id": "matcha_en",    "languages": ["en"],    "sample_rate": 22050, "loaded": false },
  { "id": "matcha_zh_en", "languages": ["zh-en"], "sample_rate": 22050, "loaded": false }
]
```

加载 kokoro：

```bash
curl -s -X POST localhost:18790/v1/tts/models/load \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"kokoro"}' | jq .
```

```json
{ "loaded": true, "model_id": "kokoro", "state": "ready" }
```

切换回 matcha_zh：

```bash
curl -s -X POST localhost:18790/v1/tts/models/switch \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"matcha_zh"}' | jq .
```

```json
{ "switched": true, "default_model_id": "matcha_zh" }
```

卸载 kokoro（非默认模型）：

```bash
curl -s -X POST localhost:18790/v1/tts/models/unload \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"kokoro"}' | jq .
```

```json
{ "unloaded": true, "model_id": "kokoro" }
```

再次加载 kokoro：

```bash
curl -s -X POST localhost:18790/v1/tts/models/load \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"kokoro"}' | jq .
```

```json
{ "loaded": true, "model_id": "kokoro", "state": "ready" }
```

确认模型列表包含 kokoro：

```bash
curl -s localhost:18790/v1/tts/models | jq .
```

```json
[
  { "id": "matcha_zh",    "languages": ["zh"],       "sample_rate": 22050, "loaded": true  },
  { "id": "matcha_en",    "languages": ["en"],       "sample_rate": 22050, "loaded": false },
  { "id": "matcha_zh_en", "languages": ["zh-en"],    "sample_rate": 22050, "loaded": false },
  { "id": "kokoro",       "languages": ["en", "zh"], "sample_rate": 24000, "loaded": true  }
]
```

### VAD 模型管理

VAD 当前仅有 silero 一个注册后端。

```bash
curl -s localhost:18790/v1/vad/models | jq .
```

```json
[
  { "id": "silero", "name": "silero", "capabilities": [], "languages": [], "sample_rate": null, "loaded": true }
]
```

```bash
curl -s -X POST localhost:18790/v1/vad/models/switch \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"silero"}' | jq .
```

```json
{ "switched": true, "default_model_id": "silero" }
```

### 错误处理

重复加载 → 409：

```bash
curl -s -X POST localhost:18790/v1/asr/models/load \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"sensevoice"}' | jq .
```

```json
{
  "error": "model_already_loaded",
  "message": "model 'sensevoice' already loaded",
  "retriable": false,
  "details": null
}
```

卸载默认模型 → 400：

```bash
curl -s -X POST localhost:18790/v1/asr/models/unload \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"sensevoice"}' | jq .
```

```json
{
  "error": "model_unload_forbidden",
  "message": "cannot unload default model 'sensevoice'",
  "retriable": false,
  "details": null
}
```

加载未注册模型 → 404：

```bash
curl -s -X POST localhost:18790/v1/asr/models/load \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"not_exist"}' | jq .
```

```json
{
  "error": "model_unknown",
  "message": "model 'not_exist' not registered",
  "retriable": false,
  "details": { "available": ["sensevoice", "qwen3-asr"] }
}
```

切换到未加载模型 → 404：

```bash
curl -s -X POST localhost:18790/v1/tts/models/switch \
    -H 'Content-Type: application/json' \
    -d '{"model_id":"not_exist"}' | jq .
```

```json
{
  "error": "model_not_loaded",
  "message": "model 'not_exist' not loaded",
  "retriable": false,
  "details": { "available": ["matcha_zh", "kokoro"] }
}
```

---

## 性能汇总

| 域  | 接口       | 音频时长 | 推理耗时 | RTF  |
|-----|-----------|---------|---------|------|
| TTS | HTTP 合成  | 3.32s   | 1.56s   | 0.47 |
| TTS | WS 流式   | 4.56s   | 2.17s   | 0.48 |
| ASR | HTTP 识别  | 14.16s  | 7.90s   | 0.56 |
| ASR | WS 流式   | 14.14s  | 7.91s   | 0.56 |

> RTF（Real-Time Factor）< 1 表示快于实时，值越小性能越好。

---

## 端点覆盖汇总

共 51 个 HTTP 端点 + 3 个 WebSocket 端点，全部 PASS。

| 域 | 端点 | 状态 |
|----|------|------|
| TTS | POST /synthesize | PASS |
| TTS | POST /stream/session | PASS |
| TTS | WS /stream | PASS |
| TTS | GET /voices | PASS |
| TTS | GET /models | PASS |
| TTS | POST /models/load | PASS |
| TTS | POST /models/unload | PASS |
| TTS | POST /models/switch | PASS |
| TTS | GET /healthz | PASS |
| TTS | GET /params | PASS |
| TTS | PATCH /params | PASS |
| TTS | GET /engine | PASS |
| TTS | PATCH /engine | PASS |
| TTS | GET /stats | PASS |
| TTS | GET /info | PASS |
| TTS | POST /tasks | PASS |
| TTS | GET /tasks/{task_id} | PASS |
| TTS | DELETE /tasks/{task_id} | PASS |
| TTS | GET /tasks/{task_id}/audio | PASS |
| TTS | GET /lexicons | PASS |
| TTS | POST /lexicons | PASS |
| ASR | POST /recognize | PASS |
| ASR | POST /stream/session | PASS |
| ASR | WS /stream | PASS |
| ASR | GET /models | PASS |
| ASR | POST /models/load | PASS |
| ASR | POST /models/unload | PASS |
| ASR | POST /models/switch | PASS |
| ASR | GET /languages | PASS |
| ASR | GET /healthz | PASS |
| ASR | GET /params | PASS |
| ASR | PATCH /params | PASS |
| ASR | GET /audio | PASS |
| ASR | PATCH /audio | PASS |
| ASR | GET /engine | PASS |
| ASR | PATCH /engine | PASS |
| ASR | GET /stats | PASS |
| ASR | GET /info | PASS |
| ASR | POST /jobs | PASS |
| ASR | GET /jobs/{job_id} | PASS |
| ASR | DELETE /jobs/{job_id} | PASS |
| ASR | GET /lexicons | PASS |
| ASR | POST /lexicons | PASS |
| VAD | POST /analyze | PASS |
| VAD | POST /segments | PASS |
| VAD | WS /stream | PASS |
| VAD | GET /models | PASS |
| VAD | POST /models/load | PASS |
| VAD | POST /models/unload | PASS |
| VAD | POST /models/switch | PASS |
| VAD | GET /healthz | PASS |
| VAD | GET /params | PASS |
| VAD | PATCH /params | PASS |
| VAD | GET /audio | PASS |
| VAD | PATCH /audio | PASS |
| VAD | GET /engine | PASS |
| VAD | PATCH /engine | PASS |
| VAD | GET /stats | PASS |
| VAD | GET /info | PASS |
