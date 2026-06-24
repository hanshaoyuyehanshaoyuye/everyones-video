#!/usr/bin/env python3
"""srt_utils.py — SRT 文件解析与格式化（共享模块）

被 translate_srt / tts_dub / eval_quality 共同引用。
"""

import re
from pathlib import Path

MAX_SRT_BYTES = 50 * 1024 * 1024  # 50 MB — refuse anything larger


def parse_srt(path: str) -> list[dict]:
    """Parse SRT file into [{index, start, end, text}]"""
    p = Path(path)
    if p.stat().st_size > MAX_SRT_BYTES:
        raise ValueError(
            f"SRT file too large: {p.stat().st_size} bytes (max {MAX_SRT_BYTES})"
        )
    raw = p.read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", raw.strip())
    cues = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(
            r"(\d+)\n(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\n(.*)",
            block, re.DOTALL,
        )
        if not m:
            # fallback parse for non-standard SRT
            idx = lines[0]
            ts = lines[1] if len(lines) > 1 else "00:00:00,000 --> 00:00:00,000"
            text = "\n".join(lines[2:])
            ts_match = re.match(r"(\S+) --> (\S+)", ts)
            start, end = ts_match.groups() if ts_match else ("00:00:00,000", "00:00:00,000")
        else:
            idx, start, end, text = m.groups()
        cues.append({"index": int(idx), "start": start, "end": end, "text": text.strip()})
    return cues


def parse_srt_text(text: str) -> list[dict]:
    """Parse SRT from raw text string (for API server use)."""
    import tempfile, os
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".srt", delete=False, encoding="utf-8"
    ) as f:
        f.write(text)
        tmp = f.name
    try:
        return parse_srt(tmp)
    finally:
        os.unlink(tmp)
