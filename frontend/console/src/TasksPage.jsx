// 异步任务 —— ASR 识别 + TTS 合成（持久化到 localStorage）
const { useState: useStateTask, useEffect: useEffectTask, useRef: useRefTask } = React;

const TASKS_KEY = 'spacemit-ai-gateway-tasks';
function loadTasks() {
  try { return JSON.parse(localStorage.getItem(TASKS_KEY)) || []; } catch { return []; }
}
function saveTasks(tasks) {
  const serializable = tasks.map(({ file, ...rest }) => rest);
  localStorage.setItem(TASKS_KEY, JSON.stringify(serializable));
}
function _patchTaskInStorage(id, updates) {
  try {
    const tasks = loadTasks();
    const idx = tasks.findIndex(t => t.id === id);
    if (idx >= 0) {
      Object.assign(tasks[idx], updates);
      localStorage.setItem(TASKS_KEY, JSON.stringify(tasks));
      window.dispatchEvent(new Event('tasks-updated'));
    }
  } catch {}
}
function _processAsrBatch(entries, files, lang) {
  (async () => {
    for (let i = 0; i < entries.length; i++) {
      _patchTaskInStorage(entries[i].id, { status: 'running' });
      try {
        const t0 = Date.now();
        const res = await window.asrApi.recognize(files[i], { language: lang !== 'auto' ? lang : undefined });
        const ms = Date.now() - t0;
        _patchTaskInStorage(entries[i].id, {
          status: 'done',
          result: res.text || JSON.stringify(res),
          meta: { processing_ms: res.processing_ms || ms, duration_ms: res.duration_ms || 0, rtf: res.rtf || 0 },
        });
      } catch (e) {
        _patchTaskInStorage(entries[i].id, { status: 'failed', error: e.message });
      }
    }
  })();
}

