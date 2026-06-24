#!/usr/bin/env python3
"""
eval_quality.py — GEMBA-MQM 翻译质量评估

用 LLM 对翻译后的 SRT 做 GEMBA-MQM 评分（0-100），
标注每条的严重程度（critical/major/minor/none）。

用法:
  python3 eval_quality.py source.srt translated.srt --from en --to zh-CN
  python3 eval_quality.py source.srt translated.srt --from en --to zh-CN --json -o report.json
  python3 eval_quality.py --server --port 8731

引擎: DeepSeek API / Ollama 本地
输出: 总分 + 错误数 + 逐条标注

参考:
  GEMBA-MQM: https://arxiv.org/abs/2303.16634
  Kocmi et al. "GEMBA-MQM: Detecting Translation Quality Issues with GPT-4" (2023)
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

API_BASE = os.environ.get("TRANSLATE_API_BASE", "https://api.deepseek.com")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
MODEL = os.environ.get("TRANSLATE_MODEL", "deepseek-chat")

LANGS = {
    "zh": "Simplified Chinese", "zh-CN": "Simplified Chinese",
    "en": "English", "ja": "Japanese", "ko": "Korean",
    "fr": "French", "de": "German", "es": "Spanish",
}


def call_llm(messages: list[dict], api_key: str) -> str:
    data = json.dumps({
        "model": MODEL, "messages": messages,
        "temperature": 0.0, "max_tokens": 2048, "stream": False,
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
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=60, context=ssl.create_default_context()) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except (urllib.error.HTTPError, urllib.error.URLError, OSError):
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise


def gemba_mqm(source_cues: list[dict], trans_cues: list[dict],
               src_lang: str, tgt_lang: str, api_key: str) -> dict:
    """Run GEMBA-MQM evaluation via LLM."""

    # Pad shorter list
    max_n = max(len(source_cues), len(trans_cues))
    lines = []
    for i in range(max_n):
        s = source_cues[i]["text"] if i < len(source_cues) else "(missing)"
        t = trans_cues[i]["text"] if i < len(trans_cues) else "(missing)"
        lines.append(f"[{i+1}] SRC: {s}\n[{i+1}] TGT: {t}")

    pairs = "\n\n".join(lines[:50])  # batch max 50 cues

    src_name = LANGS.get(src_lang, src_lang)
    tgt_name = LANGS.get(tgt_lang, tgt_lang)

    prompt = f"""Evaluate the following subtitle translations from {src_name} to {tgt_name}.

For each cue within the XML tags below, classify the error severity:
- critical: meaning completely wrong, offensive, or safety issue
- major: significant mistranslation or omission
- minor: awkward phrasing, minor nuance loss
- none: accurate and natural

Then give an overall quality score 0-100.

Output as JSON:
{{
  "score": <0-100>,
  "summary": "<one-line assessment>",
  "cues": [
    {{"index": <N>, "severity": "critical|major|minor|none", "note": "<brief>"}},
    ...
  ]
}}

