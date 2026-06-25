# 省钱优化指南

**pipeline.sh 的设计哲学：能免费，不付费。能跳过，不重复。能缓存，不重算。**

## 逐步骤优化策略

### Step 1: 字幕优先检查（省最多）

```
输入 YouTube URL
       │
       ▼
  yt-dlp --write-auto-subs --sub-lang zh,en --skip-download
       │
       ├── 有字幕 (≈80% 英文, ≈40% 中文) → ✅ 直接得到 SRT
       │    耗时: 1-2 秒
       │    成本: ¥0
       │    跳过: Step 2 (ASR) + Step 3 (文本→SRT)
       │
       └── 无字幕 → 下载音频, 进入 Step 2
```

**为什么先查字幕？**

YouTube 从 2020 年起为几乎所有英文视频生成自动字幕，中文覆盖率也在快速增长。`yt-dlp --write-auto-subs` 直接下载这些字幕，不需要任何 API 调用。

**如果 yt-dlp 下的不是中文？**

加 `--sub-lang zh-Hans,zh,en` 优先尝试中文，没有就下英文。英文 SRT 后续可以用翻译引擎翻成中文——翻译成本远低于从零转写。

### Step 2: ASR 引擎选择（免费优先）

```
无可用字幕 → 需要 ASR
       │
       ├── 中文 → 🟢 FunASR (免费, 本地)
       │    pip install -r requirements-full.txt
       │    模型: paraformer-zh (约 1GB, 首次下载)
       │    RTF: ~15× (10分钟音频约40秒)
       │    输出: 带时间戳的文本 (可直接转 SRT)
       │
       ├── 英文 → 🟢 faster-whisper (免费, 本地)
       │    pip install -r requirements-full.txt
       │    模型: base/small/medium/large (越大越准)
       │    RTF: ~40-60× (10分钟音频约12秒 on GPU)
       │    输出: word-level timestamps
       │
       ├── 中文+要极速 → StepFun (付费, ~0.4元/h)
       │    适合: 批量处理, 不在乎时间戳偏移
       │    注意: 纯文本输出, 需 text_to_srt.py 转换
       │
       └── 正式出片 → 豆包/Whisper API (付费)
            适合: 对时间戳精度有要求, 客户交付
```

### Step 3: 文本→SRT 转换（避开付费的坑）

StepFun 输出纯文本（无时间戳），`text_to_srt.py` 用标点分段 + 平均语速估算时间戳。

**什么时候可以用：**
- 翻译场景：时间戳差半秒不影响理解
- 摘要场景：根本不需要时间戳
- 快速原型：先看效果，正式版再换豆包

**什么时候不可以用：**
- 字幕需要精确口型同步
- 专业配音/字幕组交付
- 音频有大量沉默段落（语速估算会漂移）

### Step 4-5: 翻译和烧录（Claude Code 技能）

这两步走 Claude Code 技能，不走 API：
- 翻译用 LLM 做语义理解+自然翻译（比传统机器翻译好很多）
- 烧录用 ffmpeg + libass（成熟稳定，本地免费）

## 成本模拟

### 场景 A: 一个 10 分钟英文 YouTube 教程

```
pipeline.sh 默认路径:
  Step 1: yt-dlp 字幕 → ✅ 命中 (免费, 1秒)
  Step 2: 跳过
  Step 3: 跳过
  Step 4: Claude Code 翻译 (已有)
  Step 5: ffmpeg 烧录 (已有)
  
  总成本: ¥0
  总耗时: ~10秒 (下载+翻译+烧录)
```

### 场景 B: 一个 30 分钟中文会议录音

```
pipeline.sh --lang zh (本地文件, 无字幕):
  Step 1: 跳过 (本地文件)
  Step 2: FunASR 转写 (免费, ~2分钟)
  Step 3: 文本→SRT (免费, <1秒)
  Step 4: 跳过 (不需要翻译)
  Step 5: 跳过 (不需要烧录)
  
  总成本: ¥0
  总耗时: ~2分钟
```

### 场景 C: 批量 50 个中文视频, 需要精确字幕

```
手动选择豆包:
  Step 1: yt-dlp 下载音频
  Step 2: 豆包 ASR (付费, ~0.15元/10分钟/个)
  Step 3: 豆包自带 SRT
  Step 4: Claude Code 翻译
  
  总成本: ~7.5 元 (50 × 0.15)
  总耗时: ~5分钟 API 时间
```

### 三场景对比

| 场景 | 引擎 | 总成本 | 选择原因 |
|------|------|--------|---------|
| A: YouTube英文 | yt-dlp字幕 | ¥0 | 有字幕，跳过所有收费 |
| B: 中文会议 | FunASR | ¥0 | 不需要精确时间戳 |
| C: 批量出片 | 豆包 | ~7.5元 | 客户交付要精确字幕 |

## 本地免费引擎怎么装

```bash
# 一键安装（含 FunASR + faster-whisper）
pip install -r requirements-full.txt
```

## 省钱清单

- [ ] 所有 YouTube 视频先跑 yt-dlp 字幕检查（pipeline.sh 已内置）
- [ ] Chrome 实时翻译复用 TM 缓存，第二次看同一视频零 API 调用
- [ ] 中文场景能用 FunASR 不用 StepFun
- [ ] 英文场景能用 faster-whisper 不用 Whisper API
- [ ] StepFun 输出的纯文本用 text_to_srt.py 桥接，不重新转写
- [ ] 翻译和烧录用 Claude Code 技能，不另付 API 费
- [ ] TM fuzzy match 复用相似翻译，减少 API 调用
- [ ] 会议/访谈不需要翻译就直接用，跳过 Step 4-5
- [ ] 首次安装 FunASR 或 faster-whisper 的模型下载是一次性的
