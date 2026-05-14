// 系统配置中心 —— 连接 / ASR / TTS / VAD 运行时参数
const { useState: useStateCfg, useEffect: useEffectCfg } = React;

function ConfigSection({ title, loading, onSave, saving, saved, pendingRestart, children }) {
  const { t } = window;
  return (
    <div className="config-section">
      <div className="config-section-title">
        {title}
        {loading && <span className="text-xs text-dim">{t('加载中…')}</span>}
      </div>
      <div className="config-grid">
        {children}
      </div>
      <div className="config-actions">
        <button className="btn-primary" disabled={saving} onClick={onSave}>
          {saving ? t('保存中…') : t('保存')}
        </button>
        {saved && <span className="save-ok">{t('已保存')}</span>}
      </div>
      {pendingRestart && (
        <div className="restart-warn">
          ⚠ 引擎配置已更新，需��重启服务生效
        </div>
      )}
    </div>
  );
}

function ConfigPage() {
  const { asrApi, ttsApi, vadApi, visionApi, t } = window;
  const [tab, setTab] = useStateCfg('connection');

  // ============ 连接 tab ============
  const [bases, setBases] = useStateCfg(window.API_BASES);
  const updateBase = (k, v) => {
    const next = { ...bases, [k]: v };
    setBases(next);
    window.API_BASES = next;
  };

  // ============ ASR tab ============
  const [asrParams, setAsrParams] = useStateCfg(null);
  const [asrAudio, setAsrAudio] = useStateCfg(null);
  const [asrEngine, setAsrEngine] = useStateCfg(null);
  const [asrParamsLoading, setAsrParamsLoading] = useStateCfg(false);
  const [asrAudioLoading, setAsrAudioLoading] = useStateCfg(false);
  const [asrEngineLoading, setAsrEngineLoading] = useStateCfg(false);
  const [asrParamsSaving, setAsrParamsSaving] = useStateCfg(false);
  const [asrAudioSaving, setAsrAudioSaving] = useStateCfg(false);
  const [asrEngineSaving, setAsrEngineSaving] = useStateCfg(false);
  const [asrParamsSaved, setAsrParamsSaved] = useStateCfg(false);
  const [asrAudioSaved, setAsrAudioSaved] = useStateCfg(false);
  const [asrEngineSaved, setAsrEngineSaved] = useStateCfg(false);
  const [asrParamsRestart, setAsrParamsRestart] = useStateCfg(false);
  const [asrAudioRestart, setAsrAudioRestart] = useStateCfg(false);
  const [asrEngineRestart, setAsrEngineRestart] = useStateCfg(false);

  // ============ TTS tab ============
  const [ttsParams, setTtsParams] = useStateCfg(null);
  const [ttsEngine, setTtsEngine] = useStateCfg(null);
  const [ttsParamsLoading, setTtsParamsLoading] = useStateCfg(false);
  const [ttsEngineLoading, setTtsEngineLoading] = useStateCfg(false);
  const [ttsParamsSaving, setTtsParamsSaving] = useStateCfg(false);
  const [ttsEngineSaving, setTtsEngineSaving] = useStateCfg(false);
  const [ttsParamsSaved, setTtsParamsSaved] = useStateCfg(false);
  const [ttsEngineSaved, setTtsEngineSaved] = useStateCfg(false);
  const [ttsParamsRestart, setTtsParamsRestart] = useStateCfg(false);
  const [ttsEngineRestart, setTtsEngineRestart] = useStateCfg(false);

  // ============ VAD tab ============
  const [vadParams, setVadParams] = useStateCfg(null);
  const [vadAudio, setVadAudio] = useStateCfg(null);
  const [vadEngine, setVadEngine] = useStateCfg(null);
  const [vadParamsLoading, setVadParamsLoading] = useStateCfg(false);
  const [vadAudioLoading, setVadAudioLoading] = useStateCfg(false);
  const [vadEngineLoading, setVadEngineLoading] = useStateCfg(false);
  const [vadParamsSaving, setVadParamsSaving] = useStateCfg(false);
  const [vadAudioSaving, setVadAudioSaving] = useStateCfg(false);
  const [vadEngineSaving, setVadEngineSaving] = useStateCfg(false);
  const [vadParamsSaved, setVadParamsSaved] = useStateCfg(false);
  const [vadAudioSaved, setVadAudioSaved] = useStateCfg(false);
  const [vadEngineSaved, setVadEngineSaved] = useStateCfg(false);
  const [vadParamsRestart, setVadParamsRestart] = useStateCfg(false);
  const [vadAudioRestart, setVadAudioRestart] = useStateCfg(false);
  const [vadEngineRestart, setVadEngineRestart] = useStateCfg(false);

  // ============ Vision tab ============
  const [visParams, setVisParams] = useStateCfg(null);
  const [visEngine, setVisEngine] = useStateCfg(null);
  const [visParamsLoading, setVisParamsLoading] = useStateCfg(false);
  const [visEngineLoading, setVisEngineLoading] = useStateCfg(false);
  const [visParamsSaving, setVisParamsSaving] = useStateCfg(false);
  const [visEngineSaving, setVisEngineSaving] = useStateCfg(false);
  const [visParamsSaved, setVisParamsSaved] = useStateCfg(false);
  const [visEngineSaved, setVisEngineSaved] = useStateCfg(false);
  const [visParamsRestart, setVisParamsRestart] = useStateCfg(false);
  const [visEngineRestart, setVisEngineRestart] = useStateCfg(false);

  // Fetch helpers
  const fetchAsrConfig = async () => {
    setAsrParamsLoading(true); setAsrAudioLoading(true); setAsrEngineLoading(true);
    try {
      const [p, a, e] = await Promise.all([
        asrApi.getParams().catch(() => null),
        asrApi.getAudio().catch(() => null),
        asrApi.getEngine().catch(() => null),
      ]);
      if (p) setAsrParams(p);
      if (a) setAsrAudio(a);
      if (e) setAsrEngine(e);
    } catch {}
    setAsrParamsLoading(false); setAsrAudioLoading(false); setAsrEngineLoading(false);
  };

  const fetchTtsConfig = async () => {
    setTtsParamsLoading(true); setTtsEngineLoading(true);
    try {
      const [p, e] = await Promise.all([
        ttsApi.getParams().catch(() => null),
        ttsApi.getEngine().catch(() => null),
      ]);
      if (p) setTtsParams(p);
      if (e) setTtsEngine(e);
    } catch {}
    setTtsParamsLoading(false); setTtsEngineLoading(false);
  };

  const fetchVadConfig = async () => {
    setVadParamsLoading(true); setVadAudioLoading(true); setVadEngineLoading(true);
    try {
      const [p, a, e] = await Promise.all([
        vadApi.getParams().catch(() => null),
        vadApi.getAudio().catch(() => null),
        vadApi.getEngine().catch(() => null),
      ]);
      if (p) setVadParams(p);
      if (a) setVadAudio(a);
      if (e) setVadEngine(e);
    } catch {}
    setVadParamsLoading(false); setVadAudioLoading(false); setVadEngineLoading(false);
  };

  const fetchVisionConfig = async () => {
    setVisParamsLoading(true); setVisEngineLoading(true);
    try {
      const [p, e] = await Promise.all([
        visionApi.getParams().catch(() => null),
        visionApi.getEngine().catch(() => null),
      ]);
      if (p) setVisParams(p);
      if (e) setVisEngine(e);
    } catch {}
    setVisParamsLoading(false); setVisEngineLoading(false);
  };

  // Load config on mount and tab switch
  useEffectCfg(() => {
    if (tab === 'asr') fetchAsrConfig();
    if (tab === 'tts') fetchTtsConfig();
    if (tab === 'vad') fetchVadConfig();
    if (tab === 'vision') fetchVisionConfig();
  }, [tab]);

  // Save helper with "已保存" flash
  const flashSaved = (setter) => {
    setter(true);
    setTimeout(() => setter(false), 2000);
  };

  // Save handlers
  const saveAsrParams = async () => {
    setAsrParamsSaving(true);
    try {
      const res = await asrApi.updateParams(asrParams);
      flashSaved(setAsrParamsSaved);
      setAsrParamsRestart(res && res.pending_restart);
    } catch {}
    setAsrParamsSaving(false);
  };

  const saveAsrAudio = async () => {
    setAsrAudioSaving(true);
    try {
      const res = await asrApi.updateAudio(asrAudio);
      flashSaved(setAsrAudioSaved);
      setAsrAudioRestart(res && res.pending_restart);
    } catch {}
    setAsrAudioSaving(false);
  };

  const saveAsrEngine = async () => {
    setAsrEngineSaving(true);
    try {
      const res = await asrApi.updateEngine(asrEngine);
      flashSaved(setAsrEngineSaved);
      setAsrEngineRestart(res && res.pending_restart);
    } catch {}
    setAsrEngineSaving(false);
  };

  const saveTtsParams = async () => {
    setTtsParamsSaving(true);
    try {
      const res = await ttsApi.updateParams(ttsParams);
      flashSaved(setTtsParamsSaved);
      setTtsParamsRestart(res && res.pending_restart);
    } catch {}
    setTtsParamsSaving(false);
  };

  const saveTtsEngine = async () => {
    setTtsEngineSaving(true);
    try {
      const res = await ttsApi.updateEngine(ttsEngine);
      flashSaved(setTtsEngineSaved);
      setTtsEngineRestart(res && res.pending_restart);
    } catch {}
    setTtsEngineSaving(false);
  };

  const saveVadParams = async () => {
    setVadParamsSaving(true);
    try {
      const res = await vadApi.updateParams(vadParams);
      flashSaved(setVadParamsSaved);
      setVadParamsRestart(res && res.pending_restart);
    } catch {}
    setVadParamsSaving(false);
  };

  const saveVadAudio = async () => {
    setVadAudioSaving(true);
    try {
      const res = await vadApi.updateAudio(vadAudio);
      flashSaved(setVadAudioSaved);
      setVadAudioRestart(res && res.pending_restart);
    } catch {}
    setVadAudioSaving(false);
  };

  const saveVadEngine = async () => {
    setVadEngineSaving(true);
    try {
      const res = await vadApi.updateEngine(vadEngine);
      flashSaved(setVadEngineSaved);
      setVadEngineRestart(res && res.pending_restart);
    } catch {}
    setVadEngineSaving(false);
  };

  const saveVisParams = async () => {
    setVisParamsSaving(true);
    try {
      const res = await visionApi.updateParams(visParams);
      flashSaved(setVisParamsSaved);
      setVisParamsRestart(res && res.pending_restart);
    } catch {}
    setVisParamsSaving(false);
  };

  const saveVisEngine = async () => {
    setVisEngineSaving(true);
    try {
      const res = await visionApi.updateEngine(visEngine);
      flashSaved(setVisEngineSaved);
      setVisEngineRestart(res && res.pending_restart);
    } catch {}
    setVisEngineSaving(false);
  };

  const fieldLabel = {
    language: '语言', punctuation: '标点恢复', hotword_weight: '热词权重', itn: '逆文本正则化',
    sample_rate: '采样率', vad_threshold: 'VAD 阈值', denoise: '降噪', agc: '自动增益',
    num_threads: '线程数', device: '设备', power_mode: '功耗模式',
    speed: '语速', pitch: '音高', volume: '音量', emotion_strength: '情感强度',
    threads: '线程数', cache_policy: '缓存策略',
    trigger_threshold: '触发阈值', stop_threshold: '停止阈值',
    min_speech_ms: '最短语音(ms)', max_silence_ms: '最大静音(ms)',
    bit_depth: '位深', npu_priority: 'NPU 优先级', memory_limit: '内存限制',
    input_size: '输入尺寸', ai_core_group: 'AI Core 组',
    precision: '精度',
    conf: '置信度阈值 (conf)', iou: 'IoU 阈值',
  };

  // Field renderers
  const numberField = (label, value, onChange, step) => (
    <div className="config-field">
      <label>{fieldLabel[label] || label}</label>
      <input className="input" type="number" step={step || '1'} value={value ?? ''} onChange={e => onChange(e.target.value === '' ? '' : Number(e.target.value))}/>
    </div>
  );

  const textField = (label, value, onChange) => (
    <div className="config-field">
      <label>{fieldLabel[label] || label}</label>
      <input className="input" type="text" value={value ?? ''} onChange={e => onChange(e.target.value)}/>
    </div>
  );

  const toggleField = (label, value, onChange) => (
    <div className="config-field">
      <label>{fieldLabel[label] || label}</label>
      <div className={`toggle-switch ${value ? 'on' : ''}`} onClick={() => onChange(!value)}/>
    </div>
  );

  // ============ Render tabs ============
  const tabs = [
    { key: 'connection', label: t('连接') },
    { key: 'asr', label: 'ASR' },
    { key: 'tts', label: 'TTS' },
    { key: 'vad', label: 'VAD' },
    { key: 'vision', label: 'Vision' },
  ];

  const renderConnection = () => (
    <div className="config-section">
      <div className="config-section-title">API Base URLs</div>
      {Object.entries(bases).map(([k, v]) => (
        <div key={k} className="tweak-row" style={{ marginBottom: 16 }}>
          <label className="tweak-label" style={{ fontSize: 12 }}>
            <span className="text-mono" style={{ color: 'var(--accent)' }}>{k.toUpperCase()}</span>
          </label>
          <input className="input" value={v} onChange={e => updateBase(k, e.target.value)}/>
        </div>
      ))}
      <div className="text-xs text-dim mt-4">
        修改后立即对新请求生效。如出现跨域，请在后端配置 CORS 或使用反向代理。
      </div>
    </div>
  );

  const renderAsr = () => (
    <>
      <ConfigSection title={t('推理参数')} loading={asrParamsLoading}
        onSave={saveAsrParams} saving={asrParamsSaving}
        saved={asrParamsSaved} pendingRestart={asrParamsRestart}>
        {asrParams && <>
          {textField('language', asrParams.language, v => setAsrParams({ ...asrParams, language: v }))}
          {toggleField('punctuation', asrParams.punctuation, v => setAsrParams({ ...asrParams, punctuation: v }))}
          {numberField('hotword_weight', asrParams.hotword_weight, v => setAsrParams({ ...asrParams, hotword_weight: v }), '0.01')}
          {toggleField('itn', asrParams.itn, v => setAsrParams({ ...asrParams, itn: v }))}
        </>}
      </ConfigSection>

      <ConfigSection title={t('音频配置')} loading={asrAudioLoading}
        onSave={saveAsrAudio} saving={asrAudioSaving}
        saved={asrAudioSaved} pendingRestart={asrAudioRestart}>
        {asrAudio && <>
          {numberField('sample_rate', asrAudio.sample_rate, v => setAsrAudio({ ...asrAudio, sample_rate: v }), '1')}
          {numberField('vad_threshold', asrAudio.vad_threshold, v => setAsrAudio({ ...asrAudio, vad_threshold: v }), '0.01')}
          {toggleField('denoise', asrAudio.denoise, v => setAsrAudio({ ...asrAudio, denoise: v }))}
          {toggleField('agc', asrAudio.agc, v => setAsrAudio({ ...asrAudio, agc: v }))}
        </>}
      </ConfigSection>

      <ConfigSection title={t('引擎配置')} loading={asrEngineLoading}
        onSave={saveAsrEngine} saving={asrEngineSaving}
        saved={asrEngineSaved} pendingRestart={asrEngineRestart}>
        {asrEngine && <>
          {numberField('num_threads', asrEngine.num_threads, v => setAsrEngine({ ...asrEngine, num_threads: v }), '1')}
          {textField('device', asrEngine.device, v => setAsrEngine({ ...asrEngine, device: v }))}
          {textField('power_mode', asrEngine.power_mode, v => setAsrEngine({ ...asrEngine, power_mode: v }))}
        </>}
      </ConfigSection>
    </>
  );

  const renderTts = () => (
    <>
      <ConfigSection title={t('推理参数')} loading={ttsParamsLoading}
        onSave={saveTtsParams} saving={ttsParamsSaving}
        saved={ttsParamsSaved} pendingRestart={ttsParamsRestart}>
        {ttsParams && <>
          {numberField('speed', ttsParams.speed, v => setTtsParams({ ...ttsParams, speed: v }), '0.01')}
          {numberField('pitch', ttsParams.pitch, v => setTtsParams({ ...ttsParams, pitch: v }), '0.01')}
          {numberField('volume', ttsParams.volume, v => setTtsParams({ ...ttsParams, volume: v }), '0.01')}
          {numberField('emotion_strength', ttsParams.emotion_strength, v => setTtsParams({ ...ttsParams, emotion_strength: v }), '0.01')}
        </>}
      </ConfigSection>

      <ConfigSection title={t('引擎配置')} loading={ttsEngineLoading}
        onSave={saveTtsEngine} saving={ttsEngineSaving}
        saved={ttsEngineSaved} pendingRestart={ttsEngineRestart}>
        {ttsEngine && <>
          {numberField('threads', ttsEngine.threads, v => setTtsEngine({ ...ttsEngine, threads: v }), '1')}
          {numberField('sample_rate', ttsEngine.sample_rate, v => setTtsEngine({ ...ttsEngine, sample_rate: v }), '1')}
          {textField('cache_policy', ttsEngine.cache_policy, v => setTtsEngine({ ...ttsEngine, cache_policy: v }))}
        </>}
      </ConfigSection>
    </>
  );

  const renderVad = () => (
    <>
      <ConfigSection title={t('检测参数')} loading={vadParamsLoading}
        onSave={saveVadParams} saving={vadParamsSaving}
        saved={vadParamsSaved} pendingRestart={vadParamsRestart}>
        {vadParams && <>
          {numberField('trigger_threshold', vadParams.trigger_threshold, v => setVadParams({ ...vadParams, trigger_threshold: v }), '0.01')}
          {numberField('stop_threshold', vadParams.stop_threshold, v => setVadParams({ ...vadParams, stop_threshold: v }), '0.01')}
          {numberField('min_speech_ms', vadParams.min_speech_ms, v => setVadParams({ ...vadParams, min_speech_ms: v }), '1')}
          {numberField('max_silence_ms', vadParams.max_silence_ms, v => setVadParams({ ...vadParams, max_silence_ms: v }), '1')}
        </>}
      </ConfigSection>

      <ConfigSection title={t('音频配置')} loading={vadAudioLoading}
        onSave={saveVadAudio} saving={vadAudioSaving}
        saved={vadAudioSaved} pendingRestart={vadAudioRestart}>
        {vadAudio && <>
          {numberField('sample_rate', vadAudio.sample_rate, v => setVadAudio({ ...vadAudio, sample_rate: v }), '1')}
          {numberField('bit_depth', vadAudio.bit_depth, v => setVadAudio({ ...vadAudio, bit_depth: v }), '1')}
          {toggleField('denoise', vadAudio.denoise, v => setVadAudio({ ...vadAudio, denoise: v }))}
        </>}
      </ConfigSection>

      <ConfigSection title={t('引擎配置')} loading={vadEngineLoading}
        onSave={saveVadEngine} saving={vadEngineSaving}
        saved={vadEngineSaved} pendingRestart={vadEngineRestart}>
        {vadEngine && <>
          {numberField('threads', vadEngine.threads, v => setVadEngine({ ...vadEngine, threads: v }), '1')}
          {textField('npu_priority', vadEngine.npu_priority, v => setVadEngine({ ...vadEngine, npu_priority: v }))}
          {numberField('memory_limit', vadEngine.memory_limit, v => setVadEngine({ ...vadEngine, memory_limit: v }), '1')}
        </>}
      </ConfigSection>
    </>
  );

  const renderVision = () => (
    <>
      <ConfigSection title={t('推理参数')} loading={visParamsLoading}
        onSave={saveVisParams} saving={visParamsSaving}
        saved={visParamsSaved} pendingRestart={visParamsRestart}>
        {visParams && <>
          {numberField('conf', visParams.conf, v => setVisParams({ ...visParams, conf: v }), '0.01')}
          {numberField('iou', visParams.iou, v => setVisParams({ ...visParams, iou: v }), '0.01')}
          {numberField('input_size', visParams.input_size, v => setVisParams({ ...visParams, input_size: v }), '1')}
        </>}
      </ConfigSection>

      <ConfigSection title={t('引擎配置')} loading={visEngineLoading}
        onSave={saveVisEngine} saving={visEngineSaving}
        saved={visEngineSaved} pendingRestart={visEngineRestart}>
        {visEngine && <>
          {textField('ai_core_group', visEngine.ai_core_group, v => setVisEngine({ ...visEngine, ai_core_group: v }))}
          {numberField('threads', visEngine.threads, v => setVisEngine({ ...visEngine, threads: v }), '1')}
          {textField('precision', visEngine.precision, v => setVisEngine({ ...visEngine, precision: v }))}
          {numberField('memory_limit', visEngine.memory_limit, v => setVisEngine({ ...visEngine, memory_limit: v }), '1')}
        </>}
      </ConfigSection>
    </>
  );

  return (
    <div className="main-inner" style={{ maxWidth: 900 }}>
      <div className="page-header">
        <div>
          <div className="page-title">{t('系统配置')}</div>
          <div className="page-sub">{t('运行时配置')}</div>
        </div>
      </div>

      <div className="category-tabs">
        {tabs.map(t => (
          <button key={t.key}
            className={`category-tab ${tab === t.key ? 'active' : ''}`}
            onClick={() => setTab(t.key)}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === 'connection' && renderConnection()}
      {tab === 'asr' && renderAsr()}
      {tab === 'tts' && renderTts()}
      {tab === 'vad' && renderVad()}
      {tab === 'vision' && renderVision()}
    </div>
  );
}

window.ConfigPage = ConfigPage;
