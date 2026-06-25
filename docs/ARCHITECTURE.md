# Architecture Decision Records

## ADR-1: 双模式架构 — Chrome 实时 + 离线管线

### 背景

v1-v5 只有离线管线模式。v6 新增 Chrome Extension 实时翻译，两种模式共享翻译引擎和 TM。

### 决策

**双模式：Chrome Extension（实时） + pipeline.sh（离线管线），共享 TM + LLM 后端。**

```
用户需求
  ├── 看视频想要实时字幕 → Chrome Extension (content.js + realtime_server.py)
  └── 要成品视频出片     → pipeline.sh (ASR → 翻译 → TTS → 烧录)
                │
                └── 共享: TM 翻译记忆库 + LLM 翻译后端
```

### 理由

1. **实时翻译**不走 ASR——劫持平台自带字幕，直接翻译，零等待
2. **离线管线**走完整 ASR→翻译→配音→烧录，适合出片
3. **TM 共享**：两种模式的翻译结果都写入 TM，互相受益
4. **零耦合**：realtime_server.py 和 pipeline.sh 可以独立运行

---

## ADR-2: 多引擎路由而非单一引擎

### 决策

采用**多引擎路由模型**，根据源语言、场景和预算自动选择。

### 路由规则

```
输入音频 → 检测源语言 + 是否有 YouTube 自动字幕
  ├── YouTube → 有自动字幕 → yt-dlp 直接下载 (免费, 1秒)
  ├── Chrome 实时 → 劫持平台字幕 × TM+LLM (免费, 拦截模式)
  ├── 中文+免费 → FunASR (阿里达摩院, 本地运行, 时间戳+VAD)
  ├── 中文+付费+高精度 → 豆包 (Volcano ASR)
  ├── 中文+付费+极速 → StepFun (85-101× RTF)
  ├── 英文+免费 → faster-whisper (本地, 4× faster than whisper)
  └── 英文+付费 → OpenAI Whisper API (word-level timestamps)
```

---

## ADR-3: 翻译记忆库 TM — 缓存优于重复计算

### 背景

同一视频反复观看或同一句话在不同视频中重复出现，每次都调 LLM 翻译浪费 API 费和延迟。

### 决策

**所有翻译先查 TM（JSON-based，exact+fuzzy 匹配），命中直接返回，未命中再调 LLM 并写入 TM。**

### 理由

1. **Chrome Extension 模式下 TM 是必须的**：每帧字幕变化都调 LLM 会又慢又贵
2. **同视频复看 100% 缓存命中**：TM 自动落盘，第二次观看零 API 调用
3. **跨视频复用**：fuzzy match (difflib ≥80%) 复用相似句子的翻译

---

## ADR-4: 转写和翻译分两步而非端到端

### 决策

**永远分两步：先转写（source SRT），再翻译（target SRT）。**

### 理由

1. **可审查**：源语言 SRT 可以先检查有没有转写错误
2. **可替换**：可以只换翻译引擎，不用重新转写
3. **可复用**：一份 source SRT 可以翻成多种语言
4. **质量更高**：LLM 做纯翻译比同时做转写+翻译质量高

---

## ADR-5: Claude Code 技能 + 独立 CLI 双模

### 决策

**封装为 Claude Code 技能，同时提供独立 CLI 入口（translate_srt.py / realtime_server.py / tts_dub.py），不绑定 Claude Code。**

### 理由

1. **Claude Code 用户**：技能间管道编排，LLM-in-the-loop 语义理解
2. **非 Claude Code 用户**：pip install 后直接命令行使用，无需 Claude Code
3. **Chrome Extension**：只依赖 realtime_server.py，不依赖 Claude Code

---

## 技术栈总览

| 层 | 技术 | 说明 |
|----|------|------|
| 实时翻译 | Chrome Extension MV3 + HTTP backend | content.js 劫持 + realtime_server.py |
| 离线管线 | pipeline.sh + Python 脚本 | 五步管线：提取→ASR→翻译→配音→烧录 |
| TM 缓存 | JSON + difflib | exact + fuzzy match，跨会话持久化 |
| ASR | FunASR / faster-whisper / StepFun / 豆包 / Whisper | 五引擎路由 |
| 翻译 | LLM (DeepSeek / Qwen / Ollama / OpenAI) | 任意 OpenAI 兼容接口 |
| TTS | Edge-TTS | 免费，100+ 语种，神经质量 |
| 合成 | ffmpeg + libass | 字幕烧录/软字幕 |
| 安全 | rate limit + body limit + lang whitelist + CORS | 实时服务安全加固 |
