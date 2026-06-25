// popup.js — 扩展弹窗逻辑

const SERVER_DEFAULT = 'http://127.0.0.1:8739';

// Load saved settings
chrome.storage.local.get({
  enabled: true,
  sourceLang: 'auto',
  targetLang: 'zh-CN',
  serverUrl: SERVER_DEFAULT,
}, (items) => {
  document.getElementById('switch').checked = items.enabled;
  document.getElementById('source-lang').value = items.sourceLang;
  document.getElementById('target-lang').value = items.targetLang;
  document.getElementById('server-url').value = items.serverUrl;
  checkServerStatus(items.serverUrl);
});

// Toggle
document.getElementById('switch').addEventListener('change', (e) => {
  chrome.storage.local.set({ enabled: e.target.checked });
});

// Source language
document.getElementById('source-lang').addEventListener('change', (e) => {
  chrome.storage.local.set({ sourceLang: e.target.value });
  // Validate: source != target
  const target = document.getElementById('target-lang').value;
  if (e.target.value !== 'auto' && e.target.value === target) {
    document.getElementById('server-status').textContent = '源语言和目标语言不能相同';
  }
});

// Target language
document.getElementById('target-lang').addEventListener('change', (e) => {
  chrome.storage.local.set({ targetLang: e.target.value });
  const src = document.getElementById('source-lang').value;
  if (src !== 'auto' && src === e.target.value) {
    document.getElementById('server-status').textContent = '源语言和目标语言不能相同';
  }
});

// Server URL (restrict to localhost only)
document.getElementById('server-url').addEventListener('change', (e) => {
  const v = e.target.value.trim();
  if (!v) return;
  if (!/^https?:\/\/(?:127\.0\.0\.1|localhost)(?::\d+)?$/.test(v)) {
    document.getElementById('server-status').textContent = '仅允许 http://127.0.0.1 或 http://localhost';
    return;
  }
  chrome.storage.local.set({ serverUrl: v });
  checkServerStatus(v);
});

// Check server health
function checkServerStatus(url) {
  const dot = document.getElementById('server-dot');
  const status = document.getElementById('server-status');
  dot.className = 'dot';
  status.textContent = '检测中…';

  fetch(`${url}/health`, { method: 'GET', signal: AbortSignal.timeout(2000) })
    .then(r => r.json())
    .then(() => {
      dot.className = 'dot ok';
      status.textContent = '翻译服务已连接';
    })
    .catch(() => {
      dot.className = 'dot err';
      status.textContent = '翻译服务未启动 — 运行 realtime_server.py';
    });
}
