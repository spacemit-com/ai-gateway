// 词库管理 —— ASR 热词 + TTS 发音
const { useState: useStateLex, useEffect: useEffectLex } = React;

function LexiconPage() {
  const { asrApi, ttsApi, t } = window;
  const [tab, setTab] = useStateLex('asr');

  const [asrEntries, setAsrEntries] = useStateLex([]);
  const [ttsEntries, setTtsEntries] = useStateLex([]);
  const [loading, setLoading] = useStateLex(true);
  const [error, setError] = useStateLex('');
  const [success, setSuccess] = useStateLex('');

  const [asrWord, setAsrWord] = useStateLex('');
  const [asrWeight, setAsrWeight] = useStateLex(1.0);
  const [asrScope, setAsrScope] = useStateLex('global');
  const [asrAdding, setAsrAdding] = useStateLex(false);

  const [ttsWord, setTtsWord] = useStateLex('');
  const [ttsPhoneme, setTtsPhoneme] = useStateLex('');
  const [ttsLocale, setTtsLocale] = useStateLex('zh');
  const [ttsAdding, setTtsAdding] = useStateLex(false);

  useEffectLex(() => {
    if (success) {
      const t = setTimeout(() => setSuccess(''), 3000);
      return () => clearTimeout(t);
    }
  }, [success]);

  const loadAsr = async () => {
    try {
      const res = await asrApi.listLexicons();
      const rows = [];
      for (const lex of (res.lexicons || [])) {
        for (const entry of (lex.entries || [])) {
          rows.push({ ...entry, scope: lex.scope, created_at: lex.created_at, lexicon_id: lex.id });
        }
      }
      setAsrEntries(rows);
    } catch (e) {
      setError('ASR 词库加载失败: ' + e.message);
    }
  };

  const loadTts = async () => {
    try {
      const res = await ttsApi.listLexicons();
      const rows = [];
      for (const lex of (res.lexicons || [])) {
        for (const entry of (lex.entries || [])) {
          rows.push({ ...entry, created_at: lex.created_at, lexicon_id: lex.id });
        }
      }
      setTtsEntries(rows);
    } catch (e) {
      setError('TTS 词库加载失败: ' + e.message);
    }
  };

  useEffectLex(() => {
    setLoading(true);
    setError('');
    Promise.all([loadAsr(), loadTts()]).finally(() => setLoading(false));
  }, []);

  const addAsrEntry = async () => {
    if (!asrWord.trim()) return;
    setAsrAdding(true);
    setError('');
    try {
      const res = await asrApi.createLexicon({ entries: [{ word: asrWord.trim(), weight: asrWeight }], scope: asrScope });
      setAsrWord('');
      setAsrWeight(1.0);
      await loadAsr();
      setSuccess('ASR 热词已添加' + (res.id ? ' (ID: ' + res.id + ')' : ''));
    } catch (e) {
      setError('添加失败: ' + e.message);
    }
    setAsrAdding(false);
  };

  const addTtsEntry = async () => {
    if (!ttsWord.trim() || !ttsPhoneme.trim()) return;
    setTtsAdding(true);
    setError('');
    try {
      const res = await ttsApi.createLexicon({ entries: [{ word: ttsWord.trim(), phoneme: ttsPhoneme.trim(), locale: ttsLocale }] });
      setTtsWord('');
      setTtsPhoneme('');
      await loadTts();
      setSuccess('TTS 发音规则已添加' + (res.id ? ' (ID: ' + res.id + ')' : ''));
    } catch (e) {
      setError('添加失败: ' + e.message);
    }
    setTtsAdding(false);
  };

  const deleteAsrEntry = async (lexicon_id) => {
    setError('');
    try {
      await asrApi.deleteLexicon(lexicon_id);
      await loadAsr();
      setSuccess('ASR 热词已删除');
    } catch (e) {
      setError('删除失败: ' + e.message);
    }
  };

  const deleteTtsEntry = async (lexicon_id) => {
    setError('');
    try {
      await ttsApi.deleteLexicon(lexicon_id);
      await loadTts();
      setSuccess('TTS 发音规则已删除');
    } catch (e) {
      setError('删除失败: ' + e.message);
    }
  };

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <div className="page-title">{t('词库管理')}</div>
          <div className="page-sub">LEXICON MANAGEMENT</div>
        </div>
        <button className="btn-ghost" onClick={() => {
          setLoading(true); setError('');
          Promise.all([loadAsr(), loadTts()]).finally(() => setLoading(false));
        }}>{t('刷新')}</button>
      </div>

      <div className="category-tabs">
        <button className={`category-tab ${tab === 'asr' ? 'active' : ''}`} onClick={() => setTab('asr')}>
          <span>ASR {t('热词')}</span>
          <span className="tab-count">{asrEntries.length}</span>
        </button>
        <button className={`category-tab ${tab === 'tts' ? 'active' : ''}`} onClick={() => setTab('tts')}>
          <span>TTS {t('发音')}</span>
          <span className="tab-count">{ttsEntries.length}</span>
        </button>
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

      {tab === 'asr' && (
        <div>
          <div className="lex-add-row">
            <input className="input" placeholder={t('词条')} value={asrWord}
              onChange={e => setAsrWord(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addAsrEntry(); }}/>
            <input className="input" type="number" step="0.1" min="0" placeholder={t('权重')}
              value={asrWeight} onChange={e => setAsrWeight(+e.target.value)}
              style={{ flex: '0 0 100px' }}/>
            <select className="select" value={asrScope} onChange={e => setAsrScope(e.target.value)}
              style={{ flex: '0 0 120px' }}>
              <option value="global">global</option>
            </select>
            <button className="btn-primary" disabled={asrAdding || !asrWord.trim()} onClick={addAsrEntry}
              style={{ flexShrink: 0 }}>
              {asrAdding ? t('添加中…') : t('添加')}
            </button>
          </div>

          <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
            <table className="dm-table">
              <thead>
                <tr><th>{t('词条')}</th><th>{t('权重')}</th><th>{t('作用域')}</th><th>{t('创建时间')}</th><th style={{ textAlign: 'right' }}>{t('操作')}</th></tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={5} className="text-dim" style={{ textAlign: 'center', padding: 32 }}>{t('加载中…')}</td></tr>
                )}
                {!loading && asrEntries.length === 0 && (
                  <tr><td colSpan={5} className="text-dim" style={{ textAlign: 'center', padding: 32 }}>
                    暂无热词 — 添加自定义词条提升识别准确率
                  </td></tr>
                )}
                {!loading && asrEntries.map((e, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 500 }}>{e.word}</td>
                    <td className="text-mono text-xs">{e.weight}</td>
                    <td><span className="lex-tag">{e.scope}</span></td>
                    <td className="text-mono text-xs text-dim">{e.created_at || '-'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11, color: 'var(--danger)' }}
                        onClick={() => deleteAsrEntry(e.lexicon_id)}>{t('删除')}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'tts' && (
        <div>
          <div className="lex-add-row">
            <input className="input" placeholder={t('词条') + '（spacemit）'} value={ttsWord}
              onChange={e => setTtsWord(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addTtsEntry(); }}/>
            <input className="input" placeholder={t('音素') + '（si pei si mi te）'} value={ttsPhoneme}
              onChange={e => setTtsPhoneme(e.target.value)}
              onKeyDown={e => { if (e.key === 'Enter') addTtsEntry(); }}/>
            <select className="select" value={ttsLocale} onChange={e => setTtsLocale(e.target.value)}
              style={{ flex: '0 0 100px' }}>
              <option value="zh">zh</option>
              <option value="en">en</option>
            </select>
            <button className="btn-primary" disabled={ttsAdding || !ttsWord.trim() || !ttsPhoneme.trim()} onClick={addTtsEntry}
              style={{ flexShrink: 0 }}>
              {ttsAdding ? t('添加中…') : t('添加')}
            </button>
          </div>

          <div className="text-xs text-dim" style={{ marginBottom: 12 }}>
            添加发音规则后，TTS 引擎会在遇到匹配词条时使用指定音素发音。需要后端引擎支持词库功能才能生效。
          </div>

          <div style={{ background: 'var(--bg-2)', border: '1px solid var(--border)', borderRadius: 'var(--radius)' }}>
            <table className="dm-table">
              <thead>
                <tr><th>{t('词条')}</th><th>{t('音素')}</th><th>{t('语言')}</th><th>{t('创建时间')}</th><th style={{ textAlign: 'right' }}>{t('操作')}</th></tr>
              </thead>
              <tbody>
                {loading && (
                  <tr><td colSpan={5} className="text-dim" style={{ textAlign: 'center', padding: 32 }}>{t('加载中…')}</td></tr>
                )}
                {!loading && ttsEntries.length === 0 && (
                  <tr><td colSpan={5} className="text-dim" style={{ textAlign: 'center', padding: 32 }}>
                    暂无发音规则 — 添加自定义发音映射
                  </td></tr>
                )}
                {!loading && ttsEntries.map((e, i) => (
                  <tr key={i}>
                    <td style={{ fontWeight: 500 }}>{e.word}</td>
                    <td className="text-mono text-xs">{e.phoneme}</td>
                    <td><span className="lex-tag">{e.locale}</span></td>
                    <td className="text-mono text-xs text-dim">{e.created_at || '-'}</td>
                    <td style={{ textAlign: 'right' }}>
                      <button className="btn-ghost" style={{ padding: '4px 10px', fontSize: 11, color: 'var(--danger)' }}
                        onClick={() => deleteTtsEntry(e.lexicon_id)}>{t('删除')}</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}

window.LexiconPage = LexiconPage;
