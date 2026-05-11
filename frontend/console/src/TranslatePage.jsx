// 翻译页面 —— 基于 LLM chat completions 的双向翻译
const { useState: useStateTr, useRef: useRefTr, useEffect: useEffectTr } = React;

const LANG_OPTIONS = [
  { code: 'zh', label: '中文' },
  { code: 'en', label: 'English' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'fr', label: 'Français' },
  { code: 'de', label: 'Deutsch' },
  { code: 'es', label: 'Español' },
  { code: 'ru', label: 'Русский' },
];

function TranslatePage({ model, onBack }) {
  const { Icon, llmApi, t } = window;
  const [srcLang, setSrcLang] = useStateTr('zh');
  const [tgtLang, setTgtLang] = useStateTr('en');
  const [srcText, setSrcText] = useStateTr('');
  const [tgtText, setTgtText] = useStateTr('');
  const [loading, setLoading] = useStateTr(false);
  const [error, setError] = useStateTr('');
  const [metrics, setMetrics] = useStateTr(null);
  const [modelReady, setModelReady] = useStateTr(model.status === 'ready');
  const [modelError, setModelError] = useStateTr(null);
  const abortRef = useRefTr(null);

  useEffectTr(() => {
    if (model.status !== 'ready') {
      llmApi.loadModel(model.id)
        .then(() => setModelReady(true))
        .catch(e => setModelError(e.message));
    }
  }, [model.id]);

  const swapLangs = () => {
    setSrcLang(tgtLang);
    setTgtLang(srcLang);
    setSrcText(tgtText);
    setTgtText(srcText);
  };

  const translate = async () => {
    if (!srcText.trim()) return;
    setLoading(true);
    setError('');
    setTgtText('');
    setMetrics(null);

    const srcLabel = LANG_OPTIONS.find(l => l.code === srcLang)?.label || srcLang;
    const tgtLabel = LANG_OPTIONS.find(l => l.code === tgtLang)?.label || tgtLang;
    const systemPrompt = `You are a professional translator. Translate the following text from ${srcLabel} to ${tgtLabel}. Output ONLY the translation, nothing else.`;

    const body = {
      model: model.id,
      messages: [
        { role: 'system', content: systemPrompt },
        { role: 'user', content: srcText.trim() },
      ],
      temperature: 0.3,
      max_tokens: 2048,
    };

    const _t0 = Date.now();
    try {
      let result = '';
      let serverTimings = null;
      for await (const chunk of llmApi.chatStream(body)) {
        const delta = chunk.choices?.[0]?.delta?.content || '';
        if (delta) {
          result += delta;
          setTgtText(result);
        }
        if (chunk.timings) serverTimings = chunk.timings;
      }
      if (serverTimings) {
        setMetrics({
          prompt_ms: Math.round(serverTimings.prompt_ms || 0),
          tg_tps: serverTimings.predicted_per_second || 0,
          tokens: serverTimings.predicted_n || 0,
        });
      }
      window.historyStore?.push({
        model: model.id, type: t('翻译'),
        input: srcText.slice(0, 50) + (srcText.length > 50 ? '…' : ''),
        output: result.slice(0, 60),
        latency: Date.now() - _t0,
      });
    } catch (e) {
      if (/not downloaded|not loaded|No model/i.test(e.message)) {
        setModelError(t('模型不可用'));
      } else {
        setError(e.message);
      }
    }
    setLoading(false);
  };

  const langName = (code) => LANG_OPTIONS.find(l => l.code === code)?.label || code;

  return (
    <div className="main-inner">
      <div className="page-header">
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button className="btn-ghost" onClick={onBack}>{Icon.arrowLeft({ size: 16 })}</button>
          <div>
            <div className="page-title">{model.name}</div>
            <div className="page-sub">TRANSLATE · {model.id} · POST /v1/llm/chat/completions</div>
          </div>
        </div>
        <span className={`chip ${modelReady ? 'chip-accent' : ''}`}>
          <span className="status-dot" style={{ background: modelReady ? 'var(--accent)' : 'var(--text-low)' }}/>
          {modelReady ? t('就绪') : t('加载中…')}
        </span>
      </div>

      {modelError && (
        <div style={{
          background: 'oklch(0.70 0.18 25 / .08)', border: '1px solid oklch(0.70 0.18 25 / .25)',
          borderRadius: 8, padding: 14, marginBottom: 16, fontSize: 12, color: 'var(--danger)',
        }}>
          {modelError}
          <div style={{ marginTop: 8, fontSize: 11, color: 'var(--text-dim)' }}>
            {t('请前往 LLM 模型管理页面下载并加载该模型')}
          </div>
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: '1fr auto 1fr', gap: 12, alignItems: 'start' }}>
        {/* Source */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <select className="select" value={srcLang} onChange={e => setSrcLang(e.target.value)}>
            {LANG_OPTIONS.map(l => (
              <option key={l.code} value={l.code}>{l.label}</option>
            ))}
          </select>
          <textarea className="textarea" rows={10} value={srcText}
            onChange={e => setSrcText(e.target.value)}
            onKeyDown={e => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) translate(); }}
            placeholder={t('输入要翻译的文本…')}
            style={{ resize: 'vertical', minHeight: 200, fontSize: 14, lineHeight: 1.7 }}/>
          <div className="text-xs text-dim" style={{ textAlign: 'right' }}>
            {srcText.length} {t('字符')}
          </div>
        </div>

        {/* Swap button */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12, paddingTop: 36 }}>
          <button className="btn-ghost" onClick={swapLangs} title={t('交换语言')}
            style={{ padding: 10, borderRadius: '50%' }}>
            {Icon.swap({ size: 18 })}
          </button>
        </div>

        {/* Target */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          <select className="select" value={tgtLang} onChange={e => setTgtLang(e.target.value)}>
            {LANG_OPTIONS.map(l => (
              <option key={l.code} value={l.code}>{l.label}</option>
            ))}
          </select>
          <div style={{
            minHeight: 200, padding: 12, fontSize: 14, lineHeight: 1.7,
            background: 'var(--bg-2)', border: '1px solid var(--border)',
            borderRadius: 'var(--radius)', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
            color: tgtText ? 'var(--text)' : 'var(--text-low)',
          }}>
            {tgtText || (loading ? '' : t('翻译结果将显示在这里…'))}
            {loading && !tgtText && <span className="pulse-dot" style={{ marginLeft: 4 }}/>}
          </div>
          {tgtText && (
            <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
              <button className="btn-ghost" style={{ fontSize: 11 }}
                onClick={() => window.copyText(tgtText)}>{t('复制')}</button>
            </div>
          )}
        </div>
      </div>

      {error && (
        <div style={{
          marginTop: 12, padding: '10px 14px', borderRadius: 8, fontSize: 12,
          fontFamily: 'var(--font-mono)', color: 'var(--danger)',
          background: 'oklch(0.70 0.18 25 / .08)', border: '1px solid oklch(0.70 0.18 25 / .25)',
        }}>⚠ {error}</div>
      )}

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginTop: 16 }}>
        <button className="btn-primary" onClick={translate}
          disabled={loading || !srcText.trim() || !modelReady}
          style={{ minWidth: 140 }}>
          {loading ? t('翻译中…') : t('翻译')}
        </button>

        {metrics && (
          <div className="text-mono text-xs text-dim" style={{ display: 'flex', gap: 16 }}>
            <span>{metrics.tg_tps.toFixed(1)} tok/s</span>
            <span>{metrics.tokens} tokens</span>
            <span>prompt {metrics.prompt_ms} ms</span>
          </div>
        )}
      </div>

      <div className="text-xs text-dim" style={{ marginTop: 8 }}>
        Ctrl+Enter {t('快速翻译')}
      </div>
    </div>
  );
}

window.TranslatePage = TranslatePage;
