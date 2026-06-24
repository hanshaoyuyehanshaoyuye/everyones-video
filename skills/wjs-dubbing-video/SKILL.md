---
name: wjs-dubbing-video
description: >-
  Generate TTS dubbing audio from SRT subtitles using Edge-TTS (free, neural quality,
  100+ languages). Takes translated SRT, outputs a single MP3 dub track that can be
  fed into wjs-burning-subtitles for final video synthesis. Triggers on: 配音, dubbing,
  TTS dubbing, generate dub audio, SRT to speech, 字幕转语音.
---

# wjs-dubbing-video — SRT → TTS 配音

将翻译后的 SRT 字幕生成 TTS 配音音频。Edge-TTS 免费优先。

## 用法

```bash
# 中文配音
python3 integration/tts_dub.py subtitles.zh-CN.srt --lang zh-CN -o dub.mp3

# 英文配音
python3 integration/tts_dub.py subtitles.en.srt --lang en -o dub.mp3

# 指定语音
python3 integration/tts_dub.py subtitles.srt --lang ja --voice ja-JP-NanamiNeural -o dub.mp3
```

## 管线中使用

```bash
bash integration/pipeline.sh video.mp4 --lang en --translate --dub --burn
```

## 依赖

```bash
pip install edge-tts
```

## 输出

单轨 MP3 配音音频，时间轴匹配 SRT 字幕。可直接传给 render.py --dub。
