#!/usr/bin/env python3
"""
tts_dub.py — SRT → 配音音频 (Edge-TTS 免费优先)

为每条 SRT 字幕生成 TTS 语音，按时间轴拼接为完整配音音频。
可以直接喂给 render.py --dub 做最终合成。

用法:
  python3 tts_dub.py subtitles.srt --lang zh-CN -o dub.mp3
  python3 tts_dub.py subtitles.srt --lang en --voice en-US-AriaNeural -o dub.mp3
  python3 tts_dub.py subtitles.srt --lang ja --voice ja-JP-NanamiNeural -o dub.mp3

引擎: Edge-TTS (免费, 100+ 语言, 神经网络音质)
      豆包 TTS (付费, 需 DASHSCOPE_API_KEY) 通过 --engine doubao

输出: 单轨 MP3，时长匹配原 SRT 字幕时间轴
"""

import argparse
import asyncio
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from srt_utils import parse_srt

# Edge-TTS 语音映射: 语言 → 推荐语音
VOICE_MAP = {
    "zh": "zh-CN-XiaoxiaoNeural",
    "zh-CN": "zh-CN-XiaoxiaoNeural",
    "en": "en-US-AriaNeural",
    "ja": "ja-JP-NanamiNeural",
    "ko": "ko-KR-SunHiNeural",
    "fr": "fr-FR-DeniseNeural",
    "de": "de-DE-KatjaNeural",
    "es": "es-ES-ElviraNeural",
    "pt": "pt-BR-FranciscaNeural",
    "ru": "ru-RU-SvetlanaNeural",
    "ar": "ar-SA-ZariyahNeural",
}

DEFAULT_VOICE = "en-US-AriaNeural"


def ts_to_sec(ts: str) -> float:
    h, m, s = ts.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


async def edge_tts_gen(text: str, voice: str, out_path: str):
    """Generate TTS audio for a single text segment using Edge-TTS."""
    try:
        import edge_tts
    except ImportError:
        sys.exit(
            "edge-tts is not installed.\n"
            "  pip install edge-tts"
        )
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(out_path)


