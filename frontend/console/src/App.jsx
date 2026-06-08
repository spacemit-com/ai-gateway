// 主 App —— 路由 + Tweaks
const { useState: useStateApp, useEffect: useEffectApp } = React;

const TWEAK_STORAGE_KEY = 'spacemit-ai-gateway-tweaks';
const DEFAULT_TWEAKS = { layout: 'grid', accent: 'lime', density: 'comfortable' };
const VALID_LAYOUTS = ['grid', 'list', 'dense'];
const ACCENT_COLORS = {
  lime: 'oklch(0.82 0.18 135)',
  cyan: 'oklch(0.82 0.15 195)',
  violet: 'oklch(0.75 0.20 290)',
  amber: 'oklch(0.82 0.17 80)',
};

function readStoredTweaks() {
  try {
    const raw = localStorage.getItem(TWEAK_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) : {};
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch (_) {
    return {};
  }
}

function normalizeTweaks(tweaks) {
  const next = { ...DEFAULT_TWEAKS, ...(tweaks || {}) };
  if (!VALID_LAYOUTS.includes(next.layout)) next.layout = DEFAULT_TWEAKS.layout;
  if (!ACCENT_COLORS[next.accent]) next.accent = DEFAULT_TWEAKS.accent;
  return next;
}

function colorWithAlpha(color, alpha) {
  return color.replace(/\)$/, ` / ${alpha})`);
}

