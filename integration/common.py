#!/usr/bin/env python3
"""
common.py — 共享模块（v7.0 P0-1 提取）

集中所有模块共用的代码，消除 4 处重复定义：
  - 时间戳工具: ts_to_sec / sec_to_ts
  - SRT 格式化: format_srt
  - LLM 调用: call_llm / call_ollama
  - 语言名称映射: LANG_NAMES

用法:
  from common import ts_to_sec, sec_to_ts, format_srt, call_llm, call_ollama, LANG_NAMES
"""

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request

# ── 语言名称映射（12 语种）───────────────────────────

LANG_NAMES: dict[str, str] = {
    "zh": "Simplified Chinese",
    "zh-CN": "Simplified Chinese",
    "zh-TW": "Traditional Chinese",
    "en": "English",
    "ja": "Japanese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
}

# ── LLM 配置（读环境变量）───────────────────────────

API_BASE = os.environ.get(
    "TRANSLATE_API_BASE",
    "https://api.deepseek.com",
)
MODEL = os.environ.get("TRANSLATE_MODEL", "deepseek-chat")
API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")

# ── 时间戳工具 ────────────────────────────────────────

def ts_to_sec(ts: str) -> float:
    """SRT 时间戳 → 秒"""
    h, m, s = ts.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def sec_to_ts(sec: float) -> str:
    """秒 → SRT 时间戳"""
    sec = max(sec, 0.0)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")

# ── SRT 格式化 ────────────────────────────────────────

def format_srt(cues: list[dict]) -> str:
    """SRT cue 列表 → SRT 文本"""
    out = []
    for i, c in enumerate(cues, 1):
        out.append(str(i))
        out.append(f"{c['start']} --> {c['end']}")
        out.append(c["text"])
        out.append("")
    return "\n".join(out)

# ── LLM 调用 ──────────────────────────────────────────

def call_llm(
    messages: list[dict],
    api_key: str = "",
    temperature: float = 0.3,
    max_tokens: int = 4096,
    timeout: int = 120,
) -> str:
    """调用 LLM (DeepSeek / OpenAI 兼容接口)，内置 3 次指数退避重试。"""
    key = api_key or API_KEY
    data = json.dumps({
        "model": MODEL,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }).encode()
    req = urllib.request.Request(
        f"{API_BASE}/chat/completions",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {key}",
        },
        method="POST",
    )
    last_err = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=timeout,
                                         context=ssl.create_default_context()) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            last_err = e
            if e.code in (429, 500, 502, 503):
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, OSError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise
    raise last_err


def call_ollama(
    messages: list[dict],
    temperature: float = 0.3,
    timeout: int = 180,
) -> str:
    """调用本地 Ollama 模型翻译。"""
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
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())["message"]["content"]
