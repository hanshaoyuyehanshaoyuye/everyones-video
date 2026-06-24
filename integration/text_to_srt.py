#!/usr/bin/env python3
"""
text_to_srt.py — 通用纯文本 → SRT 字幕转换器

适用于任何无时间戳 ASR 输出（FunASR 纯文本、faster-whisper 文本、
StepFun 输出、手写文稿等），将纯文本转为标准 SRT 格式。

分段策略:
  - 中文: 按 。！？； 分段，每段一句
  - 英文: 按 . ! ? 分段，每段一句
  - 长句 (>80字) 按逗号二次分段

时间戳估算:
  - 中文: 4 字/秒
  - 英文: 3 words/sec
  - 每段间留 200ms 间隔

用法:
  python3 text_to_srt.py transcript.txt                    # 文件输入
  echo "你好。世界。" | python3 text_to_srt.py --stdin       # 管道输入
  python3 text_to_srt.py transcript.txt --lang en --speed 3 # 英文，3词/秒
  python3 text_to_srt.py transcript.txt --output out.srt   # 指定输出文件

别名: stepfun_to_srt.py (向后兼容)
"""

import argparse
import re
import sys
from pathlib import Path

# 默认语速 (字/秒)
DEFAULT_SPEED = {"zh": 4.0, "en": 3.0}  # words/sec for en
# 段间间隔 (秒)
GAP_SEC = 0.2
# 最大段字数（超过则按逗号二次分段）
MAX_CHARS_PER_CUE = 80


def split_sentences(text: str, lang: str) -> list[str]:
    """按标点分段，返回句子列表"""
    if lang == "zh":
        pattern = r"([^。！？；\n]+[。！？；\n]?)"
    else:
        pattern = r"([^.!?\n]+[.!?\n]?)"

    raw = re.findall(pattern, text)
    sentences = []
    for s in raw:
        s = s.strip()
        if not s:
            continue
        if len(s) > MAX_CHARS_PER_CUE:
            sub_parts = re.split(r"([，,])", s)
            merged = ""
            for part in sub_parts:
                merged += part
                if len(merged) > MAX_CHARS_PER_CUE:
                    sentences.append(merged.strip())
                    merged = ""
            if merged.strip():
                sentences.append(merged.strip())
        else:
            sentences.append(s)
    # Post-process: merge trailing single-char fragments (e.g. "U." from "U.S.")
    merged_sentences = []
    for s in sentences:
        if merged_sentences and len(s.rstrip(".")) <= 1 and len(s) <= 3:
            merged_sentences[-1] = merged_sentences[-1] + s
        else:
            merged_sentences.append(s)
    return merged_sentences


def estimate_duration(text: str, speed: float, lang: str) -> float:
    """估算朗读时长（秒）"""
    if lang == "zh":
        return len(text.replace(" ", "")) / speed
    else:
        return len(text.split()) / speed


def format_timestamp(total_seconds: float) -> str:
    """秒数 → SRT 时间戳 HH:MM:SS,mmm"""
    h = int(total_seconds // 3600)
    m = int((total_seconds % 3600) // 60)
    s = int(total_seconds % 60)
    ms = int((total_seconds - int(total_seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def text_to_srt(text: str, lang: str = "zh", speed: float | None = None) -> str:
    """主函数: 纯文本 → SRT"""
    if speed is None:
        speed = DEFAULT_SPEED.get(lang, 4.0)

    sentences = split_sentences(text, lang)
    if not sentences:
        return ""

    srt_lines = []
    cursor = 0.0  # 当前时间位置 (秒)

    for i, sentence in enumerate(sentences, 1):
        duration = estimate_duration(sentence, speed, lang)
        duration = max(duration, 1.0)

        start = cursor
        end = cursor + duration

        srt_lines.append(str(i))
        srt_lines.append(f"{format_timestamp(start)} --> {format_timestamp(end)}")
        srt_lines.append(sentence)
        srt_lines.append("")

        cursor = end + GAP_SEC

    return "\n".join(srt_lines)


def main():
    parser = argparse.ArgumentParser(
        description="通用纯文本 → SRT 字幕 (原名 stepfun_to_srt.py)"
    )
    parser.add_argument(
        "input",
        nargs="?",
        help="输入文本文件路径（不指定则从 stdin 读取）",
    )
    parser.add_argument(
        "--stdin", action="store_true", help="从 stdin 读取"
    )
    parser.add_argument(
        "--lang", default="zh", choices=["zh", "en"], help="语言 (默认: zh)"
    )
    parser.add_argument(
        "--speed", type=float,
        help=f"语速 字/秒 (默认: zh={DEFAULT_SPEED['zh']}, en={DEFAULT_SPEED['en']})"
    )
    parser.add_argument(
        "--output", "-o", help="输出 SRT 文件路径 (默认: stdout)"
    )

    args = parser.parse_args()

    if args.stdin or args.input is None:
        text = sys.stdin.read()
    else:
        text = Path(args.input).read_text(encoding="utf-8")

    srt = text_to_srt(text.strip(), args.lang, args.speed)

    if args.output:
        Path(args.output).write_text(srt, encoding="utf-8")
        print(f"SRT written to {args.output}", file=sys.stderr)
    else:
        print(srt)


if __name__ == "__main__":
    main()
