// 统一 Vision 试用页 —— 根据 model.capabilities 自动选择渲染器
const { useState: useStateV, useRef: useRefV, useEffect: useEffectV } = React;

const COCO_SKELETON = [
  [0,1],[0,2],[1,3],[2,4],
  [5,6],[5,11],[6,12],[11,12],
  [5,7],[7,9],[6,8],[8,10],
  [11,13],[13,15],[12,14],[14,16],
  [5,0],[6,0],
];
const LIMB_COLORS = [
  '#ff6b6b','#ff6b6b','#ff6b6b','#ff6b6b',
  '#ffd93d','#ffd93d','#ffd93d','#ffd93d',
  '#6bcb77','#6bcb77','#4d96ff','#4d96ff',
  '#ff922b','#ff922b','#cc5de8','#cc5de8',
  '#ffd93d','#ffd93d',
];
const KP_COLORS = [
  '#ff6b6b','#ff6b6b','#ff6b6b','#ff6b6b','#ff6b6b',
  '#6bcb77','#4d96ff','#6bcb77','#4d96ff','#6bcb77','#4d96ff',
  '#ff922b','#cc5de8','#ff922b','#cc5de8','#ff922b','#cc5de8',
];
const EMOTION_COLORS = {
  happy:'#ffd93d', sad:'#4d96ff', angry:'#ff6b6b', surprise:'#ff922b',
  fear:'#cc5de8', disgust:'#6bcb77', neutral:'#8a8e95',
};
const DET_COLORS = ['#b9f332','#32d3f3','#f3a732','#f332a7','#a732f3'];

const CAP_LABEL = {
  detect:'目标检测', pose:'姿态估计', segment:'实例分割',
  classify:'图像分类', emotion:'情绪识别', embedding:'人脸识别',
  track:'目标跟踪',
};

function detectionList(value) {
  if (!value) return [];
  if (Array.isArray(value)) return value;
  if (Array.isArray(value.items)) return value.items;
  if (Array.isArray(value.results)) return value.results;
  if (Array.isArray(value.data)) return value.data;
  if (Array.isArray(value.detections)) return value.detections;
  if (Array.isArray(value.boxes)) return value.boxes;
  return [];
}

function pickDetections(results) {
  const candidates = [
    results,
    results?.detect,
    results?.detections,
    results?.det,
    results?.boxes,
    results?.objects,
    results?.results?.detect,
    results?.results?.detections,
    results?.data?.results?.detect,
    results?.data?.results?.detections,
  ];
  for (const candidate of candidates) {
    const list = detectionList(candidate);
    if (list.length > 0) return list;
  }
  return [];
}

function toFiniteNumber(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : undefined;
}

function readBoxObject(box, normalized) {
  if (!box || typeof box !== 'object') return { bbox: [], normalized };
  const x1 = box.x1 ?? box.left ?? box.xmin ?? box.x;
  const y1 = box.y1 ?? box.top ?? box.ymin ?? box.y;
  let x2 = box.x2 ?? box.right ?? box.xmax;
  let y2 = box.y2 ?? box.bottom ?? box.ymax;
  const w = box.w ?? box.width;
  const h = box.h ?? box.height;
  if ((x2 == null || y2 == null) && w != null && h != null && x1 != null && y1 != null) {
    x2 = Number(x1) + Number(w);
    y2 = Number(y1) + Number(h);
  }
  return { bbox: [x1, y1, x2, y2], normalized };
}

function xywhToBBox(values, normalized) {
  if (!Array.isArray(values) || values.length < 4) return { bbox: [], normalized };
  const [x, y, w, h] = values.slice(0, 4).map(toFiniteNumber);
  if ([x, y, w, h].some(v => v == null)) return { bbox: [], normalized };
  return { bbox: [x, y, x + w, y + h], normalized };
}

function readXYWHObject(box, normalized) {
  if (!box || typeof box !== 'object') return { bbox: [], normalized };
  const x = toFiniteNumber(box.x ?? box.x1 ?? box.left ?? box.xmin);
  const y = toFiniteNumber(box.y ?? box.y1 ?? box.top ?? box.ymin);
  const w = toFiniteNumber(box.w ?? box.width);
  const h = toFiniteNumber(box.h ?? box.height);
  if ([x, y, w, h].some(v => v == null)) return { bbox: [], normalized };
  return { bbox: [x, y, x + w, y + h], normalized };
}

function hasNormalizedBoxFormat(format) {
  const text = String(format || '').toLowerCase();
  return text.includes('norm') || text.includes('relative') || text.includes('ratio') ||
    text.includes('xyxyn') || text.includes('xywhn');
}

function hasExplicitNormalizedBox(item, raw) {
  const d = item || {};
  return d.normalized === true || d.is_normalized === true || d.relative === true ||
    raw?.normalized === true || raw?.is_normalized === true || raw?.relative === true ||
    d.xyxyn != null || d.xywhn != null || d.bbox_xyxyn != null || d.bbox_xywhn != null ||
    hasNormalizedBoxFormat(d.bbox_format ?? d.box_format ?? d.format ?? raw?.bbox_format ?? raw?.box_format ?? raw?.format);
}

