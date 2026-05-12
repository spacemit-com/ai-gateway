// Vision 批处理任务页面
const { useState: useStateJ, useEffect: useEffectJ, useRef: useRefJ } = React;

const VJOBS_KEY = 'vision-jobs';
function loadVJobs() {
  try { return JSON.parse(localStorage.getItem(VJOBS_KEY)) || []; } catch { return []; }
}
function saveVJobs(jobs) {
  localStorage.setItem(VJOBS_KEY, JSON.stringify(jobs));
}

const TASK_OPTIONS = ['detect', 'track', 'classify', 'pose', 'segment', 'emotion'];

function VisionJobsPage() {
  const { visionApi, t } = window;
  const [jobs, setJobs] = useStateJ(() => loadVJobs());
  const [models, setModels] = useStateJ([]);
  const [showSubmit, setShowSubmit] = useStateJ(false);
  const [inputUri, setInputUri] = useStateJ('');
  const [selectedModel, setSelectedModel] = useStateJ('');
  const [tasks, setTasks] = useStateJ(['detect']);
  const [frameRate, setFrameRate] = useStateJ(1);
  const [submitting, setSubmitting] = useStateJ(false);
  const [error, setError] = useStateJ('');
  const intervalRef = useRefJ(null);

  useEffectJ(() => { saveVJobs(jobs); }, [jobs]);

  useEffectJ(() => {
    visionApi.listModels()
      .then(list => {
        const rows = Array.isArray(list) ? list : (list?.data || []);
        setModels(rows.map(m => {
          const rawModelId = m.model_id || m.id;
          const modelId = window.visionBackendModelId ? window.visionBackendModelId(rawModelId) : rawModelId;
          return {
            id: modelId,
            name: m.name || rawModelId,
            capabilities: m.capabilities || [],
          };
        }).filter(m => m.id));
      })
      .catch(() => {});
  }, []);

  // Poll active jobs
  useEffectJ(() => {
    const active = jobs.filter(j => j.status === 'PENDING' || j.status === 'RUNNING');
    if (active.length === 0) {
      if (intervalRef.current) { clearInterval(intervalRef.current); intervalRef.current = null; }
      return;
    }
    const poll = async () => {
      for (const j of active) {
        try {
          const res = await visionApi.getJob(j.job_id);
          setJobs(prev => prev.map(x => x.job_id === j.job_id ? {
            ...x,
            status: res.status || x.status,
            progress: res.progress ?? x.progress,
            results_uri: res.results_uri || x.results_uri,
            error_msg: res.artifacts?.error || x.error_msg,
          } : x));
        } catch {}
      }
    };
    poll();
    intervalRef.current = setInterval(poll, 3000);
    return () => { if (intervalRef.current) clearInterval(intervalRef.current); };
  }, [jobs.filter(j => j.status === 'PENDING' || j.status === 'RUNNING').map(j => j.job_id).join(',')]);

  const toggleTask = (task) => {
    setTasks(prev => prev.includes(task) ? prev.filter(t => t !== task) : [...prev, task]);
  };

  const submitJob = async () => {
    if (!inputUri.trim() || !selectedModel) return;
    setSubmitting(true);
    setError('');
    try {
      const body = {
        input_uri: inputUri.trim(),
        model_id: selectedModel,
        tasks,
      };
      if (frameRate > 1) body.frame_sample_rate = frameRate;
      const res = await visionApi.createJob(body);
      setJobs(prev => [{
        job_id: res.job_id,
        input_uri: inputUri.trim(),
        model_id: selectedModel,
        status: res.status || 'PENDING',
        progress: 0,
        results_uri: null,
        error_msg: null,
        created_at: new Date().toLocaleString(),
      }, ...prev]);
      setInputUri('');
      setShowSubmit(false);
    } catch (e) {
      setError(e.message);
    }
    setSubmitting(false);
  };

  const cancelJob = async (job_id) => {
    try {
      await visionApi.cancelJob(job_id);
      setJobs(prev => prev.map(j => j.job_id === job_id ? { ...j, status: 'CANCELLED' } : j));
    } catch {}
  };

  const removeJob = (job_id) => {
    setJobs(prev => prev.filter(j => j.job_id !== job_id));
  };

  const clearDone = () => {
    setJobs(prev => prev.filter(j => j.status !== 'DONE' && j.status !== 'FAILED' && j.status !== 'CANCELLED'));
  };

  const statusClass = (s) => {
    const map = { DONE: 'done', FAILED: 'failed', RUNNING: 'running', PENDING: 'pending', CANCELLED: 'cancelled' };
    return 'task-status task-status-' + (map[s] || 'pending');
  };
  const statusLabel = (s) => {
    const map = { DONE: t('完成'), FAILED: t('失败'), RUNNING: t('运行中'), PENDING: t('等待中'), CANCELLED: t('已取消') };
    return map[s] || s;
  };

  const hasDone = jobs.some(j => j.status === 'DONE' || j.status === 'FAILED' || j.status === 'CANCELLED');

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('视觉任务')}</div>
          <div className="page-sub">VISION JOBS · BATCH PROCESSING</div>
        </div>
        <div className="flex gap-2">
          {hasDone && <button className="btn-ghost" onClick={clearDone}>{t('清除已完成')}</button>}
          <button className="btn-primary" onClick={() => setShowSubmit(!showSubmit)}>
            {showSubmit ? t('取消') : t('提交任务')}
          </button>
        </div>
      </div>

      {error && (
        <div style={{
          background: 'oklch(0.70 0.18 25 / .1)', border: '1px solid oklch(0.70 0.18 25 / .3)',
          borderRadius: 8, padding: 12, color: 'var(--danger)', fontSize: 12,
          fontFamily: 'var(--font-mono)', marginBottom: 16,
        }}>{error}</div>
      )}

      {showSubmit && (
        <div className="task-submit-card" style={{ marginBottom: 24 }}>
          <div className="section-label">{t('提交任务')}</div>
          <div className="flex-col gap-3">
            <div className="job-field">
              <label className="job-field-label">{t('输入路径')}</label>
              <input className="input" placeholder="/path/to/image.jpg | /path/to/video.mp4 | URL"
                value={inputUri} onChange={e => setInputUri(e.target.value)}
                onKeyDown={e => { if (e.key === 'Enter') submitJob(); }}/>
            </div>
            <div className="job-field">
              <label className="job-field-label">{t('模型')}</label>
              <select className="select" value={selectedModel} onChange={e => setSelectedModel(e.target.value)}>
                <option value="">{t('模型选择…')}</option>
                {models.map(m => <option key={m.id} value={m.id}>{m.name || m.id}</option>)}
              </select>
            </div>
            <div className="job-field">
              <label className="job-field-label">{t('任务类型')}</label>
              <div className="flex gap-2" style={{ flexWrap: 'wrap' }}>
                {TASK_OPTIONS.map(tk => (
                  <button key={tk}
                    className={`tweak-option ${tasks.includes(tk) ? 'active' : ''}`}
                    style={{ flex: 'none', padding: '4px 10px', fontSize: 11 }}
                    onClick={() => toggleTask(tk)}>{tk}</button>
                ))}
              </div>
            </div>
            <div className="job-field">
              <label className="job-field-label">{t('帧采样率')}</label>
              <input className="input" type="number" min="1" max="100" value={frameRate}
                onChange={e => setFrameRate(Math.max(1, +e.target.value))}
                style={{ width: 100 }}/>
            </div>
            <button className="btn-primary" disabled={submitting || !inputUri.trim() || !selectedModel}
              onClick={submitJob}>
              {submitting ? t('提交中…') : t('提交任务')}
            </button>
          </div>
        </div>
      )}

      <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
        <table className="dm-table">
          <thead>
            <tr>
              <th>{t('输入')}</th>
              <th>{t('模型')}</th>
              <th>{t('状态')}</th>
              <th>{t('进度')}</th>
              <th style={{ textAlign: 'right' }}>{t('操作')}</th>
            </tr>
          </thead>
          <tbody>
            {jobs.length === 0 && (
              <tr><td colSpan={5} className="text-dim" style={{ textAlign: 'center', padding: 32 }}>
                {t('暂无任务')}
              </td></tr>
            )}
            {jobs.map(j => (
              <tr key={j.job_id}>
                <td>
                  <div className="text-xs" style={{ maxWidth: 260, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {j.input_uri}
                  </div>
                  <div className="text-mono text-xs text-dim">{j.created_at}</div>
                </td>
                <td><span className="text-mono text-xs">{j.model_id}</span></td>
                <td><span className={statusClass(j.status)}>{statusLabel(j.status)}</span></td>
                <td>
                  {(j.status === 'RUNNING' || j.status === 'PENDING') ? (
                    <div className="progress-cell">
                      <div className="progress"><div className="progress-bar" style={{ width: (j.progress || 0) + '%' }}/></div>
                      <span>{j.progress || 0}%</span>
                    </div>
                  ) : j.status === 'FAILED' ? (
                    <span className="text-xs" style={{ color: 'var(--danger)' }}>{j.error_msg || ''}</span>
                  ) : j.status === 'DONE' && j.results_uri ? (
                    <span className="text-mono text-xs" style={{ color: 'var(--accent)' }}>{j.results_uri}</span>
                  ) : null}
                </td>
                <td style={{ textAlign: 'right' }}>
                  <div className="flex gap-2" style={{ justifyContent: 'flex-end' }}>
                    {(j.status === 'RUNNING' || j.status === 'PENDING') && (
                      <button className="btn-danger" onClick={() => cancelJob(j.job_id)}>{t('取消')}</button>
                    )}
                    <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11 }}
                      onClick={() => removeJob(j.job_id)}>{t('删除')}</button>
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

window.VisionJobsPage = VisionJobsPage;
