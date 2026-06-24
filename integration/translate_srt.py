#!/usr/bin/env python3
"""
translate_srt.py — 独立 SRT 翻译脚本（不依赖 Claude Code / 命令）
调 DeepSeek API / OpenAI 兼容接口翻译，支持双语输出和标点重新分段。

用法:
  python3 translate_srt.py input.srt --to en                     # 仅目标语言
  python3 translate_srt.py input.srt --to en --bilingual          # 双语 SRT
  python3 translate_srt.py input.srt --to zh-CN --from en         # 指定源语言
  python3 translate_srt.py input.srt --to ja --api-key sk-xxx     # 其他语言

支持 DeepSeek / OpenAI / 任何兼容 API。
优先读 DEEPSEEK_API_KEY 环境变量，其次 --api-key 参数。
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
import ssl
from pathlib import Path

from srt_utils import parse_srt, parse_srt_text
from tm import TranslationMemory

API_BASE = os.environ.get("TRANSLATE_API_BASE", "https://api.deepseek.com")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("TRANSLATE_MODEL", "deepseek-chat")


def format_srt(cues: list[dict]) -> str:
    out = []
    for i, c in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{c['start']} --> {c['end']}")
        out.append(c["text"])
        out.append("")
    return "\n".join(out)


def call_llm(messages: list[dict], api_key: str, temperature: float = 0.3) -> str:
    data = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": 4096,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        },
        method="POST",
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120, context=ssl.create_default_context()) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503):
                wait = 2 ** attempt
                print(f"  HTTP {e.code}, retry in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt < 2:
                wait = 2 ** attempt
                print(f"  Network error, retry in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise last_err


def translate_batch(cues: list[dict], target: str, source: str, api_key: str = "",
                    use_ollama: bool = False, tm: "TranslationMemory | None" = None,
                    ) -> list[str]:
    """Translate a batch of SRT cues, with TM caching for reuse and consistency."""

    # Pre-filter: separate exact matches from new cues
    exact_hits: dict[int, str] = {}  # cue_index → cached translation
    new_cues: list[dict] = []
    new_pairs: list[tuple[str, str]] = []  # (source_text, target_text) to store after

    if tm is not None:
        for c in cues:
            hit = tm.lookup_exact(c["text"], source, target)
            if hit is not None:
                exact_hits[c["index"]] = hit
            else:
                new_cues.append(c)
    else:
        new_cues = list(cues)

    # If all cues were cached, early return
    cached_hit_count = len(exact_hits)
    if not new_cues:
        return [exact_hits.get(c["index"], c["text"]) for c in cues], cached_hit_count

    # Build prompt for new cues only
    texts = [f"[{c['index']}] {c['text']}" for c in new_cues]
    joined = "\n\n".join(texts)

    lang_names = {"zh": "Simplified Chinese", "zh-CN": "Simplified Chinese",
                  "en": "English", "ja": "Japanese", "ko": "Korean",
                  "fr": "French", "de": "German", "es": "Spanish",
                  "pt": "Portuguese", "ru": "Russian", "ar": "Arabic"}

    target_name = lang_names.get(target, target)
    source_name = lang_names.get(source, "the source language")

    # Add TM fuzzy matches as few-shot examples
    few_shot = ""
    if tm is not None:
        for c in new_cues:
            fuzzy = tm.lookup_fuzzy(c["text"], source, target, threshold=0.80, max_results=2)
            if fuzzy:
                few_shot += f"REF: \"{fuzzy[0][0]}\" → \"{fuzzy[0][1]}\"\n"
    if few_shot:
        few_shot = f"\nReference translations (use same style/terminology):\n{few_shot}\n"

    prompt = f"""Translate the following SRT subtitle cues from {source_name} to {target_name}.

