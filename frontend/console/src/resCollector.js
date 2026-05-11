// Global resource collector — runs from app start, independent of ResourceMonitorPage mount
(function() {
  const MAX_POINTS = 600;
  if (!window.__resData) {
    window.__resData = {
      labels: [], cpu: [], mem: [], dioR: [], dioW: [],
      netDown: [], netUp: [], events: [], lastEventTs: 0, prev: null,
    };
  }

  function fmtTime(ts) {
    const d = new Date(ts * 1000);
    return d.toLocaleTimeString('zh', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  }

  window.__resCollector = {
    timer: null,
    latest: { stats: null, rates: { netUp: 0, netDown: 0, diskR: 0, diskW: 0, memBW: 0 } },
    start() {
      if (this.timer) return;
      const tick = async () => {
        const D = window.__resData;
        try {
          const [s, evts] = await Promise.all([
            window.systemApi.stats(),
            window.systemApi.events(D.lastEventTs),
          ]);
          if (!s) return;

          const prev = D.prev;
          let rates = { netUp: 0, netDown: 0, diskR: 0, diskW: 0, memBW: 0 };
          if (prev) {
            const dt = s.timestamp - prev.timestamp || 1;
            rates = {
              netUp: (s.network.bytes_sent - prev.network.bytes_sent) / dt,
              netDown: (s.network.bytes_recv - prev.network.bytes_recv) / dt,
              diskR: (s.disk_io.read_bytes - prev.disk_io.read_bytes) / dt,
              diskW: (s.disk_io.write_bytes - prev.disk_io.write_bytes) / dt,
              memBW: Math.abs(s.memory.used_bytes - prev.memory.used_bytes) / dt,
            };
          }
          D.prev = s;

          if (evts && evts.length) {
            D.events = [...D.events, ...evts].slice(-MAX_POINTS);
            D.lastEventTs = evts[evts.length - 1].ts;
          }

          const label = fmtTime(s.timestamp);
          const trim = (arr) => { if (arr.length > MAX_POINTS) arr.shift(); };

          D.labels.push(label);
          D.cpu.push(s.cpu_percent);
          D.mem.push(s.memory.percent);
          trim(D.labels); trim(D.cpu); trim(D.mem);

          if (prev) {
            const dt = s.timestamp - prev.timestamp || 1;
            D.dioR.push((s.disk_io.read_bytes - prev.disk_io.read_bytes) / dt / 1024);
            D.dioW.push((s.disk_io.write_bytes - prev.disk_io.write_bytes) / dt / 1024);
            D.netDown.push((s.network.bytes_recv - prev.network.bytes_recv) / dt / 1024);
            D.netUp.push((s.network.bytes_sent - prev.network.bytes_sent) / dt / 1024);
          } else {
            D.dioR.push(0); D.dioW.push(0); D.netDown.push(0); D.netUp.push(0);
          }
          trim(D.dioR); trim(D.dioW); trim(D.netDown); trim(D.netUp);

          this.latest = { stats: s, rates };
          window.dispatchEvent(new CustomEvent('res-data-updated', {
            detail: { stats: s, rates }
          }));
        } catch {}
      };
      tick();
      this.timer = setInterval(tick, 1000);
    },
    stop() {
      if (this.timer) { clearInterval(this.timer); this.timer = null; }
    },
  };
})();