function normalizeBBox(item) {
  const d = item || {};
  const xywh = d.xywh ?? d.bbox_xywh ?? d.xywhn ?? d.bbox_xywhn;
  const xywhNormalized = hasExplicitNormalizedBox(d, xywh);
  if (Array.isArray(xywh)) {
    return xywhToBBox(xywh, xywhNormalized);
  }
  if (xywh && typeof xywh === 'object') {
    return readXYWHObject(xywh, xywhNormalized);
  }

  let raw = Array.isArray(d) ? d : (d.bbox ?? d.box ?? d.xyxy ?? d.xyxyn ?? d.bbox_xyxyn ?? d.rect ?? d.bounds);
  const normalized = hasExplicitNormalizedBox(d, raw);
  const boxFormat = String(d.bbox_format ?? d.box_format ?? d.format ?? raw?.bbox_format ?? raw?.box_format ?? raw?.format ?? '').toLowerCase();
  if (boxFormat.includes('xywh') && raw != null) {
    if (Array.isArray(raw)) return xywhToBBox(raw, normalized);
    if (typeof raw === 'object') return readXYWHObject(raw, normalized);
  }

  let box = [];
  if (Array.isArray(raw)) {
    box = raw.slice(0, 4);
  } else if (raw && typeof raw === 'object') {
    box = readBoxObject(raw, normalized).bbox;
  } else {
    box = [
      d.x1 ?? d.left ?? d.xmin ?? d.x,
      d.y1 ?? d.top ?? d.ymin ?? d.y,
      d.x2 ?? d.right ?? d.xmax,
      d.y2 ?? d.bottom ?? d.ymax,
    ];
  }

  let [x1, y1, x2, y2] = box.map(toFiniteNumber);
  const w = toFiniteNumber(d.w ?? d.width ?? raw?.w ?? raw?.width);
  const h = toFiniteNumber(d.h ?? d.height ?? raw?.h ?? raw?.height);
  if ((x2 == null || y2 == null) && x1 != null && y1 != null && w != null && h != null) {
    x2 = x1 + w;
    y2 = y1 + h;
  } else if (x1 != null && y1 != null && x2 != null && y2 != null && (x2 < x1 || y2 < y1)) {
    return { bbox: [], normalized };
  }

  return { bbox: [x1, y1, x2, y2], normalized };
}

function normalizeDetection(item) {
  const d = item || {};
  const { bbox, normalized } = normalizeBBox(d);
  if (bbox.length !== 4 || bbox.some(v => !Number.isFinite(v))) return null;

  const rawScore = Array.isArray(d)
    ? toFiniteNumber(d[4])
    : toFiniteNumber(d.score ?? d.confidence ?? d.conf ?? d.prob);
  const score = rawScore == null ? 1 : (rawScore > 1 && rawScore <= 100 ? rawScore / 100 : rawScore);
  const label = Array.isArray(d)
    ? (d[5] ?? 'object')
    : (d.label_name ?? d.class_name ?? d.name ?? d.label ?? d.class_id ?? d.class_idx ?? 'object');
  const rawTrackId = d.track_id ?? d.trackId ?? d.id ?? -1;
  const trackId = Number(rawTrackId);

  return {
    label: String(label),
    score,
    bbox,
    bboxNormalized: normalized,
    x1: bbox[0],
    y1: bbox[1],
    x2: bbox[2],
    y2: bbox[3],
    track_id: Number.isFinite(trackId) ? trackId : -1,
  };
}

function renderBoxForSize(detection, sourceSize, renderedSize) {
  const bbox = detection?.bbox || [];
  const [x1, y1, x2, y2] = bbox.map(Number);
  if (![x1, y1, x2, y2].every(Number.isFinite)) return null;
  if (!renderedSize?.w || !renderedSize?.h) return null;
  if (detection.bboxNormalized) {
    return [x1 * renderedSize.w, y1 * renderedSize.h, x2 * renderedSize.w, y2 * renderedSize.h];
  }
  if (!sourceSize?.w || !sourceSize?.h) return null;
  const sx = renderedSize.w / sourceSize.w;
  const sy = renderedSize.h / sourceSize.h;
  return [x1 * sx, y1 * sy, x2 * sx, y2 * sy];
}

