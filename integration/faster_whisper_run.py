#!/usr/bin/env python3
"""
faster_whisper_run.py — English ASR via faster-whisper (free, local, CTranslate2).

Usage:
  python3 faster_whisper_run.py audio.mp3 [--lang en] [-o transcript.txt] [--srt]

Output: plain text (one segment per line) by default; SRT with --srt flag.

Requirements:
  pip install faster-whisper
  # Model auto-downloads: tiny(74MB) / base(141MB) / small(461MB) / medium(1.5GB)
"""

import argparse
import sys
from pathlib import Path


def ts_srt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def main():
    parser = argparse.ArgumentParser(description="English ASR via faster-whisper")
    parser.add_argument("input", help="Audio file (mp3/wav/m4a)")
    parser.add_argument("--lang", default="en", help="Language (default: en)")
    parser.add_argument("--output", "-o", default=None, help="Output file")
    parser.add_argument("--model", default="base",
                        help="Model size: tiny/base/small/medium/large (default: base)")
    parser.add_argument("--srt", action="store_true",
                        help="Output SRT format instead of plain text")
    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        sys.exit(f"Error: file not found: {args.input}")

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit(
            "faster-whisper is not installed.\n"
            "  pip install faster-whisper\n"
            "  # Models: tiny(74MB) / base(141MB) / small(461MB) / medium(1.5GB)"
        )

    print(f"→ Loading faster-whisper model '{args.model}'…", file=sys.stderr)
    model = WhisperModel(args.model, device="cpu", compute_type="int8")

    print(f"→ Transcribing: {inp.name} ({inp.stat().st_size // 1024 // 1024} MB)",
          file=sys.stderr)
    segments, info = model.transcribe(str(inp), beam_size=5)
    lang = info.language
    print(f"  Detected language: {lang}, probability: {info.language_probability:.2f}",
          file=sys.stderr)

    lines = []
    cues = []
    idx = 0
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        if args.srt:
            idx += 1
            cues.append(f"{idx}")
            cues.append(f"{ts_srt(seg.start)} --> {ts_srt(seg.end)}")
            cues.append(text)
            cues.append("")
        else:
            lines.append(f"[{ts_srt(seg.start)}] {text}")

    out = "\n".join(cues) if args.srt else "\n".join(lines)

    if not out.strip():
        sys.exit("Error: faster-whisper returned empty output.")

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"→ {args.output}", file=sys.stderr)
    else:
        print(out)

    print(f"  Done: {idx} segments, language={lang}", file=sys.stderr)


if __name__ == "__main__":
    main()
