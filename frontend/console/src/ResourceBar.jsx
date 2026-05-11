// Compact real-time resource bar for try pages
const { useState: useStateRB, useEffect: useEffectRB } = React;

function fmtRateRB(bps) {
  if (bps >= 1e6) return (bps / 1e6).toFixed(1) + ' MB/s';
  if (bps >= 1e3) return (bps / 1e3).toFixed(1) + ' KB/s';
  return bps.toFixed(0) + ' B/s';
}

function CoreBar({ idx, pct }) {
  return (
    <div className="rb-core-bar">
      <span className="rb-core-idx">{idx}</span>
      <div className="rb-core-track">
        <div className="rb-core-fill" style={{ width: pct + '%' }}/>
      </div>
      <span className="rb-core-pct">{Math.round(pct)}%</span>
    </div>
  );
}

function ResourceBar() {
  const { t } = window;
  const [stats, setStats] = useStateRB(null);
  const [rates, setRates] = useStateRB({ netUp: 0, netDown: 0, memBW: 0 });

  useEffectRB(() => {
    if (window.__resCollector?.latest?.stats) {
      setStats(window.__resCollector.latest.stats);
      setRates(window.__resCollector.latest.rates);
    }
    const onData = (e) => {
      setStats(e.detail.stats);
      setRates(e.detail.rates);
    };
    window.addEventListener('res-data-updated', onData);
    return () => window.removeEventListener('res-data-updated', onData);
  }, []);

  const cores = stats?.cpu_per_core || (stats ? Array(16).fill(stats.cpu_percent) : []);
  const mid = Math.ceil(cores.length / 2);
  const isK3 = cores.length === 16;
  const group1Label = isK3 ? 'X100' : 'Big';
  const group2Label = isK3 ? 'A100' : 'Small';
  const mem = stats?.memory || { used_bytes: 0, total_bytes: 1, percent: 0 };

  return (
    <div className="resource-bar">
      <div className="rb-section rb-cpu-section">
        <div className="rb-cpu-group">
          <div className="rb-label">{group1Label}</div>
          <div className="rb-core-list">
            {cores.slice(0, mid).map((pct, i) => (
              <CoreBar key={i} idx={i} pct={pct}/>
            ))}
          </div>
        </div>
        <div className="rb-cpu-group">
          <div className="rb-label">{group2Label}</div>
          <div className="rb-core-list">
            {cores.slice(mid).map((pct, i) => (
              <CoreBar key={i} idx={mid + i} pct={pct}/>
            ))}
          </div>
        </div>
      </div>

      <div className="rb-section">
        <div className="rb-label">{t('内存')}</div>
        <div className="rb-value">{(mem.used_bytes / 1e9).toFixed(1)}<span style={{ color: 'var(--text-dim)' }}> / {(mem.total_bytes / 1e9).toFixed(1)} GB</span></div>
        <div className="rb-mem-bar">
          <div className="rb-mem-bar-fill" style={{ width: mem.percent + '%' }}/>
        </div>
      </div>

      <div className="rb-section">
        <div className="rb-label">{t('内存带宽')}</div>
        <div className="rb-value">{fmtRateRB(rates.memBW || 0)}</div>
      </div>

      <div className="rb-section">
        <div className="rb-label">{t('网络')}</div>
        <div className="rb-value">
          <span style={{ color: '#fb923c' }}>↑{fmtRateRB(rates.netUp || 0)}</span>
        </div>
        <div className="rb-value">
          <span style={{ color: '#38bdf8' }}>↓{fmtRateRB(rates.netDown || 0)}</span>
        </div>
      </div>
    </div>
  );
}

window.ResourceBar = ResourceBar;
