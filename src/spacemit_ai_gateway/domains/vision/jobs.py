from __future__ import annotations

import os
import json as json_mod
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import cv2

from .adapters.native import NativeAdapter, ServiceError
from .models import ModelRegistry
from .schemas import (
    ErrorCode,
    JobCancelResponse,
    JobCreateResponse,
    JobStatusResponse,
)

IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".bmp", ".webp")
VIDEO_EXTS = (".mp4", ".avi", ".mkv", ".mov", ".flv", ".wmv")


@dataclass
class Job:
    job_id: str
    input_uri: str
    tasks: List[str]
    model_id: Optional[str] = None
    model_group: Optional[str] = None
    callback_url: Optional[str] = None
    render: bool = False
    render_mode: Optional[str] = None
    frame_sample_rate: Optional[int] = None
    status: str = "PENDING"
    progress: int = 0
    results_uri: Optional[str] = None
    artifacts: Optional[Dict[str, Any]] = None
    accepted_at: str = ""
    created_at: float = field(default_factory=time.time)
    cancelled: bool = False


class JobManager:
    """管理 Vision 离线异步任务，含后台执行与状态机。"""

    MAX_JOBS = 64

    def __init__(self, adapter: NativeAdapter, registry: ModelRegistry) -> None:
        self._lock = threading.RLock()
        self._jobs: Dict[str, Job] = {}
        self._adapter = adapter
        self._registry = registry
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="vision_job")

    def create_job(
        self,
        input_uri: str,
        tasks: List[str],
        model_id: Optional[str] = None,
        model_group: Optional[str] = None,
        callback_url: Optional[str] = None,
        render: bool = False,
        render_mode: Optional[str] = None,
        frame_sample_rate: Optional[int] = None,
    ) -> JobCreateResponse:
        with self._lock:
            if len(self._jobs) >= self.MAX_JOBS:
                raise ServiceError(429, ErrorCode.TOO_MANY_REQUESTS, "too many active jobs")

        job_id = f"vision_job_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        job = Job(
            job_id=job_id,
            input_uri=input_uri,
            tasks=tasks,
            model_id=model_id,
            model_group=model_group,
            callback_url=callback_url,
            render=render,
            render_mode=render_mode,
            frame_sample_rate=frame_sample_rate,
            status="PENDING",
            accepted_at=now_iso,
        )

        with self._lock:
            self._jobs[job_id] = job

        self._executor.submit(self._run_job, job_id)
        return JobCreateResponse(job_id=job_id, status="PENDING", accepted_at=now_iso)

    def _run_job(self, job_id: str) -> None:
        """后台线程：执行任务，推进状态机 PENDING → RUNNING → DONE/FAILED。"""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job.cancelled:
                return
            job.status = "RUNNING"
            job.progress = 0

        try:
            input_path = job.input_uri
            is_local = not input_path.startswith(("http://", "https://"))

            if is_local and not os.path.exists(input_path):
                raise FileNotFoundError(f"input_uri not found: {input_path}")

            # 远程 URL → 下载到临时文件
            if not is_local:
                image_bytes = self._adapter.load_url_bytes(input_path)
                tmp_path = f"/tmp/vision_job_{job_id}_input"
                with open(tmp_path, "wb") as f:
                    f.write(image_bytes)
                input_path = tmp_path

            managed, resolved_id = self._registry.get_instance(job.model_id)
            sample_rate = job.frame_sample_rate or 1

            # 分类收集：图片 vs 视频
            image_paths: List[str] = []
            video_paths: List[str] = []

            if os.path.isdir(input_path):
                for f in sorted(os.listdir(input_path)):
                    ext = os.path.splitext(f)[1].lower()
                    full = os.path.join(input_path, f)
                    if ext in IMAGE_EXTS:
                        image_paths.append(full)
                    elif ext in VIDEO_EXTS:
                        video_paths.append(full)
            else:
                ext = os.path.splitext(input_path)[1].lower()
                if ext in VIDEO_EXTS:
                    video_paths.append(input_path)
                else:
                    image_paths.append(input_path)

            if not image_paths and not video_paths:
                raise ValueError("no processable files found in input_uri")

            all_results: List[Dict[str, Any]] = []

            # 处理图片
            total_images = len(image_paths)
            for idx, fpath in enumerate(image_paths):
                with self._lock:
                    if job.cancelled:
                        job.status = "CANCELLED"
                        return

                if idx % sample_rate != 0:
                    continue

                result = self._process_image_file(managed, fpath)
                all_results.append(result)

                with self._lock:
                    ratio = (idx + 1) / max(total_images, 1)
                    job.progress = int(ratio * 50) if video_paths else int(ratio * 100)

            # 处理视频
            for vidx, vpath in enumerate(video_paths):
                with self._lock:
                    if job.cancelled:
                        job.status = "CANCELLED"
                        return

                video_result = self._process_video_file(job, managed, vpath, sample_rate)
                all_results.append(video_result)

            # 写结果文件
            artifact_dir = f"/tmp/vision_jobs/{job_id}"
            os.makedirs(artifact_dir, exist_ok=True)
            result_path = os.path.join(artifact_dir, "result.json")
            with open(result_path, "w") as f:
                json_mod.dump({"results": all_results, "total": len(all_results)}, f)

            results_uri = f"/artifacts/vision/jobs/{job_id}/result.json"
            artifacts = None
            if job.render:
                artifacts = {"rendered_uri": f"/artifacts/vision/jobs/{job_id}/rendered/"}

            with self._lock:
                job.status = "DONE"
                job.progress = 100
                job.results_uri = results_uri
                job.artifacts = artifacts

            if job.callback_url:
                self._send_callback(job)

        except Exception as exc:
            with self._lock:
                job.status = "FAILED"
                job.artifacts = {"error": str(exc)}

    def _process_image_file(self, managed, fpath: str) -> Dict[str, Any]:
        result: Dict[str, Any] = {"type": "image", "file": os.path.basename(fpath)}
        if managed.backend_instance is not None:
            with open(fpath, "rb") as f:
                image_bytes = f.read()
            img_bgr = self._adapter.bytes_to_bgr(image_bytes)
            ok, raw = self._adapter.infer_image(managed.backend_instance, img_bgr)
            result["status"] = "ok" if ok else "error"
            result["detections_count"] = len(raw) if ok and isinstance(raw, (list, tuple)) else 0
        else:
            result["status"] = "ok"
            result["detections_count"] = 0
        return result

    def _process_video_file(self, job: Job, managed, vpath: str, sample_rate: int) -> Dict[str, Any]:
        cap = cv2.VideoCapture(vpath)
        if not cap.isOpened():
            return {"type": "video", "file": os.path.basename(vpath), "status": "error", "error": "cannot open video"}

        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sampled_total = max(total_frames // sample_rate, 1)

        frames: List[Dict[str, Any]] = []
        frame_idx = 0
        processed = 0

        while True:
            with self._lock:
                if job.cancelled:
                    job.status = "CANCELLED"
                    cap.release()
                    return {"type": "video", "file": os.path.basename(vpath), "status": "cancelled"}

            ret, frame = cap.read()
            if not ret:
                break

            if frame_idx % sample_rate == 0:
                timestamp_ms = int((frame_idx / fps) * 1000)
                frame_result: Dict[str, Any] = {"frame_index": frame_idx, "timestamp_ms": timestamp_ms}

                if managed.backend_instance is not None:
                    ok, raw = self._adapter.infer_image(managed.backend_instance, frame)
                    frame_result["status"] = "ok" if ok else "error"
                    frame_result["detections_count"] = len(raw) if ok and isinstance(raw, (list, tuple)) else 0
                else:
                    frame_result["status"] = "ok"
                    frame_result["detections_count"] = 0

                frames.append(frame_result)
                processed += 1

                with self._lock:
                    job.progress = min(int((processed / sampled_total) * 100), 99)

            frame_idx += 1

        cap.release()

        return {
            "type": "video",
            "file": os.path.basename(vpath),
            "status": "ok",
            "fps": round(fps, 2),
            "total_frames": total_frames,
            "sample_rate": sample_rate,
            "processed_frames": len(frames),
            "frames": frames,
        }

    @staticmethod
    def _send_callback(job: Job) -> None:
        """尽力发送回调通知，失败不影响任务状态。"""
        try:
            import json as json_mod
            from urllib.request import Request, urlopen
            payload = json_mod.dumps({
                "job_id": job.job_id,
                "status": job.status,
                "results_uri": job.results_uri,
            }).encode()
            req = Request(job.callback_url, data=payload, headers={"Content-Type": "application/json"})
            urlopen(req, timeout=5)
        except Exception:
            pass

    def get_job(self, job_id: str) -> JobStatusResponse:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ServiceError(404, ErrorCode.SERVICE_NOT_FOUND, f"job not found: {job_id}")
            return JobStatusResponse(
                job_id=job.job_id,
                status=job.status,
                progress=job.progress,
                results_uri=job.results_uri,
                artifacts=job.artifacts,
            )

    def cancel_job(self, job_id: str) -> JobCancelResponse:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                raise ServiceError(404, ErrorCode.SERVICE_NOT_FOUND, f"job not found: {job_id}")
            if job.status in ("DONE", "FAILED", "CANCELLED"):
                raise ServiceError(409, ErrorCode.INVALID_ARGUMENT, f"job already in terminal state: {job.status}")
            job.cancelled = True
            job.status = "CANCELLED"
        return JobCancelResponse(cancelled=True, job_id=job_id)
