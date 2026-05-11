// 系统资源监控页面
const { useState: useStateR, useEffect: useEffectR, useRef: useRefR, useCallback: useCallbackR } = React;

const MAX_POINTS = 600; // 10 min × 1/s
const EVENT_COLORS = { asr: 'oklch(0.75 0.13 230)', tts: 'oklch(0.75 0.15 155)', vad: 'oklch(0.80 0.14 80)' };

// persistent store across page switches
if (!window.__resData) {
  window.__resData = {
    labels: [],
    cpu: [], mem: [], dioR: [], dioW: [], netDown: [], netUp: [],
    events: [], lastEventTs: 0, prev: null,
  };
}

function fmtRate(bps) {
  if (bps >= 1e6) return (bps / 1e6).toFixed(1) + ' MB/s';
  if (bps >= 1e3) return (bps / 1e3).toFixed(1) + ' KB/s';
  return bps.toFixed(0) + ' B/s';
}
function fmtTime(ts) {
  const d = new Date(ts * 1000);
  return d.toLocaleTimeString('zh', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

function makeChartConfig(datasets, yMax) {
  return {
    type: 'line',
    data: { labels: [], datasets },
    options: {
      responsive: true, maintainAspectRatio: false, animation: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: datasets.length > 1, position: 'top', labels: { boxWidth: 10, font: { size: 10, family: "'JetBrains Mono'" }, color: '#8a8e95' } } },
      scales: {
        x: { display: true, ticks: { maxTicksLimit: 8, font: { size: 9, family: "'JetBrains Mono'" }, color: '#5a5e64' }, grid: { color: 'rgba(255,255,255,0.04)' } },
        y: { min: 0, max: yMax || undefined, ticks: { font: { size: 9, family: "'JetBrains Mono'" }, color: '#5a5e64' }, grid: { color: 'rgba(255,255,255,0.04)' } },
      },
    },
  };
}

function ds(label, color) {
  return { label, data: [], borderColor: color, backgroundColor: color + '33', borderWidth: 1.5, pointRadius: 0, tension: 0.3, fill: false };
}

