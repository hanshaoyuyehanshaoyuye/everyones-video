#!/usr/bin/env python3
"""
funasr_run.py — Chinese ASR via Alibaba FunASR (free, local).

Usage:
  python3 funasr_run.py audio.mp3 [--lang zh] [-o transcript.txt]

Output: plain text with sentence segmentation (period-delimited).
For time-stamped SRT, pipe into text_to_srt.py.

Requirements:
  pip install funasr
  # First run downloads paraformer-zh model (~1 GB)
"""

import argparse
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Chinese ASR via FunASR")
    parser.add_argument("input", help="Audio file (mp3/wav/m4a)")
    parser.add_argument("--lang", default="zh", help="Language (default: zh)")
    parser.add_argument("--output", "-o", default=None, help="Output text file")
    parser.add_argument("--model", default="paraformer-zh",
                        help="FunASR model (default: paraformer-zh)")
    parser.add_argument("--diarize", action="store_true",
                        help="Enable speaker diarization (who said what)")
    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        sys.exit(f"Error: file not found: {args.input}")

    try:
        from funasr import AutoModel
    except ImportError:
        sys.exit(
            "FunASR is not installed.\n"
            "  pip install funasr\n"
            "  # First run will download ~1 GB model automatically."
        )

    print(f"→ Loading FunASR model '{args.model}'"
          f"{' + speaker diarization' if args.diarize else ''}"
          f" (first run downloads model)…",
          file=sys.stderr)
    model_kwargs = dict(
        model=args.model,
        vad_model="fsmn-vad",
        punc_model="ct-punc",
    )
    if args.diarize:
        model_kwargs["spk_model"] = "cam++"
    model = AutoModel(**model_kwargs)

    print(f"→ Transcribing: {inp.name} ({inp.stat().st_size // 1024 // 1024} MB)",
          file=sys.stderr)
    result = model.generate(input=str(inp))
    text = ""
    if not result or len(result) == 0:
        sys.exit("Error: FunASR returned empty output.")

    # Build output — with speaker labels if diarization enabled
    sentences = result[0].get("sentence_info", [])
    if sentences and args.diarize:
        lines = []
        for s in sentences:
            spk = s.get("spk", "?")
            txt = s.get("text", "").strip()
            if txt:
                lines.append(f"[说话人{spk}] {txt}")
        text = "\n".join(lines)
    else:
        text = result[0].get("text", "")

    if not text.strip():
        sys.exit("Error: FunASR returned empty output.")

    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"→ {args.output} ({len(text)} chars)", file=sys.stderr)
    else:
        print(text)

    word_count = len(text.replace(" ", ""))
    print(f"  Done: {word_count} chars", file=sys.stderr)


if __name__ == "__main__":
    main()
