// LLM 模型管理页
const { useState: useStateLM, useEffect: useEffectLM, useRef: useRefLM } = React;

const _CAT_RULES = [
  [/hy-mt/i, 'translate'],
  [/deepseek-r1|smallthinker/i, 'reasoning'],
  [/embed|bge|gte/i, 'embedding'],
  [/code|starcoder|codellama/i, 'code'],
];
function _inferCat(id) {
  for (const [re, cat] of _CAT_RULES) if (re.test(id)) return cat;
  return 'chat';
}
const _STATUS_ORDER = { loaded: 0, loading: 1, downloading: 2, downloaded: 3, error: 4, available: 5 };
const _CAT_COLORS = {
  chat: 'oklch(0.82 0.18 135 / .14)', translate: 'oklch(0.72 0.14 230 / .18)',
  reasoning: 'oklch(0.72 0.14 300 / .18)', embedding: 'oklch(0.72 0.14 190 / .18)',
  code: 'oklch(0.78 0.14 80 / .18)',
};
const _CAT_TEXT = {
  chat: 'var(--accent)', translate: 'oklch(0.72 0.14 230)',
  reasoning: 'oklch(0.72 0.14 300)', embedding: 'oklch(0.72 0.14 190)',
  code: 'oklch(0.78 0.14 80)',
};

