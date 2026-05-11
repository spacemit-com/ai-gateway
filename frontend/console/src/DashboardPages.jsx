// 仪表盘 + 模型管理 + 历史记录 + 设置
const { useState: useStateD, useEffect: useEffectD } = React;

function DashboardPage() {
  const { asrApi, ttsApi, vadApi, visionApi, t } = window;
  const [s, setS] = useStateD({
    rtf: 0, asr_requests: 0, tts_requests: 0, vad_requests: 0,
    asr_errors: 0, tts_errors: 0, vad_errors: 0,
    uptime: 0, latency_avg: 0,
    vision_fps: 0, vision_infer_ms: 0, vision_queue: 0,
  });
  const [health, setHealth] = useStateD([]);

  useEffectD(() => {
    const poll = async () => {
      const [asr, tts, vad, vis] = await Promise.all([
        asrApi.stats().catch(() => ({})),
        ttsApi.stats().catch(() => ({})),
        vadApi.stats().catch(() => ({})),
        visionApi.stats().catch(() => ({})),
      ]);
      setS({
        rtf: asr.rtf_avg || 0,
        asr_requests: asr.total_requests || 0,
        tts_requests: tts.total_requests || 0,
        vad_requests: vad.total_requests || 0,
        asr_errors: asr.total_errors || 0,
        tts_errors: tts.total_errors || 0,
        vad_errors: vad.total_errors || 0,
        uptime: asr.uptime_s || tts.uptime_s || 0,
        latency_avg: vad.latency_ms_avg || 0,
        vision_fps: vis.fps || 0,
        vision_infer_ms: vis.infer_ms || 0,
        vision_queue: vis.queue || 0,
      });
    };
    poll();
    const id = setInterval(poll, 3000);
    return () => clearInterval(id);
  }, []);

  useEffectD(() => {
    const pollHealth = async () => {
      const results = await Promise.all([
        asrApi.health().then(r => ({ name: 'ASR', path: '/v1/asr/healthz', port: '18790', ...r })).catch(() => ({ name: 'ASR', path: '/v1/asr/healthz', port: '18790', ready: false })),
        ttsApi.health().then(r => ({ name: 'TTS', path: '/v1/tts/healthz', port: '18790', ...r })).catch(() => ({ name: 'TTS', path: '/v1/tts/healthz', port: '18790', ready: false })),
        vadApi.health().then(r => ({ name: 'VAD', path: '/v1/vad/healthz', port: '18790', ...r })).catch(() => ({ name: 'VAD', path: '/v1/vad/healthz', port: '18790', ready: false })),
        visionApi.health().then(r => ({ name: 'Vision', path: '/v1/vision/healthz', port: '18790', ready: !!r.readiness, backend: r.status || '-' })).catch(() => ({ name: 'Vision', path: '/v1/vision/healthz', port: '18790', ready: false })),
      ]);
      setHealth(results);
    };
    pollHealth();
    const id = setInterval(pollHealth, 5000);
    return () => clearInterval(id);
  }, []);

  const totalReq = s.asr_requests + s.tts_requests + s.vad_requests;
  const totalErr = s.asr_errors + s.tts_errors + s.vad_errors;

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('仪表盘')}</div>
          <div className="page-sub">{t('实时 · 语音服务')}</div>
        </div>
        <span className="chip chip-accent"><span className="status-dot" style={{ background: 'var(--accent)' }}/>{t('在线')}</span>
      </div>

      <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
        <HwStat label={t('ASR 请求')} value={s.asr_requests}/>
        <HwStat label={t('TTS 请求')} value={s.tts_requests}/>
        <HwStat label={t('VAD 请求')} value={s.vad_requests}/>
        <HwStat label={t('总请求')} value={totalReq}/>
        <HwStat label={t('总错误')} value={totalErr}/>
        <HwStat label="RTF" value={s.rtf.toFixed(3)}/>
        <HwStat label={t('VAD 延迟')} value={s.latency_avg.toFixed(1)} unit="ms"/>
        <HwStat label={t('运行时间')} value={Math.floor(s.uptime / 60)} unit="min"/>
        <HwStat label="Vision FPS" value={s.vision_fps.toFixed(1)}/>
        <HwStat label={t('Vision 推理')} value={s.vision_infer_ms.toFixed(1)} unit="ms"/>
        <HwStat label={t('Vision 队列')} value={s.vision_queue}/>
      </div>

      <EngineInfoSection/>
      <ServiceInfoSection/>

      <div style={{ marginTop: 32 }}>
        <div className="section-label">{t('服务健康')}</div>
        <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
          <table className="dm-table">
            <thead><tr><th>{t('服务')}</th><th>{t('端点')}</th><th>{t('状态')}</th><th>{t('后端')}</th><th>{t('状态码')}</th></tr></thead>
            <tbody>
              {health.map(h => (
                <tr key={h.name}>
                  <td style={{ fontWeight: 500 }}>{h.name}</td>
                  <td className="text-mono text-xs text-dim">127.0.0.1:{h.port}{h.path}</td>
                  <td>
                    <span className={`chip ${h.ready ? 'chip-accent' : ''}`}>
                      <span className="status-dot" style={{ background: h.ready ? 'var(--accent)' : 'var(--danger)' }}/>
                      {h.ready ? t('正常') : t('离线')}
                    </span>
                  </td>
                  <td className="text-mono text-xs">{h.backend || '-'}</td>
                  <td className="text-mono text-xs">{h.state || '-'}</td>
                </tr>
              ))}
              {health.length === 0 && <tr><td colSpan={5} className="text-dim">{t('加载中…')}</td></tr>}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function HwStat({ label, value, unit }) {
  return (
    <div className="stat-card">
      <div className="stat-label">{label}</div>
      <div className="stat-value">{value}{unit && <span className="unit">{unit}</span>}</div>
    </div>
  );
}

