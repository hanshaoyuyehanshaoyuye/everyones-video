# 工作流指南

每个场景给出**完整命令**、**解释为什么这样选**、以及**花多少钱**。

> **省钱铁律：YouTube 视频不要一上来就调 ASR。先看有没有字幕。** pipeline.sh 已自动做这一步。

---

## 场景 1: YouTube 英文教程 → 中英双语字幕 ⭐ 最常见

### 你是

中文内容创作者，想翻一个英文 YouTube 教程，做双语字幕发 B 站/YouTube。

### 为什么大概率不需要花钱

YouTube 英文视频的自动字幕覆盖率超过 95%。直接下载比调 ASR 快 100 倍、准 10 倍、零成本。

### 完整步骤

```bash
# ── Step 1: 下载自动字幕 (1秒, ¥0) ──
yt-dlp --write-auto-subs --sub-lang en --convert-subs srt \
    --skip-download \
    -o "tutorial" \
    "https://youtube.com/watch?v=VIDEO_ID"

# 得到: tutorial.en.srt
# --skip-download: 只下载字幕, 不下载视频
# --convert-subs srt: YouTube 的 vtt 格式自动转标准 SRT
```

```bash
# ── Step 2: 下载视频本体 (如果也需要带字幕的视频) ──
yt-dlp -f "best[height<=1080]" \
    -o "tutorial.mp4" \
    "https://youtube.com/watch?v=VIDEO_ID"
```

```bash
# ── Step 3: 翻译为中文 (Claude Code 中) ──
# /wjs-translating-subtitles
# 输入文件: tutorial.en.srt
# 目标语言: zh-CN
# 输出: tutorial.zh-CN.srt
#
# 为什么用 Claude Code 而不是 Google 翻译?
# Claude 能理解上下文, 翻译质量更自然。
# 例如: "Let's dive in" 不会翻成 "让我们潜入" 而是 "我们开始吧"
```

```bash
# ── Step 4: 烧录双语字幕 (Claude Code 中) ──
# /wjs-burning-subtitles
# 视频: tutorial.mp4
# SRT: tutorial.zh-CN.srt
# 模式: 硬字幕 (微信视频号/抖音用) 或 软字幕 (QuickTime/VLC用)
```

```
总耗时: ~30秒 (1秒下载 + 29秒翻译/烧录)
总成本: ¥0
```

### 如果没字幕（5% 的罕见情况）

```bash
# 降级: 下载音频 → FunASR/faster-whisper 免费转写
yt-dlp -x --audio-format mp3 "URL" -o audio.mp3
python3 integration/text_to_srt.py \
    <(faster-whisper audio.mp3 --model base --output_dir .) --lang en -o en.srt
# 然后继续 Step 3 (翻译)
```

---

## 场景 2: 中文会议录音 → 文字纪要

### 你是

录了一段 30 分钟的中文会议，需要文字纪要和行动项。

### 为什么免费就够

会议纪要不需要逐字精确字幕，有个 95% 准确的文本就够了。FunASR 中文准确度可以达到商业水平。

### 完整步骤

```bash
# ── Step 1: 免费转写 (FunASR, 本地, ¥0) ──
# 安装 (一次性):
pip install -r requirements-full.txt

# 转写:
python3 << 'EOF'
from funasr import AutoModel
model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc")
result = model.generate(input="meeting_30min.mp3")
with open("meeting.txt", "w") as f:
    f.write(result[0]["text"])
print(f"转写完成: {len(result[0]['text'])} 字")
EOF

# 耗时: ~2分钟 (30分钟音频)
# 成本: ¥0
# 输出: meeting.txt (带标点的中文文本)
```

```bash
# ── Step 2: 生成会议纪要 (Claude Code 中) ──
# /meeting-minutes-taker
# 输入: meeting.txt
# 输出: 议题 / 决策 / 行动项 / 负责人 / 截止时间
```

```
总耗时: ~3分钟 (2分钟转写 + 1分钟生成纪要)
总成本: ¥0
```

### 替代方案: 用 stepfun-asr (更快但无时间戳)

```bash
# 仅当装了 StepFun API key
python3 ~/.claude/skills/stepfun-asr/scripts/asr_transcribe.py meeting.mp3 > meeting.txt
# 30分钟音频 → ~18秒 (85× RTF)
# 成本: ~0.2 元
```

---

## 场景 3: 中文短视频 → 英文版出片

### 你是

有一个 3 分钟的抖音/视频号短视频，想加英文字幕发 YouTube/TikTok。

### 为什么选 StepFun 或 FunASR

3 分钟短视频，字幕时间戳差半秒观众看不出来。免费或便宜的方案够了。

