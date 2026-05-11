// API 配置 — 修改这里即可连接真实后端
// 如果前端和后端不同源，请在后端配置 CORS 或使用反向代理

const TWEAK_DEFAULS = /*EDITMODE-BEGIN*/{
  "layout": "grid",
  "accent": "lime",
  "density": "comfortable"
}/*EDITMODE-END*/;
window.__TWEAKS__ = TWEAK_DEFAULS;

// API base URLs — 根据后端文档默认值
window.API_BASES = {
  asr:    location.protocol + '//' + location.hostname + ':18790',  // /v1/asr/*
  tts:    location.protocol + '//' + location.hostname + ':18790',  // /v1/tts/*
  vad:    location.protocol + '//' + location.hostname + ':18790',  // /v1/vad/*
  vision: location.protocol + '//' + location.hostname + ':18790',  // /v1/vision/*
  llm:    location.protocol + '//' + location.hostname + ':18790',  // /v1/llm/*
};

// 是否使用 Mock 数据（当后端离线时自动兜底；手动置 true 强制 mock）
window.USE_MOCK = false;

window.copyText = (text) => {
  const done = () => _showCopyToast();
  if (navigator.clipboard?.writeText) {
    return navigator.clipboard.writeText(text).then(done).catch(() => { _fallbackCopy(text); done(); });
  }
  _fallbackCopy(text);
  done();
};
function _fallbackCopy(text) {
  const ta = document.createElement('textarea');
  ta.value = text;
  ta.style.cssText = 'position:fixed;opacity:0';
  document.body.appendChild(ta);
  ta.select();
  document.execCommand('copy');
  document.body.removeChild(ta);
}
function _showCopyToast() {
  let el = document.getElementById('__copy-toast');
  if (!el) {
    el = document.createElement('div');
    el.id = '__copy-toast';
    el.style.cssText = 'position:fixed;top:24px;left:50%;transform:translateX(-50%);padding:6px 18px;border-radius:6px;font-size:12px;font-family:var(--font-mono);color:var(--accent);background:var(--bg-2);border:1px solid var(--accent-3);z-index:9999;pointer-events:none;opacity:0;transition:opacity .2s';
    document.body.appendChild(el);
  }
  el.textContent = (window.__lang === 'en') ? 'Copied' : '已复制';
  el.style.opacity = '1';
  clearTimeout(el._timer);
  el._timer = setTimeout(() => { el.style.opacity = '0'; }, 1500);
}
