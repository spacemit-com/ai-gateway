"""错误码清单：什么阶段、什么情况出现什么错误，上层该怎么处理。

接口错误响应统一为 {"error": <code>, "message", "retriable", "details"}；
下载状态（GET .../models/{id}/download）里的 error_code 也取自这里。
GET /v1/errors 原样返回本清单。
"""

from __future__ import annotations

from typing import Optional

# phase: download | download_api | load | inference | request
CATALOG: list[dict] = [
    # ---- 下载过程（出现在下载状态的 error_code，以及加载时自动下载失败的错误响应里）----
    {"code": "disk_insufficient", "phase": "download", "http_status": 507, "retriable": False,
     "when": "下载前预检或写入时磁盘空间不足（需要 = 待下载大小 + 解压估算 + 预留）",
     "action": "清理磁盘后重试；details 给出 required_bytes / free_bytes"},
    {"code": "network_error", "phase": "download", "http_status": 502, "retriable": True,
     "when": "连接失败、超时、连接中途断开",
     "action": "直接重试，已下载部分会续传"},
    {"code": "remote_http_error", "phase": "download", "http_status": 502, "retriable": None,
     "when": "模型服务器返回 HTTP 4xx/5xx（如文件不存在）",
     "action": "5xx/429 可重试；4xx 需检查模型 URL（retriable 字段按状态码给出）"},
    {"code": "tls_error", "phase": "download", "http_status": 502, "retriable": False,
     "when": "开启 download.tls_verify 后证书校验失败（证书过期、域名不符、系统时间错误）",
     "action": "检查设备时间与 CA 证书；联系模型服务器维护方"},
    {"code": "redirect_blocked", "phase": "download", "http_status": 502, "retriable": False,
     "when": "下载被重定向到 http（https 降级）或重定向次数过多",
     "action": "检查模型 URL 与网络环境（可能存在劫持）"},
    {"code": "size_mismatch", "phase": "download", "http_status": 502, "retriable": True,
     "when": "下载得到的文件大小与服务器声明不一致或为空",
     "action": "重试（会重新下载）"},
    {"code": "checksum_mismatch", "phase": "download", "http_status": 502, "retriable": True,
     "when": "md5 与服务器 <url>.md5 不一致，文件已删除",
     "action": "重试；多次失败说明服务器文件与 md5 不一致，联系维护方"},
    {"code": "extract_failed", "phase": "download", "http_status": 500, "retriable": False,
     "when": "压缩包损坏、包含不安全路径，或解压后缺少必需文件",
     "action": "联系模型服务器维护方；目标目录不会留下半成品"},
    {"code": "permission_denied", "phase": "download", "http_status": 500, "retriable": False,
     "when": "模型目录没有写权限（常见于 root 与普通用户混用过）",
     "action": "修正 ~/.cache/models 的属主后重试"},
    {"code": "io_error", "phase": "download", "http_status": 500, "retriable": False,
     "when": "其他文件读写错误",
     "action": "查看 message 与 gateway 日志"},
    {"code": "cancelled", "phase": "download", "http_status": 502, "retriable": True,
     "when": "等待中的下载被用户取消",
     "action": "需要时重新发起下载"},

    # ---- 下载接口本身的请求错误 ----
    {"code": "model_not_found", "phase": "download_api", "http_status": 400, "retriable": False,
     "when": "模型 id 不存在（LLM/Embed/Rerank/VLM；查询进度接口返回 404）",
     "action": "先查询 /models 列表"},
    {"code": "model_unknown", "phase": "download_api", "http_status": 404, "retriable": False,
     "when": "模型 id 不存在（ASR/TTS/VAD/Vision）",
     "action": "先查询 /models 列表"},
    {"code": "download_not_supported", "phase": "download_api", "http_status": 400, "retriable": False,
     "when": "该模型不由 gateway 下载（remote/local_path 模型、qwen3-asr 等）",
     "action": "无需下载"},
    {"code": "already_downloaded", "phase": "download_api", "http_status": 400, "retriable": False,
     "when": "模型已下载完成",
     "action": "直接加载"},
    {"code": "download_in_progress", "phase": "download_api", "http_status": 400, "retriable": True,
     "when": "该模型已有下载任务在进行",
     "action": "轮询 GET .../download 查看进度"},
    {"code": "no_active_download", "phase": "download_api", "http_status": 400, "retriable": False,
     "when": "取消下载时没有进行中的任务",
     "action": "无需处理"},

    # ---- 加载 ----
    {"code": "model_not_downloaded", "phase": "load", "http_status": 400, "retriable": False,
     "when": "加载 LLM/Embed/Rerank/VLM 模型时文件不存在",
     "action": "先调用下载接口"},
    {"code": "model_downloading", "phase": "load", "http_status": 400, "retriable": True,
     "when": "模型仍在下载中",
     "action": "等待下载完成后再加载"},
    {"code": "load_oom", "phase": "load", "http_status": 503, "retriable": False,
     "when": "加载时内存不足（推理进程被 SIGKILL 或日志出现内存分配失败）",
     "action": "卸载其他模型、换更小的模型或减小 --ctx-size"},
    {"code": "load_invalid_model", "phase": "load", "http_status": 503, "retriable": False,
     "when": "模型文件损坏或模型架构不被推理引擎支持",
     "action": "重新下载；仍失败说明该模型与当前引擎版本不兼容"},
    {"code": "load_invalid_args", "phase": "load", "http_status": 503, "retriable": False,
     "when": "extra_args / default_args 中有推理引擎不认识的参数",
     "action": "修正参数"},
    {"code": "load_timeout", "phase": "load", "http_status": 503, "retriable": True,
     "when": "推理进程启动后 120 秒内未就绪（进程已被停止）",
     "action": "重试；持续超时检查设备负载"},
    {"code": "backend_missing", "phase": "load", "http_status": 503, "retriable": False,
     "when": "找不到推理引擎可执行文件（llama-server）",
     "action": "安装 llama.cpp-tools-spacemit"},
    {"code": "load_failed", "phase": "load", "http_status": 503, "retriable": True,
     "when": "其他加载失败；details.log_tail 附推理进程最后几行日志",
     "action": "查看 details.log_tail；重试"},

    # ---- 推理 ----
    {"code": "model_not_loaded", "phase": "inference", "http_status": 503, "retriable": False,
     "when": "没有已加载或默认模型（ASR/TTS/VAD 卸载状态下返回 404）",
     "action": "先加载模型"},
    {"code": "backend_crashed", "phase": "inference", "http_status": 503, "retriable": True,
     "when": "推理进程在处理请求时退出或连不上（流式请求中途断开时以流内错误帧给出，见 notes）",
     "action": "重试（下次请求会自动尝试重新拉起）；反复出现查看 details.log_tail"},
    {"code": "inference_failed", "phase": "inference", "http_status": 500, "retriable": True,
     "when": "推理引擎执行推理时出错（目前用于 Vision 原生推理异常）",
     "action": "重试；反复出现查看 GET /v1/errors/recent 的 details 与 gateway 日志"},
    {"code": "upstream_error", "phase": "inference", "http_status": 502, "retriable": True,
     "when": "remote 类型模型的远程 API 连不上或流式响应中途断开",
     "action": "检查网络与远程 API 地址后重试"},
    {"code": "asr_backend_unavailable", "phase": "inference", "http_status": 503, "retriable": True,
     "when": "ASR 后端未就绪", "action": "稍后重试"},
    {"code": "tts_backend_unavailable", "phase": "inference", "http_status": 503, "retriable": True,
     "when": "TTS 后端未就绪", "action": "稍后重试"},
    {"code": "vad_backend_unavailable", "phase": "inference", "http_status": 503, "retriable": True,
     "when": "VAD 后端未就绪", "action": "稍后重试"},
    {"code": "asr_invalid_audio", "phase": "request", "http_status": 400, "retriable": False,
     "when": "音频无法解码或格式不支持", "action": "修正输入"},
    {"code": "tts_invalid_text", "phase": "request", "http_status": 400, "retriable": False,
     "when": "合成文本为空或非法", "action": "修正输入"},
    {"code": "vad_invalid_audio", "phase": "request", "http_status": 400, "retriable": False,
     "when": "音频无法解码或格式不支持", "action": "修正输入"},
    {"code": "request_too_large", "phase": "request", "http_status": 413, "retriable": False,
     "when": "上传内容超过 limits.max_upload_bytes", "action": "缩小输入"},
    {"code": "validation_error", "phase": "request", "http_status": 422, "retriable": False,
     "when": "请求参数校验失败", "action": "按 details 修正参数"},
    {"code": "http_error", "phase": "request", "http_status": None, "retriable": False,
     "when": "其他请求被拒绝（如模型已注册、参数不合法），原因见 message",
     "action": "按 message 处理"},
    {"code": "internal_error", "phase": "inference", "http_status": 500, "retriable": False,
     "when": "未分类的内部错误", "action": "查看 gateway 日志（journalctl -u spacemit-ai-gateway）"},
]

