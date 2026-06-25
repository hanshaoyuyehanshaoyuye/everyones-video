---
name: everyones-video
description: >-
  End-to-end video subtitle pipeline — Chrome Extension real-time bilingual subtitles (multi-platform, 12 languages: zh/en/ja/ko/ru/de/fr/es/pt/ar) + offline pipeline (transcribe, translate, TTS dub, burn). SQI subtitle quality engine, SQLite TM with rapidfuzz, Docker, 6 CLI entry points, 64 tests. Use when
  adding subtitles to video, translating SRT files, dubbing with TTS, burning captions into MP4,
  setting up a subtitle pipeline, or localizing video content. Triggers on: 给视频加字幕, 做字幕,
  SRT翻译, 字幕翻译, 配音, 烧字幕, 硬字幕, 视频字幕管线, subtitle pipeline, add subtitles to
  video, transcribe audio to SRT, TTS dub, burn captions, video localization, 字幕, 语音转文字, SRT.
---

# Everyones Video v7.0

一站式视频字幕管线。12 语种实时翻译 + 离线管线。从音频/YouTube → SRT → 翻译 → SQI 质量修复 → 烧录成品。

## 快速使用（Claude Code 中）

```
给这个视频加上中文字幕
把这个 SRT 翻译成英文
把字幕烧进视频
打开实时双语字幕
```

Claude 会自动加载本技能并执行对应的脚本。

## 独立使用（终端）

```bash
# Chrome 扩展（实时翻译）
# Chrome → 扩展程序 → 开发者模式 → 加载 extension/ 目录

# 实时翻译后端
python3 integration/realtime_server.py --port 8739 &

# 一键离线管线
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