<translation_pairs>
{pairs}
</translation_pairs>"""

    result = call_llm([
        {"role": "system", "content": "You are a translation quality evaluator. Output only valid JSON."},
        {"role": "user", "content": prompt},
    ], api_key)

    # Extract JSON from response
    json_match = re.search(r"\{[\s\S]*\}", result)
    if not json_match:
        return {"score": -1, "summary": "parse error", "cues": [], "raw": result[:500]}
    try:
        return json.loads(json_match.group())
    except json.JSONDecodeError:
        return {"score": -1, "summary": "json error", "cues": [], "raw": result[:500]}


def main():
    parser = argparse.ArgumentParser(description="GEMBA-MQM 翻译质量评估")
    parser.add_argument("source", nargs="?", help="源语言 SRT")
    parser.add_argument("translated", nargs="?", help="翻译后 SRT")
    parser.add_argument("--from", dest="src_lang", default="auto", help="源语言")
    parser.add_argument("--to", default="zh-CN", help="目标语言")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    parser.add_argument("--output", "-o", help="输出文件")
    parser.add_argument("--server", action="store_true", help="启动 HTTP API")
    parser.add_argument("--port", type=int, default=8731)

    args = parser.parse_args()

    if args.server:
        run_server(args.port)
        return

    if not args.source or not args.translated:
        sys.exit("usage: eval_quality.py source.srt translated.srt --from en --to zh-CN")

    key = API_KEY
    if not key:
        sys.exit("Error: DEEPSEEK_API_KEY not set")

    src = parse_srt(args.source)
    tgt = parse_srt(args.translated)
    print(f"评估 {len(tgt)} 条翻译 (GEMBA-MQM, {MODEL})...", file=sys.stderr)

    report = gemba_mqm(src, tgt, args.src_lang, args.to, key)

    if args.json or args.output:
        out = json.dumps(report, ensure_ascii=False, indent=2)
        if args.output:
            Path(args.output).write_text(out, encoding="utf-8")
            print(f"→ {args.output}", file=sys.stderr)
        else:
            print(out)
    else:
        score = report.get("score", -1)
        summary = report.get("summary", "")
        cues = report.get("cues", [])
        critical = sum(1 for c in cues if c.get("severity") == "critical")
        major = sum(1 for c in cues if c.get("severity") == "major")
        minor = sum(1 for c in cues if c.get("severity") == "minor")
        print(f"Score: {score}/100  {summary}")
        print(f"Errors: {critical} critical, {major} major, {minor} minor "
              f"(of {len(tgt)} cues)")


def run_server(port: int):
    import secrets, threading
    from http.server import HTTPServer, BaseHTTPRequestHandler

    if not API_KEY:
        sys.exit("Error: DEEPSEEK_API_KEY required for server mode")

    TOKEN = os.environ.get("EVAL_API_TOKEN", secrets.token_urlsafe(24))

    rate_map: dict[str, list[float]] = {}
    rate_lock = threading.Lock()
    RATE_WINDOW = 60
    RATE_MAX = 20

    class Handler(BaseHTTPRequestHandler):
        def do_OPTIONS(self):
            self.send_response(204)
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{port}")
            self.send_header("Access-Control-Allow-Methods", "POST, GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
            self.end_headers()

        def check_rate(self) -> bool:
            ip = self.client_address[0]
            now = time.time()
            with rate_lock:
                buckets = rate_map.get(ip, [])
                buckets = [t for t in buckets if now - t < RATE_WINDOW]
                if len(buckets) >= RATE_MAX:
                    return False
                buckets.append(now)
                rate_map[ip] = buckets
            return True

        def do_POST(self):
            auth = self.headers.get("Authorization", "")
            if not auth.startswith("Bearer ") or auth[7:] != TOKEN:
                self._json(401, {"error": "unauthorized"})
                return
            if not self.check_rate():
                self._json(429, {"error": "rate limited", "retry_after": RATE_WINDOW})
                return
            cl = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(min(cl, 5 * 1024 * 1024)))
            src = parse_srt_text(body.get("source_srt", ""))
            tgt = parse_srt_text(body.get("translated_srt", ""))
            report = gemba_mqm(
                src, tgt,
                body.get("from", "auto"), body.get("to", "zh-CN"), API_KEY,
            )
            self._json(200, report)

        def do_GET(self):
            if self.path == "/health":
                self._json(200, {"status": "ok"})

        def _json(self, code, data):
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", f"http://127.0.0.1:{port}")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False).encode())

    print(f"eval_quality API → http://127.0.0.1:{port}")
    print(f"  Token: {TOKEN[:8]}… (first 8 chars)")
    print(f"  Auth: Authorization: Bearer <token>")
    HTTPServer(("127.0.0.1", port), Handler).serve_forever()


if __name__ == "__main__":
    main()
