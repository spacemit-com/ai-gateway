// VAD 试用页 —— 录音/上传 → 语音段检测
const { useState: useStateV, useRef: useRefV, useEffect: useEffectV } = React;

function VADTryPage({ model, onBack }) {
  const { Icon, vadApi, t } = window;
  const [audioUrl, setAudioUrl] = useStateV(null);
  const [result, setResult] = useStateV(null);
  const [processing, setProcessing] = useStateV(false);
  const [error, setError] = useStateV('');
  const [recording, setRecording] = useStateV(false);
  const [elapsed, setElapsed] = useStateV(0);
  const [levels, setLevels] = useStateV(Array(48).fill(6));
  const [mode, setMode] = useStateV('file');
  const [streamEvents, setStreamEvents] = useStateV([]);
  const [liveSegments, setLiveSegments] = useStateV([]);
  const currentSpeechRef = useRefV(null);
  const wsRef = useRefV(null);
  const processorRef = useRefV(null);

  const recorderRef = useRefV(null);
  const streamRef = useRefV(null);
  const chunksRef = useRefV([]);
  const analyserRef = useRefV(null);
  const audioCtxRef = useRefV(null);
  const rafRef = useRefV(null);
  const startTimeRef = useRefV(0);

  const decodeToPcm = async (blob) => {
    const arrayBuf = await blob.arrayBuffer();
    const decodeCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
    try {
      const audioBuf = await decodeCtx.decodeAudioData(arrayBuf);
      const f32 = audioBuf.getChannelData(0);
      const pcm = new Int16Array(f32.length);
      for (let i = 0; i < f32.length; i++) {
        pcm[i] = Math.max(-32768, Math.min(32767, f32[i] * 32768));
      }
      return new Blob([pcm.buffer], { type: 'audio/pcm' });
    } finally {
      decodeCtx.close().catch(() => {});
    }
  };

  const doSegment = async (blob) => {
    setProcessing(true); setError(''); setResult(null);
    try {
      const res = await vadApi.segments(blob, { sample_rate: 16000 });
      setResult(res);
      const segs = res.segments || [];
      const rtf = res.duration_ms > 0 ? (res.processing_ms / res.duration_ms).toFixed(3) : '-';
      window.historyStore?.push({
        model: model.name, type: 'VAD',
        input: (res.duration_ms / 1000).toFixed(1) + 's 音频',
        output: segs.length > 0
          ? segs.length + ' 段语音 · 占比 ' + (res.speech_ratio * 100).toFixed(0) + '%'
          : '未检测到语音',
        latency: Math.round(res.processing_ms || 0),
      });
    } catch (e) {
      setError(e.message + ' — 请确认 /v1/vad/segments 可访问');
    }
    setProcessing(false);
  };

  const startRecording = async () => {
    try {
      setResult(null); setError(''); setAudioUrl(null);
      if (mode === 'realtime') {
        setStreamEvents([]); setLiveSegments([]);
        currentSpeechRef.current = null;
      }
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000 } });
      streamRef.current = stream;

      const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioCtxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);

      const analyser = ctx.createAnalyser();
      analyser.fftSize = 128;
      src.connect(analyser);
      analyserRef.current = analyser;
      const data = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        analyser.getByteFrequencyData(data);
        const arr = [];
        const step = Math.floor(data.length / 48);
        for (let i = 0; i < 48; i++) {
          arr.push(Math.max(4, (data[i * step] || 0) * 0.4));
        }
        setLevels(arr);
        rafRef.current = requestAnimationFrame(tick);
      };
      tick();

      if (mode === 'realtime') {
        const wsUrl = vadApi.streamUrl() + '?sample_rate=16000';
        const ws = new WebSocket(wsUrl);
        wsRef.current = ws;
        ws.onmessage = (e) => {
          try {
            const m = JSON.parse(e.data);
            if (m.type === 'ready' || m.type === 'error') {
              if (m.type === 'error') setError(m.message);
              return;
            }
            const ev = { ...m, received_at: Date.now() };
            setStreamEvents(prev => [...prev, ev]);
            if (m.event === 'speech_start') {
              currentSpeechRef.current = { start_ms: m.timestamp_ms, probability: m.probability };
            } else if (m.event === 'speech_end' && currentSpeechRef.current) {
              const speech = currentSpeechRef.current;
              currentSpeechRef.current = null;
              setLiveSegments(prev => [...prev, {
                start_ms: speech.start_ms,
                end_ms: m.timestamp_ms,
                confidence: m.probability,
              }]);
            }
          } catch {}
        };
        ws.onerror = () => setError(t('无法连接视觉服务'));

        const processor = ctx.createScriptProcessor(4096, 1, 1);
        processorRef.current = processor;
        processor.onaudioprocess = (e) => {
          if (!ws || ws.readyState !== 1) return;
          const f32 = e.inputBuffer.getChannelData(0);
          const buf = new ArrayBuffer(f32.length * 2);
          const i16 = new Int16Array(buf);
          for (let i = 0; i < f32.length; i++) {
            i16[i] = Math.max(-32768, Math.min(32767, f32[i] * 32768));
          }
          ws.send(buf);
        };
        src.connect(processor);
        processor.connect(ctx.destination);
      } else {
        const rec = new MediaRecorder(stream);
        recorderRef.current = rec;
        chunksRef.current = [];
        rec.ondataavailable = (e) => {
          if (e.data.size > 0) chunksRef.current.push(e.data);
        };
        rec.onstop = async () => {
          const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
          setAudioUrl(URL.createObjectURL(blob));
          try {
            const pcmBlob = await decodeToPcm(blob);
            doSegment(pcmBlob);
          } catch (e) {
            console.warn('WebM→PCM decode failed, sending raw blob:', e);
            doSegment(blob);
          }
        };
        rec.start(250);
      }

      startTimeRef.current = Date.now();
      setRecording(true);
      const timer = setInterval(() => {
        setElapsed((Date.now() - startTimeRef.current) / 1000);
      }, 100);
      streamRef.current._timer = timer;
    } catch (e) {
      alert('无法访问麦克风：' + e.message);
    }
  };

  const stopRecording = () => {
    if (recorderRef.current) {
      clearInterval(recorderRef.current._timer);
      recorderRef.current.stop();
    }
    if (streamRef.current) {
      if (streamRef.current._timer) clearInterval(streamRef.current._timer);
      streamRef.current.getTracks().forEach(t => t.stop());
    }
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (wsRef.current && wsRef.current.readyState === 1) {
      try { wsRef.current.send(JSON.stringify({ type: 'end' })); } catch {}
      wsRef.current.close();
    }
    wsRef.current = null;
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (audioCtxRef.current) {
      audioCtxRef.current.close().catch(() => {});
      audioCtxRef.current = null;
    }
    setRecording(false);
    setLevels(Array(48).fill(6));
  };

  const onFile = async (e) => {
    const f = e.target.files[0]; if (!f) return;
    setAudioUrl(URL.createObjectURL(f));
    doSegment(f);
  };

  useEffectV(() => {
    const s = window.pageStateStore?.load('vad', model.id);
    if (s?.result) setResult(s.result);
  }, [model.id]);

  useEffectV(() => {
    if (!result) return;
    window.pageStateStore?.save('vad', model.id, { result });
  }, [result, model.id]);

  const [loadError, setLoadError] = useStateV('');
  useEffectV(() => {
    if (model.status !== 'ready') {
      setLoadError('模型加载中…');
      vadApi.loadModel(model.id)
        .then(() => setLoadError(''))
        .catch(e => {
          if (e.message && e.message.includes('409')) setLoadError('');
          else setLoadError('模型加载失败: ' + e.message);
        });
    }
  }, []);

  useEffectV(() => () => stopRecording(), []);

  const segments = result?.segments || [];
  const rtf = result && result.duration_ms > 0 ? (result.processing_ms / result.duration_ms) : null;

  return (
    <div className="main-inner try-page">
      <div className="back-link" onClick={onBack}>
        {Icon.arrowLeft({ size: 14 })}<span>{t('返回模型选择')}</span>
      </div>

      <div className="page-header">
        <div>
          <div className="page-title">{model.name}</div>
          <div className="page-sub">VAD · {model.id} · POST /v1/vad/segments{mode === 'realtime' ? ' · WS /v1/vad/stream' : ''}</div>
        </div>
        <span className={`chip ${!loadError ? 'chip-accent' : ''}`}>
          <span className="status-dot" style={{ background: !loadError ? 'var(--accent)' : 'var(--text-low)'}}/>
          {loadError || t('就绪')}
        </span>
      </div>

      <div className="try-layout">
        <div className="try-main">
          <div className="section-label">{t('音频输入')}</div>
          <div className="waveform">
            {levels.map((h, i) => (
              <div key={i} className="wave-bar" style={{ height: `${Math.min(100, h)}%` }}/>
            ))}
          </div>

          <div className="flex gap-3 mt-4" style={{ alignItems: 'center' }}>
            {!recording ? (
              <button className="btn-primary" onClick={startRecording}>
                {Icon.mic({ size: 14 })}<span>{mode === 'realtime' ? t('开始实时检测') : t('开始录音')}</span>
              </button>
            ) : (
              <button className="btn-primary" onClick={stopRecording}
                style={{ background: 'var(--danger)', color: '#fff' }}>
                <span style={{ width:10, height:10, background:'#fff', borderRadius:2, display:'inline-block' }}/>
                <span>{mode === 'realtime' ? t('停止检测') : t('停止录音')} · {elapsed.toFixed(1)}s</span>
              </button>
            )}
            {mode === 'file' && (
              <label className="btn-ghost" style={{ cursor: 'pointer' }}>
                <input type="file" accept="audio/*" onChange={onFile} style={{ display: 'none' }}/>
                {Icon.upload({ size: 14 })} <span style={{ marginLeft: 6 }}>{t('上传音频')}</span>
              </label>
            )}
            {mode === 'realtime' && recording && (
              <span className="flex gap-2" style={{ alignItems: 'center' }}>
                <span className="pulse-dot"/><span className="text-dim text-xs">{t('实时推流中，请说话…')}</span>
              </span>
            )}
            {audioUrl && mode === 'file' && <audio src={audioUrl} controls style={{ height: 32, flex: 1 }}/>}
          </div>

          {error && <div className="mt-4" style={{
            background: 'oklch(0.70 0.18 25 / .1)', border: '1px solid oklch(0.70 0.18 25 / .3)',
            borderRadius: 8, padding: 12, color: 'var(--danger)', fontSize: 12,
            fontFamily: 'var(--font-mono)',
          }}>{error}</div>}

          <div className="section-label mt-6">{t('检测结果')}</div>
          <div style={{
            background: 'var(--bg-1)', border: '1px solid var(--border)',
            borderRadius: 10, padding: 18, minHeight: 120,
          }}>
            {processing && <span className="text-dim">{t('检测中…')}</span>}

            {mode === 'realtime' && streamEvents.length > 0 && (
              <div style={{ maxHeight: 200, overflowY: 'auto', background: 'var(--bg-2)',
                            border: '1px solid var(--border)', borderRadius: 8, padding: 8, marginBottom: 16 }}>
                {streamEvents.filter(ev => ev.event === 'speech_start' || ev.event === 'speech_end').map((ev, i) => (
                  <div key={i} style={{ display: 'flex', gap: 10, fontSize: 11, fontFamily: 'var(--font-mono)',
                                        padding: '3px 0', borderBottom: '1px solid var(--border)' }}>
                    <span className="text-dim">{(ev.timestamp_ms / 1000).toFixed(2)}s</span>
                    <span className={`chip ${ev.event === 'speech_start' ? 'chip-accent' : ''}`}>{ev.event}</span>
                    <span className="text-dim">p={ev.probability?.toFixed(3)}</span>
                  </div>
                ))}
              </div>
            )}

            {mode === 'realtime' && liveSegments.length > 0 && (
              <>
                <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span className="chip chip-accent">
                    <span className="status-dot" style={{ background: 'var(--accent)' }}/>
                    {liveSegments.length + ' ' + t('段语音')}
                  </span>
                </div>
                <div style={{ position: 'relative', height: 32, background: 'var(--bg-2)',
                              border: '1px solid var(--border)', borderRadius: 6, marginBottom: 16, overflow: 'hidden' }}>
                  {liveSegments.map((seg, i) => {
                    const totalMs = elapsed * 1000;
                    const left = totalMs > 0 ? (seg.start_ms / totalMs * 100) : 0;
                    const width = totalMs > 0 ? ((seg.end_ms - seg.start_ms) / totalMs * 100) : 0;
                    return (
                      <div key={i} title={`${(seg.start_ms/1000).toFixed(2)}s - ${(seg.end_ms/1000).toFixed(2)}s`}
                        style={{
                          position: 'absolute', top: 4, bottom: 4,
                          left: left + '%', width: Math.max(width, 0.5) + '%',
                          background: 'var(--accent)', borderRadius: 3, opacity: 0.7 + (seg.confidence || 0) * 0.3,
                        }}/>
                    );
                  })}
                  <div style={{ position: 'absolute', bottom: 2, right: 6, fontSize: 9,
                                fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>
                    {elapsed.toFixed(1)}s
                  </div>
                </div>
                <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                  <table className="dm-table">
                    <thead><tr><th>#</th><th>{t('开始')}</th><th>{t('结束')}</th><th>{t('时长')}</th><th>{t('置信度')}</th></tr></thead>
                    <tbody>
                      {liveSegments.map((seg, i) => (
                        <tr key={i}>
                          <td className="text-mono text-xs">{i + 1}</td>
                          <td className="text-mono text-xs">{(seg.start_ms / 1000).toFixed(2)}s</td>
                          <td className="text-mono text-xs">{(seg.end_ms / 1000).toFixed(2)}s</td>
                          <td className="text-mono text-xs">{((seg.end_ms - seg.start_ms) / 1000).toFixed(2)}s</td>
                          <td className="text-mono text-xs">{seg.confidence != null ? (seg.confidence * 100).toFixed(0) + '%' : '-'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}

            {!processing && !result && mode === 'file' &&
              <span className="text-dim text-mono text-sm">{t('等待输入音频…')}</span>}
            {mode === 'realtime' && !recording && streamEvents.length === 0 &&
              <span className="text-dim text-mono text-sm">{t('点击"开始实时检测"后对着麦克风说话')}</span>}
            {!processing && result && (
              <div>
                <div style={{ marginBottom: 16, display: 'flex', alignItems: 'center', gap: 10 }}>
                  <span className={`chip ${segments.length > 0 ? 'chip-accent' : ''}`}>
                    <span className="status-dot" style={{ background: segments.length > 0 ? 'var(--accent)' : 'var(--text-low)' }}/>
                    {segments.length > 0 ? segments.length + ' ' + t('段语音') : t('未检测到语音')}
                  </span>
                  {result.speech_ratio != null && (
                    <span className="text-mono text-xs text-dim">{t('语音占比')} {(result.speech_ratio * 100).toFixed(1)}%</span>
                  )}
                </div>

                {segments.length > 0 && (
                  <>
                    <div style={{ position: 'relative', height: 32, background: 'var(--bg-2)',
                                  border: '1px solid var(--border)', borderRadius: 6, marginBottom: 16, overflow: 'hidden' }}>
                      {segments.map((seg, i) => {
                        const left = result.duration_ms > 0 ? (seg.start_ms / result.duration_ms * 100) : 0;
                        const width = result.duration_ms > 0 ? ((seg.end_ms - seg.start_ms) / result.duration_ms * 100) : 0;
                        return (
                          <div key={i} title={`${(seg.start_ms/1000).toFixed(2)}s - ${(seg.end_ms/1000).toFixed(2)}s`}
                            style={{
                              position: 'absolute', top: 4, bottom: 4,
                              left: left + '%', width: Math.max(width, 0.5) + '%',
                              background: 'var(--accent)', borderRadius: 3, opacity: 0.7 + (seg.confidence || 0) * 0.3,
                            }}/>
                        );
                      })}
                      <div style={{ position: 'absolute', bottom: 2, right: 6, fontSize: 9,
                                    fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>
                        {(result.duration_ms / 1000).toFixed(1)}s
                      </div>
                    </div>

                    <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
                      <table className="dm-table">
                        <thead><tr><th>#</th><th>{t('开始')}</th><th>{t('结束')}</th><th>{t('时长')}</th><th>{t('置信度')}</th></tr></thead>
                        <tbody>
                          {segments.map((seg, i) => (
                            <tr key={i}>
                              <td className="text-mono text-xs">{i + 1}</td>
                              <td className="text-mono text-xs">{(seg.start_ms / 1000).toFixed(2)}s</td>
                              <td className="text-mono text-xs">{(seg.end_ms / 1000).toFixed(2)}s</td>
                              <td className="text-mono text-xs">{((seg.end_ms - seg.start_ms) / 1000).toFixed(2)}s</td>
                              <td className="text-mono text-xs">{seg.confidence != null ? (seg.confidence * 100).toFixed(0) + '%' : '-'}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </>
                )}

                <div className="card-grid mt-4" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))' }}>
                  <div className="stat-card">
                    <div className="stat-label">{t('音频时长')}</div>
                    <div className="stat-value">{(result.duration_ms / 1000).toFixed(2)}<span className="unit">s</span></div>
                  </div>
                  <div className="stat-card">
                    <div className="stat-label">{t('处理耗时')}</div>
                    <div className="stat-value">{result.processing_ms.toFixed(1)}<span className="unit">ms</span></div>
                  </div>
                  {rtf != null && (
                    <div className="stat-card">
                      <div className="stat-label">RTF</div>
                      <div className="stat-value">{rtf.toFixed(3)}</div>
                    </div>
                  )}
                  <div className="stat-card">
                    <div className="stat-label">{t('语音段数')}</div>
                    <div className="stat-value">{segments.length}</div>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <div className="try-side">
          <div>
            <div className="section-label">{t('检测模式')}</div>
            <div className="tweak-options">
              <button className={`tweak-option ${mode === 'file' ? 'active' : ''}`}
                onClick={() => setMode('file')}>{t('文件上传')}</button>
              <button className={`tweak-option ${mode === 'realtime' ? 'active' : ''}`}
                onClick={() => setMode('realtime')}>{t('实时检测')}</button>
            </div>
          </div>
          <div>
            <div className="section-label">{t('模型信息')}</div>
            <div className="tweak-row">
              <span className="tweak-label">{t('模型')} ID</span>
              <span className="text-mono text-xs">{model.id}</span>
            </div>
            <div className="tweak-row">
              <span className="tweak-label">{t('类型')}</span>
              <span className="chip">VAD</span>
            </div>
          </div>
          <div>
            <div className="section-label">API 端点</div>
            <code style={{
              display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11,
              background: 'var(--bg-1)', padding: 10, borderRadius: 6,
              color: 'var(--text-dim)', border: '1px solid var(--border)',
            }}>
              POST /v1/vad/segments<br/>WS /v1/vad/stream
            </code>
          </div>
        </div>
      </div>
      <window.ResourceBar/>
    </div>
  );
}

window.VADTryPage = VADTryPage;
