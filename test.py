import asyncio
import json
from pathlib import Path

import cv2
import websockets

WS_URL = "ws://127.0.0.1:18790/v1/vision/stream"
IMAGE_PATH = "src/spacemit_ai_gateway/domains/vision/test.jpg"


async def main() -> None:
    async with websockets.connect(WS_URL, max_size=50 * 1024 * 1024) as ws:
        # 1) start session
        await ws.send(
            json.dumps(
                {
                    "signal": "start",
                    "model_id": "yolov8n",
                    "fps_limit": 15,
                    "priority": 1,
                }
            )
        )
        ready = json.loads(await ws.recv())
        print("ready:", ready)

        # 2) send one jpeg frame
        img = cv2.imread(str(Path(IMAGE_PATH)))
        ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
        if not ok:
            raise RuntimeError("failed to encode image")
        await ws.send(buf.tobytes())

        # 3) receive frame result
        result = json.loads(await ws.recv())
        print("result:", result)

        # 4) end session
        await ws.send(json.dumps({"signal": "end"}))
        end = json.loads(await ws.recv())
        print("end:", end)


if __name__ == "__main__":
    asyncio.run(main())