function App() {
  const { Icon } = window;
  const [page, setPage] = useStateApp({ name: 'models', category: 'text' });
  const [tweaks, setTweaks] = useStateApp(() => normalizeTweaks({
    ...(window.__TWEAKS__ || {}),
    ...readStoredTweaks(),
  }));
  const [tweaksOpen, setTweaksOpen] = useStateApp(false);
  const [theme, setTheme] = useStateApp(() => localStorage.getItem('spacemit-ai-gateway-theme') || 'system');
  const [lang, setLang] = useStateApp(() => window.__lang || 'zh');

  useEffectApp(() => {
    if (window.__resCollector) window.__resCollector.start();
    if (window.initModelCatalog) window.initModelCatalog();
  }, []);

  useEffectApp(() => {
    const apply = () => {
      let resolved = theme;
      if (theme === 'system') {
        resolved = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      }
      document.documentElement.setAttribute('data-theme', resolved);
    };
    apply();
    localStorage.setItem('spacemit-ai-gateway-theme', theme);
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    mq.addEventListener('change', apply);
    return () => mq.removeEventListener('change', apply);
  }, [theme]);

  useEffectApp(() => {
    const accent = ACCENT_COLORS[tweaks.accent] || ACCENT_COLORS[DEFAULT_TWEAKS.accent];
    document.documentElement.style.setProperty('--accent', accent);
    document.documentElement.style.setProperty('--accent-2', colorWithAlpha(accent, '.14'));
    document.documentElement.style.setProperty('--accent-3', colorWithAlpha(accent, '.30'));
    window.__TWEAKS__ = tweaks;
  }, [tweaks]);

  useEffectApp(() => {
    const onMsg = (e) => {
      if (e.data?.type === '__activate_edit_mode') setTweaksOpen(true);
      if (e.data?.type === '__deactivate_edit_mode') setTweaksOpen(false);
    };
    window.addEventListener('message', onMsg);
    window.parent.postMessage({ type: '__edit_mode_available' }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);

  const updateTweak = (k, v) => {
    const next = normalizeTweaks({ ...tweaks, [k]: v });
    setTweaks(next);
    try {
      localStorage.setItem(TWEAK_STORAGE_KEY, JSON.stringify(next));
    } catch (_) {}
    window.parent.postMessage({ type: '__edit_mode_set_keys', edits: { [k]: next[k] } }, '*');
  };

  const routeForModel = (m) => {
    if (m.domain === 'asr')  return 'ASRTryPage';
    if (m.domain === 'tts')  return 'TTSTryPage';
    if (m.domain === 'vad')  return 'VADTryPage';
    if (m.domain === 'yolo' || m.domain === 'vision') return 'VisionTryPage';
    if (m.domain === 'vlm')  return 'PlaygroundPage';
    if (m.task === 'translate') return 'TranslatePage';
    return 'PlaygroundPage';
  };

  let content;
  if (page.name === 'models')    content = <window.ModelSelectPage setPage={setPage} initialCategory={page.category}/>;
  else if (page.name === 'try')  {
    const Comp = window[routeForModel(page.model)];
    content = <Comp model={page.model} onBack={() => setPage({ name: 'models', category: page.category })}/>;
  }
  else if (page.name === 'dashboard') content = <window.DashboardPage/>;
  else if (page.name === 'resources') content = <window.ResourceMonitorPage/>;
  else if (page.name === 'history')   content = <window.HistoryPage/>;
  else if (page.name === 'manage')      content = <window.ManagePage/>;
  else if (page.name === 'vision-manage') content = <window.VisionManagePage/>;
  else if (page.name === 'llm-manage') content = <window.LLMManagePage/>;
  else if (page.name === 'vlm-manage') content = <window.VLMManagePage/>;
  else if (page.name === 'lexicons')  content = <window.LexiconPage/>;
  else if (page.name === 'tasks')     content = <window.TasksPage/>;
  else if (page.name === 'vision-jobs') content = <window.VisionJobsPage/>;
  else if (page.name === 'settings')  content = <window.ConfigPage/>;

  const layoutClass = `layout-${tweaks.layout || 'grid'}`;
  const toggleLang = () => {
    const next = lang === 'zh' ? 'en' : 'zh';
    setLang(next);
    window.__lang = next;
    localStorage.setItem('spacemit-ai-gateway-lang', next);
  };

  const themeIcon = theme === 'dark' ? 'moon' : theme === 'light' ? 'sun' : 'monitor';
  const themeLabel = { light: '亮色', dark: '暗色', system: '跟随系统' };
  const nextTheme = { light: 'dark', dark: 'system', system: 'light' };
  const tweaksLabel = lang === 'zh' ? '界面微调' : 'Tweaks';

  return (
    <div className={`app-shell ${layoutClass}`} data-accent={tweaks.accent}>
      <window.Sidebar page={page.name} setPage={setPage}/>
      <main className="main">
        <div className="top-bar">
          <div style={{ flex: 1 }}/>
          <button className="theme-toggle"
            onClick={toggleLang} title={lang === 'zh' ? 'Switch to English' : '切换到中文'}>
            <span style={{ fontSize: 12, fontWeight: 600 }}>{lang === 'zh' ? 'En' : '中'}</span>
          </button>
          <button className="theme-toggle"
            onClick={() => setTheme(nextTheme[theme])} title={themeLabel[theme]}>
            {Icon[themeIcon]({ size: 16 })}
          </button>
          <button className="theme-toggle"
            onClick={() => setTweaksOpen(open => !open)} title={tweaksLabel} aria-label={tweaksLabel}
            aria-pressed={tweaksOpen}>
            {Icon.settings({ size: 16 })}
          </button>
        </div>
        {content}
      </main>
      {tweaksOpen && <TweaksPanel tweaks={tweaks} update={updateTweak} onClose={() => setTweaksOpen(false)}/>}
    </div>
  );
}

function TweaksPanel({ tweaks, update, onClose }) {
  const { Icon } = window;
  return (
    <div className="tweaks-panel">
      <div className="tweaks-title">
        <span>TWEAKS</span>
        <button onClick={onClose} style={{ color: 'var(--text-dim)' }}>{Icon.x({ size: 12 })}</button>
      </div>
      <div className="tweak-row">
        <label className="tweak-label">列表布局</label>
        <div className="tweak-options">
          {['grid', 'list', 'dense'].map(v => (
            <button key={v}
              className={`tweak-option ${tweaks.layout === v ? 'active' : ''}`}
              onClick={() => update('layout', v)}>
              {v === 'grid' ? '网格' : v === 'list' ? '列表' : '紧凑'}
            </button>
          ))}
        </div>
      </div>
      <div className="tweak-row">
        <label className="tweak-label">强调色</label>
        <div className="tweak-options">
          {Object.keys(ACCENT_COLORS).map(k => (
            <button key={k}
              className={`tweak-option ${tweaks.accent === k ? 'active' : ''}`}
              onClick={() => update('accent', k)}>{k}</button>
          ))}
        </div>
      </div>
      <div className="text-xs text-dim text-mono mt-2" style={{ paddingTop: 8, borderTop: '1px solid var(--border)' }}>
        /projects/spacemit/spacemit-ai-gateway
      </div>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById('app')).render(<App/>);
