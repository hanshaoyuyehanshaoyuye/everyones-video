# Architecture Decision Records

## ADR-1: 多引擎路由而非单一引擎

### 背景

需要为视频字幕管线选择 ASR（语音识别）引擎。考虑过用单一引擎覆盖所有场景。

### 决策

采用**多引擎路由模型**，根据源语言、场景和预算自动选择。

### 路由规则

```
输入音频 → 检测源语言 + 是否有 YouTube 自动字幕
  ├── YouTube → 有自动字幕 → yt-dlp 直接下载 (免费, 1秒)
  ├── 中文+免费 → FunASR (阿里达摩院, 本地运行, 时间戳+VAD)
  ├── 中文+付费+高精度 → 豆包 (Volcano ASR)
  ├── 中文+付费+极速 → StepFun (85-101× RTF)
  ├── 英文+免费 → faster-whisper (本地, 4× faster than whisper)
  └── 英文+付费 → OpenAI Whisper API (word-level timestamps)
```

### 理由

- **yt-dlp 字幕提取**覆盖 80% 的 YouTube 英文视频和越来越多的中文视频——零成本，应该排在第一位
- **FunASR** 是阿里达摩院开源的工业级中文 ASR，带 VAD（语音端点检测）、标点恢复、时间戳，本地运行零成本，中文准确度接近豆包
- **faster-whisper** 基于 CTranslate2，比原版 whisper 快 4×，GPU/CPU 通用
- 付费引擎是兜底方案——当免费方案不满足精度/速度需求时使用

---

## ADR-2: 转写和翻译分两步而非端到端

### 背景

有些 ASR 服务（如 YouTube 自动字幕）直接输出翻译结果。考虑过一步到位。

### 决策

**永远分两步：先转写（source SRT），再翻译（target SRT）。**

### 理由

1. **可审查**：源语言 SRT 可以先检查有没有转写错误，再翻译
2. **可替换**：对翻译质量不满意，可以只换翻译引擎，不用重新转写
3. **可复用**：一份 source SRT 可以翻成多种语言
4. **质量更高**：LLM 做纯翻译比 LLM 同时做转写+翻译质量高

### 代价

- 多一步操作
- 两步 API 调用成本略高于一步

### 放弃的替代方案

- **端到端转写+翻译**：更快但质量不可控，无法审查中间结果

---

## ADR-3: Claude Code 技能编排而非独立 CLI

### 背景

考虑过做成一个独立的 CLI 工具（Python 包），不依赖 Claude Code。

### 决策

**封装为 Claude Code 技能，通过技能间的管道编排实现流水线。**

### 理由

1. **LLM-in-the-loop**：Claude 可以在翻译步骤做语义理解（补全省略的主语、修正口语化的不完整句），这是纯 CLI 做不到的
2. **零配置复用**：每个技能是独立可用的，用户可以单独用"转写"或"翻译"，不一定要跑全管线
3. **生态杠杆**：站在 jianshuo/claude-skills 和 stepfun-asr 的肩膀上，不重复造轮子

### 代价

- 依赖 Claude Code 运行环境
- 依赖上游技能的持续维护

### 放弃的替代方案

- **独立 CLI**：更易分发但不具备 LLM 的语义理解能力
- **SaaS 服务**：太重，不适合开源项目

---

## 技术栈总览

| 层 | 技术 | 说明 |
|----|------|------|
| 编排 | Claude Code Skills | 技能发现、路由、LLM 调用 |
| 音频提取 | yt-dlp + ffmpeg | YouTube 下载 + 格式转换 |
| ASR | 豆包/StepFun/Whisper | 三引擎路由 |
| 翻译 | LLM (Qwen/DeepSeek/Claude) | 语义级翻译+重分段 |
| 合成 | ffmpeg + libass | 字幕烧录/软字幕 |