### 完整步骤

```bash
# ── Step 1: 一键管线 ──
bash integration/pipeline.sh my_video.mp4 --lang zh

# 内部流程:
#   → 优先 yt-dlp 字幕 (本地文件, 跳过)
#   → 选择 ASR: FunASR (免费) 或 StepFun (如配置了 key)
#   → 生成 zh.srt
```

```bash
# ── Step 2: 翻译为英文 (Claude Code 中) ──
# /wjs-translating-subtitles
# SRT: zh.srt → en.srt
```

```bash
# ── Step 3: 烧录英文硬字幕 (Claude Code 中) ──
# /wjs-burning-subtitles
# 视频: my_video.mp4
# SRT: en.srt
# 模式: 硬字幕 (社交媒体播放器不认软字幕)
```

```
总耗时: ~1分钟 (转写15秒 + 翻译30秒 + 烧录15秒)
总成本: ¥0 (FunASR) 或 ~0.01元 (StepFun 3分钟)
```

---

## 场景 4: 批量处理 100 个中文视频

### 你是

内容团队，需要把 100 个中文课程视频全部加上中文字幕（正式出片）。

### 为什么这时候才用豆包

正式出片需要精确时间戳 + 最高准确度。省下的校对时间远大于 API 成本。

```bash
# 批量脚本
for video in videos/*.mp4; do
    name=$(basename "$video" .mp4)
    echo "处理: $name"

    # 转写 (豆包, 高精度)
    # /wjs-transcribing-audio (Claude Code 中)
    # 输入: $video
    # 引擎: 豆包 (Volcano ASR)
    # → ${name}.srt

    # 可选: 翻译
    # /wjs-translating-subtitles → ${name}.en.srt

    echo "完成: $name"
done
```

```
总耗时: ~30分钟 API 时间 (100 × 10分钟, RTF ~20×)
总成本: ~15 元 (100 × ~0.15元/个)
```

---

## 引擎选择速查

```
你的情况是什么？

1. 有 YouTube 链接
   → 先跑 yt-dlp 下载字幕（免费）
   → 没有再选下面

2. 中文 + 要省钱 + 不要求逐字同步
   → FunASR (免费, 本地)

3. 中文 + 要极速 + 不要求逐字同步
   → StepFun + text_to_srt.py (极便宜)

4. 中文 + 要最高精度 + 正式出片
   → 豆包 (付费, 最准的中文)

5. 英文 + 要省钱
   → faster-whisper (免费, 本地)

6. 英文 + 要最高精度
   → Whisper API (付费, word-level)

7. 我有纯文本, 想转成字幕格式
   → text_to_srt.py (免费)

8. 我已有 SRT, 想翻译
   → /wjs-translating-subtitles

9. 我已有 SRT, 想烧进视频
   → /wjs-burning-subtitles
```

---

---

## 场景 5: 播客 MP3 → 文字稿 + 时间轴

### 你是

录了一期 60 分钟的播客，需要带时间戳的逐字稿发公众号/博客。

### 为什么 FunASR 是正确选择

播客是中文对话，不需要帧级精度。FunASR 中文准确率接近商业水平，完全免费，本地跑。

### 完整步骤

```bash
# ── Step 1: 转写 ──
# 装依赖: pip install -r requirements-full.txt
python3 << 'EOF'
from funasr import AutoModel
model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc")
result = model.generate(input="podcast_ep12.mp3")
with open("podcast_ep12.txt", "w") as f:
    f.write(result[0]["text"])
EOF
# 60 分钟音频 → ~4 分钟转写
# 输出: podcast_ep12.txt (带标点中文)
```

```bash
# ── Step 2: 文本 → SRT (得到时间轴) ──
python3 integration/text_to_srt.py podcast_ep12.txt --lang zh -o podcast_ep12.srt
# 输出: podcast_ep12.srt (估算时间轴，非帧级精度但够用)
```

```bash
# ── Step 3: 翻译为英文版 (可选) ──
python3 integration/translate_srt.py podcast_ep12.srt --to en -o podcast_ep12.en.srt
```

```
总耗时: ~5 分钟
总成本: ¥0
```

---

## 场景 6: 直播切片 → 快速字幕出片

### 你是

游戏/教学主播，需要把昨晚 2 小时直播里的一段 5 分钟高光切出来，加字幕发短视频。

### 为什么用 pipeline.sh 一键搞定

不需要手动下载、转写、翻译、烧录四步分开。一条命令从原始素材到成品。