function VisionTryPage({ model, onBack: _onBack }) {
  const { Icon, visionApi, t } = window;
  const caps = model.capabilities || [];
  const hasDetect = caps.includes('detect');
  const hasPose = caps.includes('pose');
  const hasSegment = caps.includes('segment');
  const hasClassify = caps.includes('classify');
  const hasEmotion = caps.includes('emotion');
  const hasEmbedding = caps.includes('embedding');
  const hasTrack = caps.includes('track');
  const isArcface = hasEmbedding;

  const [imgUrl, setImgUrl] = useStateV(null);
  const [imgFile, setImgFile] = useStateV(null);
  const [imgUrlB, setImgUrlB] = useStateV(null);
  const [imgFileB, setImgFileB] = useStateV(null);
  const [imgSize, setImgSize] = useStateV({ w: 0, h: 0, renderedW: 0, renderedH: 0 });
  const [loading, setLoading] = useStateV(false);
  const [error, setError] = useStateV('');
  const [loadError, setLoadError] = useStateV('');
  const [modelReady, setModelReady] = useStateV(model.status === 'ready');
  const [threshold, setThreshold] = useStateV(0.25);
  const [iou, setIou] = useStateV(0.45);
  const [results, setResults] = useStateV(null);
  const [similarity, setSimilarity] = useStateV(null);
  const [timing, setTiming] = useStateV(null);
  const imgRef = useRefV(null);

  // Camera mode state
  const [mode, setMode] = useStateV('image');
  const [camActive, setCamActive] = useStateV(false);
  const [camError, setCamError] = useStateV('');
  const [streamFps, setStreamFps] = useStateV(0);
  const [streamDetections, setStreamDetections] = useStateV([]);
  const [streamPose, setStreamPose] = useStateV(null);
  const [streamEmotion, setStreamEmotion] = useStateV(null);
  const [streamClassify, setStreamClassify] = useStateV(null);
  const [streamTiming, setStreamTiming] = useStateV(null);
  const [fpsLimit, setFpsLimit] = useStateV(15);
  const videoRef = useRefV(null);
  const canvasRef = useRefV(null);
  const wsRef = useRefV(null);
  const frameLoopRef = useRefV(null);
  const heartbeatRef = useRefV(null);
  const fpsCounterRef = useRefV({ count: 0, lastTime: 0 });

  const subtitle = caps.map(c => CAP_LABEL[c] || c).join(' + ') || 'Vision';
  const apiEndpoint = isArcface ? '/v1/vision/feature' : '/v1/vision/inference';
  const backendModelId = window.visionBackendModelId ? window.visionBackendModelId(model.id) : model.id;

  useEffectV(() => {
    const unloadOthers = async () => {
      const modelsResp = await visionApi.listModels();
      const loaded = (modelsResp.data || modelsResp || []).filter(m => m.status === 'ready' && m.model_id !== backendModelId);
      for (const m of loaded) await visionApi.unloadModel(m.model_id).catch(() => {});
    };

    const syncServerParams = async () => {
      try {
        const p = await visionApi.getParams();
        if (!p) return;
        if (p.conf != null) setThreshold(+p.conf);
        if (p.iou != null) setIou(+p.iou);
      } catch {}
    };

    const loadCurrentModel = async () => {
      setLoadError(t('模型加载中…'));
      // 先卸载其他已加载的模型，释放 AI cores
      await unloadOthers();
      try {
        const res = await visionApi.loadModel(backendModelId);
        if (res && res.loaded === false) {
          const reason = (res.engine_state && res.engine_state.error_message) || t('后端加载失败');
          setLoadError(t('模型加载失败') + ': ' + reason);
          return;
        }
        await visionApi.switchModel(backendModelId);
        setLoadError(''); setModelReady(true);
      } catch (e) {
        if (e.message && e.message.includes('409')) {
          await visionApi.switchModel(backendModelId).catch(() => {});
          setLoadError(''); setModelReady(true);
        } else {
          setLoadError(t('模型加载失败') + ': ' + e.message);
        }
      }
    };

    syncServerParams();
    loadCurrentModel();
  }, []);

  // Cleanup camera + unload model on unmount
  useEffectV(() => {
    return () => {
      stopCamera();
      visionApi.unloadModel(backendModelId).catch(() => {});
    };
  }, []);

  // Push conf/iou updates to an active stream so camera mode reacts live
  useEffectV(() => {
    const ws = wsRef.current;
    if (!camActive || !ws || ws.readyState !== 1) return;
    if (!(hasDetect || hasPose || hasSegment || hasTrack)) return;
    try {
      ws.send(JSON.stringify({ signal: 'update_params', conf: threshold, iou }));
    } catch {}
  }, [threshold, iou, camActive]);

  const stopCamera = () => {
    if (frameLoopRef.current) { cancelAnimationFrame(frameLoopRef.current); frameLoopRef.current = null; }
    if (heartbeatRef.current) { clearInterval(heartbeatRef.current); heartbeatRef.current = null; }
    if (wsRef.current) {
      try { wsRef.current.send(JSON.stringify({ signal: 'end' })); } catch {}
      wsRef.current.close();
      wsRef.current = null;
    }
    if (videoRef.current && videoRef.current.srcObject) {
      videoRef.current.srcObject.getTracks().forEach(tr => tr.stop());
      videoRef.current.srcObject = null;
    }
    setCamActive(false);
    setStreamDetections([]);
    setStreamPose(null);
    setStreamEmotion(null);
    setStreamClassify(null);
    setStreamTiming(null);
    setStreamFps(0);
  };

  const handleBack = () => {
    stopCamera();
    visionApi.unloadModel(backendModelId).catch(() => {});
    _onBack();
  };

  const startCamera = async () => {
    setCamError('');
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ video: { width: 640, height: 480 } });
      const video = videoRef.current;
      video.srcObject = stream;
      await video.play();

      const wsQs = new URLSearchParams({
        model_id: backendModelId,
        fps_limit: String(fpsLimit),
      });
      if (hasDetect || hasPose || hasSegment || hasTrack) {
        wsQs.set('conf', String(threshold));
        wsQs.set('iou', String(iou));
      }
      const wsUrl = visionApi.streamUrl() + '?' + wsQs.toString();
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setCamActive(true);
        heartbeatRef.current = setInterval(() => {
          if (ws.readyState === 1) ws.send(JSON.stringify({ signal: 'heartbeat' }));
        }, 30000);
      };

      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.event === 'ready') {
            startSendLoop(ws, video);
          } else if (msg.event === 'frame_result') {
            setStreamDetections(detectionList(msg.detections).map(normalizeDetection).filter(Boolean));
            setStreamPose(msg.pose || null);
            setStreamEmotion(msg.emotion || null);
            setStreamClassify(msg.classify || null);
            setStreamTiming(msg.timing || null);
            const fc = fpsCounterRef.current;
            fc.count++;
            const now = performance.now();
            if (now - fc.lastTime >= 1000) {
              setStreamFps(Math.round(fc.count * 1000 / (now - fc.lastTime)));
              fc.count = 0;
              fc.lastTime = now;
            }
          } else if (msg.event === 'error') {
            setCamError(msg.message || 'Stream error');
          }
        } catch {}
      };

      ws.onerror = () => {
        setCamError(t('无法连接视觉服务'));
        stopCamera();
      };

      ws.onclose = () => {
        if (frameLoopRef.current) { cancelAnimationFrame(frameLoopRef.current); frameLoopRef.current = null; }
        if (heartbeatRef.current) { clearInterval(heartbeatRef.current); heartbeatRef.current = null; }
      };
    } catch (e) {
      setCamError(t('无法访问摄像头') + ': ' + e.message);
    }
  };

  const startSendLoop = (ws, video) => {
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    const minInterval = 1000 / fpsLimit;
    let lastSendTime = 0;
    fpsCounterRef.current = { count: 0, lastTime: performance.now() };

    const loop = () => {
      frameLoopRef.current = requestAnimationFrame(loop);
      const now = performance.now();
      if (now - lastSendTime < minInterval) return;
      if (ws.readyState !== 1) return;
      lastSendTime = now;
      canvas.width = video.videoWidth;
      canvas.height = video.videoHeight;
      ctx.drawImage(video, 0, 0);
      canvas.toBlob((blob) => {
        if (blob && ws.readyState === 1) ws.send(blob);
      }, 'image/jpeg', 0.7);
    };
    frameLoopRef.current = requestAnimationFrame(loop);
  };

  const onFile = (e) => {
    const f = e.target.files[0]; if (!f) return;
    setImgFile(f); setImgUrl(URL.createObjectURL(f));
    setImgSize({ w: 0, h: 0, renderedW: 0, renderedH: 0 });
    setResults(null); setSimilarity(null); setTiming(null); setError('');
  };
  const onFileB = (e) => {
    const f = e.target.files[0]; if (!f) return;
    setImgFileB(f); setImgUrlB(URL.createObjectURL(f));
    setSimilarity(null); setTiming(null); setError('');
  };
  const onImgLoad = (e) => {
    const el = e.target;
    setImgSize({ w: el.naturalWidth, h: el.naturalHeight, renderedW: el.clientWidth, renderedH: el.clientHeight });
  };

  const runInference = async () => {
    if (!imgFile) return;
    setLoading(true); setError('');
    const _t0 = Date.now();
    try {
      if (isArcface) {
        if (imgFileB) {
          const res = await visionApi.feature(imgFile, 'similarity', model.id, imgFileB);
          setSimilarity(res.similarity);
          setTiming(res.timing || null);
          window.historyStore?.push({
            model: model.id, type: 'Vision',
            input: imgFile.name || 'image',
            output: t('相似度') + ': ' + (res.similarity * 100).toFixed(1) + '%',
            latency: Date.now() - _t0,
          });
        } else {
          const res = await visionApi.feature(imgFile, 'embedding', model.id);
          setTiming(res.timing || null);
          window.historyStore?.push({
            model: model.id, type: 'Vision',
            input: imgFile.name || 'image',
            output: t('特征提取'),
            latency: Date.now() - _t0,
          });
        }
      } else {
        const tasks = caps.filter(c => ['detect','pose','segment','classify','emotion','track'].includes(c));
        const opts = {};
        if (hasDetect || hasPose || hasSegment || hasTrack) {
          opts.conf = threshold;
          opts.iou = iou;
        }
        const res = await visionApi.inference(imgFile, tasks, model.id, opts);
        const resultPayload = res.results || res;
        setResults(resultPayload);
        setTiming(res.timing || null);
        const dets = pickDetections(resultPayload).map(normalizeDetection).filter(Boolean);
        window.historyStore?.push({
          model: model.id, type: 'Vision',
          input: imgFile.name || 'image',
          output: dets.length + ' ' + t('个目标') + ' · ' + tasks.join('+'),
          latency: Date.now() - _t0,
        });
      }
    } catch (e) {
      setError(e.message);
    }
    setLoading(false);
  };

  const detections = pickDetections(results).map(normalizeDetection).filter(Boolean);
  const poses = results?.pose || [];
  const segments = results?.segment || [];
  const classifications = results?.classify || [];
  const emotions = results?.emotion || [];
  const imageScaleReady = imgSize.w > 0 && imgSize.h > 0 && imgSize.renderedW > 0 && imgSize.renderedH > 0;

  const btnLabel = isArcface
    ? (loading ? t('推理中…') : !modelReady ? t('模型加载中…') : t('计算相似度'))
    : (loading ? t('推理中…') : !modelReady ? t('模型加载中…') : t('开始推理'));

  const renderImageUpload = () => (
    <label style={{ textAlign: 'center', cursor: 'pointer', color: 'var(--text-dim)' }}>
      <input type="file" accept="image/*" onChange={onFile} style={{ display: 'none' }}/>
      <div style={{ fontSize: 48, color: 'var(--text-low)' }}>{Icon.upload({ size: 48, strokeWidth: 1 })}</div>
      <div style={{ marginTop: 12, fontSize: 13 }}>{t('点击上传图片或拖拽至此')}</div>
      <div className="text-xs text-mono mt-2" style={{ color: 'var(--text-low)' }}>JPG / PNG / WebP</div>
    </label>
  );

  return (
    <div className="main-inner">
      <div className="back-link" onClick={handleBack}>
        {Icon.arrowLeft({ size: 14 })}<span>{t('返回模型选择')}</span>
      </div>
      <div className="page-header">
        <div>
          <div className="page-title">{model.name}</div>
          <div className="page-sub">{subtitle} · {model.id} · POST {apiEndpoint}</div>
        </div>
        {loadError && <span className="chip" style={{ color: 'var(--warn)' }}>{loadError}</span>}
        {!loadError && modelReady && <span className="chip chip-accent">{t('模型就绪')}</span>}
      </div>

      {!isArcface && (
        <div className="mode-tabs">
          <button className={`mode-tab ${mode === 'image' ? 'active' : ''}`}
            onClick={() => { setMode('image'); stopCamera(); }}>{t('图片输入')}</button>
          <button className={`mode-tab ${mode === 'camera' ? 'active' : ''}`}
            onClick={() => setMode('camera')}>{t('摄像头')}</button>
        </div>
      )}

      <div className="try-layout">
        <div className="try-main">
          {mode === 'camera' && !isArcface ? (
            <>
              <div className="section-label">{t('实时检测')}</div>
              <div className="camera-container">
                <video ref={videoRef} autoPlay muted playsInline className="camera-video"/>
                <canvas ref={canvasRef} style={{ display: 'none' }}/>
                {/* Detection bounding boxes */}
                {camActive && (hasDetect || hasTrack) && streamDetections.filter(d => (d.score ?? 1) >= threshold).map((d, i) => {
                  const video = videoRef.current;
                  if (!video || !video.videoWidth) return null;
                  const box = renderBoxForSize(
                    d,
                    { w: video.videoWidth, h: video.videoHeight },
                    { w: video.clientWidth, h: video.clientHeight },
                  );
                  if (!box) return null;
                  const [x1, y1, x2, y2] = box;
                  const ci = hasTrack && d.track_id >= 0 ? d.track_id : i;
                  const c = DET_COLORS[ci % DET_COLORS.length];
                  const labelText = d.label || 'object';
                  const lbl = hasTrack && d.track_id >= 0
                    ? `#${d.track_id} ${labelText} ${((d.score ?? 1) * 100).toFixed(0)}%`
                    : `${labelText} ${((d.score ?? 1) * 100).toFixed(0)}%`;
                  return (
                    <div key={'det-'+i} style={{
                      position: 'absolute', left: x1, top: y1,
                      width: x2 - x1, height: y2 - y1,
                      border: `2px solid ${c}`, boxShadow: '0 0 0 1px rgba(0,0,0,0.3)',
                      pointerEvents: 'none',
                    }}>
                      <div style={{
                        position: 'absolute', top: -22, left: -2,
                        background: c, color: '#0a0a0b',
                        padding: '2px 6px', fontSize: 11, fontFamily: 'var(--font-mono)',
                        fontWeight: 600, borderRadius: '3px 3px 0 0', whiteSpace: 'nowrap',
                      }}>{lbl}</div>
                    </div>
                  );
                })}
                {/* Pose skeleton overlay */}
                {camActive && hasPose && streamPose && (() => {
                  const video = videoRef.current;
                  if (!video || !video.videoWidth) return null;
                  const sx = video.clientWidth / video.videoWidth;
                  const sy = video.clientHeight / video.videoHeight;
                  return (
                    <svg style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}>
                      {streamPose.map((p, pi) => {
                        const kps = p.keypoints || [];
                        return (
                          <g key={'pose-'+pi}>
                            {COCO_SKELETON.map(([a, b], li) => {
                              const ka = kps[a], kb = kps[b];
                              if (!ka || !kb || ka.visibility < 0.3 || kb.visibility < 0.3) return null;
                              return <line key={li} x1={ka.x*sx} y1={ka.y*sy} x2={kb.x*sx} y2={kb.y*sy}
                                stroke={LIMB_COLORS[li % LIMB_COLORS.length]} strokeWidth={2} opacity={0.85}/>;
                            })}
                            {kps.map((kp, ki) => kp.visibility >= 0.3 ? (
                              <circle key={ki} cx={kp.x*sx} cy={kp.y*sy} r={3}
                                fill={KP_COLORS[ki % KP_COLORS.length]} stroke="#000" strokeWidth={0.5}/>
                            ) : null)}
                          </g>
                        );
                      })}
                    </svg>
                  );
                })()}
                {/* Emotion labels overlay */}
                {camActive && hasEmotion && streamEmotion && (() => {
                  const video = videoRef.current;
                  if (!video || !video.videoWidth) return null;
                  return streamEmotion.map((em, ei) => {
                    const det = streamDetections[ei];
                    const box = det ? renderBoxForSize(
                      det,
                      { w: video.videoWidth, h: video.videoHeight },
                      { w: video.clientWidth, h: video.clientHeight },
                    ) : null;
                    const x = box ? box[0] : 10;
                    const y = box ? box[3] + 4 : 30 + ei * 28;
                    const c = EMOTION_COLORS[em.label] || '#8a8e95';
                    return (
                      <div key={'emo-'+ei} style={{
                        position: 'absolute', left: x, top: y,
                        background: c, color: '#0a0a0b',
                        padding: '2px 8px', fontSize: 11, fontFamily: 'var(--font-mono)',
                        fontWeight: 600, borderRadius: 3, whiteSpace: 'nowrap', pointerEvents: 'none',
                      }}>{em.label} {(em.score * 100).toFixed(0)}%</div>
                    );
                  });
                })()}
                {/* Classify label overlay */}
                {camActive && hasClassify && streamClassify && streamClassify.length > 0 && (
                  <div style={{
                    position: 'absolute', top: 8, left: 8,
                    background: 'rgba(0,0,0,0.7)', color: '#fff',
                    padding: '4px 10px', fontSize: 13, fontFamily: 'var(--font-mono)',
                    fontWeight: 600, borderRadius: 4, pointerEvents: 'none',
                  }}>
                    {(streamClassify[0].label_name || streamClassify[0].label)} {(streamClassify[0].score * 100).toFixed(0)}%
                  </div>
                )}
              </div>

              {camError && (
                <div className="mt-4 text-mono text-xs" style={{ color: 'var(--danger)' }}>{camError}</div>
              )}

              <div className="camera-controls mt-4">
                {!camActive ? (
                  <button className="btn-primary" disabled={!modelReady} onClick={startCamera}>
                    {t('开启摄像头')}
                  </button>
                ) : (
                  <button className="btn-ghost" onClick={stopCamera}>{t('关闭摄像头')}</button>
                )}
                <select className="select" value={fpsLimit}
                  onChange={e => setFpsLimit(+e.target.value)}
                  style={{ width: 90, padding: '6px 8px', fontSize: 12 }}>
                  {[5, 10, 15, 30].map(v => <option key={v} value={v}>{v} FPS</option>)}
                </select>
              </div>

              {camActive && (
                <div className="timing-bar mt-4">
                  <div className="timing-item">
                    <span className="timing-label">FPS</span>
                    <span className="timing-value">{streamFps}</span>
                  </div>
                  <div className="timing-item">
                    <span className="timing-label">{t('检测结果')}</span>
                    <span className="timing-value">
                      {streamDetections.filter(d => (d.score ?? 1) >= threshold).length} {t('个检测')}
                      {streamPose ? ` · ${streamPose.length} pose` : ''}
                      {streamEmotion ? ` · ${streamEmotion.map(e => e.label).join(', ')}` : ''}
                    </span>
                  </div>
                  {streamTiming && (streamTiming.detect_ms != null || streamTiming.infer_ms != null) && (
                    <div className="timing-item">
                      <span className="timing-label">{t('推理')}</span>
                      <span className="timing-value">{(streamTiming.detect_ms ?? streamTiming.infer_ms ?? 0).toFixed(1)} ms</span>
                    </div>
                  )}
                </div>
              )}
            </>
          ) : (
          <>
          <div className="section-label">{t('图片输入')}</div>

          {isArcface ? (
            <div className="arcface-layout">
              <div className="arcface-img-zone">
                <div className="section-label" style={{ marginBottom: 8 }}>{t('图片 A')}</div>
                {!imgUrl ? (
                  <label style={{ textAlign: 'center', cursor: 'pointer', color: 'var(--text-dim)' }}>
                    <input type="file" accept="image/*" onChange={onFile} style={{ display: 'none' }}/>
                    <div style={{ color: 'var(--text-low)' }}>{Icon.upload({ size: 36, strokeWidth: 1 })}</div>
                    <div style={{ marginTop: 8, fontSize: 12 }}>{t('点击上传图片或拖拽至此')}</div>
                  </label>
                ) : (
                  <img src={imgUrl} style={{ maxWidth: '100%', maxHeight: 300, borderRadius: 6 }}/>
                )}
              </div>
              <div className="arcface-img-zone">
                <div className="section-label" style={{ marginBottom: 8 }}>{t('图片 B')}</div>
                {!imgUrlB ? (
                  <label style={{ textAlign: 'center', cursor: 'pointer', color: 'var(--text-dim)' }}>
                    <input type="file" accept="image/*" onChange={onFileB} style={{ display: 'none' }}/>
                    <div style={{ color: 'var(--text-low)' }}>{Icon.upload({ size: 36, strokeWidth: 1 })}</div>
                    <div style={{ marginTop: 8, fontSize: 12 }}>{t('点击上传图片或拖拽至此')}</div>
                  </label>
                ) : (
                  <img src={imgUrlB} style={{ maxWidth: '100%', maxHeight: 300, borderRadius: 6 }}/>
                )}
              </div>
            </div>
          ) : (
            <div style={{
              background: 'var(--bg-1)', border: '1px dashed var(--border-2)',
              borderRadius: 10, padding: 16, minHeight: 420,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              position: 'relative', overflow: 'hidden',
            }}>
              {!imgUrl ? renderImageUpload() : (
                <div style={{ position: 'relative', display: 'inline-block' }}>
                  <img ref={imgRef} src={imgUrl} onLoad={onImgLoad}
                    style={{ maxWidth: '100%', maxHeight: 560, display: 'block', borderRadius: 6 }}/>

                  {/* Detection overlay */}
                  {hasDetect && imageScaleReady && detections.filter(d => (d.score ?? 1) >= threshold).map((d, i) => {
                    const box = renderBoxForSize(
                      d,
                      { w: imgSize.w, h: imgSize.h },
                      { w: imgSize.renderedW, h: imgSize.renderedH },
                    );
                    if (!box) return null;
                    const [x1, y1, x2, y2] = box;
                    const ci = hasTrack && d.track_id >= 0 ? d.track_id : i;
                    const c = DET_COLORS[ci % DET_COLORS.length];
                    const lbl = hasTrack && d.track_id >= 0
                      ? `#${d.track_id} ${d.label} ${((d.score ?? 1) * 100).toFixed(0)}%`
                      : `${d.label} ${((d.score ?? 1) * 100).toFixed(0)}%`;
                    return (
                      <div key={i} style={{
                        position: 'absolute', left: x1, top: y1,
                        width: x2 - x1, height: y2 - y1,
                        border: `2px solid ${c}`, boxShadow: '0 0 0 1px rgba(0,0,0,0.3)',
                        pointerEvents: 'none',
                      }}>
                        <div style={{
                          position: 'absolute', top: -22, left: -2,
                          background: c, color: '#0a0a0b',
                          padding: '2px 6px', fontSize: 11, fontFamily: 'var(--font-mono)',
                          fontWeight: 600, borderRadius: '3px 3px 0 0', whiteSpace: 'nowrap',
                        }}>{lbl}</div>
                      </div>
                    );
                  })}

                  {/* Pose overlay */}
                  {hasPose && imageScaleReady && poses.length > 0 && (
                    <svg style={{
                      position: 'absolute', top: 0, left: 0,
                      width: imgSize.renderedW, height: imgSize.renderedH,
                      pointerEvents: 'none',
                    }}>
                      {poses.map((pose, pi) => {
                        const kps = pose.keypoints || [];
                        const sx = imgSize.renderedW / imgSize.w;
                        const sy = imgSize.renderedH / imgSize.h;
                        return (
                          <g key={pi}>
                            {COCO_SKELETON.map(([a, b], li) => {
                              const ka = kps[a], kb = kps[b];
                              if (!ka || !kb || ka.visibility < 0.3 || kb.visibility < 0.3) return null;
                              return <line key={li}
                                x1={ka.x * sx} y1={ka.y * sy} x2={kb.x * sx} y2={kb.y * sy}
                                stroke={LIMB_COLORS[li] || '#fff'} strokeWidth={2.5}
                                strokeLinecap="round" opacity={0.85}/>;
                            })}
                            {kps.map((kp, ki) => {
                              if (kp.visibility < 0.3) return null;
                              return <circle key={ki}
                                cx={kp.x * sx} cy={kp.y * sy} r={4}
                                fill={KP_COLORS[ki] || '#fff'} stroke="#000" strokeWidth={1}/>;
                            })}
                          </g>
                        );
                      })}
                    </svg>
                  )}

                  {/* Segment overlay */}
                  {hasSegment && imageScaleReady && segments.length > 0 && (
                    <svg style={{
                      position: 'absolute', top: 0, left: 0,
                      width: imgSize.renderedW, height: imgSize.renderedH,
                      pointerEvents: 'none',
                    }}>
                      {segments.filter(s => (s.score ?? 1) >= threshold).map((seg, si) => {
                        const sx = imgSize.renderedW / imgSize.w;
                        const sy = imgSize.renderedH / imgSize.h;
                        const c = DET_COLORS[si % DET_COLORS.length];
                        const polys = seg.contour || [];
                        return (
                          <g key={si}>
                            {polys.map((poly, pi) => {
                              if (!Array.isArray(poly) || poly.length < 3) return null;
                              const points = poly.map(pt => `${pt[0] * sx},${pt[1] * sy}`).join(' ');
                              return <polygon key={pi} points={points}
                                fill={c} fillOpacity={0.35}
                                stroke={c} strokeWidth={2} strokeOpacity={0.9}/>;
                            })}
                          </g>
                        );
                      })}
                    </svg>
                  )}

                  {/* Classify overlay on image */}
                  {hasClassify && !hasEmotion && classifications.length > 0 && (
                    <div style={{
                      position: 'absolute', top: 12, left: 12,
                      background: 'rgba(0,0,0,0.75)', borderRadius: 8, padding: '8px 12px',
                      pointerEvents: 'none', maxWidth: '60%',
                    }}>
                      {classifications.slice(0, 5).map((c, i) => (
                        <div key={i} style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          fontSize: 12, fontFamily: 'var(--font-mono)', color: '#fff',
                          marginBottom: i < 4 ? 4 : 0,
                        }}>
                          <span style={{ color: DET_COLORS[i % DET_COLORS.length], fontWeight: 700, minWidth: 24 }}>#{i + 1}</span>
                          <span style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                            {c.label_name || ('Class ' + c.label)}
                          </span>
                          <span style={{ color: 'rgba(255,255,255,0.7)' }}>{(c.score * 100).toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Emotion overlay on image */}
                  {hasEmotion && emotions.length > 0 && (
                    <div style={{
                      position: 'absolute', top: 12, left: 12,
                      background: 'rgba(0,0,0,0.75)', borderRadius: 8, padding: '8px 12px',
                      pointerEvents: 'none', maxWidth: '60%',
                    }}>
                      {emotions.map((em, i) => (
                        <div key={i} style={{
                          display: 'flex', alignItems: 'center', gap: 8,
                          fontSize: 12, fontFamily: 'var(--font-mono)', color: '#fff',
                          marginBottom: i < emotions.length - 1 ? 4 : 0,
                        }}>
                          <span style={{
                            width: 8, height: 8, borderRadius: '50%', flexShrink: 0,
                            background: EMOTION_COLORS[em.label] || '#8a8e95',
                          }}/>
                          <span style={{ flex: 1 }}>{em.label}</span>
                          <span style={{ color: 'rgba(255,255,255,0.7)' }}>{(em.score * 100).toFixed(1)}%</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          )}

          {/* Action buttons */}
          <div className="flex gap-3 mt-4">
            {(imgUrl || (isArcface && imgUrl)) && (
              <>
                <button className="btn-primary" disabled={loading || !modelReady} onClick={runInference}>
                  {btnLabel}
                </button>
                <label className="btn-ghost" style={{ cursor: 'pointer' }}>
                  <input type="file" accept="image/*" onChange={onFile} style={{ display: 'none' }}/>
                  {t('更换图片')}
                </label>
              </>
            )}
          </div>

          {error && <div style={{
            marginTop: 16, padding: '10px 14px', borderRadius: 8, fontSize: 12,
            fontFamily: 'var(--font-mono)', color: 'var(--danger)',
            background: 'oklch(0.70 0.18 25 / .08)', border: '1px solid oklch(0.70 0.18 25 / .25)',
          }}>⚠ {error}</div>}

          {/* Detection chips */}
          {hasDetect && detections.length > 0 && (
            <>
              <div className="section-label mt-6">{t('检测结果')} · {detections.filter(d => (d.score ?? 1) >= threshold).length} {t('个目标')}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {detections.filter(d => (d.score ?? 1) >= threshold).map((d, i) => {
                  const ci = hasTrack && d.track_id >= 0 ? d.track_id : i;
                  return (
                    <div key={i} className="chip" style={{
                      borderColor: DET_COLORS[ci % DET_COLORS.length],
                      color: DET_COLORS[ci % DET_COLORS.length],
                    }}>
                      {hasTrack && d.track_id >= 0 ? `#${d.track_id} ` : ''}{d.label} · {((d.score ?? 1) * 100).toFixed(1)}%
                    </div>
                  );
                })}
              </div>
            </>
          )}

          {/* Segment cards */}
          {hasSegment && segments.length > 0 && (
            <>
              <div className="section-label mt-6">{t('分割结果')} · {segments.length} {t('个实例')}</div>
              <div className="seg-card-list">
                {segments.map((seg, i) => (
                  <div key={i} className="seg-card">
                    <div className="seg-card-header">
                      <span className="seg-card-class">{seg.label_name || `Class ${seg.class_id}`}</span>
                      <span className="seg-card-score">{(seg.score * 100).toFixed(1)}%</span>
                    </div>
                    <div className="seg-card-body">
                      <div className="meta-row">
                        <span className="meta-key">{t('面积')}</span>
                        <span className="meta-val">{(seg.area * 100).toFixed(2)}%</span>
                      </div>
                      {seg.mask && <div className="meta-row">
                        <span className="meta-key">{t('掩码尺寸')}</span>
                        <span className="meta-val">{seg.mask.shape?.join(' × ')}</span>
                      </div>}
                      {seg.mask && <div className="meta-row">
                        <span className="meta-key">{t('非零像素')}</span>
                        <span className="meta-val">{seg.mask.nonzero?.toLocaleString()}</span>
                      </div>}
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Classify bars */}
          {hasClassify && !hasEmotion && classifications.length > 0 && (
            <>
              <div className="section-label mt-6">{t('分类结果')}</div>
              <div className="classify-bars">
                {classifications.slice(0, 5).map((c, i) => (
                  <div key={i} className="classify-bar-row">
                    <div className="classify-bar-label">
                      <span className="classify-rank">#{i + 1}</span>
                      <span>{c.label_name || ('Class ' + c.label)}</span>
                    </div>
                    <div className="classify-bar-track">
                      <div className="classify-bar-fill" style={{ width: (c.score * 100) + '%' }}/>
                    </div>
                    <span className="classify-bar-pct">{(c.score * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Emotion bars */}
          {hasEmotion && emotions.length > 0 && (
            <>
              <div className="section-label mt-6">{t('情绪识别')}</div>
              <div className="classify-bars">
                {emotions.map((em, i) => (
                  <div key={i} className="classify-bar-row">
                    <div className="classify-bar-label">
                      <span>{em.label}</span>
                    </div>
                    <div className="classify-bar-track">
                      <div className="classify-bar-fill" style={{
                        width: (em.score * 100) + '%',
                        background: EMOTION_COLORS[em.label] || 'var(--accent)',
                      }}/>
                    </div>
                    <span className="classify-bar-pct">{(em.score * 100).toFixed(1)}%</span>
                  </div>
                ))}
              </div>
            </>
          )}

          {/* Arcface similarity */}
          {isArcface && similarity != null && (
            <div className="arcface-result">
              <div className="arcface-score">{(similarity * 100).toFixed(1)}%</div>
              <div className="arcface-verdict">
                {similarity >= 0.6 ? t('同一人') : t('不同人')}
              </div>
              <div className="classify-bar-track" style={{ maxWidth: 300, margin: '0 auto' }}>
                <div className="classify-bar-fill" style={{
                  width: (similarity * 100) + '%',
                  background: similarity >= 0.6 ? 'var(--accent)' : 'var(--danger, #ff6b6b)',
                }}/>
              </div>
            </div>
          )}

          {/* Timing */}
          {timing && (
            <div className="timing-bar mt-4">
              {timing.preprocess_ms != null && <div className="timing-item">
                <span className="timing-label">{t('预处理')}</span>
                <span className="timing-value">{timing.preprocess_ms.toFixed(1)} ms</span>
              </div>}
              {(timing.model_infer_ms ?? timing.infer_ms) != null && <div className="timing-item">
                <span className="timing-label">{t('推理')}</span>
                <span className="timing-value">{(timing.model_infer_ms ?? timing.infer_ms).toFixed(1)} ms</span>
              </div>}
              {timing.postprocess_ms != null && <div className="timing-item">
                <span className="timing-label">{t('后处理')}</span>
                <span className="timing-value">{timing.postprocess_ms.toFixed(1)} ms</span>
              </div>}
              {timing.infer_ms != null && timing.model_infer_ms != null && <div className="timing-item">
                <span className="timing-label">{t('总计')}</span>
                <span className="timing-value">{timing.infer_ms.toFixed(1)} ms</span>
              </div>}
            </div>
          )}
          </>
          )}
        </div>

        <div className="try-side">
          {hasDetect && (
            <div>
              <div className="section-label">{t('检测参数')}</div>
              <div className="tweak-row">
                <label className="tweak-label">{t('置信度阈值')} · <span className="text-mono">{threshold.toFixed(2)}</span></label>
                <input type="range" className="slider" min="0" max="1" step="0.05"
                  value={threshold} onChange={e => setThreshold(+e.target.value)}/>
              </div>
              <div className="tweak-row">
                <label className="tweak-label">NMS IoU · <span className="text-mono">{iou.toFixed(2)}</span></label>
                <input type="range" className="slider" min="0" max="1" step="0.05"
                  value={iou} onChange={e => setIou(+e.target.value)}/>
              </div>
            </div>
          )}
          <div>
            <div className="section-label">API {t('端点')}</div>
            <code style={{
              display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11,
              background: 'var(--bg-1)', padding: 10, borderRadius: 6,
              color: 'var(--text-dim)', border: '1px solid var(--border)',
            }}>
              {mode === 'camera' ? (
                <>WS {visionApi.streamUrl().replace(/^ws/, 'ws')}<br/>&nbsp;&nbsp;model_id={backendModelId}</>
              ) : (
                <>POST {apiEndpoint}<br/>
                {isArcface
                  ? <>&nbsp;&nbsp;type='similarity'</>
                  : <>&nbsp;&nbsp;tasks={JSON.stringify(caps.filter(c => c !== 'vlm'))}</>}
                </>
              )}
            </code>
          </div>
        </div>
      </div>
      <window.ResourceBar/>
    </div>
  );
}

window.VisionTryPage = VisionTryPage;
