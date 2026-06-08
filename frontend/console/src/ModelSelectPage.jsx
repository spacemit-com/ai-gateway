// 模型选择页 —— 对标参考图
const { useState: useStateM, useRef: useRefM, useEffect: useEffectM } = React;

const _MS_CAT_RULES = [
  [/hy-mt/i, 'translate'],
  [/deepseek-r1|smallthinker/i, 'reasoning'],
  [/embed|bge|gte/i, 'embedding'],
  [/code|starcoder|codellama/i, 'code'],
];
function _msInferCat(id) {
  for (const [re, cat] of _MS_CAT_RULES) if (re.test(id)) return cat;
  return 'chat';
}
function _msInferVlmCat(m) {
  const id = (m.id || '').toLowerCase();
  if (m.source_type === 'remote') return 'remote';
  if (/fastvlm/.test(id)) return 'fastvlm';
  if (/qwen/.test(id)) return 'qwen';
  return 'local';
}
const _MS_CAT_COLORS = {
  chat: 'oklch(0.82 0.18 135 / .14)', translate: 'oklch(0.72 0.14 230 / .18)',
  reasoning: 'oklch(0.72 0.14 300 / .18)', embedding: 'oklch(0.72 0.14 190 / .18)',
  code: 'oklch(0.78 0.14 80 / .18)', qwen: 'oklch(0.72 0.14 230 / .18)',
  fastvlm: 'oklch(0.78 0.14 80 / .18)', remote: 'oklch(0.72 0.14 300 / .18)',
  local: 'oklch(0.72 0.14 190 / .18)',
};
const _MS_CAT_TEXT = {
  chat: 'var(--accent)', translate: 'oklch(0.72 0.14 230)',
  reasoning: 'oklch(0.72 0.14 300)', embedding: 'oklch(0.72 0.14 190)',
  code: 'oklch(0.78 0.14 80)', qwen: 'oklch(0.72 0.14 230)',
  fastvlm: 'oklch(0.78 0.14 80)', remote: 'oklch(0.72 0.14 300)',
  local: 'oklch(0.72 0.14 190)',
};

function modelActionFor(model, t) {
  const rawStatus = String(model.rawStatus || '').toLowerCase();
  const canDownload = model.domain === 'llm' || model.domain === 'vlm';
  if (rawStatus === 'downloading') return { kind: 'none', label: t('下载中…'), disabled: true };
  if (rawStatus === 'loading') return { kind: 'none', label: t('加载中…'), disabled: true };
  if (canDownload &&
      rawStatus !== 'downloaded' && rawStatus !== 'unloaded' &&
      rawStatus !== 'loaded' && rawStatus !== 'ready' &&
      model.status !== 'ready' && model.source_type !== 'remote') {
    if (rawStatus === 'error') return { kind: 'download', label: t('重试下载') };
    return { kind: 'download', label: t('下载模型') };
  }
  return { kind: 'load', label: t('加载模型') };
}

function apiForModel(model) {
  const { asrApi, ttsApi, vadApi, visionApi, llmApi, vlmApi } = window;
  if (model.domain === 'asr') return asrApi;
  if (model.domain === 'tts') return ttsApi;
  if (model.domain === 'vad') return vadApi;
  if (model.domain === 'vision' || model.domain === 'yolo') return visionApi;
  if (model.domain === 'llm') return llmApi;
  if (model.domain === 'vlm') return vlmApi;
  return null;
}

async function loadModelForEntry(model) {
  const api = apiForModel(model);
  if (!api?.loadModel) return;
  const rawStatus = String(model.rawStatus || '').toLowerCase();
  const alreadyLoaded = model.status === 'ready' || rawStatus === 'loaded' || rawStatus === 'ready';
  if (!alreadyLoaded) {
    try {
      await api.loadModel(model.id);
    } catch (e) {
      if (!/409|already/i.test(e.message || '')) throw e;
    }
  }
  if (api.switchModel) {
    await api.switchModel(model.id).catch(() => {});
  }
}

