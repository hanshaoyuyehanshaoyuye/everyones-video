#!/usr/bin/env python3
"""
realtime_server.py — YouTube 实时字幕翻译后端

轻量 HTTP 服务器，供 Chrome Extension 调用。
复用 TranslationMemory + 现有 LLM 调用逻辑。

端点:
  POST /translate       单条翻译 (热路径: TM 命中 <1ms, LLM 回退 ~300ms)
  POST /translate/batch 批量预翻译 (TM 命中即时, LLM 未命中异步填充)
  GET  /health          健康检查
  GET  /tm/stats        翻译记忆库统计

启动:
  python3 integration/realtime_server.py [--port 8739] [--host 127.0.0.1]
  DEEPSEEK_API_KEY=sk-... python3 integration/realtime_server.py
"""

import argparse
import json
import os
import re
import signal
import ssl
import sys
import threading
import time
import urllib.request
import urllib.error
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path

# 确保可以 import 同目录模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from tm import TranslationMemory

# ── LLM 配置 ──
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_BASE = os.environ.get("TRANSLATE_API_BASE", "https://api.deepseek.com")
MODEL = os.environ.get("TRANSLATE_MODEL", "deepseek-chat")

LANG_NAMES = {
    "zh": "Simplified Chinese", "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese", "en": "English",
    "ja": "Japanese", "ko": "Korean", "fr": "French",
    "de": "German", "es": "Spanish", "pt": "Portuguese",
    "ru": "Russian", "ar": "Arabic",
}


def call_llm(messages: list[dict], temperature: float = 0.3) -> str:
    data = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 256,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_KEY}",
        },
        method="POST",
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl.create_default_context()) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise


