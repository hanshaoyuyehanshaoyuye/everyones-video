// content.js — 多平台实时翻译字幕 (v6.2)
// 平台: YouTube / Bilibili / <track> WebVTT / 通用 fetch 拦截
// 语种: 自动检测 + 手动选择 (日韩俄德法+中英西葡阿)
// 共用后端 realtime_server.py (127.0.0.1:8739)

(function () {
  'use strict';

  // Polyfill: AbortSignal.timeout() (Chrome 103+, missing in older Chromium/Firefox ext)
  if (typeof AbortSignal !== 'undefined' && !AbortSignal.timeout) {
    AbortSignal.timeout = ms => {
      const ctrl = new AbortController();
      setTimeout(() => ctrl.abort(new DOMException('Timeout', 'TimeoutError')), ms);
      return ctrl.signal;
    };
  }

  const SERVER = 'http://127.0.0.1:8739';
  const POLL_MS = 250;
  const OVERLAY_ID = 'ev-overlay-root';

  // ── 状态 ──
  let video = null;
  let cueArray = [];        // [{startMs, endMs, text, translation, cached, _fetching}] (sorted by startMs)
  let activeCue = null;
  let overlayEl = null;
  let pollTimer = null;
  let rafId = null;
  let lang = { from: 'auto', to: 'zh-CN' };
  let enabled = true;
  let serverOk = false;
  let pendingUrl = null;
  let lastVideoId = null;
  let detectedLang = null;

  // ── 早期退出: 页面无 <video> 则跳过所有拦截（减少非视频页面的开销）──
  function hasVideo() {
    return !!document.querySelector('video');
  }

  function waitForVideo(timeoutMs, cb) {
    if (hasVideo()) { cb(); return; }
    const deadline = Date.now() + timeoutMs;
    const mo = new MutationObserver(() => {
      if (hasVideo()) { mo.disconnect(); cb(); return; }
      if (Date.now() > deadline) { mo.disconnect(); /* no video found, skip */ return; }
    });
    mo.observe(document.body || document.documentElement, { childList: true, subtree: true });
    setTimeout(() => { mo.disconnect(); }, timeoutMs);
  }

  // ── 初始化 ──
  loadSettings(() => {
    if (!enabled) return;
    checkServer(() => {
      // Wait up to 8s for a <video> element before attaching
      waitForVideo(8000, () => {
        if (!hasVideo()) return;  // page has no video — skip all overhead
        injectOverlay();
        start();
      });
    });
  });

  function loadSettings(cb) {
    chrome.storage.local.get({
      enabled: true, sourceLang: 'auto', targetLang: 'zh-CN', serverUrl: SERVER,
    }, items => {
      enabled = items.enabled;
      lang.from = items.sourceLang;
      lang.to = items.targetLang;
      if (cb) cb();
    });
  }
  chrome.storage.onChanged.addListener(changes => {
    if (changes.enabled) { enabled = changes.enabled.newValue; if (!enabled) stop(); else start(); }
    if (changes.sourceLang) { lang.from = changes.sourceLang.newValue; detectedLang = null; cueArray = []; }
    if (changes.targetLang) { lang.to = changes.targetLang.newValue; cueArray = []; }
  });

  // ── 源语言自动检测 (Unicode 范围) ──
  function detectSourceLang(texts) {
    // Sample first N non-empty texts
    const sample = texts.filter(t => t.trim()).slice(0, 5).join(' ');
    if (!sample) return 'en';

    const scripts = {};

    for (const ch of sample) {
      const cp = ch.codePointAt(0);
      if (cp >= 0x3040 && cp <= 0x309F || cp >= 0x30A0 && cp <= 0x30FF) scripts['ja'] = (scripts['ja'] || 0) + 1;        // Hiragana + Katakana
      else if (cp >= 0xAC00 && cp <= 0xD7AF) scripts['ko'] = (scripts['ko'] || 0) + 1;                                   // Hangul
      else if (cp >= 0x0400 && cp <= 0x04FF) scripts['ru'] = (scripts['ru'] || 0) + 1;                                   // Cyrillic
      else if (cp >= 0x4E00 && cp <= 0x9FFF || cp >= 0x3400 && cp <= 0x4DBF) scripts['zh'] = (scripts['zh'] || 0) + 1;   // CJK Unified
      else if (cp >= 0x0600 && cp <= 0x06FF) scripts['ar'] = (scripts['ar'] || 0) + 1;                                   // Arabic
      else if (cp >= 0x0E00 && cp <= 0x0E7F) scripts['th'] = (scripts['th'] || 0) + 1;                                   // Thai
      else scripts['latin'] = (scripts['latin'] || 0) + 1;
    }

    // Pick the script with most characters
    let best = 'latin', max = 0;
    for (const [s, count] of Object.entries(scripts)) {
      if (count > max) { max = count; best = s; }
    }

    // latin could be en/fr/de/es/pt — default en, user can override in popup
    if (best === 'latin') best = 'en';

    // Need a minimum CJK presence to distinguish zh from ja
    if (best === 'zh' && scripts['ja'] && scripts['ja'] > scripts['zh'] * 0.3) best = 'ja';

    return best;
  }

  function resolveSourceLang(cues) {
    if (lang.from && lang.from !== 'auto') return lang.from;
    if (detectedLang) return detectedLang;
    detectedLang = detectSourceLang(cues.map(c => c.text));
    console.log('[EV] Auto-detected source language:', detectedLang);
    return detectedLang;
  }

  function checkServer(cb) {
    fetch(`${SERVER}/health`, { method: 'GET', signal: AbortSignal.timeout(2000) })
      .then(r => r.json())
      .then(() => { serverOk = true; if (cb) cb(); })
      .catch(() => { serverOk = false; if (cb) cb(); });
  }

  // ── DOM 叠加层 ──
  function injectOverlay() {
    if (document.getElementById(OVERLAY_ID)) return;
    const root = document.createElement('div');
    root.id = OVERLAY_ID;
    root.className = 'ev-overlay-container';
    const cue = document.createElement('div');
    cue.className = 'ev-overlay-cue empty';
    root.appendChild(cue);
    const tryInject = () => {
      const container = document.querySelector('.html5-video-container')
        || document.querySelector('[class*="video"]')
        || document.querySelector('video')?.parentElement;
      if (container) { container.appendChild(root); overlayEl = cue; }
      else setTimeout(tryInject, 500);
    };
    tryInject();
  }
  setInterval(() => { if (!document.getElementById(OVERLAY_ID)) injectOverlay(); }, 3000);

  // ── 主循环（视频暂停时自动停止轮询）──
  function start() {
    if (pollTimer) return;
    findVideo(); attachCaptionSource(); observeVideoChange();
    pollTimer = setInterval(tick, POLL_MS);
  }
  function stop() {
    clearInterval(pollTimer); pollTimer = null;
    cancelAnimationFrame(rafId); rafId = null;
    if (overlayEl) overlayEl.className = 'ev-overlay-cue empty';
    cueArray = []; activeCue = null;
  }

  function findVideo() {
    const v = document.querySelector('video');
    if (v && v !== video) {
      if (video) { video.removeEventListener('play', onPlay); video.removeEventListener('pause', onPause); }
      video = v;
      video.addEventListener('play', onPlay);
      video.addEventListener('pause', onPause);
      const vid = location.href;
      if (vid !== lastVideoId) { lastVideoId = vid; cueArray = []; }
    }
    if (!video) setTimeout(findVideo, 1000);
  }

  function onPlay() {
    if (enabled && !pollTimer) pollTimer = setInterval(tick, POLL_MS);
  }
  function onPause() {
    clearInterval(pollTimer); pollTimer = null;
  }

  // ── 二分查找当前 cue（O(log n)，替代 O(n) 遍历）──
  function bsearchCue(tMs) {
    let lo = 0, hi = cueArray.length - 1;
    while (lo <= hi) {
      const mid = (lo + hi) >>> 1;
      const c = cueArray[mid];
      if (tMs >= c.startMs && tMs < c.endMs) return c;
      if (tMs < c.startMs) hi = mid - 1;
      else lo = mid + 1;
    }
    return null;
  }

  function tick() {
    if (!enabled || !video || video.paused || video.readyState < 2) { hideOverlay(); return; }
    if (!cueArray.length) return;
    const t = video.currentTime * 1000;
    const match = bsearchCue(t);
    if (!match) { hideOverlay(); return; }
    if (activeCue && activeCue.startMs === match.startMs) return;
    activeCue = match;
    renderCue(match);
  }

  function renderCue(cue) {
    if (!overlayEl) return;
    if (cue.translation) { overlayEl.className = 'ev-overlay-cue'; overlayEl.textContent = cue.translation; }
    else if (cue._fetching) { overlayEl.className = 'ev-overlay-cue loading'; overlayEl.textContent = '…'; }
    else {
      overlayEl.className = 'ev-overlay-cue loading'; overlayEl.textContent = '…';
      cue._fetching = true;
      translateOne(cue.text, trans => {
        cue.translation = trans; cue._fetching = false; cue.cached = false;
        if (activeCue === cue && overlayEl) { overlayEl.className = 'ev-overlay-cue'; overlayEl.textContent = trans; }
      }, cueArray);
    }
  }

  function hideOverlay() { if (overlayEl && activeCue) { overlayEl.className = 'ev-overlay-cue empty'; activeCue = null; } }

  // ── 翻译调用 ──
  function translateOne(text, cb, cues) {
    const src = cues ? resolveSourceLang(cues) : (lang.from === 'auto' ? 'en' : lang.from);
    fetch(`${SERVER}/translate`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, from: src, to: lang.to }),
      signal: AbortSignal.timeout(8000),
    }).then(r => r.json()).then(d => cb(d.translation || text)).catch(() => cb('[翻译失败]'));
  }

  function preTranslateBatch(cues, done) {
    if (!cues.length) { done(); return; }
    const src = resolveSourceLang(cues);
    const texts = cues.map(c => c.text);
    fetch(`${SERVER}/translate/batch`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ texts, from: src, to: lang.to }),
      signal: AbortSignal.timeout(15000),
    }).then(r => r.json()).then(data => {
      for (const r of (data.results || [])) {
        for (const cue of cueArray) {
          if (cue.text === r.original && r.translation) { cue.translation = r.translation; cue.cached = !!r.cached; break; }
        }
      }
      done();
    }).catch(() => done());
  }

  // ── 通用 cue → 排序数组 ──
  function ingestCues(cues) {
    cues.sort((a, b) => a.startMs - b.startMs);
    for (const c of cues) {
      c.translation = null; c.cached = false; c._fetching = false;
    }
    cueArray = cues;
    preTranslateBatch(cues, () => {});
  }

  // ── XML/SRT 文本清理 ──
  function cleanText(t) {
    return t.replace(/<[^>]+>/g, '').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&quot;/g, '"').replace(/&#39;/g, "'").trim();
  }

  // ═══════════════════════════════════════
  //  平台检测 + 字幕源适配器
  // ═══════════════════════════════════════

  function detectPlatform() {
    const host = location.hostname;
    if (host.includes('youtube.com') || host.includes('youtu.be')) return 'youtube';
    if (host.includes('bilibili.com')) return 'bilibili';
    // Generic: any site with <video> + <track>
    const track = document.querySelector('video track[kind="subtitles"], video track[kind="captions"]');
    if (track && track.src) return 'track';
    return 'generic';
  }

  function attachCaptionSource() {
    findVideo();
    const platform = detectPlatform();
    console.log('[EV] Platform:', platform);

    switch (platform) {
      case 'youtube': attachYouTube(); break;
      case 'bilibili': attachBilibili(); break;
      case 'track': attachTrackElement(); break;
      default: attachGenericFetch(); break;
    }
  }

  // ── YouTube 适配器 ──
  function attachYouTube() {
    // timedtext XML 拦截
    const origFetch = window.fetch;
    window.fetch = function (...args) {
      const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
      return origFetch.apply(this, args).then(resp => {
        if (url.includes('/api/timedtext') || url.includes('youtube.com/api/timedtext')) {
          resp.clone().text().then(txt => handleTimedtextXML(txt, url));
        }
        return resp;
      });
    };
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      this._ev_url = url; return origOpen.apply(this, arguments);
    };
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function () {
      const url = this._ev_url || '';
      if (url.includes('/api/timedtext') || url.includes('youtube.com/api/timedtext')) {
        this.addEventListener('load', () => handleTimedtextXML(this.responseText, url));
      }
      return origSend.apply(this, arguments);
    };
    // auto-detection handles source language
  }

  function handleTimedtextXML(xml, url) {
    const vid = location.href;
    if (pendingUrl === vid) return;
    pendingUrl = vid;
    const cues = parseTimedtextXML(xml);
    if (cues.length) ingestCues(cues);
  }

  function parseTimedtextXML(xml) {
    const cues = [];
    const re = /<p\s[^>]*t="(\d+)"[^>]*d="(\d+)"[^>]*>([\s\S]*?)<\/p>/g;
    let m;
    while ((m = re.exec(xml)) !== null) {
      const startMs = parseInt(m[1]), durMs = parseInt(m[2]);
      let text = cleanText(m[3]);
      if (!text || text === '♪' || text === '[Music]' || text === '[音乐]') continue;
      cues.push({ startMs, endMs: startMs + durMs, text });
    }
    return cues;
  }

  // ── Bilibili 适配器 ──
  function attachBilibili() {
    // Bilibili uses subtitle API: https://api.bilibili.com/x/player/v2?cid=...&bvid=...
    // auto-detection handles source language (zh/ja usually)
    // Also can intercept the internal player subtitle fetch
    const origFetch = window.fetch;
    window.fetch = function (...args) {
      const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
      return origFetch.apply(this, args).then(resp => {
        if (url.includes('bilibili.com') && (url.includes('subtitle') || url.includes('caption'))) {
          resp.clone().text().then(txt => handleBilibiliSubtitle(txt, url));
        }
        return resp;
      });
    };

    // Bilibili player API: window.player?.getCaptions?.()
    setTimeout(() => {
      try {
        const player = window.player || window.__BiliPlayer__;
        if (player && typeof player.getCaptions === 'function') {
          const captions = player.getCaptions();
          if (captions && captions.length) {
            const cues = captions.map(c => ({
              startMs: c.from * 1000,
              endMs: c.to * 1000,
              text: cleanText(c.content),
            })).filter(c => c.text);
            if (cues.length) ingestCues(cues);
          }
        }
      } catch (e) { /* not available */ }
    }, 3000);
  }

  function handleBilibiliSubtitle(jsonText, url) {
    try {
      const data = JSON.parse(jsonText);
      // Bilibili subtitle API returns { data: { subtitles: [{ lan_doc: "...", lan: "..." }] } }
      // or direct: { body: [{ from, to, content }] }
      let items = [];
      if (data.data?.body) items = data.data.body;
      else if (data.data?.subtitles) {
        // Pick Chinese subtitle
        const zh = data.data.subtitles.find(s => s.lan?.includes('zh') || s.lan_doc?.includes('中文')) || data.data.subtitles[0];
        if (zh && zh.subtitle_url) {
          fetch(zh.subtitle_url.startsWith('//') ? 'https:' + zh.subtitle_url : zh.subtitle_url)
            .then(r => r.json())
            .then(d => {
              const cues = (d.body || []).map(c => ({
                startMs: c.from * 1000, endMs: c.to * 1000, text: cleanText(c.content),
              })).filter(c => c.text);
              if (cues.length) ingestCues(cues);
            }).catch(() => {});
          return;
        }
      }
      if (items.length) {
        const cues = items.map(c => ({
          startMs: c.from * 1000, endMs: c.to * 1000, text: cleanText(c.content),
        })).filter(c => c.text);
        if (cues.length) ingestCues(cues);
      }
    } catch (e) { /* not JSON */ }
  }

  // ── <track> 适配器 (WebVTT) ──
  function attachTrackElement() {
    const tracks = document.querySelectorAll('video track[kind="subtitles"], video track[kind="captions"]');
    let fetched = false;
    for (const track of tracks) {
      if (!track.src || fetched) continue;
      const src = track.src;
      // Detect language from srclang or label
      if (track.srclang) lang.from = track.srclang.split('-')[0];
      fetch(src)
        .then(r => r.text())
        .then(vtt => {
          const cues = parseWebVTT(vtt);
          if (cues.length) { ingestCues(cues); fetched = true; }
        }).catch(() => {});
    }

    // Fallback: watch for new <track> elements (SPA sites)
    new MutationObserver(() => {
      const newTracks = document.querySelectorAll('video track[kind="subtitles"]:not([data-ev-seen])');
      for (const t of newTracks) {
        t.setAttribute('data-ev-seen', '1');
        if (t.src && !fetched) {
          // Try English first
          fetch(t.src).then(r => r.text()).then(vtt => {
            const cues = parseWebVTT(vtt);
            if (cues.length) { ingestCues(cues); fetched = true; }
          }).catch(() => {});
        }
      }
    }).observe(document.body, { childList: true, subtree: true });
  }

  function parseWebVTT(vtt) {
    const cues = [];
    // WebVTT format: [id]\nHH:MM:SS.mmm --> HH:MM:SS.mmm\n(text)\n\n
    const blocks = vtt.split(/\n\s*\n/);
    for (const block of blocks) {
      const lines = block.trim().split('\n');
      if (lines.length < 2) continue;
      const timeMatch = lines.find(l => l.includes('-->'));
      if (!timeMatch) continue;
      const textIdx = lines.indexOf(timeMatch) + 1;
      const text = lines.slice(textIdx).join(' ').trim();
      if (!text || text.startsWith('NOTE') || text.startsWith('WEBVTT')) continue;
      const m = timeMatch.match(/([\d:.]+)\s*-->\s*([\d:.]+)/);
      if (!m) continue;
      const startMs = parseVTTTime(m[1]), endMs = parseVTTTime(m[2]);
      cues.push({ startMs, endMs, text: cleanText(text) });
    }
    return cues;
  }

  function parseVTTTime(ts) {
    // HH:MM:SS.mmm or MM:SS.mmm
    const parts = ts.split(':');
    if (parts.length === 3) {
      return parseInt(parts[0]) * 3600000 + parseInt(parts[1]) * 60000 + parseFloat(parts[2]) * 1000;
    }
    return parseInt(parts[0]) * 60000 + parseFloat(parts[1]) * 1000;
  }

  // ── 通用 fetch 拦截 (兜底) ──
  function attachGenericFetch() {
    // auto-detection handles source language from subtitle text
    const origFetch = window.fetch;
    window.fetch = function (...args) {
      const url = typeof args[0] === 'string' ? args[0] : (args[0]?.url || '');
      return origFetch.apply(this, args).then(resp => {
        tryInterceptGeneric(resp.clone(), url);
        return resp;
      });
    };
    const origOpen = XMLHttpRequest.prototype.open;
    XMLHttpRequest.prototype.open = function (method, url) {
      this._ev_url = url; return origOpen.apply(this, arguments);
    };
    const origSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.send = function () {
      const url = this._ev_url || '';
      this.addEventListener('load', () => {
        tryInterceptGeneric({ text: () => Promise.resolve(this.responseText) }, url);
      });
      return origSend.apply(this, arguments);
    };

    // Also observe all <track> elements on any page
    setTimeout(() => { attachTrackElement(); }, 2000);
  }

  function tryInterceptGeneric(resp, url) {
    // Pattern match: subtitle file extensions
    const subExt = url.match(/\.(srt|vtt|dfxp|ttml|xml)(\?|$)/i);
    const subPath = url.match(/\/(subtitle|caption|timedtext|transcript)/i);
    if (!subExt && !subPath) return;

    const vid = location.href;
    if (pendingUrl === vid) return;
    pendingUrl = vid;

    resp.text().then(txt => {
      let cues = [];
      if (txt.includes('-->')) {
        // SRT or WebVTT
        cues = parseWebVTT(txt);
        if (!cues.length) cues = parseSRT(txt);
      } else if (txt.trim().startsWith('{')) {
        // JSON — try common subtitle JSON formats
        try { cues = parseSubtitleJSON(txt); } catch (e) { /* not subtitle JSON */ }
      }
      if (cues.length) ingestCues(cues);
    });
  }

  function parseSRT(srt) {
    const cues = [];
    const blocks = srt.split(/\n\s*\n/);
    for (const block of blocks) {
      const lines = block.trim().split('\n');
      if (lines.length < 3) continue;
      const timeLine = lines.find(l => l.includes('-->'));
      if (!timeLine) continue;
      const textIdx = lines.indexOf(timeLine) + 1;
      const text = lines.slice(textIdx).join(' ').trim();
      if (!text) continue;
      const m = timeLine.match(/(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})/);
      if (!m) continue;
      cues.push({
        startMs: parseSRTTime(m[1]),
        endMs: parseSRTTime(m[2]),
        text: cleanText(text),
      });
    }
    return cues;
  }

  function parseSRTTime(ts) {
    const [h, m, rest] = ts.split(':');
    const [s, ms] = rest.replace(',', '.').split('.');
    return parseInt(h) * 3600000 + parseInt(m) * 60000 + parseInt(s) * 1000 + parseInt(ms.padEnd(3, '0'));
  }

  function parseSubtitleJSON(txt) {
    const data = JSON.parse(txt);
    // Try many common JSON subtitle formats
    let items = null;
    // Format: { cues: [{ start, end, text }] }
    if (data.cues) items = data.cues;
    // Format: { segments: [{ start, end, text }] }
    else if (data.segments) items = data.segments;
    // Format: { events: [{ tStartMs, dDurationMs, segs: [{ utf8 }] }] } — YouTube JSON
    else if (data.events) {
      items = [];
      for (const ev of data.events) {
        if (ev.segs) {
          items.push({
            start: ev.tStartMs / 1000, end: (ev.tStartMs + (ev.dDurationMs || 0)) / 1000,
            text: ev.segs.map(s => s.utf8 || '').join(''),
            utf8: ev.segs.map(s => s.utf8 || '').join(''),
          });
        }
      }
    }
    // Format: { results: [{ alternatives: [{ words, transcript }] }] } — speech API
    else if (data.results) items = data.results;
    // Format: { body: [...] } — Bilibili
    else if (data.body) items = data.body;
    // Format: { words: [{ start, end, word }] } — word-level
    else if (data.words) items = data.words;

    if (!items) return [];

    return items.map(c => ({
      startMs: Math.round((c.start || c.from || c.startTime || c.begin || 0) * 1000),
      endMs: Math.round((c.end || c.to || c.endTime || c.finish || 0) * 1000),
      text: cleanText(c.text || c.content || c.utf8 || c.transcript || c.word || ''),
    })).filter(c => c.text && c.endMs > c.startMs);
  }

  // ── 视频切换 / SPA 路由变化 ──
  function observeVideoChange() {
    let lastUrl = location.href;
    new MutationObserver(() => {
      if (location.href !== lastUrl) {
        lastUrl = location.href;
        cueArray = []; activeCue = null; pendingUrl = null; lastVideoId = location.href;
        findVideo();
        setTimeout(() => attachCaptionSource(), 1000);
      }
    }).observe(document.querySelector('title') || document.head, { subtree: true, childList: true, characterData: true });
  }

})();