function compactCardMeta(metaRows) {
  const seen = new Set();
  const rows = [];
  for (const row of metaRows || []) {
    if (!Array.isArray(row)) continue;
    const key = String(row[0] ?? '').trim();
    if (!key) continue;
    const normalizedKey = key.toLowerCase();
    if (seen.has(normalizedKey)) continue;
    seen.add(normalizedKey);
    rows.push([key, row[1] ?? '-']);
    if (rows.length >= 4) break;
  }
  return rows;
}

function ModelSelectPage({ setPage, initialCategory }) {
  const { Icon, t } = window;
  const [category, setCategory] = useStateM(initialCategory || 'text');
  const [search, setSearch] = useStateM('');
  const [subCat, setSubCat] = useStateM('all');
  const [catalog, setCatalog] = useStateM(() => window.MODEL_CATALOG);

  useEffectM(() => {
    const handler = () => setCatalog({ ...window.MODEL_CATALOG });
    window.addEventListener('model-catalog-updated', handler);
    return () => window.removeEventListener('model-catalog-updated', handler);
  }, []);

  const refreshCatalog = async () => {
    if (!window.initModelCatalog) return;
    await window.initModelCatalog();
    setCatalog({ ...window.MODEL_CATALOG });
  };

  const hasPendingCatalogModels = Object.values(catalog || {}).some(models =>
    (models || []).some(m => ['downloading', 'loading'].includes(String(m.rawStatus || '').toLowerCase()))
  );

  useEffectM(() => {
    if (!hasPendingCatalogModels || !window.initModelCatalog) return undefined;
    let cancelled = false;
    const refreshPending = async () => {
      try {
        await window.initModelCatalog();
        if (!cancelled) setCatalog({ ...window.MODEL_CATALOG });
      } catch {}
    };
    refreshPending();
    const timer = setInterval(refreshPending, 2000);
    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [hasPendingCatalogModels]);

  const switchCategory = (k) => { setCategory(k); setSubCat('all'); setSearch(''); };

  const categoryLabels = { text: t('语言模型'), voice: t('语音模型'), vision: t('视觉模型'), vlm: t('VLM 模型') };
  const categoryIcons = { text: 'grid', voice: 'mic', vision: 'eye', vlm: 'image' };

  const allModels = catalog[category] || [];
  const subCatLabels = category === 'text'
    ? { all: t('全部'), chat: t('对话'), translate: t('翻译'), reasoning: t('推理'), embedding: t('嵌入'), code: t('代码') }
    : category === 'vlm'
      ? { all: t('全部'), qwen: 'Qwen', fastvlm: 'FastVLM', remote: t('远程API'), local: t('本地模型') }
      : null;
  const inferSubCat = (m) => category === 'vlm' ? _msInferVlmCat(m) : _msInferCat(m.id);

  const subCatCounts = {};
  if (subCatLabels) {
    allModels.forEach(m => { const c = inferSubCat(m); subCatCounts[c] = (subCatCounts[c] || 0) + 1; });
    subCatCounts.all = allModels.length;
  }

  const _MS_STATUS_ORDER = { ready: 0, idle: 1, offline: 2 };
  let models = allModels;
  if (search) {
    const q = search.toLowerCase();
    models = models.filter(m => m.id.toLowerCase().includes(q) || (m.name && m.name.toLowerCase().includes(q)));
  }
  if (subCat !== 'all' && subCatLabels) {
    models = models.filter(m => inferSubCat(m) === subCat);
  }
  models = [...models].sort((a, b) => (_MS_STATUS_ORDER[a.status] ?? 9) - (_MS_STATUS_ORDER[b.status] ?? 9));

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('模型选择')}</div>
          <div className="page-sub">SPACEMIT-AI-PROVIDER · {models.length} MODELS</div>
        </div>
      </div>

      <div className="category-tabs">
        {Object.entries(categoryLabels).map(([k, v]) => (
          <button key={k}
            className={`category-tab ${category === k ? 'active' : ''}`}
            onClick={() => switchCategory(k)}>
            {Icon[categoryIcons[k]]({ size: 14 })}
            <span>{v}</span>
            <span className="tab-count">{(catalog[k] || []).length}</span>
          </button>
        ))}
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
        <input className="input" placeholder={t('搜索模型…')} value={search}
          onChange={e => setSearch(e.target.value)}
          style={{ flex: '0 0 220px', fontSize: 12, fontFamily: 'var(--font-mono)' }}/>
        {subCatLabels && (
          <div className="category-tabs" style={{ flex: 1, marginBottom: 0, borderBottom: 'none', paddingBottom: 0 }}>
            {Object.entries(subCatLabels).filter(([c]) => c === 'all' || subCatCounts[c]).map(([c, label]) => (
              <button key={c} className={`category-tab ${subCat === c ? 'active' : ''}`}
                onClick={() => setSubCat(c)}>
                {label}{subCatCounts[c] ? <span className="tab-count">{subCatCounts[c]}</span> : null}
              </button>
            ))}
          </div>
        )}
      </div>

      <div className="card-grid">
        {models.map(m => {
          const cat = subCatLabels ? inferSubCat(m) : null;
          return <ModelCard key={m.domain + '-' + m.id} model={m}
            catLabel={cat && subCatLabels ? subCatLabels[cat] : null}
            catColor={cat ? _MS_CAT_COLORS[cat] : null}
            catTextColor={cat ? _MS_CAT_TEXT[cat] : null}
            onRefresh={refreshCatalog}
            onEnter={(loadedModel) => setPage({ name: 'try', model: loadedModel, category })}/>;
        })}
        {models.length === 0 && (
          <div className="text-dim" style={{ textAlign: 'center', padding: 32, gridColumn: '1 / -1' }}>
            {allModels.length === 0 ? t('加载中…') : t('无匹配模型')}
          </div>
        )}
      </div>
    </div>
  );
}

