// ASR 试用页 —— 录音/上传 → 转写
const { useState: useStateA, useRef: useRefA, useEffect: useEffectA } = React;

function ASRTryPage({ model, onBack }) {
  const { Icon, asrApi, API_BASES, t } = window;
  const [recording, setRecording] = useStateA(false);
  const [audioUrl, setAudioUrl] = useStateA(null);
  const [transcript, setTranscript] = useStateA('');
  const [partial, setPartial] = useStateA('');
  const [processing, setProcessing] = useStateA(false);
  const [elapsed, setElapsed] = useStateA(0);
  const [levels, setLevels] = useStateA(Array(48).fill(6));
  const [language, setLanguage] = useStateA('auto');
  const [enablePunc, setEnablePunc] = useStateA(true);
  const [streaming, setStreaming] = useStateA(true);
  const [recogMeta, setRecogMeta] = useStateA(null);
  const [langList, setLangList] = useStateA([
    { code: 'auto', label: '自动检测' }, { code: 'zh', label: '中文' },
    { code: 'en', label: 'English' }, { code: 'ja', label: '日本語' },
  ]);

  const recorderRef = useRefA(null);
  const streamRef = useRefA(null);
  const chunksRef = useRefA([]);
  const wsRef = useRefA(null);
  const analyserRef = useRefA(null);
  const audioCtxRef = useRefA(null);
  const processorRef = useRefA(null);
  const rafRef = useRefA(null);
  const startTimeRef = useRefA(0);
  const wsHandledRef = useRefA(false);

  const startRecording = async () => {
    try {
      setTranscript(''); setPartial(''); setAudioUrl(null); setRecogMeta(null); wsHandledRef.current = false;
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { sampleRate: 16000 } });
      streamRef.current = stream;

      const ctx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      audioCtxRef.current = ctx;
      const src = ctx.createMediaStreamSource(stream);

      // Waveform visualization
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

      // MediaRecorder for non-streaming fallback + playback
      const rec = new MediaRecorder(stream);
      recorderRef.current = rec;
      chunksRef.current = [];
      rec.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };
      rec.onstop = async () => {
        const blob = new Blob(chunksRef.current, { type: 'audio/webm' });
        setAudioUrl(URL.createObjectURL(blob));

        // If WS was not used (non-streaming or WS failed), do POST recognize
        if (!wsHandledRef.current) {
            setProcessing(true);
            try {
              // Decode compressed audio (WebM/Opus) to PCM int16 WAV
              const arrayBuf = await blob.arrayBuffer();
              const decodeCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
              const audioBuf = await decodeCtx.decodeAudioData(arrayBuf);
              const f32 = audioBuf.getChannelData(0);
              const pcm = new Int16Array(f32.length);
              for (let i = 0; i < f32.length; i++) {
                pcm[i] = Math.max(-32768, Math.min(32767, f32[i] * 32768));
              }
              decodeCtx.close();
              const pcmBlob = new Blob([pcm.buffer], { type: 'audio/pcm' });

              const t0 = Date.now();
              const res = await asrApi.recognize(pcmBlob, {
                model: model.id, language, punctuation: enablePunc, sample_rate: 16000,
              });
              const clientMs = Date.now() - t0;
              setTranscript(res.text || '[无返回]');
              setRecogMeta({
                processing_ms: res.processing_ms || clientMs,
                duration_ms: res.duration_ms || 0,
                rtf: res.rtf || (res.duration_ms > 0 ? res.processing_ms / res.duration_ms : 0),
                latency: clientMs,
              });
              if (res.text) {
                window.historyStore?.push({
                  model: model.name, type: 'ASR',
                  input: ((Date.now() - startTimeRef.current) / 1000).toFixed(1) + 's 音频',
                  output: (res.text || '').slice(0, 60),
                  latency: clientMs,
                });
              }
            } catch (e) {
              setTranscript('[识别失败] ' + e.message);
            }
            setProcessing(false);
        }
      };
      rec.start(250);

      // WebSocket streaming: session → connect → send PCM
      if (streaming) {
        try {
          const sess = await asrApi.createSession({
            model: model.id, language, sample_rate: 16000, partial_results: true,
          });
          const wsUrl = asrApi.streamUrl()
            + '?session_id=' + encodeURIComponent(sess.session_id)
            + '&language=' + language
            + '&sample_rate=16000&partial=true';
          const ws = new WebSocket(wsUrl);
          wsRef.current = ws;

          ws.onmessage = (e) => {
            try {
              const m = JSON.parse(e.data);
              if (m.type === 'partial')      { wsHandledRef.current = true; setPartial(m.text || ''); }
              if (m.type === 'sentence_end') { wsHandledRef.current = true; setTranscript(t => t + (m.text || '') + ' '); setPartial(''); }
              if (m.type === 'final')        { wsHandledRef.current = true; setTranscript(t => t + (m.text || '')); setPartial(''); }
            } catch {}
          };
          ws.onerror = () => { console.warn('[asr-ws] error, will fallback to POST'); };

          // ScriptProcessor: send PCM int16 frames over WS
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
        } catch (e) {
          console.warn('[asr-ws] session/connect failed:', e.message);
        }
      }

      startTimeRef.current = Date.now();
      setRecording(true);
      const timer = setInterval(() => {
        setElapsed((Date.now() - startTimeRef.current) / 1000);
      }, 100);
      recorderRef.current._timer = timer;
    } catch (e) {
      alert('无法访问麦克风：' + e.message);
    }
  };

  const stopRecording = () => {
    if (recorderRef.current) {
      clearInterval(recorderRef.current._timer);
      recorderRef.current.stop();
    }
    if (streamRef.current) streamRef.current.getTracks().forEach(t => t.stop());
    if (rafRef.current) cancelAnimationFrame(rafRef.current);
    if (processorRef.current) {
      processorRef.current.disconnect();
      processorRef.current = null;
    }
    if (wsRef.current && wsRef.current.readyState === 1) {
      try { wsRef.current.send(JSON.stringify({ type: 'end' })); } catch {}
      wsRef.current.close();
    }
    wsRef.current = null;
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
    setProcessing(true); setTranscript(''); setPartial(''); setRecogMeta(null);
    const t0 = Date.now();
    try {
      // Decode any audio format to PCM int16 via AudioContext
      const arrayBuf = await f.arrayBuffer();
      const decodeCtx = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
      const audioBuf = await decodeCtx.decodeAudioData(arrayBuf);
      const f32 = audioBuf.getChannelData(0);
      const pcm = new Int16Array(f32.length);
      for (let i = 0; i < f32.length; i++) {
        pcm[i] = Math.max(-32768, Math.min(32767, f32[i] * 32768));
      }
      decodeCtx.close();
      const pcmBlob = new Blob([pcm.buffer], { type: 'audio/pcm' });
      const res = await asrApi.recognize(pcmBlob, { model: model.id, language, punctuation: enablePunc, sample_rate: 16000 });
      const clientMs = Date.now() - t0;
      setTranscript(res.text || JSON.stringify(res));
      setRecogMeta({
        processing_ms: res.processing_ms || clientMs,
        duration_ms: res.duration_ms || 0,
        rtf: res.rtf || (res.duration_ms > 0 ? res.processing_ms / res.duration_ms : 0),
        latency: clientMs,
      });
      if (res.text) {
        window.historyStore?.push({
          model: model.name, type: 'ASR',
          input: '上传音频 ' + f.name,
          output: (res.text || '').slice(0, 60),
          latency: clientMs,
        });
      }
    } catch (err) {
      setTranscript('[识别失败] ' + err.message);
    }
    setProcessing(false);
  };

  useEffectA(() => {
    asrApi.languages().then(res => {
      const langs = res.languages || res;
      if (Array.isArray(langs) && langs.length > 0) {
        const list = [{ code: 'auto', label: '自动检测' }];
        for (const l of langs) {
          const code = typeof l === 'string' ? l : l.code || l.id;
          const label = typeof l === 'string' ? l : l.name || l.label || l.code;
          if (code !== 'auto') list.push({ code, label });
        }
        setLangList(list);
      }
    }).catch(() => {});
  }, []);

  useEffectA(() => {
    const s = window.pageStateStore?.load('asr', model.id);
    if (s?.transcript) setTranscript(s.transcript);
    if (s?.recogMeta) setRecogMeta(s.recogMeta);
  }, [model.id]);

  useEffectA(() => {
    if (!transcript) return;
    window.pageStateStore?.save('asr', model.id, { transcript, recogMeta });
  }, [transcript, recogMeta, model.id]);

  const [loadError, setLoadError] = useStateA('');
  useEffectA(() => {
    if (model.status !== 'ready') {
      setLoadError('模型加载中…');
      asrApi.loadModel(model.id)
        .then(() => setLoadError(''))
        .catch(e => {
          if (e.message && e.message.includes('409')) setLoadError('');
          else setLoadError('模型加载失败: ' + e.message);
        });
    }
  }, []);

  useEffectA(() => () => stopRecording(), []);

  return (
    <div className="main-inner try-page">
      <div className="back-link" onClick={onBack}>
        {Icon.arrowLeft({ size: 14 })}<span>{t('返回模型选择')}</span>
      </div>

      <div className="page-header">
        <div>
          <div className="page-title">{model.name}</div>
          <div className="page-sub">ASR · {model.id} · POST /v1/asr/recognize</div>
        </div>
        <span className={`chip ${model.status === 'ready' || !loadError ? 'chip-accent' : ''}`}>
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
                {Icon.mic({ size: 14 })}<span>{t('开始录音')}</span>
              </button>
            ) : (
              <button className="btn-primary" onClick={stopRecording}
                style={{ background: 'var(--danger)', color: '#fff' }}>
                <span style={{ width:10, height:10, background:'#fff', borderRadius:2, display:'inline-block' }}/>
                <span>{t('停止录音')} · {elapsed.toFixed(1)}s</span>
              </button>
            )}
            <label className="btn-ghost" style={{ cursor: 'pointer' }}>
              <input type="file" accept="audio/*" onChange={onFile} style={{ display: 'none' }}/>
              {Icon.upload({ size: 14 })} <span style={{ marginLeft: 6 }}>{t('上传音频')}</span>
            </label>
            {audioUrl && <audio src={audioUrl} controls style={{ height: 32, flex: 1 }}/>}
          </div>

          <div className="section-label mt-6">{t('识别结果')}</div>
          <div style={{
            background: 'var(--bg-1)', border: '1px solid var(--border)',
            borderRadius: 10, padding: 18, minHeight: 140,
            fontSize: 15, lineHeight: 1.7, letterSpacing: '0.2px',
          }}>
            {processing && <span className="text-dim">{t('识别中…')}</span>}
            {!processing && !transcript && !partial &&
              <span className="text-dim text-mono text-sm">{t('等待输入音频…')}</span>}
            {transcript && <span>{transcript}</span>}
            {partial && <span style={{ color: 'var(--text-dim)', fontStyle: 'italic' }}> {partial}</span>}
          </div>

          {transcript && (
            <div className="flex gap-2 mt-4">
              <button className="btn-ghost" onClick={() => window.copyText(transcript)}>{t('复制文本')}</button>
              <button className="btn-ghost" onClick={() => { setTranscript(''); setRecogMeta(null); window.pageStateStore?.clear('asr', model.id); }}>{t('清空')}</button>
            </div>
          )}

          {recogMeta && (
            <>
              <div className="section-label mt-6">{t('性能指标')}</div>
              <div className="card-grid" style={{ gridTemplateColumns: 'repeat(auto-fill, minmax(150px, 1fr))' }}>
                {recogMeta.duration_ms > 0 && (
                  <div className="stat-card">
                    <div className="stat-label">{t('音频时长')}</div>
                    <div className="stat-value">{(recogMeta.duration_ms / 1000).toFixed(2)}<span className="unit">s</span></div>
                  </div>
                )}
                <div className="stat-card">
                  <div className="stat-label">{t('处理耗时')}</div>
                  <div className="stat-value">{Math.round(recogMeta.processing_ms)}<span className="unit">ms</span></div>
                </div>
                {recogMeta.rtf > 0 && (
                  <div className="stat-card">
                    <div className="stat-label">RTF</div>
                    <div className="stat-value">{recogMeta.rtf.toFixed(3)}</div>
                  </div>
                )}
                <div className="stat-card">
                  <div className="stat-label">{t('端到端延迟')}</div>
                  <div className="stat-value">{Math.round(recogMeta.latency)}<span className="unit">ms</span></div>
                </div>
              </div>
            </>
          )}
        </div>

        <div className="try-side">
          <div>
            <div className="section-label">{t('参数配置')}</div>
            <div className="tweak-row">
              <label className="tweak-label">{t('识别模式')}</label>
              <div className="tweak-options">
                <button className={`tweak-option ${streaming ? 'active' : ''}`} onClick={() => setStreaming(true)}>{t('流式')}</button>
                <button className={`tweak-option ${!streaming ? 'active' : ''}`} onClick={() => setStreaming(false)}>{t('一次性')}</button>
              </div>
            </div>
            <div className="tweak-row">
              <label className="tweak-label">{t('语言')}</label>
              <select className="select" value={language} onChange={e => setLanguage(e.target.value)}>
                {langList.map(l => <option key={l.code} value={l.code}>{l.label}</option>)}
              </select>
            </div>
            <div className="tweak-row">
              <label className="tweak-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                <input type="checkbox" checked={enablePunc} onChange={e => setEnablePunc(e.target.checked)}/>
                <span>{t('自动标点（ITN）')}</span>
              </label>
            </div>
          </div>

          <div>
            <div className="section-label">API 端点</div>
            <code style={{
              display: 'block', fontFamily: 'var(--font-mono)', fontSize: 11,
              background: 'var(--bg-1)', padding: 10, borderRadius: 6,
              color: 'var(--text-dim)', border: '1px solid var(--border)',
              wordBreak: 'break-all',
            }}>
              POST /v1/asr/recognize<br/>
              WS&nbsp;&nbsp; /v1/asr/stream
            </code>
          </div>
        </div>
      </div>
      <window.ResourceBar/>
    </div>
  );
}

window.ASRTryPage = ASRTryPage;