```bash
# ── 先手动切出高光片段 (用 ffmpeg 不重编码) ──
ffmpeg -ss 01:23:45 -i stream_vod.mp4 -to 00:05:00 -c copy highlight.mp4

# ── 一键管线 ──
bash integration/pipeline.sh highlight.mp4 --lang zh --translate --burn
# 内部: 音频提取 → FunASR 转写 → 文本→SRT → DeepSeek 翻译 → ffmpeg 烧录
```

```
总耗时: ~2 分钟
总成本: ~0.01 元 (DeepSeek API)
```

### 如果只要中文字幕（跳过翻译）

```bash
bash integration/pipeline.sh highlight.mp4 --lang zh --burn
# 更快，零 API 成本
```

---

## 场景 7: 批量多语言字幕（1 个视频 → 5 种语言）

### 你是

产品团队，做了一个 3 分钟的英文产品演示视频，需要中/日/韩/法/西五种语言字幕。

### 为什么用 translate_srt.py 而不是每个语言调一次 API

translate_srt.py 支持批量，一键五语言。

```bash
# ── Step 1: 提取英文字幕 ──
yt-dlp --write-auto-subs --sub-lang en --convert-subs srt --skip-download \
    -o "demo" "https://youtube.com/watch?v=DEMO_ID"
# 得到: demo.en.srt

# ── Step 2: 批量翻译 ──
for lang in zh-CN ja ko fr es; do
    echo "→ $lang"
    python3 integration/translate_srt.py demo.en.srt --to $lang --from en -o "demo.${lang}.srt"
done
# 输出: demo.zh-CN.srt, demo.ja.srt, demo.ko.srt, demo.fr.srt, demo.es.srt

# ── Step 3: 烧录 (选一个语言烧硬字幕) ──
python3 skills/wjs-burning-subtitles/scripts/render.py \
    --video demo.mp4 --srt demo.zh-CN.srt --out demo_zh.mp4
# 其他语言同理
```

```
总耗时: ~60 秒 (5 个 API 调用，每个 ~12 秒)
总成本: ~0.03 元 (DeepSeek 5 × ~200 tokens)
```

---

## 场景 8: 纯本地离线字幕（完全零网络）

### 你是

处理敏感内容的视频，不能上传到任何云服务。全程本地。

```bash
# ── 全部本地引擎 ──
# 中文: FunASR (免费, 本地)
python3 << 'EOF'
from funasr import AutoModel
model = AutoModel(model="paraformer-zh", vad_model="fsmn-vad", punc_model="ct-punc")
result = model.generate(input="sensitive_meeting.mp3")
with open("meeting.txt", "w") as f: f.write(result[0]["text"])
EOF

# 文本 → SRT
python3 integration/text_to_srt.py meeting.txt --lang zh -o meeting.srt

# 烧录 (ffmpeg libass, 本地)
PY="$PWD/skills/wjs-burning-subtitles/scripts/render.py"
python3 "$PY" --video sensitive_meeting.mp4 --srt meeting.srt --out output.mp4
```

```
网络: 完全离线
成本: ¥0
隐私: 数据不离开本机
```

---

## 场景 9: 短音频 → 字幕文本（最简单的入门路径）

### 你是

第一次用这个工具，只有一个 30 秒的语音备忘录，想试试能不能出字幕。

```bash
# 最快路径
bash integration/pipeline.sh ~/VoiceMemos/idea.m4a --lang zh
# 输出:
#   ~/.subtitle_pipeline_work/audio.mp3       (转换后的音频)
#   ~/.subtitle_pipeline_work/transcript.txt  (转写文本)
#   ~/.subtitle_pipeline_work/subtitles.srt   (字幕文件)
```

```
耗时: ~5 秒
成本: ¥0
```

---

## 依赖技能调用速查

| 工具 | 类型 | 命令 |
|------|------|------|
| yt-dlp 字幕 | Shell | `yt-dlp --write-auto-subs --skip-download URL` |
| FunASR | Python | 本地免费 |
| faster-whisper | Python | 本地免费 |
| pipeline.sh | Shell | `bash integration/pipeline.sh <URL或文件>` |
| text_to_srt.py | Shell | `python3 integration/text_to_srt.py text.txt -o out.srt` |
| translate_srt.py | Shell | `python3 integration/translate_srt.py in.srt --to en` |
| render.py (burn) | Shell | `python3 skills/wjs-burning-subtitles/scripts/render.py --video ... --srt ... --out ...` |
| volc_asr_stream.py | Shell | `python3 skills/wjs-transcribing-audio/scripts/volc_asr_stream.py audio.mp3` |

> 所有工具已包含在本仓库内，无需额外安装 Claude Code 或外部技能。
> 翻译需要 DEEPSEEK_API_KEY 环境变量。豆包转写需要 DASHSCOPE_API_KEY。
