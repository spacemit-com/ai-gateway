// TTS 试用页
const { useState: useStateT, useRef: useRefT, useEffect: useEffectT } = React;

function TTSTryPage({ model, onBack }) {
  const { Icon, ttsApi, t } = window;
  const [text, setText] = useStateT('你好，我是 SpaceMIT 的语音合成模型，很高兴为你服务。');
  const [audioUrl, setAudioUrl] = useStateT(null);
  const [loading, setLoading] = useStateT(false);
  const [error, setError] = useStateT('');
  const [voices, setVoices] = useStateT([]);
  const [voiceId, setVoiceId] = useStateT('');
  const [speed, setSpeed] = useStateT(1.0);
  const [pitch, setPitch] = useStateT(1.0);
  const [format, setFormat] = useStateT('wav');
  const [synthMeta, setSynthMeta] = useStateT(null);
  const [streaming, setStreaming] = useStateT(false);
  const [streamStatus, setStreamStatus] = useStateT('idle');
  const wsRef = useRefT(null);
  const audioCtxRef = useRefT(null);
  const nextStartTimeRef = useRefT(0);
  const pcmBufferRef = useRefT([]);

  const availableRates = [...new Set(model.sample_rates || [])];
  const [sampleRate, setSampleRate] = useStateT(availableRates[0] || null);
  const [modelReady, setModelReady] = useStateT(model.status === 'ready');

  useEffectT(() => {
    const s = window.pageStateStore?.load('tts', model.id);
    if (s?.text) setText(s.text);
    if (s?.synthMeta) setSynthMeta(s.synthMeta);
  }, [model.id]);

  useEffectT(() => {
    if (!synthMeta) return;
    window.pageStateStore?.save('tts', model.id, { text, synthMeta });
  }, [text, synthMeta, model.id]);

  useEffectT(() => {
    ttsApi.listVoices().then(list => {
      if (Array.isArray(list) && list.length > 0) setVoices(list);
    }).catch(() => {});
    if (model.status !== 'ready') {
      ttsApi.loadModel(model.id)
        .then(() => { setModelReady(true); })
        .catch(e => {
          if (e.message && e.message.includes('409')) setModelReady(true);
          else setError('模型加载失败: ' + e.message);
        });
    }
  }, []);

  const scheduleChunk = (ctx, i16, sr) => {
    const f32 = new Float32Array(i16.length);
    for (let i = 0; i < i16.length; i++) f32[i] = i16[i] / 32768;
    const buf = ctx.createBuffer(1, f32.length, sr);
    buf.getChannelData(0).set(f32);
    const src = ctx.createBufferSource();
    src.buffer = buf;
    src.connect(ctx.destination);
    const now = ctx.currentTime;
    if (nextStartTimeRef.current < now) nextStartTimeRef.current = now;
    src.start(nextStartTimeRef.current);
    nextStartTimeRef.current += buf.duration;
  };

  const writeWavString = (view, offset, str) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };

  const buildDownloadBlob = (sr) => {
    const chunks = pcmBufferRef.current;
    let totalLen = 0;
    for (const c of chunks) totalLen += c.length;
    const merged = new Int16Array(totalLen);
    let off = 0;
    for (const c of chunks) { merged.set(c, off); off += c.length; }
    const wavBuf = new ArrayBuffer(44 + merged.byteLength);
    const v = new DataView(wavBuf);
    writeWavString(v, 0, 'RIFF');
    v.setUint32(4, 36 + merged.byteLength, true);
    writeWavString(v, 8, 'WAVE');
    writeWavString(v, 12, 'fmt ');
    v.setUint32(16, 16, true); v.setUint16(20, 1, true); v.setUint16(22, 1, true);
    v.setUint32(24, sr, true); v.setUint32(28, sr * 2, true);
    v.setUint16(32, 2, true); v.setUint16(34, 16, true);
    writeWavString(v, 36, 'data');
    v.setUint32(40, merged.byteLength, true);
    new Int16Array(wavBuf, 44).set(merged);
    const blob = new Blob([wavBuf], { type: 'audio/wav' });
    setAudioUrl(URL.createObjectURL(blob));
  };

  const synth = async () => {
    const startTime = Date.now();
    setLoading(true); setError(''); setAudioUrl(null); setSynthMeta(null);
    try {
      const { blob, meta } = await ttsApi.synthesize({
        model: model.id, text, voice_id: voiceId || undefined,
        speed, pitch, response_format: format,
        sample_rate: sampleRate || undefined,
      });
      if (blob.size <= 44) {
        setError('合成结果为空 — 该模型可能不支持当前输入语言');
      } else {
        const url = URL.createObjectURL(blob);
        setAudioUrl(url);
        const clientMs = Date.now() - startTime;
        setSynthMeta({ ...meta, latency: clientMs });
        window.historyStore?.push({
          model: model.name, type: 'TTS',
          input: text.slice(0, 50) + (text.length > 50 ? '…' : ''),
          output: (meta.duration_ms / 1000).toFixed(1) + 's · RTF ' + meta.rtf.toFixed(3),
          latency: meta.processing_ms || (Date.now() - startTime),
          audioUrl: url,
        });
      }
    } catch (e) {
      setError(e.message + ' — 请确认 /v1/tts/synthesize 可访问');
    }
    setLoading(false);
  };

  const synthStream = async () => {
    const startTime = Date.now();
    setLoading(true); setError(''); setAudioUrl(null); setSynthMeta(null);
    setStreamStatus('connecting');
    pcmBufferRef.current = [];
    nextStartTimeRef.current = 0;
    try {
      const sess = await ttsApi.createStreamSession({
        model: model.id, voice_id: voiceId || undefined, speed,
        response_format: 'pcm',
      });
      const sr = sampleRate || (model.sample_rates?.[0]) || 22050;
      const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: sr });
      audioCtxRef.current = ctx;
      const wsUrl = ttsApi.streamUrl()
        + '?session_id=' + encodeURIComponent(sess.session_id)
        + '&voice_id=' + encodeURIComponent(voiceId || '')
        + '&response_format=pcm';
      const ws = new WebSocket(wsUrl);
      ws.binaryType = 'arraybuffer';
      wsRef.current = ws;

      ws.onmessage = (e) => {
        if (e.data instanceof ArrayBuffer) {
          const i16 = new Int16Array(e.data);
          pcmBufferRef.current.push(i16);
          scheduleChunk(ctx, i16, sr);
        } else {
          try {
            const m = JSON.parse(e.data);
            if (m.type === 'ready') {
              setStreamStatus('streaming');
              ws.send(JSON.stringify({ type: 'start', text }));
              ws.send(JSON.stringify({ type: 'end' }));
            } else if (m.type === 'done') {
              setSynthMeta({
                duration_ms: m.duration_ms || 0, rtf: m.rtf || 0,
                processing_ms: m.duration_ms ? Math.round(m.duration_ms * (m.rtf || 0)) : 0,
                latency: Date.now() - startTime, sample_rate: sr,
              });
              setStreamStatus('done');
              setLoading(false);
              buildDownloadBlob(sr);
            } else if (m.type === 'error') {
              setError(m.message || 'Streaming error');
              setStreamStatus('idle'); setLoading(false);
            }
          } catch {}
        }
      };
      ws.onerror = () => { setError(t('连接中…') + ' failed'); setStreamStatus('idle'); setLoading(false); };
      ws.onclose = () => { if (streamStatus !== 'done') setLoading(false); };
    } catch (e) {
      setError(e.message); setStreamStatus('idle'); setLoading(false);
    }
  };

  const stopStream = () => {
    if (wsRef.current && wsRef.current.readyState === 1) {
      try { wsRef.current.send(JSON.stringify({ type: 'end' })); } catch {}
      wsRef.current.close();
    }
    wsRef.current = null;
    if (audioCtxRef.current) { audioCtxRef.current.close().catch(() => {}); audioCtxRef.current = null; }
  };

  useEffectT(() => () => stopStream(), []);

  const download = () => {
    if (!audioUrl) return;
    const a = document.createElement('a');
    a.href = audioUrl; a.download = `tts-${Date.now()}.${format}`;
    a.click();
  };

  return (
    <div className="main-inner try-page">
      <div className="back-link" onClick={onBack}>
        {Icon.arrowLeft({ size: 14 })}<span>{t('返回模型选择')}</span>
      </div>
      <div className="page-header">
        <div>
          <div className="page-title">{model.name}</div>
          <div className="page-sub">TTS · {model.id} · POST /v1/tts/synthesize{streaming ? ' · WS /v1/tts/stream' : ''}</div>
        </div>
        <span className={`chip ${modelReady ? 'chip-accent' : ''}`}>
          <span className="status-dot" style={{ background: modelReady ? 'var(--accent)' : 'var(--text-low)'}}/>
          {modelReady ? t('就绪') : t('加载中…')}
        </span>
      </div>

      <div className="try-layout">
        <div className="try-main">
          <div className="section-label">{t('输入文本')}</div>
          <textarea className="textarea" value={text} onChange={e => setText(e.target.value)}
            rows={6} placeholder="输入要合成为语音的文本…"/>
          <div className="text-dim text-xs text-mono mt-2">{text.length} {t('字符')} · ~{(text.length * 0.12).toFixed(1)}s</div>

          <div className="flex gap-3 mt-4">
            <button className="btn-primary" disabled={loading || !text.trim()} onClick={() => streaming ? synthStream() : synth()}>
              {loading ? t('合成中…') : <><span style={{ width: 8, height: 8, background: '#0a0a0b', borderRadius: 99 }}/>{t('合成音频')}</>}
            </button>
            {audioUrl && (
              <button className="btn-ghost" onClick={download}>
                {Icon.download({ size: 14 })} <span style={{ marginLeft: 6 }}>{t('下载')} .{format}</span>
              </button>
            )}
          </div>

          {streamStatus === 'streaming' && (
            <div className="mt-4 flex gap-2" style={{ alignItems: 'center' }}>
              <span className="pulse-dot"/><span className="text-dim text-xs">{t('流式合成中…')}</span>
            </div>
          )}

          {error && <div className="mt-4" style={{
            background: 'oklch(0.70 0.18 25 / .1)', border: '1px solid oklch(0.70 0.18 25 / .3)',
            borderRadius: 8, padding: 12, color: 'var(--danger)', fontSize: 12,
            fontFamily: 'var(--font-mono)',
          }}>{error}</div>}

          {audioUrl && (
            <>
              <div className="section-label mt-6">{t('播放')}</div>
              <div style={{
                background: 'var(--bg-1)', border: '1px solid var(--border)',
                borderRadius: 10, padding: 18,
              }}>
                <audio src={audioUrl} controls style={{ width: '100%' }}/>
              </div>
            </>
          )}

          {synthMeta && (
            <>
              <div className="section-label mt-6">{t('性能指标')}</div>
              <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))' }}>
                {synthMeta.duration_ms > 0 && (
                  <div className="stat-card">
                    <div className="stat-label">{t('音频时长')}</div>
                    <div className="stat-value">{(synthMeta.duration_ms / 1000).toFixed(2)}<span className="unit">s</span></div>
                  </div>
                )}
                <div className="stat-card">
                  <div className="stat-label">{t('处理耗时')}</div>
                  <div className="stat-value">{synthMeta.processing_ms || synthMeta.latency}<span className="unit">ms</span></div>
                </div>
                {synthMeta.rtf > 0 && (
                  <div className="stat-card">
                    <div className="stat-label">RTF</div>
                    <div className="stat-value">{synthMeta.rtf.toFixed(3)}</div>
                  </div>
                )}
                <div className="stat-card">
                  <div className="stat-label">{t('端到端延迟')}</div>
                  <div className="stat-value">{synthMeta.latency}<span className="unit">ms</span></div>
                </div>
                {synthMeta.sample_rate > 0 && (
                  <div className="stat-card">
                    <div className="stat-label">{t('采样率')}</div>
                    <div className="stat-value">{synthMeta.sample_rate}<span className="unit">Hz</span></div>
                  </div>
                )}
              </div>
            </>
          )}
        </div>

        <div className="try-side">
          <div>
            <div className="section-label">{t('合成参数')}</div>
            <div className="tweak-row">
              <label className="tweak-label">{t('音色')}</label>
              <select className="select" value={voiceId} onChange={e => setVoiceId(e.target.value)}>
                <option value="">默认</option>
                {voices.filter(v => v.id !== 'default').map(v => (
                  <option key={v.id} value={v.id}>{v.name || v.id}{v.language ? ` (${v.language})` : ''}</option>
                ))}
              </select>
            </div>
            {availableRates.length > 1 && (
              <div className="tweak-row">
                <label className="tweak-label">{t('采样率')}</label>
                <div className="tweak-options">
                  {availableRates.map(r => (
                    <button key={r} className={`tweak-option ${sampleRate === r ? 'active' : ''}`}
                      onClick={() => setSampleRate(r)}>
                      {r >= 1000 ? (r / 1000) + 'kHz' : r + 'Hz'}
                    </button>
                  ))}
                </div>
              </div>
            )}
            <div className="tweak-row">
              <label className="tweak-label">{t('语速')} · <span className="text-mono">{speed.toFixed(2)}x</span></label>
              <input type="range" className="slider" min="0.5" max="2" step="0.05"
                value={speed} onChange={e => setSpeed(+e.target.value)}/>
            </div>
            <div className="tweak-row">
              <label className="tweak-label">{t('音高')} · <span className="text-mono">{pitch.toFixed(2)}x</span></label>
              <input type="range" className="slider" min="0.5" max="2" step="0.05"
                value={pitch} onChange={e => setPitch(+e.target.value)}/>
            </div>
            <div className="tweak-row">
              <label className="tweak-label">{t('输出格式')}</label>
              <div className="tweak-options">
                {['wav', 'pcm'].map(f => (
                  <button key={f} className={`tweak-option ${format === f ? 'active' : ''}`}
                    onClick={() => setFormat(f)}>{f.toUpperCase()}</button>
                ))}
              </div>
            </div>
            <div className="tweak-row">
              <label className="tweak-label">{t('合成模式')}</label>
              <div className="tweak-options">
                <button className={`tweak-option ${!streaming ? 'active' : ''}`}
                  onClick={() => setStreaming(false)}>{t('一次性')}</button>
                <button className={`tweak-option ${streaming ? 'active' : ''}`}
                  onClick={() => setStreaming(true)}>{t('流式')}</button>
              </div>
            </div>
          </div>

          <div>
            <div className="section-label">API 端点</div>
            <code style={{
              display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11,
              background: 'var(--bg-1)', padding: 10, borderRadius: 6,
              color: 'var(--text-dim)', border: '1px solid var(--border)',
            }}>
              POST /v1/tts/synthesize<br/>WS /v1/tts/stream
            </code>
          </div>
        </div>
      </div>
      <window.ResourceBar/>
    </div>
  );
}

window.TTSTryPage = TTSTryPage;