RULES (follow strictly):
1. Keep the [N] index markers exactly as-is on each line.
2. Translate each cue naturally — prioritize meaning, not literal wording.
3. For Chinese output: use Simplified characters, natural spoken Mandarin, ~15 chars per line max. Avoid filler words like 这/那 unless needed for meaning.
4. For English output: natural conversational English, ~40 chars per line max.
5. Do NOT merge or split cues — each [N] marker must appear exactly once in order.
6. Output ONLY the translated text with markers. No commentary.
{few_shot}
TRANSLATE:
{joined}"""

    messages = [
        {"role": "system", "content": "You are a professional subtitle translator. Output only the translation with index markers. No explanations."},
        {"role": "user", "content": prompt},
    ]
    if use_ollama:
        result = call_ollama(messages, temperature=0.3)
    else:
        result = call_llm(messages, api_key, temperature=0.3)

    # Parse back: extract [N] text pairs
    translated: dict[int, str] = {}
    for line in result.split("\n"):
        m = re.match(r"\[(\d+)\]\s*(.+)", line.strip())
        if m:
            translated[int(m.group(1))] = m.group(2).strip()

    # Store new pairs in TM
    if tm is not None:
        for c in new_cues:
            tgt_text = translated.get(c["index"], c["text"])
            if tgt_text != c["text"]:  # don't cache untranslated
                new_pairs.append((c["text"], tgt_text))
        if new_pairs:
            tm.store_batch(new_pairs, source, target)

    # Merge exact matches + new translations
    merged = {}
    merged.update(exact_hits)
    merged.update(translated)
    result = [merged.get(c["index"], c["text"]) for c in cues]
    return result, cached_hit_count


def re_segment(cues: list[dict], lang: str) -> list[dict]:
    """Re-segment cues to end at punctuation boundaries."""
    is_zh = lang.startswith("zh")
    punct = re.compile(r"[。！？；：，——]" if is_zh else r"[.!?;:,—]")
    out = []
    for c in cues:
        if not punct.search(c["text"]):
            out.append(c)
        else:
            parts = punct.split(c["text"])
            parts = [p.strip() for p in parts if p.strip()]
            if len(parts) <= 1:
                out.append(c)
            else:
                total_len = sum(len(p) for p in parts)
                total_dur = ts_to_sec(c["end"]) - ts_to_sec(c["start"])
                cursor = ts_to_sec(c["start"])
                for part in parts:
                    dur = total_dur * (len(part) / total_len) if total_len > 0 else 2.0
                    dur = max(dur, 1.0)
                    end = cursor + dur
                    out.append({
                        "index": len(out) + 1,
                        "start": sec_to_ts(cursor),
                        "end": sec_to_ts(min(end, ts_to_sec(c["end"]))),
                        "text": part,
                    })
                    cursor = end
    return out


def ts_to_sec(ts: str) -> float:
    h, m, s = ts.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def sec_to_ts(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def main():
    parser = argparse.ArgumentParser(description="独立 SRT 字幕翻译")
    parser.add_argument("input", nargs="?", help="源 SRT 文件")
    parser.add_argument("--to", help="目标语言 (zh-CN, en, ja, ko...)")
    parser.add_argument("--from", dest="source", default="auto", help="源语言 (默认自动)")
    parser.add_argument("--bilingual", action="store_true", help="输出双语字幕")
    parser.add_argument("--api-key", help="API key (默认读 DEEPSEEK_API_KEY 环境变量)")
    parser.add_argument("--output", "-o", help="输出文件路径")
    parser.add_argument("--no-resegment", action="store_true", help="跳过标点重新分段")
    parser.add_argument("--batch-size", type=int, default=30, help="每批翻译条数 (默认30)")
    parser.add_argument("--engine", default="auto",
                        choices=["auto", "deepseek", "ollama"],
                        help="翻译引擎: auto(自动) / deepseek / ollama (默认: auto)")
    parser.add_argument("--tm-path", default=None,
                        help="翻译记忆库路径 (默认: ~/.everyones-video/translation_memory.json)")
    parser.add_argument("--no-tm", action="store_true",
                        help="禁用翻译记忆库 (不使用缓存)")
    parser.add_argument("--server", action="store_true", help="启动 HTTP API 服务器")
    parser.add_argument("--port", type=int, default=8730, help="API 服务器端口 (默认 8730)")

    args = parser.parse_args()

    if args.server:
        run_server(args.port)
        return

    if not args.input:
        sys.exit("Error: need input file or --server")
    if not args.to:
        sys.exit("Error: need --to <language>")

    key = args.api_key or API_KEY
    use_ollama = False

    # Engine selection: auto → prefer DeepSeek, fallback to Ollama
    if args.engine == "ollama":
        use_ollama = True
    elif args.engine == "deepseek":
        if not key:
            sys.exit("Error: --engine deepseek requires DEEPSEEK_API_KEY or --api-key")
    elif args.engine == "auto":
        if not key:
            # Try Ollama as fallback
            ollama_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
            try:
                import urllib.request as _ur
                _ur.urlopen(ollama_host + "/api/tags", timeout=3)
                print("→ DeepSeek key not set, using Ollama local translation...", file=sys.stderr)
                use_ollama = True
            except Exception:
                sys.exit(
                    "Error: No translation backend available.\n"
                    "  Set DEEPSEEK_API_KEY for cloud translation, or\n"
                    "  install Ollama (https://ollama.com) for local translation.\n"
                    "  Or use: --engine ollama  (if Ollama is running on a different host)"
                )

    if use_ollama:
        # Override model environment for Ollama
        os.environ.setdefault("OLLAMA_MODEL", "qwen3:14b")

    cues = parse_srt(args.input)
    if not cues:
        sys.exit(f"No cues found in {args.input}")

    # Init Translation Memory
    tm = None
    if not args.no_tm:
        tm = TranslationMemory(args.tm_path)
        tm_stats = tm.stats()
        tm_size = sum(tm_stats.values())
        if tm_size > 0:
            print(f"→ TM: {tm_size} 条已有翻译 ({tm.path})")
        else:
            print(f"→ TM: 空 ({tm.path})")

    engine_name = "Ollama" if use_ollama else MODEL
    print(f"翻译 {len(cues)} 条字幕 → {args.to} (引擎: {engine_name})")

    # Batch translate
    translated = []
    cached_count = 0
    for i in range(0, len(cues), args.batch_size):
        batch = cues[i:i + args.batch_size]
        batch_num = i // args.batch_size + 1
        total_batches = (len(cues) - 1) // args.batch_size + 1
        print(f"  批次 {batch_num}/{total_batches}", end="")
        translated_batch, batch_cached = translate_batch(
            batch, args.to, args.source, key, use_ollama=use_ollama, tm=tm,
        )
        translated += translated_batch
        cached_count += batch_cached
        print(f" → {len(translated_batch)} 条")

    if cached_count > 0:
        print(f"  TM 命中: {cached_count}/{len(cues)} 条 (省 {cached_count} 次 API 调用)")

    # Build output cues
    out_cues = []
    for c, trans in zip(cues, translated):
        new_cue = dict(c)
        if args.bilingual:
            new_cue["text"] = f"{c['text']}\n{trans}"
        else:
            new_cue["text"] = trans
        out_cues.append(new_cue)

    # Re-segment at punctuation (if enabled).
    # Skip when bilingual — re-segmentation would misalign source/target text.
    if not args.no_resegment and not args.bilingual:
        out_cues = re_segment(out_cues, args.to)

    srt_output = format_srt(out_cues)

    # Write output
    out_path = args.output
    if not out_path:
        stem = Path(args.input).stem
        out_path = f"{stem}.{args.to}.srt"

    Path(out_path).write_text(srt_output, encoding="utf-8")
    print(f"→ {out_path} ({len(out_cues)} 条字幕)")


def run_server(port: int):
    """Start HTTP API server with token auth and rate limiting."""
    import secrets
    import threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    if not API_KEY:
        sys.exit(
            "Error: DEEPSEEK_API_KEY is required for server mode.\n"
            "  Set the environment variable and restart:\n"
            "    export DEEPSEEK_API_KEY=sk-..."
        )

    SERVER_TOKEN = os.environ.get("TRANSLATE_API_TOKEN", "")
    if not SERVER_TOKEN:
        SERVER_TOKEN = secrets.token_urlsafe(24)
        print(
            f"[auth] TRANSLATE_API_TOKEN not set, auto-generated (first 8 chars):"
            f" {SERVER_TOKEN[:8]}…",
            file=sys.stderr,
        )
        print(
            "[auth] Set env var for a persistent token:"
            " TRANSLATE_API_TOKEN=<your-secret>",
            file=sys.stderr,
        )

    RATE_WINDOW = 60         # 1 minute window
    RATE_MAX_REQUESTS = 30   # per window
    MAX_BODY_BYTES = 10 * 1024 * 1024  # 10 MB
    rate_map: dict[str, list[float]] = {}  # ip -> [timestamps]
    rate_lock = threading.Lock()
    _req_counter = [0]  # mutable counter for periodic cleanup

    class TranslateHandler(BaseHTTPRequestHandler):
        def check_auth(self) -> bool:
            auth = self.headers.get("Authorization", "")
            if auth.startswith("Bearer "):
                token = auth[7:]
                return secrets.compare_digest(token, SERVER_TOKEN)
            return False

        def check_rate(self) -> bool:
            ip = self.client_address[0]
            now = time.time()
            with rate_lock:
                buckets = rate_map.get(ip, [])
                buckets = [t for t in buckets if now - t < RATE_WINDOW]
                if len(buckets) >= RATE_MAX_REQUESTS:
                    return False
                buckets.append(now)
                rate_map[ip] = buckets
                # Periodic cleanup: every ~100 requests, purge stale IP entries
                _req_counter[0] += 1
                if _req_counter[0] % 100 == 0:
                    stale = [
                        ip_
                        for ip_, ts_list in rate_map.items()
                        if not any(now - t < RATE_WINDOW for t in ts_list)
                    ]
                    for ip_ in stale:
                        del rate_map[ip_]
            return True

        def do_POST(self):
            if not self.check_auth():
                self._json(401, {"error": "unauthorized", "hint": "use Authorization: Bearer <token>"})
                return
            if not self.check_rate():
                self._json(429, {"error": "rate limited", "retry_after": RATE_WINDOW})
                return
            content_len = min(int(self.headers.get("Content-Length", "0")), MAX_BODY_BYTES)
            body = json.loads(self.rfile.read(content_len))

            if self.path == "/v1/chat/completions":
                self._chat_completions(body)
            elif self.path == "/translate":
                self._translate_srt(body)
            elif self.path == "/translate/text":
                self._translate_text(body)
            else:
                self._json(404, {"error": "not found"})

        def do_GET(self):
            if self.path == "/health":
                self._json(200, {"status": "ok", "model": MODEL})
            elif self.path == "/":
                auth_ok = self.check_auth()
                self._json(200, {
                    "service": "translate_srt.py API",
                    "model": MODEL,
                    "auth_required": not auth_ok,
                    "endpoints": {
                        "/v1/chat/completions": "OpenAI-compatible chat (POST, auth)",
                        "/translate": "SRT file translation (POST, auth)",
                        "/translate/text": "Plain text translation (POST, auth)",
                        "/health": "Health check (GET, public)",
                    }
                })
            else:
                self._json(404, {"error": "not found"})

        def _chat_completions(self, body):
            messages = body.get("messages", [])
            temperature = body.get("temperature", 0.3)
            model = body.get("model", MODEL)
            try:
                api_key = API_KEY
                if model == "ollama" or model.startswith("ollama/"):
                    result = call_ollama(messages, temperature)
                else:
                    result = call_llm(messages, api_key, temperature)
                self._json(200, {
                    "choices": [{"message": {"content": result}}],
                    "model": model,
                })
            except Exception as e:
                self._json(500, {"error": str(e)})

        def _translate_srt(self, body):
            srt_text = body.get("srt", "")
            target = body.get("to", "zh-CN")
            source = body.get("from", "auto")
            bilingual = body.get("bilingual", False)
            engine = body.get("engine", "auto")

            cues = parse_srt_text(srt_text)
            if not cues:
                self._json(400, {"error": "invalid SRT"})
                return

            # Detect Ollama availability when engine=auto
            use_ollama = engine == "ollama"
            if engine == "auto":
                ollama_host = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
                try:
                    import urllib.request as _ur
                    _ur.urlopen(ollama_host + "/api/tags", timeout=2)
                    use_ollama = True
                except Exception:
                    use_ollama = False

            translated = []
            batch_size = body.get("batch_size", 30)
            use_tm = body.get("tm", True)
            server_tm = TranslationMemory(body.get("tm_path")) if use_tm else None
            for i in range(0, len(cues), batch_size):
                batch = cues[i:i + batch_size]
                batch_result, _ = translate_batch(
                    batch, target, source, API_KEY, use_ollama=use_ollama, tm=server_tm,
                )
                translated += batch_result

            out_cues = []
            for c, trans in zip(cues, translated):
                new = dict(c)
                new["text"] = f"{c['text']}\n{trans}" if bilingual else trans
                out_cues.append(new)

            if not bilingual:
                out_cues = re_segment(out_cues, target)
            self._json(200, {"srt": format_srt(out_cues), "cues": len(out_cues)})

        def _translate_text(self, body):
            text = body.get("text", "")
            target = body.get("to", "zh-CN")
            source = body.get("from", "auto")
            try:
                result = call_llm([
                    {"role": "system", "content": f"Translate to {target}. Output only the translation."},
                    {"role": "user", "content": text},
                ], API_KEY, 0.3)
                self._json(200, {"translation": result.strip()})
            except Exception as e:
                self._json(500, {"error": str(e)})

        def _json(self, code, data):
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{port}")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

        def log_message(self, format, *args):
            elapsed = time.time() - self._start_time if hasattr(self, "_start_time") else 0
            print(f"[{self.log_date_time_string()}] {self.client_address[0]} {args[0]} {elapsed:.2f}s", file=sys.stderr)

    print(f"╔═══════════════════════════════════════╗")
    print(f"║  translate_srt.py API Server         ║")
    print(f"║  Model: {MODEL:<29s}║")
    print(f"║  http://127.0.0.1:{port:<5}                ║")
    print(f"║  Token: {SERVER_TOKEN[:8]}… (first 8)  ║")
    print(f"╚═══════════════════════════════════════╝")
    print(f"")
    print(f"  Auth: Authorization: Bearer <token>")
    print(f"")

    server = HTTPServer(("127.0.0.1", port), TranslateHandler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nshutdown", file=sys.stderr)
        server.shutdown()


def call_ollama(messages: list[dict], temperature: float = 0.3) -> str:
    """Local translation fallback via Ollama."""
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

