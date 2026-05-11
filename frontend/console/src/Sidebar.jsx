// 侧边栏
const { useState, useEffect } = React;

function Sidebar({ page, setPage }) {
  const { Icon, asrApi, ttsApi, vadApi, visionApi, llmApi, t } = window;
  const [health, setHealth] = useState({ asr: null, tts: null, vad: null, vision: null, llm: null });

  useEffect(() => {
    const poll = async () => {
      const [a, tt, v, vis, llm] = await Promise.all([
        asrApi.health().then(r => !!r.ready).catch(() => false),
        ttsApi.health().then(r => !!r.ready).catch(() => false),
        vadApi.health().then(r => !!r.ready).catch(() => false),
        visionApi.health().then(r => !!r.readiness).catch(() => false),
        llmApi.health().then(r => r.status === 'ready' || r.status === 'ok').catch(() => false),
      ]);
      setHealth({ asr: a, tts: tt, vad: v, vision: vis, llm });
    };
    poll();
    const id = setInterval(poll, 5000);
    return () => clearInterval(id);
  }, []);

  const allOnline = health.asr && health.tts && health.vad;

  const nav = [
    { id: 'models',    label: t('模型选择'), icon: 'grid' },
    { id: 'dashboard', label: t('仪表盘'),   icon: 'activity' },
    { id: 'resources', label: t('资源监控'), icon: 'monitor' },
    { id: 'history',   label: t('历史记录'), icon: 'history' },
    { id: 'manage',    label: t('语音模型管理'), icon: 'package' },
    { id: 'vision-manage', label: t('视觉模型管理'), icon: 'eye' },
    { id: 'llm-manage', label: t('LLM 管理'), icon: 'cpu' },
    { id: 'lexicons',  label: t('词库管理'), icon: 'book' },
    { id: 'tasks',     label: t('异步任务'), icon: 'clock' },
    { id: 'vision-jobs', label: t('视觉任务'), icon: 'eye' },
    { id: 'settings',  label: t('系统配置'), icon: 'settings' },
  ];
  return (
    <aside className="sidebar">
      <a className="brand" href="../index.html" style={{ textDecoration: 'none', color: 'inherit' }}>
        <img src="img/spacemit.png" alt="SpaceMIT" style={{ width: 32, height: 32, borderRadius: 6, objectFit: 'contain' }}/>
        <div>
          <div className="brand-name">SpaceMIT</div>
          <div className="brand-sub">spacemit-ai-gateway / v0.3</div>
        </div>
      </a>

      <div className="nav-group-title">{t('工作区')}</div>
      {nav.map(n => (
        <button key={n.id}
          className={`nav-item ${page === n.id ? 'active' : ''}`}
          onClick={() => setPage({ name: n.id })}>
          <span className="nav-icon">{Icon[n.icon]({ size: 16 })}</span>
          <span>{n.label}</span>
        </button>
      ))}

      <div className="nav-group-title">{t('服务')}</div>
      <ServiceStatus name="ASR"    port="18790" ok={health.asr}/>
      <ServiceStatus name="TTS"    port="18790" ok={health.tts}/>
      <ServiceStatus name="VAD"    port="18790" ok={health.vad}/>
      <ServiceStatus name="Vision" port="18790" ok={health.vision}/>
      <ServiceStatus name="LLM"    port="18790" ok={health.llm}/>

      <div className="sidebar-footer">
        {allOnline ? (
          <><span className="pulse-dot"/><span>{t('AI 服务在线')}</span></>
        ) : (
          <span style={{ color: 'var(--text-dim)' }}>{t('检查服务中…')}</span>
        )}
      </div>
    </aside>
  );
}

function ServiceStatus({ name, port, ok }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 10,
                  padding: '6px 10px', fontSize: 12, color: 'var(--text-dim)',
                  fontFamily: 'var(--font-mono)' }}>
      <span className="status-dot" style={{
        background: ok === true ? 'var(--accent)' : ok === false ? 'var(--danger)' : 'var(--text-low)',
        boxShadow: ok === true ? '0 0 4px var(--accent)' : 'none'
      }}/>
      <span style={{ flex: 1 }}>{name}</span>
      <span style={{ color: 'var(--text-low)' }}>:{port}</span>
    </div>
  );
}

window.Sidebar = Sidebar;
