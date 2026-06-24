// background.js — Service Worker (minimal)
// Just handles extension icon badge and keeps the service worker alive.

chrome.runtime.onInstalled.addListener(() => {
  console.log('[EV] Extension installed');
});

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'status') {
    sendResponse({ ok: true });
  }
});