function EngineInfoSection() {
  const { asrApi, ttsApi, vadApi, visionApi, t } = window;
  const [engines, setEngines] = useStateD([]);
  const [loading, setLoading] = useStateD(true);

  useEffectD(() => {
    Promise.all([
      asrApi.getEngine().then(r => ({ domain: 'ASR', ...r })).catch(() => null),
      ttsApi.getEngine().then(r => ({ domain: 'TTS', ...r })).catch(() => null),
      vadApi.getEngine().then(r => ({ domain: 'VAD', ...r })).catch(() => null),
      visionApi.getEngine().then(r => ({ domain: 'Vision', ...r })).catch(() => null),
    ]).then(results => {
      setEngines(results.filter(Boolean));
      setLoading(false);
    });
  }, []);

  return (
    <div style={{ marginTop: 32 }}>
      <div className="section-label">{t('引擎信息')}</div>
      <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))' }}>
        {loading && <div className="text-dim text-xs" style={{ padding: 16 }}>{t('加载中…')}</div>}
        {engines.map(e => (
          <div key={e.domain} className="stat-card" style={{ padding: 16 }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className="chip chip-accent">{e.domain}</span>
              <span style={{ fontWeight: 500, fontSize: 13 }}>{e.engine || e.name || '-'}</span>
            </div>
            <div style={{ fontSize: 12, color: 'var(--text-dim)', display: 'grid', gap: 4 }}>
              {e.model && <div><span className="text-low">{t('模型')}: </span><span className="text-mono">{e.model}</span></div>}
              {e.backend && <div><span className="text-low">{t('后端')}: </span><span className="text-mono">{e.backend}</span></div>}
              {e.version && <div><span className="text-low">{t('版本')}: </span><span className="text-mono">{e.version}</span></div>}
              {e.status && <div><span className="text-low">{t('状态')}: </span><span className="text-mono">{e.status}</span></div>}
              {e.sample_rate && <div><span className="text-low">{t('采样率')}: </span><span className="text-mono">{e.sample_rate}Hz</span></div>}
            </div>
          </div>
        ))}
        {!loading && engines.length === 0 && <div className="text-dim text-xs" style={{ padding: 16 }}>无法获取引擎信息</div>}
      </div>
    </div>
  );
}