function LLMManagePage() {
  const { Icon, llmApi, t } = window;
  const [models, setModels] = useStateLM([]);
  const [search, setSearch] = useStateLM('');
  const [filterCat, setFilterCat] = useStateLM('all');
  const [healthInfo, setHealthInfo] = useStateLM({ status: 'unknown', model: '' });
  const [loading, setLoading] = useStateLM(false);
  const [showRegister, setShowRegister] = useStateLM(false);
  const [flash, setFlash] = useStateLM(null);
  const pollRef = useRefLM(null);

  const showFlash = (msg, type = 'ok') => {
    setFlash({ msg, type });
    setTimeout(() => setFlash(null), 3000);
  };

  const refresh = async () => {
    try {
      const [list, h] = await Promise.all([
        llmApi.listModels().catch(() => []),
        llmApi.health().catch(() => ({ status: 'unknown', model: '' })),
      ]);
      setModels(Array.isArray(list) ? list : []);
      setHealthInfo(h || { status: 'unknown', model: '' });
    } catch (e) {
      console.warn('[llm-manage] refresh failed:', e);
    }
  };

  useEffectLM(() => { refresh(); }, []);

  // Download progress polling
  useEffectLM(() => {
    const downloading = models.filter(m => m.status === 'downloading');
    if (downloading.length === 0) {
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = setInterval(async () => {
      let changed = false;
      for (const m of downloading) {
        try {
          const prog = await llmApi.getDownload(m.id);
          if (prog && typeof prog.progress === 'number') {
            m.download_progress = prog.progress;
            changed = true;
            if (prog.status && prog.status !== 'downloading') changed = true;
          }
        } catch {}
      }
      if (changed) {
        setModels(prev => [...prev]);
        const anyDone = downloading.some(m => m.download_progress >= 1 || m.status !== 'downloading');
        if (anyDone) refresh();
      }
    }, 2000);
    return () => { if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; } };
  }, [models.filter(m => m.status === 'downloading').length]);

  const handleDownload = async (m) => {
    setLoading(true);
    try {
      await llmApi.startDownload(m.id);
      showFlash(m.id + ' downloading...');
      await refresh();
    } catch (e) { showFlash(e.message, 'err'); }
    setLoading(false);
  };

  const handleCancelDownload = async (m) => {
    setLoading(true);
    try {
      await llmApi.cancelDownload(m.id);
      await refresh();
    } catch (e) { showFlash(e.message, 'err'); }
    setLoading(false);
  };

  const handleLoad = async (m) => {
    setLoading(true);
    try {
      await llmApi.loadModel(m.id);
      showFlash(m.id + ' loaded');
      await refresh();
    } catch (e) { showFlash(e.message, 'err'); }
    setLoading(false);
  };

  const handleUnload = async (m) => {
    setLoading(true);
    try {
      await llmApi.unloadModel(m.id);
      showFlash(m.id + ' unloaded');
      await refresh();
    } catch (e) { showFlash(e.message, 'err'); }
    setLoading(false);
  };

  const handleSwitch = async (m) => {
    setLoading(true);
    try {
      await llmApi.switchModel(m.id);
      showFlash(m.id + ' set as default');
      await refresh();
    } catch (e) { showFlash(e.message, 'err'); }
    setLoading(false);
  };

  const handleDeregister = async (m) => {
    if (!confirm(t('确认注销') + ': ' + m.id + '?')) return;
    setLoading(true);
    try {
      await llmApi.deregisterModel(m.id);
      showFlash(m.id + ' deregistered');
      await refresh();
    } catch (e) { showFlash(e.message, 'err'); }
    setLoading(false);
  };

  const statusLabel = (s) => {
    const map = {
      available: t('可用'), downloading: t('下载中'), downloaded: t('已下载'),
      loading: t('加载中…'), loaded: t('已加载'), error: t('错误'),
    };
    return map[s] || s;
  };

  const statusColor = (s) => {
    if (s === 'loaded') return 'var(--accent)';
    if (s === 'error') return 'var(--danger)';
    if (s === 'downloading' || s === 'loading') return 'var(--info, #5bc0de)';
    return 'var(--text-low)';
  };

  const currentModel = healthInfo.model || '';
  const isRunning = healthInfo.status === 'ok';

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('LLM 模型管理')}</div>
          <div className="page-sub">
            {models.length} {t('模型')} ·{' '}
            {isRunning
              ? <span style={{ color: 'var(--accent)' }}>{t('当前模型')}: {currentModel}</span>
              : <span className="text-dim">{t('无模型运行')}</span>
            }
          </div>
        </div>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={() => setShowRegister(!showRegister)}>
            {showRegister ? t('取消') : t('注册模型')}
          </button>
          <button className="btn-ghost" onClick={refresh} title={t('刷新')}>{Icon.refresh({ size: 14 })}</button>
        </div>
      </div>

      {flash && (
        <div style={{
          padding: '8px 14px', borderRadius: 6, fontSize: 12, marginBottom: 12,
          background: flash.type === 'err' ? 'oklch(0.70 0.18 25 / .1)' : 'oklch(0.82 0.18 135 / .1)',
          color: flash.type === 'err' ? 'var(--danger)' : 'var(--accent)',
          border: '1px solid ' + (flash.type === 'err' ? 'oklch(0.70 0.18 25 / .2)' : 'oklch(0.82 0.18 135 / .2)'),
        }}>{flash.msg}</div>
      )}

      {showRegister && (
        <RegisterModelDialog
          onDone={() => { setShowRegister(false); refresh(); }}
          onCancel={() => setShowRegister(false)}
        />
      )}

      {(() => {
        const cats = ['all', 'chat', 'translate', 'reasoning', 'embedding', 'code'];
        const catLabels = { all: t('全部'), chat: t('对话'), translate: t('翻译'), reasoning: t('推理'), embedding: t('嵌入'), code: t('代码') };
        const catCounts = {};
        models.forEach(m => { const c = _inferCat(m.id); catCounts[c] = (catCounts[c] || 0) + 1; });
        catCounts.all = models.length;

        const filtered = models
          .filter(m => !search || m.id.toLowerCase().includes(search.toLowerCase()))
          .filter(m => filterCat === 'all' || _inferCat(m.id) === filterCat)
          .sort((a, b) => (_STATUS_ORDER[a.status] ?? 9) - (_STATUS_ORDER[b.status] ?? 9));

        return <>
          <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16, flexWrap: 'wrap' }}>
            <input className="input" placeholder={t('搜索模型…')} value={search}
              onChange={e => setSearch(e.target.value)}
              style={{ flex: '0 0 220px', fontSize: 12, fontFamily: 'var(--font-mono)' }}/>
            <div className="category-tabs" style={{ flex: 1 }}>
              {cats.filter(c => c === 'all' || catCounts[c]).map(c => (
                <button key={c} className={`category-tab ${filterCat === c ? 'active' : ''}`}
                  onClick={() => setFilterCat(c)}>
                  {catLabels[c]}{catCounts[c] ? <span className="tab-count">{catCounts[c]}</span> : null}
                </button>
              ))}
            </div>
          </div>

          <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
            <table className="dm-table">
              <thead>
                <tr>
                  <th>{t('模型')}</th>
                  <th>{t('来源')}</th>
                  <th>{t('状态')}</th>
                  <th>{t('进度')}</th>
                  <th style={{ textAlign: 'right' }}>{t('操作')}</th>
                  <th style={{ textAlign: 'right' }}>{t('类型')}</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map(m => {
                  const cat = _inferCat(m.id);
                  return (
                    <tr key={m.id}>
                      <td>
                        <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6, paddingLeft: 6 }}>
                          {m.id}
                          {currentModel === m.id && <span className="badge-default">{t('默认')}</span>}
                          {!!m.is_preset && <span className="chip" style={{ fontSize: 9, padding: '1px 5px' }}>{t('预设')}</span>}
                        </div>
                        <div className="text-mono text-xs text-dim" style={{ marginTop: 2, paddingLeft: 6 }}>
                          {m.source_type === 'remote' ? (m.api_base_url || '-') : (m.url || m.local_path || '-')}
                        </div>
                      </td>
                      <td><span className="chip">{m.source_type || '-'}</span></td>
                      <td>
                        <span className="chip" style={m.status === 'loaded' ? { background: 'oklch(0.82 0.18 135 / .14)', color: 'var(--accent)' } : {}}>
                          <span className="status-dot" style={{
                            background: statusColor(m.status),
                            animation: (m.status === 'downloading' || m.status === 'loading') ? 'pulse 1.5s infinite' : 'none',
                          }}/>
                          {statusLabel(m.status)}
                        </span>
                      </td>
                      <td>
                        {m.status === 'downloading' ? (
                          <div className="progress-cell">
                            <div className="progress"><div className="progress-bar" style={{ width: ((m.download_progress || 0) * 100) + '%' }}/></div>
                            <span>{((m.download_progress || 0) * 100).toFixed(0)}%</span>
                          </div>
                        ) : <span className="text-dim">-</span>}
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <div className="flex gap-2" style={{ justifyContent: 'flex-end' }}>
                          {m.status === 'available' && (
                            <button className="btn-ghost" disabled={loading} onClick={() => handleDownload(m)}>
                              {t('开始下载')}
                            </button>
                          )}
                          {m.status === 'downloading' && (
                            <button className="btn-ghost" disabled={loading} onClick={() => handleCancelDownload(m)}>
                              {t('取消下载')}
                            </button>
                          )}
                          {m.status === 'downloaded' && (
                            <button className="btn-ghost" disabled={loading} onClick={() => handleLoad(m)}>
                              {t('加载')}
                            </button>
                          )}
                          {m.status === 'loading' && (
                            <button className="btn-ghost" disabled>{t('加载中…')}</button>
                          )}
                          {m.status === 'loaded' && (
                            <>
                              {currentModel !== m.id && (
                                <button className="btn-ghost" disabled={loading} onClick={() => handleSwitch(m)}
                                  style={{ fontSize: 11, padding: '4px 10px' }}>{t('设为默认')}</button>
                              )}
                              <button className="btn-ghost" disabled={loading} onClick={() => handleUnload(m)}>
                                {t('卸载')}
                              </button>
                            </>
                          )}
                          {m.status === 'error' && (
                            <button className="btn-ghost" disabled={loading} onClick={() => handleDownload(m)}>
                              {t('重试')}
                            </button>
                          )}
                          {!m.is_preset && (
                            <button className="btn-danger" disabled={loading} onClick={() => handleDeregister(m)}>
                              {t('注销')}
                            </button>
                          )}
                        </div>
                      </td>
                      <td style={{ textAlign: 'right' }}>
                        <span className="chip" style={{ background: _CAT_COLORS[cat], color: _CAT_TEXT[cat], fontSize: 10 }}>
                          {catLabels[cat]}
                        </span>
                      </td>
                    </tr>
                  );
                })}
                {filtered.length === 0 && (
                  <tr><td colSpan={6} className="text-dim" style={{ textAlign: 'center', padding: 32 }}>
                    {models.length === 0 ? t('加载中…') : t('无匹配模型')}
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </>;
      })()}
    </div>
  );
}

