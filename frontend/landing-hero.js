// Animated hero background — grid of pulsing "compute nodes" reacting to mouse
(function() {
  const cvs = document.getElementById('hero-canvas');
  if (!cvs) return;
  const ctx = cvs.getContext('2d');
  let W = 0, H = 0, dpr = Math.min(window.devicePixelRatio || 1, 2);
  let mouse = { x: -9999, y: -9999, active: false };
  let t0 = performance.now();

  function resize() {
    const r = cvs.getBoundingClientRect();
    W = r.width; H = r.height;
    cvs.width = W * dpr; cvs.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }
  window.addEventListener('resize', resize);
  resize();

  window.addEventListener('mousemove', (e) => {
    const r = cvs.getBoundingClientRect();
    mouse.x = e.clientX - r.left;
    mouse.y = e.clientY - r.top;
    mouse.active = true;
  });
  window.addEventListener('mouseout', () => { mouse.active = false; });

  // grid
  const GAP = 36;
  // Lemon-green accent (oklch(0.84 0.19 135)) → roughly rgb(183, 229, 60)
  const ACCENT = [183, 229, 60];

  function draw(now) {
    const t = (now - t0) / 1000;
    ctx.clearRect(0, 0, W, H);

    const cols = Math.ceil(W / GAP) + 1;
    const rows = Math.ceil(H / GAP) + 1;

    // sweep origin: slow-moving "inference pulse"
    const pulseX = W * (0.5 + 0.35 * Math.cos(t * 0.3));
    const pulseY = H * (0.5 + 0.35 * Math.sin(t * 0.22));

    for (let i = 0; i < cols; i++) {
      for (let j = 0; j < rows; j++) {
        const x = i * GAP;
        const y = j * GAP;

        // distance to pulse source
        const dp = Math.hypot(x - pulseX, y - pulseY);
        const wave = Math.sin(dp * 0.02 - t * 1.8) * 0.5 + 0.5; // 0..1

        // distance to mouse
        let md = Infinity;
        if (mouse.active) md = Math.hypot(x - mouse.x, y - mouse.y);
        const mouseInfluence = mouse.active ? Math.max(0, 1 - md / 220) : 0;

        // base dim node
        const base = 0.05 + wave * 0.12;
        const alpha = Math.min(1, base + mouseInfluence * 0.8);

        // size
        const s = 1 + wave * 0.6 + mouseInfluence * 2.2;

        // color: far nodes = gray, near mouse = green
        const greenness = Math.max(wave * 0.25, mouseInfluence);
        const r = Math.round(120 + (ACCENT[0] - 120) * greenness);
        const g = Math.round(130 + (ACCENT[1] - 130) * greenness);
        const b = Math.round(140 + (ACCENT[2] - 140) * greenness);

        ctx.fillStyle = `rgba(${r},${g},${b},${alpha})`;
        ctx.fillRect(x - s / 2, y - s / 2, s, s);

        // occasional "hot" node — draws a cross glow
        if (mouseInfluence > 0.6) {
          ctx.fillStyle = `rgba(${ACCENT[0]},${ACCENT[1]},${ACCENT[2]},${mouseInfluence * 0.3})`;
          ctx.fillRect(x - 8, y - 0.5, 16, 1);
          ctx.fillRect(x - 0.5, y - 8, 1, 16);
        }
      }
    }

    // scan lines
    const scanY = (t * 90) % (H + 200) - 100;
    const grad = ctx.createLinearGradient(0, scanY - 80, 0, scanY + 80);
    grad.addColorStop(0, 'rgba(183,229,60,0)');
    grad.addColorStop(0.5, 'rgba(183,229,60,0.04)');
    grad.addColorStop(1, 'rgba(183,229,60,0)');
    ctx.fillStyle = grad;
    ctx.fillRect(0, scanY - 80, W, 160);

    requestAnimationFrame(draw);
  }
  requestAnimationFrame(draw);
})();

