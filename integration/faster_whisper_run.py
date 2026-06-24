#!/usr/bin/env python3
"""
faster_whisper_run.py — English ASR via faster-whisper (free, local, CTranslate2).

Usage:
  python3 faster_whisper_run.py audio.mp3 [--lang en] [-o transcript.txt] [--srt]
  python3 faster_whisper_run.py audio.mp3 --diarize [--hf-token hf_...] [-o out.srt]

Output: plain text (one segment per line) by default; SRT with --srt.
With --diarize: WhisperX pipeline (transcribe → align → pyannote diarize) → SRT.

Requirements:
  pip install faster-whisper
  # Model auto-downloads: tiny(74MB) / base(141MB) / small(461MB) / medium(1.5GB)
  # Diarization: pip install whisperx  (also needs HF_TOKEN from huggingface.co/settings/tokens
  #   + accept pyannote/segmentation-3.0 and pyannote/speaker-diarization-3.1 terms)
"""

import argparse
import os
import sys
from pathlib import Path


def ts_srt(sec: float) -> str:
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


def run_standard(inp, args):
    """Standard faster-whisper transcription (no diarization)."""
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


def run_diarize(inp, args):
    """WhisperX pipeline: transcribe + align + pyannote diarize → SRT."""
    try:
        import whisperx
    except ImportError:
        sys.exit(
            "WhisperX is not installed. Install with:\n"
            "  pip install whisperx\n\n"
            "Diarization also requires:\n"
            "  1. HF_TOKEN env var or --hf-token (from huggingface.co/settings/tokens)\n"
            "  2. Accept terms at huggingface.co/pyannote/segmentation-3.0\n"
            "  3. Accept terms at huggingface.co/pyannote/speaker-diarization-3.1"
        )

    hf_token = args.hf_token or os.environ.get("HF_TOKEN", "")
    if not hf_token:
        sys.exit(
            "HF_TOKEN is required for speaker diarization.\n"
            "  1. Get token: https://huggingface.co/settings/tokens\n"
            "  2. Accept: https://huggingface.co/pyannote/segmentation-3.0\n"
            "  3. Accept: https://huggingface.co/pyannote/speaker-diarization-3.1\n"
            "  4. Set: export HF_TOKEN=hf_...\n"
            "  Or pass: --hf-token hf_..."
        )

    device = "cpu"
    compute_type = "int8"
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            compute_type = "float16"
    except ImportError:
        pass

    print(f"→ Device: {device}, compute: {compute_type}", file=sys.stderr)

    # Step 1: Transcribe via WhisperX
    print(f"→ [1/4] Loading WhisperX model '{args.model}'…", file=sys.stderr)
    model = whisperx.load_model(args.model, device, compute_type=compute_type)

    audio = whisperx.load_audio(str(inp))
    print(f"→ [2/4] Transcribing {inp.name}…", file=sys.stderr)
    result = model.transcribe(audio, batch_size=16)
    lang = result.get("language", args.lang)
    print(f"  Detected language: {lang}", file=sys.stderr)

    # Step 2: Align (word-level timestamps)
    print(f"→ [3/4] Aligning word timestamps…", file=sys.stderr)
    try:
        model_a, metadata = whisperx.load_align_model(
            language_code=lang, device=device
        )
        result = whisperx.align(
            result["segments"], model_a, metadata, audio, device,
            return_char_alignments=False,
        )
    except Exception as e:
        print(f"  ⚠ Alignment failed ({e}), using unaligned segments",
              file=sys.stderr)

    # Step 3: Diarize
    print(f"→ [4/4] Speaker diarization (pyannote)…", file=sys.stderr)
    try:
        diarize_model = whisperx.DiarizationPipeline(
            use_auth_token=hf_token, device=device
        )
        diarize_segments = diarize_model(audio)
        result = whisperx.assign_word_speakers(diarize_segments, result)
    except Exception as e:
        sys.exit(f"Diarization failed: {e}\n\n"
                 f"Common causes:\n"
                 f"  - HF_TOKEN invalid or expired\n"
                 f"  - Didn't accept pyannote model terms on HuggingFace\n"
                 f"  - Audio too short (< 1s) or silent\n"
                 f"  - Memory exhausted (try smaller model)")

    # Build SRT with speaker labels
    cues = []
    idx = 0
    for seg in result.get("segments", []):
        speaker = seg.get("speaker", "UNKNOWN")
        text = seg.get("text", "").strip()
        if not text:
            continue
        idx += 1
        cues.append(str(idx))
        cues.append(f"{ts_srt(seg['start'])} --> {ts_srt(seg['end'])}")
        cues.append(f"[{speaker}] {text}")
        cues.append("")

    out = "\n".join(cues)

    if not out.strip():
        sys.exit("Error: WhisperX diarization returned empty output.")

    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"→ {args.output}", file=sys.stderr)
    else:
        print(out)

    # Speaker stats
    speaker_counts = {}
    for seg in result.get("segments", []):
        spk = seg.get("speaker", "UNKNOWN")
        speaker_counts[spk] = speaker_counts.get(spk, 0) + 1
    print(f"  Done: {idx} segments, {len(speaker_counts)} speakers: "
          f"{dict(speaker_counts)}, language={lang}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(
        description="English ASR via faster-whisper (+ WhisperX diarization)"
    )
    parser.add_argument("input", help="Audio file (mp3/wav/m4a)")
    parser.add_argument("--lang", default="en", help="Language (default: en)")
    parser.add_argument("--output", "-o", default=None, help="Output file")
    parser.add_argument("--model", default="base",
                        help="Model size: tiny/base/small/medium/large (default: base)")
    parser.add_argument("--srt", action="store_true",
                        help="Output SRT format instead of plain text")
    parser.add_argument("--diarize", action="store_true",
                        help="Speaker diarization via WhisperX + pyannote (outputs SRT)")
    parser.add_argument("--hf-token", default=None,
                        help="HuggingFace token for pyannote models (or set HF_TOKEN env)")
    args = parser.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        sys.exit(f"Error: file not found: {args.input}")

    if args.diarize:
        # Diarization always outputs SRT (real timestamps from WhisperX)
        run_diarize(inp, args)
    else:
        run_standard(inp, args)


if __name__ == "__main__":
    main()
