// popup.js — 扩展弹窗逻辑

const SERVER_DEFAULT = 'http://127.0.0.1:8739';

// Load saved settings
chrome.storage.local.get({
  enabled: true,
  targetLang: 'zh-CN',
  serverUrl: SERVER_DEFAULT,
}, (items) => {
  document.getElementById('switch').checked = items.enabled;
  document.getElementById('target-lang').value = items.targetLang;
  document.getElementById('server-url').value = items.serverUrl;
  checkServerStatus(items.serverUrl);
});

// Toggle
document.getElementById('switch').addEventListener('change', (e) => {
  const v = e.target.checked;
  chrome.storage.local.set({ enabled: v });
  // 通知 content script (via storage change event)
});

// Language
document.getElementById('target-lang').addEventListener('change', (e) => {
  const v = e.target.value;
  chrome.storage.local.set({ targetLang: v });
});

// Server URL
document.getElementById('server-url').addEventListener('change', (e) => {
  const v = e.target.value;
  if (!v) return;
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