NOTES = [
    "GET /v1/errors/recent 按域、模型、时间查询实际发生过的模型故障（下载 / 加载 / 推理阶段），"
    "gateway 和开发板重启后仍可查到；request / download_api 阶段的调用方错误不记录。",
    "LLM/Embed/Rerank/VLM 推理请求被推理引擎拒绝时（如上下文超长），按 OpenAI 格式原样透传引擎的错误体。",
    "Vision 接口保留原有整数 code 包装，错误响应额外带字符串字段 error，取值同本清单。",
    "流式请求（stream=true）在响应头发出后失败时 HTTP 状态码已是 200，错误以流内最后一帧给出："
    "OpenAI 兼容接口为 data: {\"error\": {\"code\", \"message\", \"retriable\", ...}}；"
    "Anthropic /v1/messages 与 /v1/responses 为 event: error；Ollama /api/chat 为 {\"error\", \"code\", \"done\": true}。"
    "帧里的 code 取自本清单（本地模型 backend_crashed，remote 模型 upstream_error）。",
]

_BY_CODE = {item["code"]: item for item in CATALOG}


def is_retriable(code: str) -> bool:
    item = _BY_CODE.get(code)
    return bool(item and item["retriable"])


def lookup(code: str) -> Optional[dict]:
    return _BY_CODE.get(code)