function RegisterModelDialog({ onDone, onCancel }) {
  const { t, llmApi } = window;
  const [sourceType, setSourceType] = useStateLM('local_url');
  const [modelId, setModelId] = useStateLM('');
  const [url, setUrl] = useStateLM('');
  const [localPath, setLocalPath] = useStateLM('');
  const [apiBaseUrl, setApiBaseUrl] = useStateLM('');
  const [apiKey, setApiKey] = useStateLM('');
  const [submitting, setSubmitting] = useStateLM(false);
  const [error, setError] = useStateLM('');

  const submit = async () => {
    setError('');
    const body = { source_type: sourceType };
    if (modelId.trim()) body.model = modelId.trim();
    if (sourceType === 'remote') {
      if (!apiBaseUrl.trim()) { setError('API base URL is required'); return; }
      body.api_base_url = apiBaseUrl.trim();
      if (apiKey.trim()) body.api_key = apiKey.trim();
    } else if (sourceType === 'local_url') {
      if (!url.trim()) { setError('URL is required'); return; }
      body.url = url.trim();
    } else if (sourceType === 'local_path') {
      if (!localPath.trim()) { setError('Local path is required'); return; }
      body.local_path = localPath.trim();
    }
    setSubmitting(true);
    try {
      await llmApi.registerModel(body);
      onDone();
    } catch (e) {
      setError(e.message);
    }
    setSubmitting(false);
  };

  return (
    <div style={{
      background: 'var(--bg-2)', border: '1px solid var(--border)',
      borderRadius: 'var(--radius)', padding: 20, marginBottom: 16,
    }}>
      <div className="section-label">{t('注册模型')}</div>

      <div className="tweak-row" style={{ marginBottom: 12 }}>
        <label className="tweak-label">{t('来源类型')}</label>
        <div className="tweak-options">
          {[['local_url', t('下载URL')], ['local_path', t('本地路径')], ['remote', t('远程API')]].map(([k, v]) => (
            <button key={k} className={`tweak-option ${sourceType === k ? 'active' : ''}`}
              onClick={() => setSourceType(k)}>{v}</button>
          ))}
        </div>
      </div>

      <div style={{ display: 'grid', gap: 10, marginBottom: 14 }}>
        <div>
          <label className="text-xs text-dim" style={{ display: 'block', marginBottom: 4 }}>{t('模型ID')} ({t('可选')})</label>
          <input className="input" placeholder="auto-generated if empty" value={modelId}
            onChange={e => setModelId(e.target.value)} style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}/>
        </div>
        {sourceType === 'remote' && (
          <>
            <div>
              <label className="text-xs text-dim" style={{ display: 'block', marginBottom: 4 }}>{t('API 地址')}</label>
              <input className="input" placeholder="https://api.openai.com/v1" value={apiBaseUrl}
                onChange={e => setApiBaseUrl(e.target.value)} style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}/>
            </div>
            <div>
              <label className="text-xs text-dim" style={{ display: 'block', marginBottom: 4 }}>{t('API 密钥')} ({t('可选')})</label>
              <input className="input" type="password" placeholder="sk-..." value={apiKey}
                onChange={e => setApiKey(e.target.value)} style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}/>
            </div>
          </>
        )}
        {sourceType === 'local_url' && (
          <div>
            <label className="text-xs text-dim" style={{ display: 'block', marginBottom: 4 }}>{t('下载URL')}</label>
            <input className="input" placeholder="https://example.com/model.gguf" value={url}
              onChange={e => setUrl(e.target.value)} style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}/>
          </div>
        )}
        {sourceType === 'local_path' && (
          <div>
            <label className="text-xs text-dim" style={{ display: 'block', marginBottom: 4 }}>{t('本地路径')}</label>
            <input className="input" placeholder="/path/to/model.gguf" value={localPath}
              onChange={e => setLocalPath(e.target.value)} style={{ fontFamily: 'var(--font-mono)', fontSize: 12 }}/>
          </div>
        )}
      </div>

      {error && <div style={{ color: 'var(--danger)', fontSize: 12, marginBottom: 10 }}>{error}</div>}

      <div className="flex gap-2">
        <button className="btn-primary" disabled={submitting} onClick={submit}>
          {submitting ? t('加载中…') : t('注册')}
        </button>
        <button className="btn-ghost" onClick={onCancel}>{t('取消')}</button>
      </div>
    </div>
  );
}

window.LLMManagePage = LLMManagePage;