def call_ollama(messages: list[dict], temperature: float = 0.3) -> str:
    data = json.dumps({
        "model": os.environ.get("OLLAMA_MODEL", "qwen3:14b"),
        "messages": messages,
        "stream": False,
        "options": {"temperature": temperature},
    }).encode()
    req = urllib.request.Request(
        f"{os.environ.get('OLLAMA_HOST', 'http://127.0.0.1:11434')}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        return json.loads(r.read())["message"]["content"]


def translate_single(text: str, source: str, target: str, use_ollama: bool) -> str:
    """LLM 翻译单条文本, 不带 index marker."""
    src_name = LANG_NAMES.get(source, source)
    tgt_name = LANG_NAMES.get(target, target)

    prompt = f"""Translate this subtitle from {src_name} to {tgt_name}.

Rules:
- Natural spoken language, not literal translation
- Keep the same tone and style
- Output ONLY the translation, nothing else

Source: {text}
Translation:"""

    messages = [
        {"role": "system", "content": f"You translate subtitles from {src_name} to {tgt_name}. Output only the translation."},
        {"role": "user", "content": prompt},
    ]
    if use_ollama:
        return call_ollama(messages, 0.3).strip()
    return call_llm(messages, 0.3).strip()


def translate_batch_llm(texts: list[str], source: str, target: str, use_ollama: bool) -> dict[str, str]:
    """LLM 批量翻译, 返回 {original: translated}."""
    src_name = LANG_NAMES.get(source, source)
    tgt_name = LANG_NAMES.get(target, target)

    numbered = [f"[{i}] {t}" for i, t in enumerate(texts)]
    prompt = f"""Translate these subtitle cues from {src_name} to {tgt_name}.

RULES:
1. Keep [N] markers exactly as-is
2. Natural spoken language
3. For Chinese: Simplified, ~15 chars max per line
4. For English: natural conversational, ~40 chars max
5. Output ONLY the translated text with markers. No commentary.

{chr(10).join(numbered)}"""

    messages = [
        {"role": "system", "content": "You translate subtitles. Output only the translation with [N] markers."},
        {"role": "user", "content": prompt},
    ]
    if use_ollama:
        result = call_ollama(messages, 0.3)
    else:
        result = call_llm(messages, 0.3)

    # Parse [N] text
    parsed = {}
    for line in result.split("\n"):
        m = re.match(r"\[(\d+)\]\s*(.+)", line.strip())
        if m:
            idx = int(m.group(1))
            parsed[texts[idx]] = m.group(2).strip()

    return parsed


class RealtimeHandler(BaseHTTPRequestHandler):
    """极简 HTTP handler — 不做鉴权，仅 localhost。"""

    tm: TranslationMemory = None  # 类变量, 由 main() 注入

    def do_GET(self):
        if self.path == "/health":
            self._json(200, {"status": "ok", "model": MODEL, "tm_size": sum(RealtimeHandler.tm.stats().values()) if RealtimeHandler.tm else 0})
        elif self.path == "/tm/stats":
            s = RealtimeHandler.tm.stats() if RealtimeHandler.tm else {}
            self._json(200, {"stats": s, "total": sum(s.values()), "path": str(RealtimeHandler.tm.path) if RealtimeHandler.tm else ""})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        content_len = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(content_len)
        body = {}
        if content_len > 0:
            try:
                body = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                try:
                    body = json.loads(raw.decode("gbk"))
                except (UnicodeDecodeError, json.JSONDecodeError):
                    body = {}

        if self.path == "/translate":
            self._handle_translate(body)
        elif self.path == "/translate/batch":
            self._handle_translate_batch(body)
        elif self.path == "/detect-lang":
            self._handle_detect_lang(body)
        else:
            self._json(404, {"error": "not found"})

    def _handle_translate(self, body):
        text = body.get("text", "").strip()
        if not text:
            self._json(400, {"error": "empty text"})
            return

        source = body.get("from", "en")
        target = body.get("to", "zh-CN")
        use_ollama = self._use_ollama()

        # 1. TM exact match
        if RealtimeHandler.tm:
            hit = RealtimeHandler.tm.lookup_exact(text, source, target)
            if hit:
                self._json(200, {"translation": hit, "cached": True, "source": "tm"})
                return

        # 2. LLM
        if not API_KEY and not use_ollama:
            self._json(503, {"error": "no API key configured"})
            return

        try:
            result = translate_single(text, source, target, use_ollama)
            if RealtimeHandler.tm:
                RealtimeHandler.tm.store(text, result, source, target)
                RealtimeHandler.tm.flush()
            self._json(200, {"translation": result, "cached": False, "source": "llm"})
        except Exception as e:
            self._json(500, {"error": str(e)})

    def _handle_translate_batch(self, body):
        texts = body.get("texts", [])
        if not texts:
            self._json(400, {"error": "empty texts"})
            return

        source = body.get("from", "en")
        target = body.get("to", "zh-CN")
        use_ollama = self._use_ollama()

        results = []
        misses = []

        # 1. TM pass
        for text in texts:
            t = text.strip()
            if not t:
                results.append({"original": text, "translation": "", "cached": True})
                continue
            if RealtimeHandler.tm:
                hit = RealtimeHandler.tm.lookup_exact(t, source, target)
                if hit:
                    results.append({"original": text, "translation": hit, "cached": True})
                    continue
            results.append({"original": text, "translation": None, "cached": False})
            misses.append(t)

        # 2. LLM batch pass for misses
        if misses and (API_KEY or use_ollama):
            try:
                translated = translate_batch_llm(misses, source, target, use_ollama)
                for r in results:
                    if not r["cached"] and r["original"].strip() in translated:
                        r["translation"] = translated[r["original"].strip()]
                        if RealtimeHandler.tm:
                            RealtimeHandler.tm.store(
                                r["original"].strip(), r["translation"], source, target
                            )
                if RealtimeHandler.tm:
                    RealtimeHandler.tm.flush()
            except Exception as e:
                print(f"[batch] LLM error: {e}", file=sys.stderr)

        self._json(200, {"results": results, "cached": len(texts) - len(misses), "total": len(texts)})

    def _handle_detect_lang(self, body):
        """Detect language from sample texts via Unicode range analysis."""
        texts = body.get("texts", [])
        if not texts:
            self._json(400, {"error": "empty texts"})
            return

        sample = " ".join(texts[:5]).strip()
        if not sample:
            self._json(200, {"lang": "en", "confidence": 0})
            return

        scripts = {}
        for ch in sample:
            cp = ord(ch)
            if 0x3040 <= cp <= 0x309F or 0x30A0 <= cp <= 0x30FF: scripts["ja"] = scripts.get("ja", 0) + 1
            elif 0xAC00 <= cp <= 0xD7AF: scripts["ko"] = scripts.get("ko", 0) + 1
            elif 0x0400 <= cp <= 0x04FF: scripts["ru"] = scripts.get("ru", 0) + 1
            elif 0x4E00 <= cp <= 0x9FFF or 0x3400 <= cp <= 0x4DBF: scripts["zh"] = scripts.get("zh", 0) + 1
            elif 0x0600 <= cp <= 0x06FF: scripts["ar"] = scripts.get("ar", 0) + 1
            elif 0x0E00 <= cp <= 0x0E7F: scripts["th"] = scripts.get("th", 0) + 1
            elif cp > 0x7F: scripts["latin"] = scripts.get("latin", 0) + 1
            else: scripts["latin"] = scripts.get("latin", 0) + 1

        best = max(scripts, key=scripts.get) if scripts else "en"
        if best == "latin": best = "en"
        if best == "zh" and scripts.get("ja", 0) > scripts.get("zh", 0) * 0.3: best = "ja"

        total = sum(scripts.values())
        win_count = scripts.get("latin", 0) if best == "en" and "latin" in scripts else scripts.get(best, 0)
        conf = win_count / max(total, 1)
        self._json(200, {"lang": best, "confidence": round(conf, 2)})

    def _use_ollama(self) -> bool:
        if not API_KEY:
            return True  # fallback to Ollama
        return False

    def _json(self, code, data):
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def log_message(self, format, *args):
        # 压缩日志: 只显示关键信息
        if "/health" in (args[0] if args else ""):
            return  # 健康检查不记日志
        print(f"[{self.log_date_time_string()}] {args[0]}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description="实时翻译服务器 (Chrome Extension 后端)")
    parser.add_argument("--port", type=int, default=8739, help="端口 (默认: 8739)")
    parser.add_argument("--host", default="127.0.0.1", help="监听地址 (默认: 127.0.0.1)")
    parser.add_argument("--tm-path", default=None, help="TM 文件路径")
    args = parser.parse_args()

    # 检查 LLM 后端
    use_ollama = False
    if not API_KEY:
        # 探测 Ollama
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/api/tags", timeout=2)
            use_ollama = True
            print(f"→ 翻译后端: Ollama (本地 qwen3:14b)")
        except Exception:
            print(f"⚠ DEEPSEEK_API_KEY 未设置, 且 Ollama 未运行")
            print(f"  设置: export DEEPSEEK_API_KEY=sk-...")
            print(f"  或启动: ollama serve && ollama pull qwen3:14b")
            print(f"  服务器将只响应 TM 缓存的翻译 (命中则秒回, 未命中则 503)")
    else:
        print(f"→ 翻译后端: DeepSeek ({MODEL})")

    # 初始化 TM
    tm_path = args.tm_path or os.path.join(
        os.path.expanduser("~"), ".everyones-video", "translation_memory.json"
    )
    RealtimeHandler.tm = TranslationMemory(tm_path)
    tm_size = sum(RealtimeHandler.tm.stats().values())
    print(f"→ 翻译记忆库: {tm_path} ({tm_size} 条)")

    # 启动
    server = HTTPServer((args.host, args.port), RealtimeHandler)
    print(f"→ 实时翻译服务: http://{args.host}:{args.port}")

    def shutdown(sig, frame):
        print(f"\n→ 关闭服务器...")
        if RealtimeHandler.tm:
            RealtimeHandler.tm.flush()
        server.shutdown()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        shutdown(None, None)


if __name__ == "__main__":
    main()