def gen_edge_tts(cues: list[dict], voice: str, work_dir: str) -> str:
    """Generate dub audio from SRT cues via Edge-TTS (free).

    Each cue gets its own TTS audio clip, then all clips are concatenated
    with proper timing using ffmpeg.
    """
    print(f"→ Edge-TTS ({voice}): {len(cues)} 条字幕", file=sys.stderr)

    # Generate per-cue audio
    clip_files = []
    for i, cue in enumerate(cues):
        text = cue["text"].replace("\n", " ").strip()
        if not text:
            clip_files.append(None)
            continue
        clip_path = os.path.join(work_dir, f"tts_{i:04d}.mp3")
        try:
            asyncio.run(edge_tts_gen(text, voice, clip_path))
            clip_files.append(clip_path)
        except Exception as e:
            print(f"  ⚠ cue {i+1} TTS failed: {e}", file=sys.stderr)
            # Generate silence for this cue
            silence_path = os.path.join(work_dir, f"silence_{i:04d}.mp3")
            dur = ts_to_sec(cue["end"]) - ts_to_sec(cue["start"])
            r = subprocess.run([
                "ffmpeg", "-y", "-f", "lavfi",
                "-i", f"anullsrc=r=24000:cl=mono",
                "-t", str(max(dur, 0.5)),
                "-codec:a", "libmp3lame", "-qscale:a", "2",
                silence_path,
            ], capture_output=True)
            if r.returncode != 0:
                print(f"  ⚠ ffmpeg silence gen failed: {r.stderr.decode()[:200]}", file=sys.stderr)
            clip_files.append(silence_path)
        if (i + 1) % 10 == 0:
            print(f"  [{i+1}/{len(cues)}]", file=sys.stderr)

    # Build ffmpeg concat: pad/silence between cues, trim to duration
    concat_list = os.path.join(work_dir, "tts_concat.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        prev_end = 0.0
        for i, (cue, clip) in enumerate(zip(cues, clip_files)):
            start = ts_to_sec(cue["start"])
            gap = start - prev_end

            # Insert silence if there's a gap before this cue
            if gap > 0.05:
                gap_path = os.path.join(work_dir, f"gap_{i:04d}.mp3")
                r = subprocess.run([
                    "ffmpeg", "-y", "-f", "lavfi",
                    "-i", f"anullsrc=r=24000:cl=mono",
                    "-t", str(gap),
                    "-codec:a", "libmp3lame", "-qscale:a", "2",
                    gap_path,
                ], capture_output=True)
                if r.returncode != 0:
                    print(f"  ⚠ gap gen failed: {r.stderr.decode()[:200]}", file=sys.stderr)
                f.write(f"file '{gap_path}'\n")

            if clip and os.path.exists(clip):
                f.write(f"file '{clip}'\n")
                dur = os.path.getsize(clip) / 16000  # rough estimate
                prev_end = start + max(
                    ts_to_sec(cue["end"]) - start,
                    dur if dur > 0 else 1.0,
                )
            else:
                prev_end = ts_to_sec(cue["end"])

    # Concat all clips
    dub_path = os.path.join(work_dir, "dub.mp3")
    r = subprocess.run([
        "ffmpeg", "-y", "-f", "concat", "-safe", "0",
        "-i", concat_list, "-codec:a", "libmp3lame",
        "-qscale:a", "2", dub_path,
    ], capture_output=True)

    if r.returncode != 0:
        sys.exit(f"TTS 配音生成失败: {r.stderr.decode()[:300]}")
    if os.path.exists(dub_path) and os.path.getsize(dub_path) > 0:
        return dub_path
    sys.exit("TTS 配音生成失败: 输出文件为空")


def main():
    parser = argparse.ArgumentParser(description="SRT → TTS 配音音频")
    parser.add_argument("srt", help="字幕 SRT 文件")
    parser.add_argument("--lang", default="zh-CN", help="目标语言 (默认: zh-CN)")
    parser.add_argument("--voice", help="TTS 语音名称 (默认: 根据语言自动选择)")
    parser.add_argument("--engine", default="edge-tts",
                        choices=["edge-tts", "doubao"],
                        help="TTS 引擎 (默认: edge-tts)")
    parser.add_argument("--output", "-o", required=True, help="输出音频文件 (MP3)")
    parser.add_argument("--work-dir", help="临时文件目录 (默认: 系统临时目录)")

    args = parser.parse_args()

    cues = parse_srt(args.srt)
    if not cues:
        sys.exit(f"No cues found in {args.srt}")

    # Determine voice
    voice = args.voice or VOICE_MAP.get(args.lang, DEFAULT_VOICE)
    work_dir = args.work_dir or tempfile.mkdtemp(prefix="tts_dub_")

    try:
        if args.engine == "edge-tts":
            dub_path = gen_edge_tts(cues, voice, work_dir)
        elif args.engine == "doubao":
            sys.exit(
                "豆包 TTS 暂未集成。请使用 --engine edge-tts (免费)。\n"
                "  或等待 v4.1 豆包 TTS 支持。"
            )
        else:
            sys.exit(f"Unknown engine: {args.engine}")
    finally:
        # Cleanup temp clips (keep the final output)
        for f in Path(work_dir).glob("tts_*.mp3"):
            f.unlink(missing_ok=True)
        for f in Path(work_dir).glob("gap_*.mp3"):
            f.unlink(missing_ok=True)
        for f in Path(work_dir).glob("silence_*.mp3"):
            f.unlink(missing_ok=True)
        concat = os.path.join(work_dir, "tts_concat.txt")
        if os.path.exists(concat):
            os.unlink(concat)

    # Copy to output
    shutil.copy(dub_path, args.output)
    print(f"→ {args.output} ({os.path.getsize(args.output)//1024} KB)", file=sys.stderr)


if __name__ == "__main__":
    main()