function ServiceInfoSection() {
  const { asrApi, ttsApi, vadApi, t } = window;
  const [infos, setInfos] = useStateD(null);

  useEffectD(() => {
    Promise.all([
      asrApi.info().then(r => ({ domain: 'ASR', ...r })).catch(() => null),
      ttsApi.info().then(r => ({ domain: 'TTS', ...r })).catch(() => null),
      vadApi.info().then(r => ({ domain: 'VAD', ...r })).catch(() => null),
    ]).then(results => setInfos(results.filter(Boolean)));
  }, []);

  if (!infos || infos.length === 0) return null;

  return (
    <div style={{ marginTop: 32 }}>
      <div className="section-label">{t('服务信息')}</div>
      <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))' }}>
        {infos.map(info => (
          <div key={info.domain} className="stat-card">
            <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <span className="status-dot" style={{
                background: info.initialized ? 'var(--accent)' : 'var(--text-low)',
                boxShadow: info.initialized ? '0 0 4px var(--accent)' : 'none',
              }}/>
              <span style={{ fontWeight: 600 }}>{info.domain}</span>
              <span className="text-dim text-xs">{info.initialized ? t('已初始化') : t('未初始化')}</span>
            </div>
            <div className="text-xs" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
              <div><span className="text-dim">{t('后端')}:</span> <span className="text-mono">{info.backend || '-'}</span></div>
              <div><span className="text-dim">{t('默认模型')}:</span> <span className="text-mono">{info.default_model || '-'}</span></div>
              {info.num_voices != null && (
                <div><span className="text-dim">{t('音色数')}:</span> <span className="text-mono">{info.num_voices}</span></div>
              )}
              {info.backends_loaded && (
                <div><span className="text-dim">{t('已加载后端')}:</span> <span className="text-mono">{
                  Array.isArray(info.backends_loaded) ? info.backends_loaded.join(', ') : String(info.backends_loaded)
                }</span></div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

// ---------- 历史记录 ----------
function HistoryPage() {
  const { t } = window;
  const [records, setRecords] = useStateD([]);
  const [playingId, setPlayingId] = useStateD(null);
  const audioRef = React.createRef ? React.createRef() : { current: null };

  useEffectD(() => {
    const load = () => setRecords(window.historyStore ? window.historyStore.getAll() : []);
    load();
    window.addEventListener('history-updated', load);
    return () => window.removeEventListener('history-updated', load);
  }, []);

  const playAudio = (h) => {
    if (!h.audioUrl) return;
    if (playingId === h.id) {
      setPlayingId(null);
      return;
    }
    setPlayingId(h.id);
    const a = new Audio(h.audioUrl);
    a.onended = () => setPlayingId(null);
    a.onerror = () => setPlayingId(null);
    a.play().catch(() => setPlayingId(null));
  };

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('历史记录')}</div>
          <div className="page-sub">{records.length} {t('会话')}</div>
        </div>
        {records.length > 0 && (
          <button className="btn-ghost" onClick={() => {
            if (window.historyStore) window.historyStore.clear();
            setRecords([]);
          }}>{t('清空历史')}</button>
        )}
      </div>
      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
        <table className="dm-table">
          <thead><tr><th>{t('时间')}</th><th>{t('模型')}</th><th>{t('类型')}</th><th>{t('输入')}</th><th>{t('输出')}</th><th>{t('延迟')}</th><th></th></tr></thead>
          <tbody>
            {records.length === 0 && (
              <tr><td colSpan={7} className="text-dim" style={{ textAlign: 'center', padding: 32 }}>
                暂无历史记录 — 使用模型后将自动记录
              </td></tr>
            )}
            {records.map(h => (
              <tr key={h.id}>
                <td className="text-mono text-xs text-dim">{h.time}</td>
                <td style={{ fontWeight: 500 }}>{h.model}</td>
                <td><span className="chip">{h.type}</span></td>
                <td className="text-dim">{h.input}</td>
                <td>{h.output}</td>
                <td className="text-mono text-xs">{h.latency}ms</td>
                <td>
                  {h.audioUrl && (
                    <button className="btn-ghost" style={{ padding: '2px 8px', fontSize: 11 }}
                      onClick={() => playAudio(h)}>
                      {playingId === h.id ? '⏹' : '▶'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------- 模型管理 ----------
function ManagePage() {
  const { asrApi, ttsApi, vadApi, visionApi, t } = window;
  const [items, setItems] = useStateD([]);
  const [loadingId, setLoadingId] = useStateD(null);
  const [defaults, setDefaults] = useStateD(() => {
    try { return JSON.parse(localStorage.getItem('spacemit-ai-gateway-defaults')) || { asr: null, tts: null, vad: null, vision: null }; }
    catch { return { asr: null, tts: null, vad: null, vision: null }; }
  });

  const refresh = async () => {
    try {
      const [a, t, v, vis] = await Promise.all([
        asrApi.listModels().catch(() => []),
        ttsApi.listModels().catch(() => []),
        vadApi.listModels().catch(() => []),
        visionApi.listModels().catch(() => ({ data: [] })),
      ]);

      const visionModels = vis.data || vis || [];

      // TTS: 按 id 分组，合并 sample_rates（Set 去重）
      const ttsGrouped = {};
      for (const m of t) {
        if (!ttsGrouped[m.id]) {
          ttsGrouped[m.id] = { ...m, domain: 'tts', _rates: new Set(), status: m.loaded ? 'ready' : 'idle' };
        }
        if (m.sample_rate) ttsGrouped[m.id]._rates.add(m.sample_rate);
        if (m.loaded) { ttsGrouped[m.id].loaded = true; ttsGrouped[m.id].status = 'ready'; }
      }
      for (const g of Object.values(ttsGrouped)) {
        g.sample_rates = [...g._rates];
        delete g._rates;
      }

      setItems([
        ...a.map(m => ({ ...m, domain: 'asr', status: m.loaded ? 'ready' : 'idle' })),
        ...Object.values(ttsGrouped),
        ...v.map(m => ({ ...m, domain: 'vad', status: m.loaded ? 'ready' : 'idle' })),
      ]);

      const [asrEng, ttsEng, vadEng] = await Promise.all([
        asrApi.getEngine().catch(() => ({})),
        ttsApi.getEngine().catch(() => ({})),
        vadApi.getEngine().catch(() => ({})),
      ]);
      const defs = {
        asr: asrEng.model || null,
        tts: ttsEng.model || null,
        vad: vadEng.model || null,
      };
      setDefaults(prev => {
        const merged = { ...prev };
        if (defs.asr) merged.asr = defs.asr;
        if (defs.tts) merged.tts = defs.tts;
        if (defs.vad) merged.vad = defs.vad;
        localStorage.setItem('spacemit-ai-gateway-defaults', JSON.stringify(merged));
        return merged;
      });
    } catch (e) {
      console.warn('[manage] refresh failed:', e);
    }
  };

  useEffectD(() => { refresh(); }, []);

  const toggle = async (item) => {
    const key = item.domain + '-' + item.id;
    setLoadingId(key);
    try {
      const api = { asr: asrApi, tts: ttsApi, vad: vadApi }[item.domain];
      if (!api) return;
      if (item.loaded) {
        await api.unloadModel(item.id);
      } else {
        await api.loadModel(item.id);
      }
      await refresh();
    } catch (e) {
      if (e.message && e.message.includes('409')) {
        await refresh();
      } else {
        alert('操作失败: ' + e.message);
      }
    }
    setLoadingId(null);
  };

  const switchDefault = async (item) => {
    const key = item.domain + '-' + item.id;
    setLoadingId(key);
    try {
      const api = { asr: asrApi, tts: ttsApi, vad: vadApi }[item.domain];
      if (api) await api.switchModel(item.id);
      setDefaults(prev => {
        const next = { ...prev, [item.domain]: item.id };
        localStorage.setItem('spacemit-ai-gateway-defaults', JSON.stringify(next));
        return next;
      });
    } catch (e) {
      alert('切换默认模型失败: ' + e.message);
    }
    setLoadingId(null);
  };

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('语音模型管理')}</div>
          <div className="page-sub">{items.length} {t('模型 · 加载 / 卸载')}</div>
        </div>
        <button className="btn-ghost" onClick={refresh} title={t('刷新')}>{Icon.refresh({ size: 14 })}</button>
      </div>
      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
        <table className="dm-table">
          <thead><tr><th>{t('模型')}</th><th>{t('类型')}</th><th>{t('状态')}</th><th>{t('采样率')}</th><th>{t('语言')}</th><th style={{ textAlign: 'right' }}>{t('操作')}</th></tr></thead>
          <tbody>
            {items.map(m => (
              <tr key={m.domain + '-' + m.id}>
                <td>
                  <div style={{ fontWeight: 500, display: 'flex', alignItems: 'center', gap: 6 }}>
                    {m.name || m.id}
                    {m.loaded && defaults[m.domain] === m.id && <span className="badge-default">{t('默认')}</span>}
                  </div>
                  <div className="text-mono text-xs text-dim">{m.id}</div>
                </td>
                <td><span className="chip">{(m.domain || '').toUpperCase()}</span></td>
                <td>
                  <span className={`chip ${m.loaded ? 'chip-accent' : ''}`}>
                    <span className="status-dot" style={{
                      background: m.loaded ? 'var(--accent)' : 'var(--text-low)'
                    }}/>
                    {m.loaded ? t('已加载') : t('空闲')}
                  </span>
                </td>
                <td className="text-mono text-xs">{m.sample_rates ? m.sample_rates.map(r => r + 'Hz').join(', ') : m.sample_rate ? m.sample_rate + 'Hz' : '-'}</td>
                <td className="text-mono text-xs">{(m.languages || []).join(', ') || '-'}</td>
                <td style={{ textAlign: 'right' }}>
                  <div className="flex gap-2" style={{ justifyContent: 'flex-end' }}>
                    {m.loaded && defaults[m.domain] !== m.id && (
                      <button className="btn-ghost" disabled={!!loadingId} onClick={() => switchDefault(m)}
                        style={{ fontSize: 11, padding: '4px 10px' }}>{t('设为默认')}</button>
                    )}
                    <button className="btn-ghost" disabled={!!loadingId} onClick={() => toggle(m)}>
                      {loadingId === m.domain + '-' + m.id
                        ? (m.loaded ? t('卸载中…') : t('加载中…'))
                        : (m.loaded ? t('卸载') : t('加载'))}
                    </button>
                  </div>
                </td>
              </tr>
            ))}
            {items.length === 0 && <tr><td colSpan={6} className="text-dim">{t('加载中…')}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ---------- 设置 ----------
function SettingsPage() {
  const { t } = window;
  const [bases, setBases] = useStateD(window.API_BASES);
  const update = (k, v) => {
    const next = { ...bases, [k]: v };
    setBases(next);
    window.API_BASES = next;
  };
  return (
    <div className="main-inner" style={{ maxWidth: 720 }}>
      <div className="page-header">
        <div>
          <div className="page-title">{t('系统配置')}</div>
          <div className="page-sub">API ENDPOINTS · RUNTIME CONFIG</div>
        </div>
      </div>

      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)',
                    borderRadius: 'var(--radius)', padding: 24 }}>
        <div className="section-label">API Base URLs</div>
        {Object.entries(bases).map(([k, v]) => (
          <div key={k} className="tweak-row" style={{ marginBottom: 16 }}>
            <label className="tweak-label" style={{ fontSize: 12 }}>
              <span className="text-mono" style={{ color: 'var(--accent)' }}>{k.toUpperCase()}</span>
            </label>
            <input className="input" value={v} onChange={e => update(k, e.target.value)}/>
          </div>
        ))}
        <div className="text-xs text-dim mt-4">
          修改后立即对新请求生效。如出现跨域，请在后端配置 CORS 或使用反向代理。
        </div>
      </div>
    </div>
  );
}

// ---------- 视觉模型管理 ----------
function VisionManagePage() {
  const { visionApi, t } = window;
  const [models, setModels] = useStateD([]);
  const [loadingId, setLoadingId] = useStateD(null);

  const refresh = async () => {
    try {
      const raw = await visionApi.listModels();
      const list = Array.isArray(raw) ? raw : (raw.data || []);
      setModels(list.map(m => ({
        id: m.model_id, name: m.model_id,
        loaded: m.status === 'ready',
        status: m.status || 'unloaded',
        backend: m.backend || '-',
        capabilities: m.capabilities || [],
      })));
    } catch (e) {
      console.warn('[vision-manage] refresh failed:', e);
    }
  };

  useEffectD(() => { refresh(); }, []);

  const toggle = async (item) => {
    setLoadingId(item.id);
    try {
      if (item.loaded) {
        await visionApi.unloadModel(item.id);
      } else {
        const loaded = models.filter(m => m.loaded && m.id !== item.id);
        for (const m of loaded) await visionApi.unloadModel(m.id).catch(() => {});
        await visionApi.loadModel(item.id);
      }
      await refresh();
    } catch (e) {
      if (e.message && e.message.includes('409')) {
        await refresh();
      } else {
        alert('操作失败: ' + e.message);
      }
    }
    setLoadingId(null);
  };

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('视觉模型管理')}</div>
          <div className="page-sub">{models.length} {t('模型 · 加载 / 卸载')}</div>
        </div>
        <button className="btn-ghost" onClick={refresh} title={t('刷新')}>{Icon.refresh({ size: 14 })}</button>
      </div>
      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
        <table className="dm-table">
          <thead><tr><th>{t('模型')}</th><th>{t('后端')}</th><th>{t('能力')}</th><th>{t('状态')}</th><th style={{ textAlign: 'right' }}>{t('操作')}</th></tr></thead>
          <tbody>
            {models.map(m => (
              <tr key={m.id}>
                <td>
                  <div style={{ fontWeight: 500 }}>{m.name}</div>
                  <div className="text-mono text-xs text-dim">{m.id}</div>
                </td>
                <td className="text-mono text-xs">{m.backend}</td>
                <td>
                  <div className="flex gap-1" style={{ flexWrap: 'wrap' }}>
                    {m.capabilities.map(c => (
                      <span key={c} className="chip" style={{ fontSize: 9 }}>{c}</span>
                    ))}
                    {m.capabilities.length === 0 && <span className="text-dim">-</span>}
                  </div>
                </td>
                <td>
                  <span className={`chip ${m.loaded ? 'chip-accent' : ''}`}>
                    <span className="status-dot" style={{ background: m.loaded ? 'var(--accent)' : 'var(--text-low)' }}/>
                    {m.loaded ? t('已加载') : t('空闲')}
                  </span>
                </td>
                <td style={{ textAlign: 'right' }}>
                  <button className="btn-ghost" disabled={!!loadingId} onClick={() => toggle(m)}>
                    {loadingId === m.id
                      ? (m.loaded ? t('卸载中…') : t('加载中…'))
                      : (m.loaded ? t('卸载') : t('加载'))}
                  </button>
                </td>
              </tr>
            ))}
            {models.length === 0 && <tr><td colSpan={5} className="text-dim">{t('加载中…')}</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}

window.DashboardPage = DashboardPage;
window.HistoryPage = HistoryPage;
window.ManagePage = ManagePage;
window.VisionManagePage = VisionManagePage;
window.SettingsPage = SettingsPage;