/* ===== Nav scroll state ===== */
(function() {
  const nav = document.querySelector('.nav');
  if (!nav) return;
  const onScroll = () => {
    if (window.scrollY > 20) nav.classList.add('scrolled');
    else nav.classList.remove('scrolled');
  };
  window.addEventListener('scroll', onScroll);
  onScroll();
})();

/* ===== Typed live-stream in hero console ===== */
(function() {
  const stream = document.getElementById('stream');
  if (!stream) return;

  const LOG_TEMPLATES = [
    { tag: 'ASR', cls: 'info',  tmpl: (n) => `sensevoice · 输入 ${n}s · 置信度 <b>0.9${Math.floor(Math.random()*9)}</b>` },
    { tag: 'TTS', cls: '',      tmpl: (n) => `matcha_zh · 合成 ${n} tokens · 22050Hz` },
    { tag: 'VAD', cls: 'info',  tmpl: (n) => `silero · 检测到 <b>${n}</b> 段语音` },
    { tag: 'VLM', cls: '',      tmpl: (n) => `qwen2.5-vl · 输入图像 ${n}x${n} · 推理完成` },
    { tag: 'YOLO',cls: '',      tmpl: (n) => `yolov11n · 检测到 <b>${n}</b> 个目标 · INT8` },
    { tag: 'LLM', cls: '',      tmpl: (n) => `qwen3-4b · 流式 <b>${n}</b> tok/s` },
    { tag: 'SYS', cls: 'info',  tmpl: ()  => `调度器 · 队列 0 · Matrix 负载 ${60+Math.floor(Math.random()*30)}%` },
    { tag: 'ASR', cls: 'warn',  tmpl: ()  => `qwen3-asr · 预热完成 · cold start 去除` },
  ];

  let lines = [];
  const MAX = 14;
  let counters = { asr: 0, tts: 0, vad: 0 };

  function pad(n) { return n.toString().padStart(2, '0'); }
  function ts() {
    const d = new Date();
    return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}.${d.getMilliseconds().toString().padStart(3,'0')}`;
  }

  function addLine() {
    const tpl = LOG_TEMPLATES[Math.floor(Math.random() * LOG_TEMPLATES.length)];
    const n = Math.floor(Math.random() * 40) + 2;
    const msg = tpl.tmpl(n);
    lines.push({ ts: ts(), tag: tpl.tag, cls: tpl.cls, msg });
    if (lines.length > MAX) lines.shift();
    render();

    // update live stats
    if (tpl.tag === 'ASR') counters.asr++;
    if (tpl.tag === 'TTS') counters.tts++;
    if (tpl.tag === 'VAD') counters.vad++;
    const req = document.getElementById('stat-req');
    if (req) req.firstChild.nodeValue = (3240 + counters.asr + counters.tts + counters.vad).toLocaleString();
  }

  function render() {
    stream.innerHTML = lines.map((l, i) => {
      const last = i === lines.length - 1;
      return `<div class="ln"><span class="ts">${l.ts}</span><span class="tag ${l.cls}">${l.tag}</span><span class="msg">${l.msg}${last ? '<span class="caret"></span>' : ''}</span></div>`;
    }).join('');
  }

  // seed with a few lines
  for (let i = 0; i < 6; i++) addLine();
  setInterval(addLine, 900 + Math.random() * 800);

  // animate latency stat
  const lat = document.getElementById('stat-lat');
  const npu = document.getElementById('stat-npu');
  if (lat && npu) {
    setInterval(() => {
      const l = 42 + Math.floor(Math.random() * 24);
      const n = 58 + Math.floor(Math.random() * 32);
      lat.firstChild.nodeValue = l;
      npu.firstChild.nodeValue = n;
    }, 1100);
  }
})();

/* ===== Capability card mouse-tracking ===== */
document.querySelectorAll('.cap').forEach(card => {
  card.addEventListener('mousemove', (e) => {
    const r = card.getBoundingClientRect();
    card.style.setProperty('--mx', (e.clientX - r.left) + 'px');
    card.style.setProperty('--my', (e.clientY - r.top) + 'px');
  });
});

/* ===== Numbers countup on scroll ===== */
(function() {
  const nums = document.querySelectorAll('[data-count]');
  const done = new WeakSet();
  const io = new IntersectionObserver((entries) => {
    entries.forEach(e => {
      if (!e.isIntersecting || done.has(e.target)) return;
      done.add(e.target);
      const el = e.target;
      const target = parseFloat(el.dataset.count);
      const decimals = parseInt(el.dataset.decimals || '0', 10);
      const dur = 1400;
      const start = performance.now();
      function tick(now) {
        const k = Math.min(1, (now - start) / dur);
        const ease = 1 - Math.pow(1 - k, 3);
        const v = target * ease;
        el.firstChild.nodeValue = decimals > 0 ? v.toFixed(decimals) : Math.floor(v).toLocaleString();
        if (k < 1) requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    });
  }, { threshold: 0.4 });
  nums.forEach(n => io.observe(n));
})();

/* ===== Mini waveform viz inside ASR card ===== */
(function() {
  const cvs = document.getElementById('viz-wave');
  if (!cvs) return;
  const ctx = cvs.getContext('2d');
  function resize() {
    const r = cvs.getBoundingClientRect();
    cvs.width = r.width * 2; cvs.height = r.height * 2;
    ctx.scale(2, 2);
  }
  resize();
  window.addEventListener('resize', () => { ctx.setTransform(1,0,0,1,0,0); resize(); });

  let t = 0;
  function draw() {
    const w = cvs.width / 2, h = cvs.height / 2;
    ctx.clearRect(0, 0, w, h);
    ctx.strokeStyle = 'rgba(183,229,60,.7)';
    ctx.lineWidth = 1.2;
    ctx.beginPath();
    const bars = 64;
    for (let i = 0; i < bars; i++) {
      const x = (i / bars) * w;
      const a = Math.sin(i * 0.4 + t) * Math.sin(i * 0.13 + t * 0.5);
      const y = h/2 + a * h * 0.35 * (0.3 + Math.abs(Math.sin(i * 0.2 + t * 0.8)));
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    }
    ctx.stroke();
    t += 0.12;
    requestAnimationFrame(draw);
  }
  draw();
})();

/* ===== Orbit viz inside LLM card ===== */
(function() {
  const cvs = document.getElementById('viz-orbit');
  if (!cvs) return;
  const ctx = cvs.getContext('2d');
  function resize() {
    const r = cvs.getBoundingClientRect();
    cvs.width = r.width * 2; cvs.height = r.height * 2;
    ctx.scale(2, 2);
  }
  resize();

  let t = 0;
  function draw() {
    const w = cvs.width / 2, h = cvs.height / 2;
    ctx.clearRect(0, 0, w, h);
    const cx = w * 0.82, cy = h * 0.55;
    ctx.strokeStyle = 'rgba(183,229,60,.18)';
    ctx.lineWidth = 0.8;
    [22, 36, 52].forEach(r => {
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI * 2); ctx.stroke();
    });
    // tokens orbiting
    const speeds = [1, -0.6, 0.35];
    [22, 36, 52].forEach((r, i) => {
      for (let k = 0; k < 4; k++) {
        const a = t * speeds[i] + (k * Math.PI / 2);
        const x = cx + Math.cos(a) * r;
        const y = cy + Math.sin(a) * r;
        ctx.fillStyle = `rgba(183,229,60,${0.3 + 0.2 * Math.sin(t + k)})`;
        ctx.fillRect(x - 1.5, y - 1.5, 3, 3);
      }
    });
    t += 0.015;
    requestAnimationFrame(draw);
  }
  draw();
})();

/* ===== Archi diagram SVG — animated packets ===== */
(function() {
  const svg = document.getElementById('arch-svg');
  if (!svg) return;
  // position of packets animates via CSS — already handled in SVG
})();
