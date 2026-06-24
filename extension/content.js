// content.js — YouTube 实时翻译字幕
// 三阶段: ① 拦截 timedtext → 解析 XML → 预翻译 ② rAF 轮询播放时间 → 匹配 cue ③ DOM 叠加翻译
// 复用本地 realtime_server.py (127.0.0.1:8739) 的 TM + LLM 翻译

(function () {
  'use strict';

  // ── 配置 ──
  const SERVER = 'http://127.0.0.1:8739';
  const POLL_MS = 250; // 播放时间轮询间隔
  const OVERLAY_ID = 'ev-overlay-root';

  // ── 状态 ──
  let video = null;           // <video> 元素
  let subtitleMap = {};       // {startMs: {text, endMs, translation, cached}}
  let activeCue = null;       // 当前活跃的字幕
  let overlayEl = null;       // 叠加 DOM 元素
  let pollTimer = null;       // rAF/setInterval ID
  let lang = {};              // {from: 'en', to: 'zh-CN'}
  let enabled = true;         // 是否启用
  let serverOk = false;       // 服务器是否可达
  let pendingFetch = null;    // 防抖: 同一个 timedtext 不重复请求
  let lastVideoId = null;     // 检测视频切换

  // ── 初始化 ──
  loadSettings(() => {
    if (!enabled) return;
    checkServer(() => {
      injectOverlay();
      start();
    });
  });

  // ── 设置读写 ──
  function loadSettings(cb) {
    chrome.storage.local.get({
      enabled: true,
      targetLang: 'zh-CN',
      serverUrl: SERVER,
    }, (items) => {
      enabled = items.enabled;
      lang = { from: 'en', to: items.targetLang };
      if (cb) cb();
    });
  }

  chrome.storage.onChanged.addListener((changes) => {
    if (changes.enabled) { enabled = changes.enabled.newValue; if (!enabled) stop(); else start(); }
    if (changes.targetLang) { lang.to = changes.targetLang.newValue; subtitleMap = {}; }
    if (changes.serverUrl) { /* 需要重连 */ }
  });

  // ── 服务器探测 ──
  function checkServer(cb) {
    fetch(`${SERVER}/health`, { method: 'GET', signal: AbortSignal.timeout(2000) })
      .then(r => r.json())
      .then(() => { serverOk = true; if (cb) cb(); })
      .catch(() => { serverOk = false; if (cb) cb(); });
  }

  // ── 创建叠加层 ──
  function injectOverlay() {
    if (document.getElementById(OVERLAY_ID)) return;
    const root = document.createElement('div');
    root.id = OVERLAY_ID;
    root.className = 'ev-overlay-container';
    const cue = document.createElement('div');
    cue.className = 'ev-overlay-cue empty';
    root.appendChild(cue);
    // 注入到 YouTube player 容器中
    const tryInject = () => {
      const player = document.querySelector('#movie_player .html5-video-container')
        || document.querySelector('.html5-video-container');
      if (player) {
        player.appendChild(root);
        overlayEl = cue;
      } else {
        setTimeout(tryInject, 500);
      }
    };
    tryInject();
  }

  // ── 主循环 ──
  function start() {
    if (pollTimer) return;
    findVideo();
    interceptTimedtext();
    observeCaptionDOM();
    observeVideoChange();
    pollTimer = setInterval(tick, POLL_MS);
  }

  function stop() {
    clearInterval(pollTimer);
    pollTimer = null;
    if (overlayEl) overlayEl.className = 'ev-overlay-cue empty';
    subtitleMap = {};
    activeCue = null;
  }

  // ── 找 <video> ──
  function findVideo() {
    const v = document.querySelector('.html5-main-video')
      || document.querySelector('video');
    if (v && v !== video) {
      video = v;
      // 视频切换 → 清字幕缓存
      const vid = extractVideoId();
      if (vid !== lastVideoId) {
        lastVideoId = vid;
        subtitleMap = {};
      }
    }
    if (!video) setTimeout(findVideo, 1000);
  }

  function extractVideoId() {
    const url = new URL(location.href);
    return url.searchParams.get('v') || '';
  }

  // ── 每帧 tick: 检查播放时间, 匹配字幕 ──
  function tick() {
    if (!enabled || !video || video.paused || video.readyState < 2) {
      hideOverlay();
      return;
    }
    const t = video.currentTime * 1000; // ms

    // 找匹配的 cue
    let match = null;
    for (const [startMs, cue] of Object.entries(subtitleMap)) {
      const s = parseInt(startMs);
      if (t >= s && t < cue.endMs) {
        match = cue;
        break;
      }
    }

    if (!match) {
      hideOverlay();
      return;
    }

    // 相同 cue 不重复渲染
    if (activeCue && activeCue.startMs === match.startMs) return;
    activeCue = match;

    renderCue(match);
  }

  function renderCue(cue) {
    if (!overlayEl) return;
    if (cue.translation) {
      overlayEl.className = 'ev-overlay-cue';
      overlayEl.textContent = cue.translation;
    } else if (cue._fetching) {
      overlayEl.className = 'ev-overlay-cue loading';
      overlayEl.textContent = '…';
    } else {
      // 有原文但还没翻译 → 单条即时翻译
      overlayEl.className = 'ev-overlay-cue loading';
      overlayEl.textContent = '…';
      cue._fetching = true;
      translateOne(cue.text, (trans) => {
        cue.translation = trans;
        cue._fetching = false;
        cue.cached = false;
        if (activeCue === cue && overlayEl) {
          overlayEl.className = 'ev-overlay-cue';
          overlayEl.textContent = trans;
        }
      });
    }
  }

  function hideOverlay() {
    if (overlayEl && activeCue) {
      overlayEl.className = 'ev-overlay-cue empty';
      activeCue = null;
    }
  }

  // ── 单条翻译 (即时热路径) ──
  function translateOne(text, cb) {
    fetch(`${SERVER}/translate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: text, from: lang.from, to: lang.to }),
      signal: AbortSignal.timeout(8000),
    })
      .then(r => r.json())
      .then(data => cb(data.translation || text))
      .catch(() => cb('[翻译失败]'));
  }

  // ── 拦截 timedtext ──
  function interceptTimedtext() {
    const origFetch = window.fetch;
    const self = this;
    window.fetch = function (...args) {
      const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
      return origFetch.apply(this, args).then(resp => {
        if (url.includes('/api/timedtext') || url.includes('youtube.com/api/timedtext')) {
          handleTimedtextResponse(resp.clone(), url);
        }
        return resp;
      });
    };

    // 也拦截 XHR
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      this._ev_url = url;
      return origOpen.apply(this, arguments);
    };
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function () {
      const url = this._ev_url || '';
      if (url.includes('/api/timedtext') || url.includes('youtube.com/api/timedtext')) {
        this.addEventListener('load', () => {
          handleTimedtextText(this.responseText, url);
        });
      }
      return origSend.apply(this, arguments);
    };
  }

  function handleTimedtextResponse(resp, url) {
    resp.text().then(txt => handleTimedtextText(txt, url));
  }

  function handleTimedtextText(xmlText, url) {
    // 防抖: 同一个视频的 timedtext 只处理一次
    const vid = extractVideoId();
    const cacheKey = `${vid}`;
    if (pendingFetch === cacheKey) return;
    pendingFetch = cacheKey;

    const cues = parseTimedtextXML(xmlText);
    if (!cues.length) return;

    // 构建 subtitleMap
    const newMap = {};
    for (const c of cues) {
      newMap[c.startMs] = { text: c.text, endMs: c.endMs, translation: null, cached: false, startMs: c.startMs };
    }
    subtitleMap = newMap;

    // 批量预翻译
    preTranslateBatch(cues, () => {
      pendingFetch = null;
    });
  }

  function parseTimedtextXML(xml) {
    const cues = [];
    // YouTube timedtext XML: <p t="0" d="3000">text</p>
    const re = /<p\s[^>]*t="(\d+)"[^>]*d="(\d+)"[^>]*>([\s\S]*?)<\/p>/g;
    let m;
    while ((m = re.exec(xml)) !== null) {
      const startMs = parseInt(m[1]);
      const durMs = parseInt(m[2]);
      let text = m[3]
        .replace(/<[^>]+>/g, '')  // strip HTML tags
        .replace(/&amp;/g, '&')
        .replace(/&lt;/g, '<')
        .replace(/&gt;/g, '>')
        .replace(/&quot;/g, '"')
        .replace(/&#39;/g, "'")
        .trim();
      // Skip music cues and empty
      if (!text || text === '♪' || text === '[Music]' || text === '[音乐]') continue;
      cues.push({ startMs, endMs: startMs + durMs, text });
    }
    return cues;
  }

  // ── 批量预翻译 ──
  function preTranslateBatch(cues, done) {
    const texts = cues.map(c => c.text);
    fetch(`${SERVER}/translate/batch`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts, from: lang.from, to: lang.to }),
      signal: AbortSignal.timeout(15000),
    })
      .then(r => r.json())
      .then(data => {
        const results = data.results || [];
        for (const r of results) {
          // 找到匹配的 cue 并填入翻译
          for (const [startMs, cue] of Object.entries(subtitleMap)) {
            if (cue.text === r.original && r.translation) {
              cue.translation = r.translation;
              cue.cached = !!r.cached;
              break;
            }
          }
        }
        done();
      })
      .catch(() => done());
  }

  // ── 检测 YouTube 开启/关闭字幕 ──
  function observeCaptionDOM() {
    // 监听 caption 按钮状态变化, 辅助判断字幕是否开启
    const observer = new MutationObserver(() => {
      const captionBtn = document.querySelector('.ytp-subtitles-button');
      if (captionBtn && captionBtn.getAttribute('aria-pressed') === 'false') {
        // 字幕关闭 → 我们的叠加层也可以选择隐藏/显示（取决于偏好）
      }
    });
    const tryObserve = () => {
      const controls = document.querySelector('.ytp-right-controls');
      if (controls) {
        observer.observe(controls, { attributes: true, subtree: true, attributeFilter: ['aria-pressed'] });
      } else {
        setTimeout(tryObserve, 1000);
      }
    };
    tryObserve();
  }

  // ── 检测视频切换 (YouTube SPA) ──
  function observeVideoChange() {
    let lastUrl = location.href;
    new MutationObserver(() => {
      if (location.href !== lastUrl) {
        lastUrl = location.href;
        subtitleMap = {};
        activeCue = null;
        pendingFetch = null;
        lastVideoId = extractVideoId();
        findVideo();
      }
    }).observe(document.querySelector('title') || document.head, { subtree: true, childList: true, characterData: true });
  }

  // ── 恢复注入 (YouTube SPA 可能会清 DOM) ──
  setInterval(() => {
    if (!document.getElementById(OVERLAY_ID)) {
      injectOverlay();
      findVideo();
    }
  }, 3000);

})();