function ResourceMonitorPage() {
  const { t, systemApi } = window;

  const [stats, setStats] = useStateR(null);
  const [rates, setRates] = useStateR({ netUp: 0, netDown: 0, diskR: 0, diskW: 0 });

  const chartsRef = useRefR({ cpu: null, mem: null, dio: null, net: null });
  const canvasRefs = { cpu: useRefR(null), mem: useRefR(null), dio: useRefR(null), net: useRefR(null) };
  const D = window.__resData;

  const eventPlugin = useCallbackR(() => ({
    id: 'eventMarkers',
    afterDraw(chart) {
      const events = D.events;
      if (!events.length) return;
      const { ctx, chartArea: { left, right, top, bottom }, scales: { x } } = chart;
      const labels = chart.data.labels;
      if (!labels.length) return;
      events.forEach(ev => {
        const label = fmtTime(ev.ts);
        const idx = labels.lastIndexOf(label);
        if (idx < 0) return;
        const xPos = x.getPixelForValue(idx);
        if (xPos < left || xPos > right) return;
        ctx.save();
        ctx.strokeStyle = EVENT_COLORS[ev.domain] || '#888';
        ctx.lineWidth = 1;
        ctx.globalAlpha = 0.6;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(xPos, top);
        ctx.lineTo(xPos, bottom);
        ctx.stroke();
        ctx.restore();
      });
    }
  }), []);

  useEffectR(() => {
    const C = window.Chart;
    if (!C) return;

    const theme = document.documentElement.getAttribute('data-theme');
    const gridAlpha = theme === 'light' ? 'rgba(0,0,0,0.06)' : 'rgba(255,255,255,0.04)';
    const tickColor = theme === 'light' ? '#666' : '#5a5e64';

    const plugin = eventPlugin();
    const createChart = (ref, datasets, yMax, storedData) => {
      if (!ref.current) return null;
      const cfg = makeChartConfig(datasets, yMax);
      cfg.options.scales.x.grid.color = gridAlpha;
      cfg.options.scales.y.grid.color = gridAlpha;
      cfg.options.scales.x.ticks.color = tickColor;
      cfg.options.scales.y.ticks.color = tickColor;
      cfg.plugins = [plugin];
      cfg.data.labels = [...D.labels];
      storedData.forEach((arr, i) => { cfg.data.datasets[i].data = [...arr]; });
      return new C(ref.current, cfg);
    };

    chartsRef.current.cpu = createChart(canvasRefs.cpu, [ds('CPU %', '#84cc16')], 100, [D.cpu]);
    chartsRef.current.mem = createChart(canvasRefs.mem, [ds('MEM %', '#38bdf8')], 100, [D.mem]);
    chartsRef.current.dio = createChart(canvasRefs.dio, [ds(t('读取'), '#38bdf8'), ds(t('写入'), '#fb923c')], undefined, [D.dioR, D.dioW]);
    chartsRef.current.net = createChart(canvasRefs.net, [ds(t('下行'), '#38bdf8'), ds(t('上行'), '#fb923c')], undefined, [D.netDown, D.netUp]);

    return () => {
      Object.values(chartsRef.current).forEach(c => c && c.destroy());
      chartsRef.current = { cpu: null, mem: null, dio: null, net: null };
    };
  }, []);

  useEffectR(() => {
    const onData = (e) => {
      setStats(e.detail.stats);
      setRates(e.detail.rates);
      const charts = chartsRef.current;
      const syncChart = (chart, arrs) => {
        if (!chart) return;
        chart.data.labels = D.labels;
        arrs.forEach((arr, i) => { chart.data.datasets[i].data = arr; });
        chart.update('none');
      };
      syncChart(charts.cpu, [D.cpu]);
      syncChart(charts.mem, [D.mem]);
      syncChart(charts.dio, [D.dioR, D.dioW]);
      syncChart(charts.net, [D.netDown, D.netUp]);
    };
    if (window.__resCollector?.latest?.stats) {
      setStats(window.__resCollector.latest.stats);
      setRates(window.__resCollector.latest.rates);
    }
    window.addEventListener('res-data-updated', onData);
    return () => window.removeEventListener('res-data-updated', onData);
  }, []);

  const cpu = stats ? stats.cpu_percent : 0;
  const mem = stats ? stats.memory : { used_bytes: 0, total_bytes: 1, percent: 0 };
  const disk = stats ? stats.disk : { used_bytes: 0, total_bytes: 1, percent: 0 };

  return (
    <div className="main-inner">
      <div className="page-header">
        <div>
          <h2 className="page-title">{t('资源监控')}</h2>
          <div className="page-sub">{t('系统资源 · 实时')}</div>
        </div>
      </div>

      <div className="card-grid" style={{ marginBottom: 20 }}>
        <div className="stat-card">
          <div className="stat-label">{t('CPU 使用率')}</div>
          <div className="stat-value">{cpu.toFixed(1)}<span style={{ fontSize: 14, color: 'var(--text-dim)' }}> %</span></div>
          <div className="stat-bar"><div className="stat-bar-fill" style={{ width: cpu + '%', background: 'var(--accent)' }}/></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">{t('内存使用')}</div>
          <div className="stat-value">{(mem.used_bytes / 1e9).toFixed(1)}<span style={{ fontSize: 14, color: 'var(--text-dim)' }}> / {(mem.total_bytes / 1e9).toFixed(1)} GB</span></div>
          <div className="stat-bar"><div className="stat-bar-fill" style={{ width: mem.percent + '%', background: 'var(--info)' }}/></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">{t('磁盘空间')}</div>
          <div className="stat-value">{(disk.used_bytes / 1e9).toFixed(1)}<span style={{ fontSize: 14, color: 'var(--text-dim)' }}> / {(disk.total_bytes / 1e9).toFixed(1)} GB</span></div>
          <div className="stat-bar"><div className="stat-bar-fill" style={{ width: disk.percent + '%', background: 'var(--warn)' }}/></div>
        </div>
        <div className="stat-card">
          <div className="stat-label">{t('网络速率')}</div>
          <div className="stat-value" style={{ fontSize: 20 }}>
            <span style={{ color: '#38bdf8' }}>↓{fmtRate(rates.netDown)}</span>
            <span style={{ fontSize: 14, color: 'var(--text-low)', margin: '0 6px' }}>/</span>
            <span style={{ color: '#fb923c' }}>↑{fmtRate(rates.netUp)}</span>
          </div>
        </div>
      </div>

      <div style={{ marginBottom: 12, display: 'flex', alignItems: 'center', gap: 16 }}>
        <span className="section-label" style={{ margin: 0 }}>EVENT MARKERS</span>
        {Object.entries(EVENT_COLORS).map(([k, c]) => (
          <span key={k} style={{ display: 'inline-flex', alignItems: 'center', gap: 4, fontSize: 11, fontFamily: 'var(--font-mono)', color: 'var(--text-dim)' }}>
            <span style={{ width: 10, height: 3, borderRadius: 2, background: c, display: 'inline-block' }}/>
            {k.toUpperCase()}
          </span>
        ))}
      </div>

      <div className="chart-grid">
        <div className="chart-card">
          <div className="chart-card-title">{t('CPU 使用率')} (%)</div>
          <div style={{ height: 200 }}><canvas ref={canvasRefs.cpu}/></div>
        </div>
        <div className="chart-card">
          <div className="chart-card-title">{t('内存使用')} (%)</div>
          <div style={{ height: 200 }}><canvas ref={canvasRefs.mem}/></div>
        </div>
        <div className="chart-card">
          <div className="chart-card-title">{t('磁盘 I/O')} (KB/s)</div>
          <div style={{ height: 200 }}><canvas ref={canvasRefs.dio}/></div>
        </div>
        <div className="chart-card">
          <div className="chart-card-title">{t('网络速率')} (KB/s)</div>
          <div style={{ height: 200 }}><canvas ref={canvasRefs.net}/></div>
        </div>
      </div>
    </div>
  );
}

window.ResourceMonitorPage = ResourceMonitorPage;
