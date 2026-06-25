# Everyones Video — 实时字幕 + 离线管线 🎬

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Chrome Extension](https://img.shields.io/badge/Chrome-Extension-4285F4?logo=googlechrome)](https://github.com/hanshaoyuyehanshaoyuye/everyones-video/tree/main/extension)
[![Tests](https://img.shields.io/badge/tests-58%20passed-brightgreen)](https://github.com/hanshaoyuyehanshaoyuye/everyones-video/blob/main/tests/test_core.py)
[![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB?logo=python)](https://python.org)
[![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker)](https://ghcr.io)
[![Languages](https://img.shields.io/badge/语言-12_语种-blue)]()

> **两大模式 + 12 语种：实时翻译 + 离线出片。免费优先，MIT 开源。** / Real-time translation + offline pipeline. Free first, MIT licensed.

**Chrome 扩展**：打开 YouTube/Bilibili 自动双语字幕，12 语种任意互译，零下载零等待。**离线管线**：一句话从 URL/文件到成品视频，Claude Code 技能 + 独立 CLI 双模。

---

## 为什么选 everyones-video

**免费优先、MIT 许可、Chrome 实时翻译、Docker 就绪、安全加固 — 五张牌同时具备的只有我们。**

| 能力 | everyones-video | pyvideotrans | VideoLingo | Mazinger | jianshuo/skills |
|------|:--:|:--:|:--:|:--:|:--:|
| **许可** | **MIT** | GPL-3.0 | Apache 2.0 | 待确认 | MIT |
| **Chrome 实时翻译** | **✅ v6.2** | — | — | — | — |
| **12 语种翻译** | **✅ 中日韩俄德法西葡阿** | 部分 | 部分 | — | — |
| **整管线 ¥0 跑通** | **✅** | 需配 API | 需配 API | 需配 API | 需配 API |
| **Docker + API Server** | **✅** | — | — | — | — |
| **翻译记忆库 TM** | **✅** | — | — | — | — |
| **SQI 字幕质量引擎** | **✅ v7.0** | — | — | — | — |
| **安全加固** | **✅** | — | — | — | — |
| **Claude Code 技能** | **✅ 4 个** | — | — | — | ✅ 15 个 |
| 说话人分离 | ✅ FunASR + WhisperX | ✅ | ✅ | — | — |
| 翻译质量反思 | ✅ GEMBA-MQM修复 | — | ✅ 3步 | — | — |
| 翻译质量评估 | ✅ GEMBA-MQM | — | — | — | — |
| 语音合成 | ✅ Edge-TTS | ✅ 3引擎 | — | — | — |

> **MIT 许可：** 嵌入产品、SaaS 服务、二次开发 — 都无需开源你的代码。
>
> **Docker 部署：** 跑在服务器上、集成到 CI/CD、被其他工具调用 — 从本机工具到平台组件。

同赛道还有很多优秀项目：[pyvideotrans](https://github.com/jianchang512/pyvideotrans)（18k★，GUI + 声克隆）、[VideoLingo](https://github.com/Huanshere/VideoLingo)（17.5k★，Netflix 级字幕质量）、[Mazinger](https://github.com/bakrianoo/mazinger)（10 段式管线）、[jianshuo/claude-skills](https://github.com/jianshuo/claude-skills)（15 个视频创作技能）。各有千秋，按需选择。

---

## 多语种翻译

**12 语种互通：中文、English、日本語、한국어、Русский、Deutsch、Français、Español、Português、العربية — 任意方向互译。**

| 源语言 | 自动检测方式 |
|--------|-------------|
| 🇨🇳 中文 | CJK 统一汉字检测 (4E00-9FFF) |
| 🇬🇧 English | 拉丁字母，默认回退 |
| 🇯🇵 日本語 | 平假名 (3040-309F) + 片假名 (30A0-30FF) |
| 🇰🇷 한국어 | 韩文音节 (AC00-D7AF) |
| 🇷🇺 Русский | 西里尔字母 (0400-04FF) |
| 🇩🇪🇫🇷🇪🇸🇧🇷 拉丁语系 | Unicode Latin 检测，用户手动区分 |
| 🇸🇦 العربية | 阿拉伯字母 (0600-06FF) |

- **离线管线**: `python3 integration/translate_srt.py input.srt --to ja`（日/韩/俄/德/法/西/葡/阿均支持）
- **实时翻译**: Chrome Extension 自动检测或手动选择，`Alt+L` 切换语言
- **LLM 后端**: DeepSeek / OpenAI / Ollama 均支持多语种 prompt

---

## Chrome 实时翻译 (v6.2)

**任意网页视频 → 自动双语字幕。不下视频、不等处理、零 ASR 成本。**

### 支持平台

| 平台 | 字幕源 | 方式 |
|------|--------|------|
| **YouTube** | timedtext API | XML 拦截 |
| **Bilibili** | 播放器 API | getCaptions() + subtitle API |
| **Vimeo / Coursera / …** | `<track>` WebVTT | 自动拉取 |
| **任意网站** | XHR/fetch 响应 | SRT/VTT/JSON 模式匹配 |

### 原理

```
任意网页 <video>
    │
    ▼
平台检测 → 匹配字幕源适配器
    │
    ├─ YouTube → 拦截 timedtext XML
    ├─ Bilibili → player.getCaptions() / subtitle API
    ├─ <track>  → fetch WebVTT
    └─ 通用     → XHR/fetch 模式匹配 (SRT/VTT/JSON)
    │
    ▼
POST /translate/batch → realtime_server.py
    │
    ├─ TM 命中 → <1ms 直接返回
    └─ TM 未命中 → DeepSeek/Ollama → 写入 TM
    │
    ▼
rAF 轮询 video.currentTime → 匹配 cue → DOM 叠加中文
```

### 30 秒安装

```bash
# 1. 启动翻译后端
export DEEPSEEK_API_KEY=sk-...
python3 integration/realtime_server.py &

# 2. 加载扩展
# Chrome → 扩展程序 → 开发者模式 → "加载已解压的扩展程序" → 选 extension/ 目录

# 3. 打开任意视频网站 (YouTube/Bilibili/Vimeo/…)，开启字幕
```

### 特性

- **多平台**: YouTube · Bilibili · Vimeo · Coursera · 任意 `<track>` / fetch 字幕源
- **零下载**：拦截平台自带字幕，不调用 yt-dlp
- **零延迟感**：TM 缓存命中 <1ms，LLM 翻译 ~300ms
- **同视频复看免费**：翻译缓存到 TM，二次观看 100% 命中，不调 API
- **12 语种互通**：中日韩俄德法西葡阿 + 英文。Unicode 自动检测源语言 + 手动指定
- **Alt+T 开关**，**Alt+L 切语言**

---

## 五分钟效果 (离线管线)

**Before:** 一个没字幕的英文教程视频，需要 30 分钟手动操作、花几十元调 API。

**After:** 一条命令，已有字幕时秒级完成，¥0。

```bash
bash integration/pipeline.sh "https://youtube.com/watch?v=dQw4w9WgXcQ" --translate --dub --burn
```

```text
════════════════════════════════════
 视频字幕管线
 语言: zh | ASR: auto
 翻译: true | 反思: false | 配音: true | 烧录: true
════════════════════════════════════

═══ Step 1: 提取音频 + 字幕检查 ═══
  → 检查 YouTube 自动字幕...
  🎯 找到已有字幕！跳过 ASR (省时省钱)
  → subtitles.srt (142 条字幕)

═══ Step 2: ASR 转写 — 跳过 (已有字幕) ═══

═══ Step 3: 文本 → SRT — 跳过 (已有 SRT) ═══

═══ Step 4: 翻译字幕 ═══
  → subtitles_translated.srt (142 条)

═══ Step 5: TTS 配音 ═══
  → dub.mp3

═══ Step 6: 烧录字幕 ═══
  → tutorial_subtitled.mp4

════════════════════════════════════
 完成！
════════════════════════════════════
```

---

## 流程图

### 实时模式 (Chrome Extension)

```mermaid
flowchart LR
    A[任意视频网站] --> B[content.js<br/>多平台字幕劫持]
    B --> C[realtime_server.py<br/>TM + LLM 翻译 · 12语种]
    C --> D[DOM 叠加<br/>双语字幕]
    D --> E{换语言?}
    E -->|Alt+L| C
    E -->|无操作| F[✅ 持续实时翻译]
```

### 离线管线 (pipeline.sh)

```mermaid
flowchart TD
    A[🎥 YouTube URL / 本地文件] --> B{字幕检查}
    B -->|✅ 有字幕| D[⏭️ 跳过 ASR]
    B -->|❌ 无字幕| C[🎙️ ASR 引擎选择]
    C -->|中文| C1[🟢 FunASR<br/>免费 · 本地]
    C -->|英文| C2[🟢 faster-whisper<br/>免费 · 本地]
    C -->|付费极速| C3[🔵 StepFun<br/>~0.4元/h]
    C1 & C2 & C3 --> E[📝 文本 → SRT]
    D --> E
    E --> F{需要翻译?}
    F -->|是| G[🌐 翻译<br/>DeepSeek / Ollama]
    F -->|否| H[🎬 成品 SRT]
    G --> H
    H --> I{需要配音?}
    I -->|是| J[🎙️ TTS 配音<br/>Edge-TTS 免费]
    I -->|否| K{需要烧录?}
    J --> K
    K -->|是| L[🔥 字幕烧录<br/>libass 硬字幕]
    K -->|否| M[✅ 完成]
    L --> M
```

---

## 安装

### 方式 1：git clone（推荐）

```bash
git clone https://github.com/hanshaoyuyehanshaoyuye/everyones-video ~/.claude/skills/everyones-video
```

### 方式 2：ClawHub 安装 `[即将上线]`

```bash
clawhub install everyones-video
```

### 方式 3：Claude Code marketplace `[即将上线]`

```bash
claude plugin marketplace add hanshaoyuyehanshaoyuye/everyones-video
claude plugin install everyones-video
```

### 方式 4：独立工具（不需要 Claude Code）

```bash
git clone https://github.com/hanshaoyuyehanshaoyuye/everyones-video
cd everyones-video && pip install -r requirements.txt
```

---

## 引擎对比

| 引擎 | 价格 | 中文 | 英文 | 速度 | 时间戳 | 说话人 | 离线 |
|------|:--:|:--:|:--:|:--:|:--:|:--:|:--:|
| **FunASR** 阿里达摩院 | 🟢 免费 | ⭐⭐⭐ | ⭐ | ~15× | ✅ | ✅ cam++ | ✅ |
| **faster-whisper** CTranslate2 | 🟢 免费 | ⭐⭐ | ⭐⭐⭐ | ~50× | ✅ | ✅ WhisperX | ✅ |
| yt-dlp 字幕提取 | 🟢 免费 | — | — | 1s | ✅ | — | ❌ |
| StepFun | ~0.4元/h | ⭐⭐ | ⭐⭐ | ~90× | ❌ | — | ❌ |
| 豆包 Volcano | 付费 | ⭐⭐⭐ | — | ~20× | ✅ | — | ❌ |
| Whisper API | $0.006/min | ⭐⭐ | ⭐⭐⭐ | ~15× | ✅ | — | ❌ |

> 详 [docs/ASR_COMPARISON.md](docs/ASR_COMPARISON.md)

---

## 快速上手

### 1. 装依赖

```bash
# 轻量核心（推荐 — 几十 MB，无模型下载）
pip install -r requirements.txt

# 完整版（需离线 ASR 再加这个 — FunASR ~1GB + faster-whisper ~74MB+）
pip install -r requirements-full.txt

# 检查环境
bash smoke_test.sh
```

| 安装方式 | 大小 | 能做什么 |
|------|------|------|
| `requirements.txt` | ~20MB | YouTube 字幕 + 翻译 + 配音 + 烧录 |
| `+ requirements-full.txt` | + ~2GB 模型 | 上面全部 + 离线 ASR（无需网络也能转写） |

### 2. 跑第一个视频

```bash
# YouTube → 自动字幕优先（80% 场景零成本）
bash integration/pipeline.sh "https://youtube.com/watch?v=dQw4w9WgXcQ"

# 翻译 + 配音 + 烧录
bash integration/pipeline.sh ~/tutorial.mp4 --lang en --translate --dub --burn

# 只预览不执行
bash integration/pipeline.sh ~/audio.mp3 --dry-run
```

### 3. 单独用某个模块

```bash
# 翻译 SRT
python3 integration/translate_srt.py input.srt --to en --bilingual

# 纯文本转 SRT
python3 integration/text_to_srt.py transcript.txt --lang zh -o output.srt

# SRT → TTS 配音
python3 integration/tts_dub.py subtitles.srt --lang zh-CN -o dub.mp3

# 翻译记忆库（TM）
python3 integration/tm.py stats                             # 查看统计
python3 integration/tm.py export --lang-pair en-zh-CN       # 导出
python3 integration/tm.py import --file tm_backup.json      # 导入

# 烧字幕 + 配音到视频
python3 skills/wjs-burning-subtitles/scripts/render.py \
    --video in.mp4 --srt subs.srt --dub dub.mp3 --out out.mp4
```

### 4. 换翻译后端

任何 OpenAI 兼容接口都能用，换三个环境变量即可：

```bash
# 用 OpenAI
export TRANSLATE_API_BASE=https://api.openai.com
export TRANSLATE_MODEL=gpt-4o-mini
export DEEPSEEK_API_KEY=sk-...

# 用阿里通义千问
export TRANSLATE_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
export TRANSLATE_MODEL=qwen-plus
export DEEPSEEK_API_KEY=sk-...

# 用本地 Ollama
export TRANSLATE_API_BASE=http://127.0.0.1:11434/v1
export TRANSLATE_MODEL=qwen3:14b
# 不需要 API key
```

也支持 `--api-key` 参数直传，不用环境变量。

### 5. 启动 API 服务器

**离线翻译服务 (端口 8730)：**

```bash
export DEEPSEEK_API_KEY=sk-...
export TRANSLATE_API_TOKEN=my-secret-token
python3 integration/translate_srt.py --server --port 8730
```

**实时翻译服务 (端口 8739，供 Chrome 扩展调用)：**

```bash
export DEEPSEEK_API_KEY=sk-...
python3 integration/realtime_server.py --port 8739
```

```bash
# 检测源语言
curl -X POST http://127.0.0.1:8739/detect-lang \
     -d '{"texts":["こんにちは世界"]}'

# 单条翻译
curl -X POST http://127.0.0.1:8739/translate \
     -d '{"text":"Hello","from":"en","to":"zh-CN"}'
```

### 6. 批量处理

```bash
bash integration/batch_pipeline.sh ~/videos/ --lang zh --translate --parallel 4
```

### 7. 质量评估

```bash
python3 integration/eval_quality.py source.srt translated.srt --from en --to zh-CN
```

### 8. 字幕质量修复 (SQI — v7.0)

```bash
# 修复重叠、过长/过短、间距问题
python3 integration/subtitle_quality.py subtitles.srt --lang zh --fix

# 仅诊断不修改
python3 integration/subtitle_quality.py subtitles.srt --check-only
```

翻译后自动运行（`translate_srt.py` 已内置），`--no-sqi` 可跳过。

---

## 10 个场景

| # | 场景 | 成本 | 引擎 |
|---|------|------|------|
| 1 | **YouTube 实时双语字幕** | **¥0** | **Chrome Extension** |
| 2 | YouTube 英文教程 → 中英双语出片 | ¥0 | yt-dlp 字幕 |
| 3 | 中文会议录音 → 文字纪要 | ¥0 | FunASR |
| 4 | 中文短视频 → 英文版出片 | ¥0~0.01 | FunASR |
| 5 | 批量 100 个视频 → 字幕 | ~¥15 | 豆包 |
| 6 | 播客 MP3 → 文字稿 + 时间轴 | ¥0 | FunASR |
| 7 | 1 视频 → 5 语言字幕 | ~¥0.03 | DeepSeek + TM |
| 8 | 纯本地离线（零网络） | ¥0 | FunASR |
| 9 | 30 秒语音 → 入门测试 | ¥0 | FunASR |
| 10 | 目录批量处理 | ~¥0 | batch_pipeline.sh |

> 详 [docs/WORKFLOWS.md](docs/WORKFLOWS.md)

---

## Docker

```bash
# 本地构建
docker build -t everyones-video .
docker run --rm \
    -v $(pwd)/work:/app/work \
    -e DEEPSEEK_API_KEY=$DEEPSEEK_API_KEY \
    everyones-video \
    "https://youtube.com/watch?v=VIDEO_ID"

# 或 pull 官方镜像
# docker pull ghcr.io/hanshaoyuyehanshaoyuye/everyones-video:latest

# API 服务器
export DEEPSEEK_API_KEY=sk-...
export TRANSLATE_API_TOKEN=my-token
docker compose up api
```

---

## 目录

| 文件 | 说明 |
|------|------|
| [integration/pipeline.sh](integration/pipeline.sh) | 一键管线脚本 (--engine 路由) |
| [extension/](extension/) | Chrome 实时翻译扩展 (v6.2, 多平台+12语种) |
| [integration/realtime_server.py](integration/realtime_server.py) | 实时翻译后端 (TM + LLM, HTTP API) |
| [integration/funasr_run.py](integration/funasr_run.py) | 免费中文 ASR (FunASR + cam++ 说话人) |
| [integration/faster_whisper_run.py](integration/faster_whisper_run.py) | 免费英文 ASR (faster-whisper + WhisperX 说话人) |
| [integration/text_to_srt.py](integration/text_to_srt.py) | 通用文本 → SRT |
| [integration/translate_srt.py](integration/translate_srt.py) | SRT 翻译 + TM 缓存 + API 服务器 |
| [integration/tm.py](integration/tm.py) | 翻译记忆库 (exact + fuzzy, 零依赖) |
| [integration/reflect_fix.py](integration/reflect_fix.py) | 翻译反思修复 (GEMBA-MQM → LLM → 再评) |
| [integration/tts_dub.py](integration/tts_dub.py) | SRT → TTS 配音 (Edge-TTS) |
| [integration/eval_quality.py](integration/eval_quality.py) | GEMBA-MQM 翻译质量评分 |
| [integration/subtitle_quality.py](integration/subtitle_quality.py) | SQI 字幕质量引擎 (重叠修复/时长截断/CPS检查) — v7.0 |
| [integration/batch_pipeline.sh](integration/batch_pipeline.sh) | 批量处理（并行+日志） |
| [skills/](skills/) | 四个 Claude Code 技能 |
| [Dockerfile](Dockerfile) | Docker 镜像（多阶段） |
| [docs/](docs/) | 架构 / 引擎对比 / 省钱指南 / 工作流 |

---

## 包含的四个技能

| 技能 | 触发词 | 功能 |
|------|--------|------|
| **wjs-transcribing-audio** | 转写 / 做 SRT / transcribe | 音频 → SRT |
| **wjs-translating-subtitles** | 翻译字幕 / translate this SRT | SRT 翻译 |
| **wjs-dubbing-video** | 配音 / TTS dub / SRT 转语音 | SRT → TTS 配音 (Edge-TTS) |
| **wjs-burning-subtitles** | 烧字幕 / 硬字幕 / burn | 字幕烧录到视频 |

---

## 依赖

| 工具 | 来源 | 用途 |
|------|------|------|
| `yt-dlp` | pip | YouTube 下载 + 字幕提取 |
| `FunASR` | 阿里达摩院 (Apache 2.0) | 中文免费 ASR + cam++ 说话人分离 |
| `faster-whisper` | SYSTRAN (MIT) | 英文免费 ASR |
| `WhisperX` | MIT | faster-whisper 说话人分离 (pyannote) |
| `ffmpeg` | 系统安装 | 音频转换 + 字幕烧录 |
| `edge-tts` | MIT | TTS 配音 (Chrome Extension 不需要) |

---

## License

MIT
