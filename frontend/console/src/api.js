// 统一的 API 封装 —— 所有后端请求从这里走
// 真实后端对接：window.API_BASES 里配置 base URL

const { API_BASES } = window;

// ---------------- 通用请求 ----------------
async function request(base, path, opts = {}) {
  const url = base + path;
  try {
    const res = await fetch(url, {
      headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
      ...opts,
    });
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const json = await res.clone().json();
        detail = json.detail?.message || json.message || json.detail || detail;
      } catch (_) {}
      const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
      err.status = res.status;
      throw err;
    }
    const ct = res.headers.get('content-type') || '';
    if (ct.includes('application/json')) return await res.json();
    if (ct.startsWith('audio/')) return await res.blob();
    return await res.text();
  } catch (e) {
    console.warn('[api]', url, e.message);
    throw e;
  }
}

// ---------------- ASR ----------------
window.asrApi = {
  listModels:   () => request(API_BASES.asr, '/v1/asr/models'),
  health:       () => request(API_BASES.asr, '/v1/asr/healthz'),
  stats:        () => request(API_BASES.asr, '/v1/asr/stats'),
  info:         () => request(API_BASES.asr, '/v1/asr/info'),
  languages:    () => request(API_BASES.asr, '/v1/asr/languages'),
  getParams:    () => request(API_BASES.asr, '/v1/asr/params'),
  updateParams: (body) => request(API_BASES.asr, '/v1/asr/params',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  getAudio:     () => request(API_BASES.asr, '/v1/asr/audio'),
  updateAudio:  (body) => request(API_BASES.asr, '/v1/asr/audio',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  getEngine:    () => request(API_BASES.asr, '/v1/asr/engine'),
  updateEngine: (body) => request(API_BASES.asr, '/v1/asr/engine',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  recognize:    (audioBlob, opts = {}) => {
    const form = new FormData();
    form.append('file', audioBlob, 'audio.wav');
    if (opts.model) form.append('model', opts.model);
    if (opts.language) form.append('language', opts.language);
    if (opts.punctuation !== undefined) form.append('punctuation', String(opts.punctuation));
    if (opts.sample_rate) form.append('sample_rate', String(opts.sample_rate));
    return fetch(API_BASES.asr + '/v1/asr/recognize', { method: 'POST', body: form })
      .then(r => r.json());
  },
  createSession: (body) => request(API_BASES.asr, '/v1/asr/stream/session',
                   { method: 'POST', body: JSON.stringify(body) }),
  loadModel:    (model_id) => request(API_BASES.asr, '/v1/asr/models/load',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  unloadModel:  (model_id) => request(API_BASES.asr, '/v1/asr/models/unload',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  switchModel:  (model_id) => request(API_BASES.asr, '/v1/asr/models/switch',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  submitJob:    (body) => request(API_BASES.asr, '/v1/asr/jobs',
                   { method: 'POST', body: JSON.stringify(body) }),
  getJob:       (job_id) => request(API_BASES.asr, '/v1/asr/jobs/' + encodeURIComponent(job_id)),
  cancelJob:    (job_id) => request(API_BASES.asr, '/v1/asr/jobs/' + encodeURIComponent(job_id),
                   { method: 'DELETE' }),
  listLexicons: () => request(API_BASES.asr, '/v1/asr/lexicons'),
  createLexicon:(body) => request(API_BASES.asr, '/v1/asr/lexicons',
                   { method: 'POST', body: JSON.stringify(body) }),
  deleteLexicon:(id) => request(API_BASES.asr, '/v1/asr/lexicons/' + encodeURIComponent(id),
                   { method: 'DELETE' }),
  streamUrl:    () => API_BASES.asr.replace(/^http/, 'ws') + '/v1/asr/stream',
};

// ---------------- TTS ----------------
window.ttsApi = {
  listModels:   () => request(API_BASES.tts, '/v1/tts/models'),
  listVoices:   () => request(API_BASES.tts, '/v1/tts/voices'),
  stats:        () => request(API_BASES.tts, '/v1/tts/stats'),
  health:       () => request(API_BASES.tts, '/v1/tts/healthz'),
  info:         () => request(API_BASES.tts, '/v1/tts/info'),
  getParams:    () => request(API_BASES.tts, '/v1/tts/params'),
  updateParams: (body) => request(API_BASES.tts, '/v1/tts/params',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  getEngine:    () => request(API_BASES.tts, '/v1/tts/engine'),
  updateEngine: (body) => request(API_BASES.tts, '/v1/tts/engine',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  synthesize:   (body) => fetch(API_BASES.tts + '/v1/tts/synthesize', {
                   method: 'POST',
                   headers: { 'Content-Type': 'application/json' },
                   body: JSON.stringify(body),
                 }).then(async r => {
                   if (!r.ok) {
                     const e = await r.json().catch(() => ({}));
                     throw new Error(e.detail?.message || e.message || e.detail || r.statusText);
                   }
                   let blob = await r.blob();
                   const ct = r.headers.get('content-type') || 'audio/wav';
                   if (!blob.type || blob.type === 'application/octet-stream') {
                     blob = new Blob([blob], { type: ct });
                   }
                   return {
                     blob,
                     meta: {
                       rtf: parseFloat(r.headers.get('x-rtf')) || 0,
                       duration_ms: parseInt(r.headers.get('x-duration-ms')) || 0,
                       processing_ms: parseInt(r.headers.get('x-processing-ms')) || 0,
                       sample_rate: parseInt(r.headers.get('x-sample-rate')) || 0,
                     },
                   };
                 }),
  loadModel:    (model_id) => request(API_BASES.tts, '/v1/tts/models/load',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  unloadModel:  (model_id) => request(API_BASES.tts, '/v1/tts/models/unload',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  switchModel:  (model_id) => request(API_BASES.tts, '/v1/tts/models/switch',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  createStreamSession: (body) => request(API_BASES.tts, '/v1/tts/stream/session',
                   { method: 'POST', body: JSON.stringify(body) }),
  submitTask:   (body) => request(API_BASES.tts, '/v1/tts/tasks',
                   { method: 'POST', body: JSON.stringify(body) }),
  getTask:      (task_id) => request(API_BASES.tts, '/v1/tts/tasks/' + encodeURIComponent(task_id)),
  cancelTask:   (task_id) => request(API_BASES.tts, '/v1/tts/tasks/' + encodeURIComponent(task_id),
                   { method: 'DELETE' }),
  getTaskAudio: (task_id) => fetch(API_BASES.tts + '/v1/tts/tasks/' + encodeURIComponent(task_id) + '/audio')
                   .then(r => { if (!r.ok) throw new Error(r.status + ' ' + r.statusText); return r.blob(); }),
  listLexicons: () => request(API_BASES.tts, '/v1/tts/lexicons'),
  createLexicon:(body) => request(API_BASES.tts, '/v1/tts/lexicons',
                   { method: 'POST', body: JSON.stringify(body) }),
  deleteLexicon:(id) => request(API_BASES.tts, '/v1/tts/lexicons/' + encodeURIComponent(id),
                   { method: 'DELETE' }),
  streamUrl:    () => API_BASES.tts.replace(/^http/, 'ws') + '/v1/tts/stream',
};

// ---------------- VAD ----------------
window.vadApi = {
  listModels:   () => request(API_BASES.vad, '/v1/vad/models'),
  health:       () => request(API_BASES.vad, '/v1/vad/healthz'),
  stats:        () => request(API_BASES.vad, '/v1/vad/stats'),
  info:         () => request(API_BASES.vad, '/v1/vad/info'),
  getParams:    () => request(API_BASES.vad, '/v1/vad/params'),
  updateParams: (body) => request(API_BASES.vad, '/v1/vad/params',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  getAudio:     () => request(API_BASES.vad, '/v1/vad/audio'),
  updateAudio:  (body) => request(API_BASES.vad, '/v1/vad/audio',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  getEngine:    () => request(API_BASES.vad, '/v1/vad/engine'),
  updateEngine: (body) => request(API_BASES.vad, '/v1/vad/engine',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  analyze:      (audioBlob, opts = {}) => {
    const form = new FormData();
    form.append('file', audioBlob, 'audio.wav');
    const qs = opts.sample_rate ? '?sample_rate=' + opts.sample_rate : '';
    return fetch(API_BASES.vad + '/v1/vad/analyze' + qs, { method: 'POST', body: form })
      .then(r => { if (!r.ok) throw new Error(r.status + ' ' + r.statusText); return r.json(); });
  },
  segments:     (audioBlob, opts = {}) => {
    const form = new FormData();
    form.append('file', audioBlob, 'audio.wav');
    const qs = opts.sample_rate ? '?sample_rate=' + opts.sample_rate : '';
    return fetch(API_BASES.vad + '/v1/vad/segments' + qs, { method: 'POST', body: form })
      .then(r => { if (!r.ok) throw new Error(r.status + ' ' + r.statusText); return r.json(); });
  },
  loadModel:    (model_id) => request(API_BASES.vad, '/v1/vad/models/load',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  unloadModel:  (model_id) => request(API_BASES.vad, '/v1/vad/models/unload',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  switchModel:  (model_id) => request(API_BASES.vad, '/v1/vad/models/switch',
                   { method: 'POST', body: JSON.stringify({ model_id }) }),
  streamUrl:    () => API_BASES.vad.replace(/^http/, 'ws') + '/v1/vad/stream',
};

// ---------------- Vision ----------------
// Vision API wraps responses in {code, message, data} — unwrap automatically
const VISION_BACKEND_MODEL_ID_ALIASES = {
  yolo11n: 'yolov11n',
  yolo11s: 'yolov11s',
  yolo11m: 'yolov11m',
};

function visionBackendModelId(model_id) {
  return VISION_BACKEND_MODEL_ID_ALIASES[model_id] || model_id;
}
window.visionBackendModelId = visionBackendModelId;

async function visionRequest(base, path, opts = {}) {
  const raw = await request(base, path, opts);
  return raw && raw.data !== undefined ? raw.data : raw;
}

function visionModelList(data) {
  if (Array.isArray(data)) return data;
  if (Array.isArray(data?.data)) return data.data;
  return [];
}

window.visionApi = {
  listModels:   () => visionRequest(API_BASES.vision, '/v1/vision/models').then(visionModelList),
  stats:        () => visionRequest(API_BASES.vision, '/v1/vision/stats'),
  health:       () => visionRequest(API_BASES.vision, '/v1/vision/healthz'),
  getParams:    () => visionRequest(API_BASES.vision, '/v1/vision/params'),
  updateParams: (body) => visionRequest(API_BASES.vision, '/v1/vision/params',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  getEngine:    () => visionRequest(API_BASES.vision, '/v1/vision/engine'),
  updateEngine: (body) => visionRequest(API_BASES.vision, '/v1/vision/engine',
                   { method: 'PATCH', body: JSON.stringify(body) }),
  inference:    (imageFile, tasks, model_id, opts) => {
    const form = new FormData();
    form.append('file', imageFile);
    if (tasks) form.append('tasks', JSON.stringify(tasks));
    const qs = new URLSearchParams();
    if (model_id) qs.set('model_id', visionBackendModelId(model_id));
    if (opts && opts.conf != null && opts.conf !== '') qs.set('conf', String(opts.conf));
    if (opts && opts.iou != null && opts.iou !== '') qs.set('iou', String(opts.iou));
    const suffix = qs.toString() ? ('?' + qs.toString()) : '';
    return fetch(API_BASES.vision + '/v1/vision/inference' + suffix, { method: 'POST', body: form })
      .then(async r => {
        const json = await r.json();
        if (!r.ok) throw new Error(json.message || json.detail || `${r.status} ${r.statusText}`);
        return json;
      })
      .then(r => r && r.data !== undefined ? r.data : r);
  },
  feature:      (imageFile, type, model_id, imageFileB) => {
    const form = new FormData();
    form.append('file', imageFile);
    form.append('type', type);
    if (imageFileB) form.append('file_b', imageFileB);
    const qs = model_id ? '?model_id=' + encodeURIComponent(visionBackendModelId(model_id)) : '';
    return fetch(API_BASES.vision + '/v1/vision/feature' + qs, { method: 'POST', body: form })
      .then(async r => {
        const json = await r.json();
        if (!r.ok) throw new Error(json.message || json.detail || `${r.status} ${r.statusText}`);
        return json;
      })
      .then(r => r && r.data !== undefined ? r.data : r);
  },
  loadModel:    (model_id) => visionRequest(API_BASES.vision, '/v1/vision/models/load',
                   { method: 'POST', body: JSON.stringify({ model_id: visionBackendModelId(model_id) }) }),
  unloadModel:  (model_id) => visionRequest(API_BASES.vision, '/v1/vision/models/unload',
                   { method: 'POST', body: JSON.stringify({ model_id: visionBackendModelId(model_id) }) }),
  switchModel:  (model_id) => visionRequest(API_BASES.vision, '/v1/vision/models/switch',
                   { method: 'POST', body: JSON.stringify({ model_id: visionBackendModelId(model_id) }) }),
  createJob:    (body) => visionRequest(API_BASES.vision, '/v1/vision/jobs',
                   { method: 'POST', body: JSON.stringify({
                     ...body,
                     model_id: body?.model_id ? visionBackendModelId(body.model_id) : body?.model_id,
                   }) }),
  getJob:       (job_id) => visionRequest(API_BASES.vision, '/v1/vision/jobs/' + encodeURIComponent(job_id)),
  cancelJob:    (job_id) => visionRequest(API_BASES.vision, '/v1/vision/jobs/' + encodeURIComponent(job_id),
                   { method: 'DELETE' }),
  streamUrl:    () => API_BASES.vision.replace(/^http/, 'ws') + '/v1/vision/stream',
};

// ---------------- System ----------------
window.systemApi = {
  stats:  () => request(API_BASES.asr, '/api/stats').catch(() => window.mockSystemStats ? window.mockSystemStats() : null),
  events: (since) => request(API_BASES.asr, '/api/events?since=' + since).catch(() => []),
};

async function* chatCompletionStream(base, path, body) {
  const t0 = performance.now();
  const res = await fetch(base + path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ...body, stream: true }),
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const j = await res.json();
      detail = j.detail?.message || j.message || j.detail || detail;
    } catch (_) {}
    const err = new Error(typeof detail === 'string' ? detail : JSON.stringify(detail));
    err.status = res.status;
    throw err;
  }
  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buf = '';
  let firstTokenAt = null;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += decoder.decode(value, { stream: true });
    const lines = buf.split('\n');
    buf = lines.pop();
    for (const line of lines) {
      if (!line.startsWith('data:')) continue;
      const payload = line.slice(5).trim();
      if (payload === '[DONE]') return;
      try {
        const chunk = JSON.parse(payload);
        if (!firstTokenAt && chunk.choices?.[0]?.delta?.content) {
          firstTokenAt = performance.now();
        }
        chunk._timing = { t0, firstTokenAt, now: performance.now() };
        yield chunk;
      } catch (_) {}
    }
  }
}

// ---------------- LLM ----------------
window.llmApi = {
  listModels:   () => request(API_BASES.llm, '/v1/llm/models'),
  health:       () => request(API_BASES.llm, '/v1/llm/healthz'),
  chat:         (body) => request(API_BASES.llm, '/v1/llm/chat/completions',
                   { method: 'POST', body: JSON.stringify(body) }),
  chatStream:   (body) => chatCompletionStream(API_BASES.llm, '/v1/llm/chat/completions', body),
  // Model management
  registerModel:   (body) => request(API_BASES.llm, '/v1/llm/models/register',
                     { method: 'POST', body: JSON.stringify(body) }),
  deregisterModel: (model) => request(API_BASES.llm, '/v1/llm/models/deregister',
                     { method: 'POST', body: JSON.stringify({ model }) }),
  loadModel:       (model, extra_args = []) => request(API_BASES.llm, '/v1/llm/models/load',
                     { method: 'POST', body: JSON.stringify({ model, extra_args }) }),
  unloadModel:     (model) => request(API_BASES.llm, '/v1/llm/models/unload',
                     { method: 'POST', body: JSON.stringify({ model }) }),
  switchModel:     (model) => request(API_BASES.llm, '/v1/llm/models/switch',
                     { method: 'POST', body: JSON.stringify({ model }) }),
  // Download management
  startDownload:   (model) => request(API_BASES.llm, '/v1/llm/models/' + encodeURIComponent(model) + '/download',
                     { method: 'POST' }),
  getDownload:     (model) => request(API_BASES.llm, '/v1/llm/models/' + encodeURIComponent(model) + '/download'),
  cancelDownload:  (model) => request(API_BASES.llm, '/v1/llm/models/' + encodeURIComponent(model) + '/download',
                     { method: 'DELETE' }),
};

// ---------------- VLM ----------------
window.vlmApi = {
  listModels:   () => request(API_BASES.vlm, '/v1/vlm/models'),
  health:       () => request(API_BASES.vlm, '/v1/vlm/healthz'),
  chat:         (body) => request(API_BASES.vlm, '/v1/vlm/chat/completions',
                   { method: 'POST', body: JSON.stringify(body) }),
  chatStream:   (body) => chatCompletionStream(API_BASES.vlm, '/v1/vlm/chat/completions', body),
  registerModel:   (body) => request(API_BASES.vlm, '/v1/vlm/models/register',
                     { method: 'POST', body: JSON.stringify(body) }),
  deregisterModel: (model) => request(API_BASES.vlm, '/v1/vlm/models/deregister',
                     { method: 'POST', body: JSON.stringify({ model }) }),
  loadModel:       (model, extra_args = []) => request(API_BASES.vlm, '/v1/vlm/models/load',
                     { method: 'POST', body: JSON.stringify({ model, extra_args }) }),
  unloadModel:     (model) => request(API_BASES.vlm, '/v1/vlm/models/unload',
                     { method: 'POST', body: JSON.stringify({ model }) }),
  switchModel:     (model) => request(API_BASES.vlm, '/v1/vlm/models/switch',
                     { method: 'POST', body: JSON.stringify({ model }) }),
  startDownload:   (model) => request(API_BASES.vlm, '/v1/vlm/models/' + encodeURIComponent(model) + '/download',
                     { method: 'POST' }),
  getDownload:     (model) => request(API_BASES.vlm, '/v1/vlm/models/' + encodeURIComponent(model) + '/download'),
  cancelDownload:  (model) => request(API_BASES.vlm, '/v1/vlm/models/' + encodeURIComponent(model) + '/download',
                     { method: 'DELETE' }),
};
