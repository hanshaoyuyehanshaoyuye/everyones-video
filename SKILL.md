---
name: everyones-video
description: >-
  End-to-end video subtitle pipeline — transcribe audio to SRT, translate subtitles between
  any languages, TTS dubbing via Edge-TTS (free), and burn subtitles into video (hard-coded or
  soft-mux). Free-first strategy: FunASR (Chinese) / faster-whisper (English) → StepFun/Doubao/
  Whisper API (paid fallback). Docker support, REST API server, 9 workflow scenarios. Use when
  adding subtitles to video, translating SRT files, dubbing with TTS, burning captions into MP4,
  setting up a subtitle pipeline, or localizing video content. Triggers on: 给视频加字幕, 做字幕,
  SRT翻译, 字幕翻译, 配音, 烧字幕, 硬字幕, 视频字幕管线, subtitle pipeline, add subtitles to
  video, transcribe audio to SRT, TTS dub, burn captions, video localization, 字幕, 语音转文字, SRT.
---

# Everyones Video

一站式视频字幕管线。从音频/YouTube → SRT → 翻译 → 烧录成品。

## 快速使用（Claude Code 中）

```
给这个视频加上中文字幕
把这个 SRT 翻译成英文
把字幕烧进视频
```

Claude 会自动加载本技能并执行对应的脚本。

## 独立使用（终端）

```bash
# 一键管线
bash integration/pipeline.sh "https://youtube.com/watch?v=VIDEO"

# 翻译 SRT
python3 integration/translate_srt.py input.srt --to en --bilingual

# 烧录字幕
python3 skills/wjs-burning-subtitles/scripts/render.py --video in.mp4 --srt subs.srt --out out.mp4

# API 服务器
python3 integration/translate_srt.py --server --port 8730

# Docker
docker compose up api
```