function ModelCard({ model, onEnter, onRefresh, catLabel, catColor, catTextColor }) {
  const { Icon, llmApi, vlmApi, t } = window;
  const cardRef = useRefM(null);
  const [actionBusy, setActionBusy] = useStateM(false);
  const [actionError, setActionError] = useStateM('');
  const action = modelActionFor(model, t);
  const metaRows = compactCardMeta(model.meta);

  const onMove = (e) => {
    if (!cardRef.current) return;
    const r = cardRef.current.getBoundingClientRect();
    cardRef.current.style.setProperty('--mx', `${e.clientX - r.left}px`);
    cardRef.current.style.setProperty('--my', `${e.clientY - r.top}px`);
  };

  const runAction = async () => {
    if (action.disabled || actionBusy) return;
    setActionBusy(true);
    setActionError('');
    try {
      if (action.kind === 'download') {
        const api = model.domain === 'vlm' ? vlmApi : llmApi;
        await api.startDownload(model.id);
        await onRefresh?.().catch(() => {});
        return;
      }
      await loadModelForEntry(model);
      const loadedModel = { ...model, status: 'ready', rawStatus: 'loaded' };
      await onRefresh?.().catch(() => {});
      onEnter(loadedModel);
    } catch (e) {
      setActionError(e.message || t('模型操作失败'));
    } finally {
      setActionBusy(false);
    }
  };

  const actionLabel = actionBusy
    ? (action.kind === 'download' ? t('下载中…') : t('加载中…'))
    : action.label;

  return (
    <div className="model-card" ref={cardRef} onMouseMove={onMove}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div className={`card-status status-${model.status}`}>
          <span className="status-dot"/>
          <span>{model.status === 'ready' ? t('就绪') : model.status === 'idle' ? t('空闲') : t('离线状态')}</span>
        </div>
        {catLabel && (
          <span className="chip" style={{ background: catColor, color: catTextColor, fontSize: 10 }}>
            {catLabel}
          </span>
        )}
      </div>
      <div className="card-icon">{Icon[model.icon]({ size: 18 })}</div>
      <div>
        <div className="card-title">{model.name}</div>
      </div>
      <div className="card-desc">{model.desc}</div>
      <div className="meta-list">
        {metaRows.map(([k, v], i) => (
          <div key={i} className="meta-row">
            <span className="meta-key">{k}</span>
            <span className="meta-val">{v}</span>
          </div>
        ))}
      </div>
      <button className="btn-card" disabled={actionBusy || action.disabled} onClick={runAction}>{actionLabel}</button>
      {actionError && (
        <div className="text-xs text-mono mt-2" style={{ color: 'var(--danger)' }}>{actionError}</div>
      )}
    </div>
  );
}

window.ModelSelectPage = ModelSelectPage;
