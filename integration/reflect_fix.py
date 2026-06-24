#!/usr/bin/env python3
"""
reflect_fix.py — 翻译反思修复闭环

用 GEMBA-MQM 评估翻译质量，找出 critical/major 错误，
让 LLM 针对性修复。循环直到达标或达到最大轮次。

用法:
  python3 reflect_fix.py source.srt translated.srt --from en --to zh-CN -o fixed.srt
  python3 reflect_fix.py source.srt translated.srt --max-rounds 3 --threshold major

引擎: DeepSeek API / Ollama 本地
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

from srt_utils import parse_srt
from eval_quality import gemba_mqm, call_llm, LANGS

API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
API_BASE = os.environ.get("TRANSLATE_API_BASE", "https://api.deepseek.com")
MODEL = os.environ.get("TRANSLATE_MODEL", "deepseek-chat")


def reflect_fix_one(
    cue_index: int,
    source_text: str,
    current_trans: str,
    severity: str,
    note: str,
    src_lang: str,
    tgt_lang: str,
    api_key: str,
) -> str:
    """Ask LLM to repair one bad translation."""
    src_name = LANGS.get(src_lang, src_lang)
    tgt_name = LANGS.get(tgt_lang, tgt_lang)

    prompt = f"""Fix this subtitle translation from {src_name} to {tgt_name}.

Original: {source_text}
Current translation: {current_trans}
Issue: [{severity}] {note}

Rules:
1. Output ONLY the fixed translation. No commentary, no markers.
2. Keep the same length and style as the original cues around it.
3. Natural spoken language, not literal.

Fixed translation:"""

    return call_llm([
        {"role": "system", "content": "You fix subtitle translation errors. Output only the fixed text."},
        {"role": "user", "content": prompt},
    ], api_key).strip()


def main():
    parser = argparse.ArgumentParser(description="翻译反思修复闭环")
    parser.add_argument("source", nargs="?", help="源语言 SRT")
    parser.add_argument("translated", nargs="?", help="翻译后 SRT")
    parser.add_argument("--from", dest="src_lang", default="auto", help="源语言")
    parser.add_argument("--to", default="zh-CN", help="目标语言")
    parser.add_argument("--max-rounds", type=int, default=3, help="最大修复轮次")
    parser.add_argument("--threshold", default="major",
                        choices=["critical", "major", "minor"],
                        help="最低修复级别 (默认: major)")
    parser.add_argument("--output", "-o", required=True, help="输出文件")
    parser.add_argument("--verbose", "-v", action="store_true", help="显示详细日志")

    args = parser.parse_args()

    if not args.source or not args.translated:
        sys.exit("usage: reflect_fix.py source.srt translated.srt -o fixed.srt")

    key = API_KEY
    if not key:
        sys.exit("Error: DEEPSEEK_API_KEY not set")

    src_cues = parse_srt(args.source)
    tgt_cues = parse_srt(args.translated)

    if len(src_cues) != len(tgt_cues):
        print(f"Warning: cue count mismatch ({len(src_cues)} vs {len(tgt_cues)})",
              file=sys.stderr)

    severity_rank = {"critical": 3, "major": 2, "minor": 1, "none": 0}
    threshold_rank = severity_rank[args.threshold]
    total_fixed = 0

    for round_num in range(1, args.max_rounds + 1):
        if args.verbose:
            print(f"\n--- Round {round_num}/{args.max_rounds} ---", file=sys.stderr)

        # Evaluate current translation
        report = gemba_mqm(src_cues, tgt_cues, args.src_lang, args.to, key)
        cues = report.get("cues", [])
        bad = [
            c for c in cues
            if severity_rank.get(c.get("severity", "none"), 0) >= threshold_rank
        ]

        if not bad:
            if args.verbose:
                print("  No errors above threshold. Done.", file=sys.stderr)
            break

        score = report.get("score", "?")
        print(f"  Score: {score}/100  |  Errors: {len(bad)}", file=sys.stderr)

        # Fix each bad cue
        fixed_in_round = 0
        for c in bad:
            idx = c.get("index", 0) - 1  # 1-based → 0-based
            if idx < 0 or idx >= len(tgt_cues):
                continue
            try:
                new_text = reflect_fix_one(
                    idx + 1,
                    src_cues[idx]["text"],
                    tgt_cues[idx]["text"],
                    c.get("severity", "major"),
                    c.get("note", ""),
                    args.src_lang, args.to, key,
                )
                if new_text and new_text != tgt_cues[idx]["text"]:
                    if args.verbose:
                        old = tgt_cues[idx]["text"][:50]
                        new = new_text[:50]
                        print(f"  [{idx+1}] {old} → {new}", file=sys.stderr)
                    tgt_cues[idx]["text"] = new_text
                    fixed_in_round += 1
            except Exception as e:
                print(f"  ⚠ cue {idx+1}: {e}", file=sys.stderr)

        total_fixed += fixed_in_round
        if fixed_in_round == 0:
            if args.verbose:
                print("  No fixes applied this round.", file=sys.stderr)
            break

    # Write output
    out_lines = []
    for i, c in enumerate(tgt_cues, 1):
        out_lines.append(str(i))
        out_lines.append(f"{c['start']} --> {c['end']}")
        out_lines.append(c["text"])
        out_lines.append("")

    Path(args.output).write_text("\n".join(out_lines), encoding="utf-8")
    print(f"→ {args.output} ({total_fixed} cues fixed)", file=sys.stderr)


if __name__ == "__main__":
    main()