function TasksPage() {
  const { asrApi, ttsApi, t } = window;
  const [tasks, setTasks] = useStateTask(() => loadTasks());

  const [asrMode, setAsrMode] = useStateTask('file');
  const [asrUrl, setAsrUrl] = useStateTask('');
  const [asrFiles, setAsrFiles] = useStateTask([]);
  const [asrLang, setAsrLang] = useStateTask('auto');
  const [asrSubmitting, setAsrSubmitting] = useStateTask(false);

  const [ttsText, setTtsText] = useStateTask('');
  const [ttsVoice, setTtsVoice] = useStateTask('');
  const [ttsFormat, setTtsFormat] = useStateTask('wav');
  const [ttsSubmitting, setTtsSubmitting] = useStateTask(false);
  const [ttsMode, setTtsMode] = useStateTask('sync');
  const [ttsModels, setTtsModels] = useStateTask([]);
  const [ttsModel, setTtsModel] = useStateTask('');

  const [error, setError] = useStateTask('');
  const [success, setSuccess] = useStateTask('');
  const intervalRef = useRefTask(null);
  const fileRef = useRefTask(null);

  useEffectTask(() => {
    ttsApi.listModels().then(res => {
      const list = res.models || res || [];
      setTtsModels(list);
      const loaded = list.filter(m => m.loaded || m.status === 'loaded');
      const def = loaded.find(m => m.is_default) || loaded[0];
      if (def) setTtsModel(def.id || def.name || '');
    }).catch(() => {});
  }, []);

  const skipSaveRef = useRefTask(false);
  useEffectTask(() => {
    if (skipSaveRef.current) { skipSaveRef.current = false; return; }
    saveTasks(tasks);
  }, [tasks]);

  useEffectTask(() => {
    const sync = () => { skipSaveRef.current = true; setTasks(loadTasks()); };
    window.addEventListener('tasks-updated', sync);
    return () => window.removeEventListener('tasks-updated', sync);
  }, []);

  useEffectTask(() => {
    if (success) {
      const t = setTimeout(() => setSuccess(''), 3000);
      return () => clearTimeout(t);
    }
  }, [success]);

  const genId = () => Date.now().toString(36) + Math.random().toString(36).slice(2, 6);

  const submitAsrFile = () => {
    if (asrFiles.length === 0) return;
    setError('');
    const entries = asrFiles.map(f => ({
      id: genId(), type: 'asr', mode: 'file', status: 'pending',
      input: f.name, result: null, error: null,
      created_at: new Date().toLocaleString(),
    }));
    const files = asrFiles.slice();
    const lang = asrLang;
    const updated = [...entries, ...loadTasks()];
    saveTasks(updated);
    setTasks(updated);
    setAsrFiles([]);
    if (fileRef.current) fileRef.current.value = '';
    _processAsrBatch(entries, files, lang);
  };

  const submitAsrUrl = async () => {
    if (!asrUrl.trim()) return;
    setAsrSubmitting(true);
    setError('');
    try {
      const body = { audio_url: asrUrl.trim() };
      if (asrLang !== 'auto') body.language = asrLang;
      const res = await asrApi.submitJob(body);
      setTasks(prev => [{
        id: res.job_id, type: 'asr', mode: 'url', status: res.status || 'pending',
        input: asrUrl.trim(), result: null, error: null,
        created_at: new Date().toLocaleString(),
      }, ...prev]);
      setAsrUrl('');
      setSuccess('ASR 任务已提交');
    } catch (e) {
      setError('ASR 提交失败: ' + e.message);
    }
    setAsrSubmitting(false);
  };

  const submitAsr = () => {
    if (asrMode === 'file') submitAsrFile();
    else submitAsrUrl();
  };

  const submitTts = async () => {
    if (!ttsText.trim()) return;
    setTtsSubmitting(true);
    setError('');
    const taskId = genId();
    const taskEntry = {
      id: taskId, type: 'tts', status: 'running',
      input: ttsText.trim().slice(0, 60) + (ttsText.trim().length > 60 ? '…' : ''),
      result: null, audioUrl: null, error: null,
      created_at: new Date().toLocaleString(),
    };
    setTasks(prev => [taskEntry, ...prev]);

    try {
      const body = { text: ttsText.trim() };
      if (ttsModel) body.model = ttsModel;
      if (ttsVoice.trim()) body.voice_id = ttsVoice.trim();
      body.response_format = ttsFormat;
      const t0 = Date.now();
      const { blob, meta } = await ttsApi.synthesize(body);
      const ms = Date.now() - t0;
      const audioUrl = URL.createObjectURL(blob);
      setTasks(prev => prev.map(tk => tk.id === taskId ? {
        ...tk, status: 'done', audioUrl, result: '合成完成',
        meta: { ...meta, latency: ms },
      } : tk));
      setTtsText('');
      setSuccess('TTS 合成完成');
    } catch (e) {
      setTasks(prev => prev.map(tk => tk.id === taskId ? { ...tk, status: 'failed', error: e.message } : tk));
      setError('TTS 合成失败: ' + e.message);
    }
    setTtsSubmitting(false);
  };

  const removeTask = (id) => {
    setTasks(prev => prev.filter(t => t.id !== id));
  };

  const cancelAsrJob = async (task) => {
    try {
      await asrApi.cancelJob(task.id);
      setTasks(prev => prev.map(tk => tk.id === task.id ? { ...tk, status: 'cancelled' } : tk));
      setSuccess('ASR 任务已取消');
    } catch (e) { setError(t('取消失败') + ': ' + e.message); }
  };

  const submitTtsAsync = async () => {
    if (!ttsText.trim()) return;
    setTtsSubmitting(true); setError('');
    try {
      const body = { text: ttsText.trim() };
      if (ttsModel) body.model = ttsModel;
      if (ttsVoice.trim()) body.voice_id = ttsVoice.trim();
      body.response_format = ttsFormat;
      const res = await ttsApi.submitTask(body);
      setTasks(prev => [{
        id: res.task_id, type: 'tts', mode: 'async', status: 'pending',
        input: ttsText.trim().slice(0, 60) + (ttsText.trim().length > 60 ? '…' : ''),
        result: null, audioUrl: null, error: null,
        created_at: new Date().toLocaleString(),
      }, ...prev]);
      setTtsText('');
      setSuccess('任务已提交，后台合成中');
    } catch (e) { setError('TTS 提交失败: ' + e.message); }
    setTtsSubmitting(false);
  };

  const cancelTtsTask = async (task) => {
    try {
      await ttsApi.cancelTask(task.id);
      setTasks(prev => prev.map(tk => tk.id === task.id ? { ...tk, status: 'cancelled' } : tk));
      setSuccess('TTS 任务已取消');
    } catch (e) { setError(t('取消失败') + ': ' + e.message); }
  };

  const downloadTtsTaskAudio = async (task) => {
    try {
      const blob = task.audioUrl
        ? await fetch(task.audioUrl).then(r => r.blob())
        : await ttsApi.getTaskAudio(task.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `tts-${task.id}.${ttsFormat || 'wav'}`;
      a.click();
    } catch (e) { setError(t('下载失败') + ': ' + e.message); }
  };

  const clearDone = () => {
    setTasks(prev => prev.filter(t => t.status !== 'done' && t.status !== 'failed'));
  };

  const downloadAudio = (task) => {
    if (!task.audioUrl) return;
    const a = document.createElement('a');
    a.href = task.audioUrl;
    a.download = `tts-${task.id}.${ttsFormat || 'wav'}`;
    a.click();
  };

  useEffectTask(() => {
    const poll = async () => {
      const active = tasks.filter(t =>
        (t.status === 'pending' || t.status === 'running') &&
        ((t.type === 'asr' && t.mode === 'url') || (t.type === 'tts' && t.mode === 'async'))
      );
      if (active.length === 0) return;

      for (const t of active) {
        try {
          if (t.type === 'asr') {
            const res = await asrApi.getJob(t.id);
            if (res.status !== t.status) {
              setTasks(prev => prev.map(x => x.id === t.id ? {
                ...x, status: res.status === 'DONE' ? 'done' : res.status === 'FAILED' ? 'failed' : res.status.toLowerCase(),
                result: res.result?.text || res.result || null,
                error: res.error || null,
              } : x));
            }
          } else if (t.type === 'tts' && t.mode === 'async') {
            const res = await ttsApi.getTask(t.id);
            const newStatus = res.status === 'DONE' ? 'done' : res.status === 'FAILED' ? 'failed' : res.status.toLowerCase();
            if (newStatus !== t.status) {
              let audioUrl = null;
              if (newStatus === 'done') {
                try {
                  const blob = await ttsApi.getTaskAudio(t.id);
                  audioUrl = URL.createObjectURL(blob);
                } catch {}
              }
              setTasks(prev => prev.map(x => x.id === t.id ? {
                ...x, status: newStatus, result: newStatus === 'done' ? '合成完成' : null,
                error: res.error || null, ...(audioUrl ? { audioUrl } : {}),
              } : x));
            }
          }
        } catch {}
      }
    };

    if (tasks.some(t =>
      (t.status === 'pending' || t.status === 'running') &&
      ((t.type === 'asr' && t.mode === 'url') || (t.type === 'tts' && t.mode === 'async'))
    )) {
      intervalRef.current = setInterval(poll, 3000);
      return () => clearInterval(intervalRef.current);
    }
  }, [tasks]);

  const statusLabel = (s) => {
    const map = { done: t('完成'), failed: t('失败'), running: t('运行中'), pending: t('等待中'), cancelled: t('已取消') };
    return map[s] || s;
  };

  const asrReady = asrMode === 'file' ? asrFiles.length > 0 : !!asrUrl.trim();

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('异步任务')}</div>
          <div className="page-sub">ASR RECOGNIZE & TTS SYNTHESIZE</div>
        </div>
        {tasks.some(tk => tk.status === 'done' || tk.status === 'failed') && (
          <button className="btn-ghost" onClick={clearDone}>{t('清除已完成')}</button>
        )}
      </div>

      {error && (
        <div style={{
          background: 'oklch(0.70 0.18 25 / .1)', border: '1px solid oklch(0.70 0.18 25 / .3)',
          borderRadius: 8, padding: 12, color: 'var(--danger)', fontSize: 12,
          fontFamily: 'var(--font-mono)', marginBottom: 16,
        }}>{error}</div>
      )}

      {success && (
        <div style={{
          background: 'var(--accent-2)', border: '1px solid var(--accent-3)',
          borderRadius: 8, padding: 12, color: 'var(--accent)', fontSize: 12,
          fontFamily: 'var(--font-mono)', marginBottom: 16,
        }}>{success}</div>
      )}

      <div className="task-submit">
        <div className="task-submit-card">
          <div className="section-label">ASR</div>
          <div className="flex-col gap-3">
            <div className="tweak-options" style={{ marginBottom: 4 }}>
              <button className={`tweak-option ${asrMode === 'file' ? 'active' : ''}`}
                onClick={() => setAsrMode('file')}>{t('上传文件')}</button>
              <button className={`tweak-option ${asrMode === 'url' ? 'active' : ''}`}
                onClick={() => setAsrMode('url')}>{t('音频 URL')}</button>
            </div>

            {asrMode === 'file' ? (
              <div>
                <input ref={fileRef} type="file" accept="audio/*" multiple
                  onChange={e => setAsrFiles(Array.from(e.target.files || []))}
                  style={{ fontSize: 12, color: 'var(--text-dim)' }}/>
                {asrFiles.length > 0 && <div className="text-xs text-dim" style={{ marginTop: 4 }}>
                  {asrFiles.length === 1 ? `${asrFiles[0].name} (${(asrFiles[0].size / 1024).toFixed(0)} KB)`
                    : `${asrFiles.length} ${t('个文件')}，${(asrFiles.reduce((s, f) => s + f.size, 0) / 1024).toFixed(0)} KB`}
                </div>}
              </div>
            ) : (
              <input className="input" placeholder="输入音频文件 URL" value={asrUrl}
                onChange={e => setAsrUrl(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') submitAsr(); }}/>
            )}

            <select className="select" value={asrLang} onChange={e => setAsrLang(e.target.value)}>
              <option value="auto">{t('自动检测')}</option>
              <option value="zh">中文</option>
              <option value="en">English</option>
            </select>
            <button className="btn-primary" disabled={asrSubmitting || !asrReady} onClick={submitAsr}>
              {asrSubmitting ? t('处理中…') : asrMode === 'file' ? t('开始识别') : t('提交任务')}
            </button>
          </div>
        </div>

        <div className="task-submit-card">
          <div className="section-label">TTS</div>
          <div className="flex-col gap-3">
            <div className="tweak-options" style={{ marginBottom: 4 }}>
              <button className={`tweak-option ${ttsMode === 'sync' ? 'active' : ''}`}
                onClick={() => setTtsMode('sync')}>{t('同步合成')}</button>
              <button className={`tweak-option ${ttsMode === 'async' ? 'active' : ''}`}
                onClick={() => setTtsMode('async')}>{t('异步合成')}</button>
            </div>
            <textarea className="textarea" placeholder="输入要合成的文本" value={ttsText}
              onChange={e => setTtsText(e.target.value)} rows={3}
              onKeyDown={e => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (ttsText.trim()) ttsMode === 'async' ? submitTtsAsync() : submitTts();
                }
              }}/>
            {ttsModels.length > 0 && (
              <select className="select" value={ttsModel} onChange={e => setTtsModel(e.target.value)}>
                {ttsModels.filter(m => m.loaded || m.status === 'loaded').map(m => (
                  <option key={m.id || m.name} value={m.id || m.name}>
                    {m.name || m.id}{m.is_default ? ` (${t('默认')})` : ''}
                  </option>
                ))}
              </select>
            )}
            <div className="flex gap-2">
              <input className="input" placeholder="voice_id (可选)" value={ttsVoice}
                onChange={e => setTtsVoice(e.target.value)}/>
              <select className="select" value={ttsFormat} onChange={e => setTtsFormat(e.target.value)}
                style={{ flex: '0 0 100px' }}>
                <option value="wav">WAV</option>
                <option value="pcm">PCM</option>
              </select>
            </div>
            <button className="btn-primary" disabled={ttsSubmitting || !ttsText.trim()} onClick={() => ttsMode === 'async' ? submitTtsAsync() : submitTts()}>
              {ttsSubmitting ? (ttsMode === 'async' ? t('提交中…') : t('合成中…')) : ttsMode === 'async' ? t('提交异步任务') : t('开始合成')}
            </button>
            <div className="text-xs text-dim" style={{ marginTop: -4 }}>
              {ttsMode === 'sync' ? t('同步：等待合成完成后返回音频') : t('异步：提交后立即返回，后台合成，可连续提交多个')}
            </div>
          </div>
        </div>
      </div>

      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
        <table className="dm-table">
          <thead>
            <tr>
              <th>{t('类型')}</th>
              <th>{t('输入')}</th>
              <th>{t('状态')}</th>
              <th>{t('结果')}</th>
              <th style={{ textAlign: 'right' }}>{t('操作')}</th>
            </tr>
          </thead>
          <tbody>
            {tasks.length === 0 && (
              <tr><td colSpan={5} className="text-dim" style={{ textAlign: 'center', padding: 32 }}>
                暂无任务 — 上传音频或输入文本开始处理
              </td></tr>
            )}
            {tasks.map(tk => (
              <tr key={tk.id}>
                <td>
                  <span className="chip">{tk.type.toUpperCase()}</span>
                  {tk.mode === 'async' && <span className="chip" style={{ marginLeft: 4, fontSize: 9 }}>ASYNC</span>}
                  {tk.mode === 'url' && <span className="chip" style={{ marginLeft: 4, fontSize: 9 }}>URL</span>}
                </td>
                <td>
                  <div className="text-xs" style={{ maxWidth: 240, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {tk.input || tk.id}
                  </div>
                  <div className="text-mono text-xs text-dim">{tk.created_at}</div>
                </td>
                <td>
                  <span className={`task-status task-status-${tk.status}`}>
                    {statusLabel(tk.status)}
                  </span>
                </td>
                <td>
                  {tk.status === 'done' && tk.type === 'asr' && (
                    <span className="text-xs">{typeof tk.result === 'string' ? tk.result.slice(0, 100) : ''}</span>
                  )}
                  {tk.status === 'done' && tk.type === 'tts' && tk.audioUrl && (
                    <audio src={tk.audioUrl} controls style={{ height: 28, maxWidth: 200 }}/>
                  )}
                  {tk.status === 'failed' && (
                    <span className="text-xs" style={{ color: 'var(--danger)' }}>{tk.error || '未知错误'}</span>
                  )}
                  {tk.status === 'running' && (
                    <span className="text-dim text-xs">{t('处理中…')}</span>
                  )}
                  {tk.status === 'pending' && (
                    <span className="text-dim text-xs">{t('等待中…')}</span>
                  )}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <div className="flex gap-2" style={{ justifyContent: 'flex-end' }}>
                    {tk.status === 'done' && tk.type === 'asr' && tk.result && (
                      <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11 }}
                        onClick={() => window.copyText(tk.result)}>{t('复制')}</button>
                    )}
                    {tk.status === 'done' && tk.type === 'tts' && tk.audioUrl && (
                      <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11 }}
                        onClick={() => downloadAudio(tk)}>{t('下载')}</button>
                    )}
                    {(tk.status === 'pending' || tk.status === 'running') && tk.type === 'asr' && tk.mode === 'url' && (
                      <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11 }}
                        onClick={() => cancelAsrJob(tk)}>{t('取消')}</button>
                    )}
                    {(tk.status === 'pending' || tk.status === 'running') && tk.type === 'tts' && tk.mode === 'async' && (
                      <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11 }}
                        onClick={() => cancelTtsTask(tk)}>{t('取消')}</button>
                    )}
                    {tk.status === 'done' && tk.type === 'tts' && tk.mode === 'async' && !tk.audioUrl && (
                      <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11 }}
                        onClick={() => downloadTtsTaskAudio(tk)}>{t('下载')}</button>
                    )}
                    <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11 }}
                      onClick={() => removeTask(tk.id)}>{t('删除')}</button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

window.TasksPage = TasksPage;
