// YOLO 视觉检测试用页
const { useState: useStateY, useRef: useRefY, useEffect: useEffectY } = React;

function YoloTryPage({ model, onBack }) {
  const { Icon, visionApi, t } = window;
  const [imgUrl, setImgUrl] = useStateY(null);
  const [imgFile, setImgFile] = useStateY(null);
  const [detections, setDetections] = useStateY([]);
  const [loading, setLoading] = useStateY(false);
  const [threshold, setThreshold] = useStateY(0.5);
  const [error, setError] = useStateY('');
  const imgRef = useRefY(null);
  const [imgSize, setImgSize] = useStateY({ w: 1, h: 1, renderedW: 1, renderedH: 1 });
  const [loadError, setLoadError] = useStateY('');
  const [modelReady, setModelReady] = useStateY(model.status === 'ready');
  const backendModelId = window.visionBackendModelId ? window.visionBackendModelId(model.id) : model.id;

  useEffectY(() => {
    const s = window.pageStateStore?.load('yolo', model.id);
    if (s?.detections) setDetections(s.detections);
    if (s?.threshold != null) setThreshold(s.threshold);
  }, [model.id]);

  useEffectY(() => {
    if (detections.length === 0) return;
    window.pageStateStore?.save('yolo', model.id, { detections, threshold });
  }, [detections, threshold, model.id]);

  useEffectY(() => {
    const unloadOthers = async () => {
      const modelsResp = await visionApi.listModels();
      const loaded = (modelsResp.data || modelsResp || []).filter(m => m.status === 'ready' && m.model_id !== backendModelId);
      for (const m of loaded) await visionApi.unloadModel(m.model_id).catch(() => {});
    };

    const loadCurrentModel = async () => {
      setLoadError(t('模型加载中…'));
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

    if (model.status !== 'ready') {
      loadCurrentModel();
    } else {
      visionApi.switchModel(backendModelId).catch(() => {});
    }
  }, []);

  const onFile = (e) => {
    const f = e.target.files[0]; if (!f) return;
    setImgFile(f); setImgUrl(URL.createObjectURL(f));
    setDetections([]); setError('');
  };

  const onImgLoad = (e) => {
    const el = e.target;
    setImgSize({
      w: el.naturalWidth, h: el.naturalHeight,
      renderedW: el.clientWidth, renderedH: el.clientHeight,
    });
  };

  const detect = async () => {
    if (!imgFile) return;
    setLoading(true); setError('');
    try {
      const res = await visionApi.inference(imgFile, ['detect'], model.id);
      const dets = (res.results && res.results.detect) || res.detections || res.results || [];
      const mapped = Array.isArray(dets) ? dets.map(d => ({
        label: d.label != null ? String(d.label) : 'object',
        score: d.score,
        bbox: d.bbox || [d.x1, d.y1, d.x2, d.y2],
      })) : [];
      setDetections(mapped);
    } catch (e) {
      setError(e.message);
      // Mock 兜底 —— 展示 UI 效果
      setDetections([
        { label: 'person',  score: 0.94, bbox: [120, 80, 320, 420] },
        { label: 'laptop',  score: 0.82, bbox: [360, 220, 620, 380] },
        { label: 'cup',     score: 0.71, bbox: [650, 260, 740, 360] },
        { label: 'chair',   score: 0.63, bbox: [70,  300, 200, 560] },
      ]);
    }
    setLoading(false);
  };

  const colors = ['#b9f332', '#32d3f3', '#f3a732', '#f332a7', '#a732f3'];

  return (
    <div className="main-inner">
      <div className="back-link" onClick={onBack}>
        {Icon.arrowLeft({ size: 14 })}<span>{t('返回模型选择')}</span>
      </div>
      <div className="page-header">
        <div>
          <div className="page-title">{model.name}</div>
          <div className="page-sub">YOLO · {model.id} · POST /v1/vision/inference</div>
        </div>
        {loadError && <span className="chip" style={{ color: 'var(--warn)' }}>{loadError}</span>}
        {!loadError && modelReady && <span className="chip chip-accent">{t('模型就绪')}</span>}
      </div>

      <div className="try-layout">
        <div className="try-main">
          <div className="section-label">{t('图片输入')}</div>
          <div style={{
            background: 'var(--bg-1)', border: '1px dashed var(--border-2)',
            borderRadius: 10, padding: 16, minHeight: 420,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            position: 'relative', overflow: 'hidden',
          }}>
            {!imgUrl ? (
              <label style={{ textAlign: 'center', cursor: 'pointer', color: 'var(--text-dim)' }}>
                <input type="file" accept="image/*" onChange={onFile} style={{ display: 'none' }}/>
                <div style={{ fontSize: 48, color: 'var(--text-low)' }}>{Icon.upload({ size: 48, strokeWidth: 1 })}</div>
                <div style={{ marginTop: 12, fontSize: 13 }}>{t('点击上传图片或拖拽至此')}</div>
                <div className="text-xs text-mono mt-2" style={{ color: 'var(--text-low)' }}>JPG / PNG / WebP · 最大 10MB</div>
              </label>
            ) : (
              <div style={{ position: 'relative', display: 'inline-block' }}>
                <img ref={imgRef} src={imgUrl} onLoad={onImgLoad}
                  style={{ maxWidth: '100%', maxHeight: 560, display: 'block', borderRadius: 6 }}/>
                {detections.filter(d => (d.score ?? 1) >= threshold).map((d, i) => {
                  const [x1, y1, x2, y2] = d.bbox;
                  const sx = imgSize.renderedW / imgSize.w;
                  const sy = imgSize.renderedH / imgSize.h;
                  const c = colors[i % colors.length];
                  return (
                    <div key={i} style={{
                      position: 'absolute',
                      left: x1 * sx, top: y1 * sy,
                      width: (x2 - x1) * sx, height: (y2 - y1) * sy,
                      border: `2px solid ${c}`,
                      boxShadow: `0 0 0 1px rgba(0,0,0,0.3)`,
                      pointerEvents: 'none',
                    }}>
                      <div style={{
                        position: 'absolute', top: -22, left: -2,
                        background: c, color: '#0a0a0b',
                        padding: '2px 6px', fontSize: 11, fontFamily: 'var(--font-mono)',
                        fontWeight: 600, borderRadius: '3px 3px 0 0',
                        whiteSpace: 'nowrap',
                      }}>{d.label} {((d.score ?? 1) * 100).toFixed(0)}%</div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          <div className="flex gap-3 mt-4">
            {imgUrl && (
              <>
                <button className="btn-primary" disabled={loading || !modelReady} onClick={detect}>
                  {loading ? t('检测中…') : !modelReady ? t('模型加载中…') : t('开始检测')}
                </button>
                <label className="btn-ghost" style={{ cursor: 'pointer' }}>
                  <input type="file" accept="image/*" onChange={onFile} style={{ display: 'none' }}/>
                  {t('更换图片')}
                </label>
              </>
            )}
          </div>

          {error && <div className="mt-4 text-mono text-xs" style={{ color: 'var(--warn)' }}>
            ⚠ 后端请求失败：{error} · 已显示 mock 检测结果
          </div>}

          {detections.length > 0 && (
            <>
              <div className="section-label mt-6">{t('检测结果')} · {detections.length} {t('个目标')}</div>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
                {detections.map((d, i) => (
                  <div key={i} className="chip" style={{
                    borderColor: colors[i % colors.length],
                    color: colors[i % colors.length],
                  }}>
                    {d.label} · {((d.score ?? 1) * 100).toFixed(1)}%
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <div className="try-side">
          <div>
            <div className="section-label">{t('检测参数')}</div>
            <div className="tweak-row">
              <label className="tweak-label">{t('置信度阈值')} · <span className="text-mono">{threshold.toFixed(2)}</span></label>
              <input type="range" className="slider" min="0" max="1" step="0.05"
                value={threshold} onChange={e => setThreshold(+e.target.value)}/>
            </div>
            <div className="tweak-row">
              <label className="tweak-label">NMS IoU</label>
              <input type="range" className="slider" min="0" max="1" step="0.05" defaultValue="0.45"/>
            </div>
          </div>
          <div>
            <div className="section-label">API 端点</div>
            <code style={{
              display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11,
              background: 'var(--bg-1)', padding: 10, borderRadius: 6,
              color: 'var(--text-dim)', border: '1px solid var(--border)',
            }}>
              POST /v1/vision/inference<br/>
              &nbsp;&nbsp;tasks=['detect']
            </code>
          </div>
        </div>
      </div>
      <window.ResourceBar/>
    </div>
  );
}

window.YoloTryPage = YoloTryPage;
