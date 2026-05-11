// Playground —— LLM / VLM 通用对话
const { useState: useStateP, useRef: useRefP, useEffect: useEffectP } = React;

function PlaygroundPage({ model, onBack }) {
  const { Icon, llmApi, t } = window;
  const [messages, setMessages] = useStateP([]);
  const [input, setInput] = useStateP('');
  const [imgFile, setImgFile] = useStateP(null);
  const [imgDataUrl, setImgDataUrl] = useStateP(null);
  const [loading, setLoading] = useStateP(false);
  const [temperature, setTemperature] = useStateP(0.7);
  const [maxTokens, setMaxTokens] = useStateP(512);
  const [streamMode, setStreamMode] = useStateP(true);
  const [availableModels, setAvailableModels] = useStateP([]);
  const [selectedModel, setSelectedModel] = useStateP(model.id);
  const [metrics, setMetrics] = useStateP(null);
  const [modelError, setModelError] = useStateP(null);
  const endRef = useRefP(null);

  const isVLM = model.domain === 'vlm';

  useEffectP(() => { endRef.current?.scrollIntoView({ block: 'nearest' }); }, [messages]);

  useEffectP(() => {
    const s = window.pageStateStore?.load('llm', model.id);
    if (s?.messages) setMessages(s.messages);
  }, [model.id]);

  useEffectP(() => {
    if (messages.length === 0) return;
    const toSave = messages.map(m => {
      const { _img, ...rest } = m;
      return rest;
    });
    window.pageStateStore?.save('llm', model.id, { messages: toSave });
  }, [messages, model.id]);

  useEffectP(() => {
    llmApi.listModels().then(models => {
      const loaded = (models || []).filter(m => m.status === 'loaded');
      setAvailableModels(loaded);
    }).catch(() => {});
  }, []);

  const onImage = (e) => {
    const f = e.target.files[0]; if (!f) return;
    setImgFile(f);
    const r = new FileReader();
    r.onload = () => setImgDataUrl(r.result);
    r.readAsDataURL(f);
  };

  const send = async () => {
    if (!input.trim() && !imgDataUrl) return;

    let userContent = input;
    if (isVLM && imgDataUrl) {
      userContent = [
        { type: 'text', text: input || '请描述这张图片' },
        { type: 'image_url', image_url: { url: imgDataUrl } },
      ];
    }

    const userMsg = { role: 'user', content: userContent, _preview: input, _img: imgDataUrl };
    const history = [...messages, userMsg];
    setMessages(history);
    setInput(''); setImgFile(null); setImgDataUrl(null); setLoading(true);

    const body = {
      model: selectedModel,
      messages: history.map(({ role, content }) => ({ role, content })),
      temperature, max_tokens: maxTokens,
    };

    const assistantIdx = history.length;
    setMessages(m => [...m, { role: 'assistant', content: '' }]);

    setMetrics(null);
    setModelError(null);
    const _t0 = Date.now();
    try {
      if (streamMode) {
        let completionTokens = 0, promptTokens = 0, serverTimings = null, accText = '';
        for await (const chunk of llmApi.chatStream(body)) {
          const delta = chunk.choices?.[0]?.delta?.content || '';
          if (delta) {
            accText += delta;
            completionTokens++;
            setMessages(m => {
              const copy = [...m];
              copy[assistantIdx] = { ...copy[assistantIdx], content: (copy[assistantIdx].content || '') + delta };
              return copy;
            });
          }
          if (chunk.usage) {
            promptTokens = chunk.usage.prompt_tokens || promptTokens;
            completionTokens = chunk.usage.completion_tokens || completionTokens;
          }
          if (chunk.timings) serverTimings = chunk.timings;
        }
        const promptMs = serverTimings?.prompt_ms || 0;
        const predictedTps = serverTimings?.predicted_per_second || 0;
        const ppTps = serverTimings?.prompt_per_second || 0;
        setMetrics({
          ttft_ms: promptMs ? Math.round(promptMs) : null,
          tg_tps: predictedTps,
          pp_tps: ppTps,
          prompt_tokens: serverTimings?.prompt_n || promptTokens,
          completion_tokens: serverTimings?.predicted_n || completionTokens,
        });
        window.historyStore?.push({
          model: selectedModel, type: 'LLM',
          input: input.slice(0, 50) + (input.length > 50 ? '…' : ''),
          output: accText.slice(0, 60),
          latency: Date.now() - _t0,
        });
      } else {
        const res = await llmApi.chat(body);
        const txt = res.choices?.[0]?.message?.content || '[无返回]';
        setMessages(m => {
          const copy = [...m];
          copy[assistantIdx] = { role: 'assistant', content: txt };
          return copy;
        });
        if (res.usage) {
          setMetrics({
            ttft_ms: null,
            tg_tps: 0,
            pp_tps: 0,
            prompt_tokens: res.usage.prompt_tokens || 0,
            completion_tokens: res.usage.completion_tokens || 0,
          });
        }
        window.historyStore?.push({
          model: selectedModel, type: 'LLM',
          input: input.slice(0, 50) + (input.length > 50 ? '…' : ''),
          output: txt.slice(0, 60),
          latency: Date.now() - _t0,
        });
      }
    } catch (e) {
      setMessages(m => m.slice(0, assistantIdx));
      if (e.status === 503 || /not downloaded|not loaded|No model loaded/i.test(e.message)) {
        setModelError(e.message);
      } else {
        setModelError(`${t('请求失败')}: ${e.message}`);
      }
    }
    setLoading(false);
  };

  return (
    <div className="main-inner">
      <div className="back-link" onClick={onBack}>
        {Icon.arrowLeft({ size: 14 })}<span>{t('返回模型选择')}</span>
      </div>
      <div className="page-header">
        <div>
          <div className="page-title">{model.name}</div>
          <div className="page-sub">{isVLM ? 'VLM' : 'LLM'} · {selectedModel} · POST /v1/chat/completions</div>
        </div>
        <div className="flex gap-2" style={{ alignItems: 'center' }}>
          {availableModels.length > 1 && (
            <select className="select" value={selectedModel}
              onChange={e => setSelectedModel(e.target.value)}
              style={{ width: 'auto', maxWidth: 260, fontSize: 12 }}>
              <option value={model.id}>{model.name || model.id}</option>
              {availableModels.filter(m => m.id !== model.id).map(m => (
                <option key={m.id} value={m.id}>{m.id}</option>
              ))}
            </select>
          )}
          <button className="btn-ghost" onClick={() => { setMessages([]); setMetrics(null); window.pageStateStore?.clear('llm', model.id); }}>{t('清空对话')}</button>
        </div>
      </div>

      <div className="try-layout">
        <div className="try-main" style={{ display: 'flex', flexDirection: 'column', padding: 0, maxHeight: 'calc(100vh - 240px)' }}>
          <div style={{
            flex: 1, overflowY: 'auto', padding: 24, display: 'flex', flexDirection: 'column',
            gap: 12, minHeight: 0,
          }}>
            {messages.length === 0 && (
              <div style={{ textAlign: 'center', color: 'var(--text-low)', margin: 'auto',
                            fontFamily: 'var(--font-mono)', fontSize: 12 }}>
                开始和 {model.name} 对话…
                {isVLM && <div className="mt-2">支持上传图片进行多模态理解</div>}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={`bubble bubble-${m.role}`}>
                {m._img && <img src={m._img} style={{ maxWidth: 240, borderRadius: 6, marginBottom: 8, display: 'block' }}/>}
                <div style={{ whiteSpace: 'pre-wrap' }}>{m._preview || (typeof m.content === 'string' ? m.content : '')}</div>
                {m.role === 'assistant' && loading && i === messages.length - 1 &&
                  <span style={{ opacity: 0.6 }}>▋</span>}
              </div>
            ))}
            {modelError && (
              <div style={{
                display: 'flex', alignItems: 'flex-start', gap: 12, padding: '14px 16px',
                background: 'var(--bg-1)', border: '1px solid var(--border)', borderRadius: 10,
              }}>
                <span style={{ fontSize: 20, lineHeight: 1 }}>⚠</span>
                <div style={{ flex: 1, fontSize: 13 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>{t('模型不可用')}</div>
                  <div style={{ color: 'var(--text-dim)', marginBottom: 10, fontFamily: 'var(--font-mono)', fontSize: 11 }}>{modelError}</div>
                  <div style={{ color: 'var(--text-dim)', fontSize: 12 }}>{t('请前往 LLM 模型管理页面下载并加载该模型')}</div>
                </div>
                <button className="btn-ghost" onClick={() => setModelError(null)}
                  style={{ padding: 4, flexShrink: 0 }}>{Icon.x({ size: 14 })}</button>
              </div>
            )}
            <div ref={endRef}/>
          </div>

          <div style={{ borderTop: '1px solid var(--border)', padding: 16 }}>
            {imgDataUrl && (
              <div style={{ marginBottom: 10, display: 'inline-flex', gap: 8, alignItems: 'center',
                            background: 'var(--bg-1)', borderRadius: 8, padding: 6 }}>
                <img src={imgDataUrl} style={{ height: 40, borderRadius: 4 }}/>
                <button className="btn-ghost" onClick={() => { setImgDataUrl(null); setImgFile(null); }}
                  style={{ padding: 4 }}>{Icon.x({ size: 14 })}</button>
              </div>
            )}
            <div className="flex gap-2">
              {isVLM && (
                <label className="btn-ghost" style={{ cursor: 'pointer', padding: '10px 12px' }}>
                  <input type="file" accept="image/*" onChange={onImage} style={{ display: 'none' }}/>
                  {Icon.upload({ size: 14 })}
                </label>
              )}
              <textarea className="textarea" style={{ minHeight: 44, maxHeight: 140 }}
                placeholder="输入消息… (Enter 发送，Shift+Enter 换行)"
                value={input}
                onChange={e => setInput(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); } }}/>
              <button className="btn-primary" disabled={loading} onClick={send}
                style={{ padding: '0 16px' }}>
                {Icon.send({ size: 14 })}
              </button>
            </div>
          </div>
        </div>

        <div className="try-side">
          <div>
            <div className="section-label">{t('生成参数')}</div>
            <div className="tweak-row">
              <label className="tweak-label">{t('温度')} · <span className="text-mono">{temperature.toFixed(2)}</span></label>
              <input type="range" className="slider" min="0" max="2" step="0.05"
                value={temperature} onChange={e => setTemperature(+e.target.value)}/>
            </div>
            <div className="tweak-row">
              <label className="tweak-label">{t('最大长度')} · <span className="text-mono">{maxTokens}</span></label>
              <input type="range" className="slider" min="64" max="4096" step="64"
                value={maxTokens} onChange={e => setMaxTokens(+e.target.value)}/>
            </div>
            <div className="tweak-row">
              <label className="tweak-label">{t('流式输出')}</label>
              <div className="tweak-options">
                <button className={`tweak-option ${streamMode ? 'active' : ''}`} onClick={() => setStreamMode(true)}>{t('流式')}</button>
                <button className={`tweak-option ${!streamMode ? 'active' : ''}`} onClick={() => setStreamMode(false)}>{t('一次性')}</button>
              </div>
            </div>
          </div>
          {metrics && (
            <div>
              <div className="section-label">{t('性能指标')}</div>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 8 }}>
                <div style={{ background: 'var(--bg-1)', borderRadius: 6, padding: '8px 10px', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>TTFT</div>
                  <div style={{ fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                    {metrics.ttft_ms != null ? metrics.ttft_ms + ' ms' : '-'}
                  </div>
                </div>
                <div style={{ background: 'var(--bg-1)', borderRadius: 6, padding: '8px 10px', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>{t('生成速度')}</div>
                  <div style={{ fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                    {metrics.tg_tps > 0 ? metrics.tg_tps.toFixed(1) + ' tok/s' : '-'}
                  </div>
                </div>
                <div style={{ background: 'var(--bg-1)', borderRadius: 6, padding: '8px 10px', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>{t('Prompt 处理')}</div>
                  <div style={{ fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                    {metrics.pp_tps > 0 ? metrics.pp_tps.toFixed(1) + ' tok/s' : '-'}
                  </div>
                </div>
                <div style={{ background: 'var(--bg-1)', borderRadius: 6, padding: '8px 10px', border: '1px solid var(--border)' }}>
                  <div style={{ fontSize: 10, color: 'var(--text-dim)', fontFamily: 'var(--font-mono)' }}>Tokens</div>
                  <div style={{ fontSize: 16, fontWeight: 600, fontFamily: 'var(--font-mono)' }}>
                    {metrics.prompt_tokens || 0} → {metrics.completion_tokens || 0}
                  </div>
                </div>
              </div>
            </div>
          )}
          <div>
            <div className="section-label">API 端点</div>
            <code style={{
              display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11,
              background: 'var(--bg-1)', padding: 10, borderRadius: 6,
              color: 'var(--text-dim)', border: '1px solid var(--border)',
            }}>
              POST /v1/chat/completions<br/>
              &nbsp;&nbsp;model={selectedModel}<br/>
              &nbsp;&nbsp;stream={streamMode ? 'true' : 'false'}
            </code>
          </div>
        </div>
      </div>
      <window.ResourceBar/>
    </div>
  );
}

window.PlaygroundPage = PlaygroundPage;
