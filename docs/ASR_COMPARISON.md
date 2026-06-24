# ASR 引擎对比

## 引擎总览

| 指标 | yt-dlp 字幕提取 | FunASR (达摩院) | faster-whisper | StepFun | 豆包 | Whisper API |
|------|:--:|:--:|:--:|--------|------|-------------|
| **价格** | 🟢 免费 | 🟢 免费/本地 | 🟢 免费/本地 | ~0.4 元/h | 付费 | $0.006/min |
| **中文准确度** | — | ⭐⭐⭐ | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **英文准确度** | — | ⭐ | ⭐⭐⭐ | ⭐⭐ | — | ⭐⭐⭐ |
| **速度** | 1 秒 (下载) | ~15× RTF | ~40-60× RTF | ~85-101× | ~15-25× | ~10-20× |
| **时间戳** | ✅ SRT | ✅ word级 | ✅ word级 | ❌ 纯文本 | ✅ SRT | ✅ word级 |
| **VAD** | — | ✅ | ✅ | ❌ | — | ❌ |
| **标点恢复** | — | ✅ | ❌ | ❌ | — | ❌ |
| **本地运行** | — | ✅ | ✅ | ❌ | ❌ | ❌ |
| **安装** | pip install yt-dlp | pip install -r requirements-full.txt | pip install -r requirements-full.txt | API key | API key | API key |

> FunASR 和 faster-whisper 为本地模型，首次运行需下载模型文件（~500MB-2GB），后续直接使用无网络开销。

## 长音频性能

StepFun 在长音频场景表现突出：

| 音频长度 | StepFun 耗时 | vs 旧版 step-asr-1.1 |
|---------|-------------|---------------------|
| 5-15 秒 | ~0.5 秒 | ~2× speedup |
| 1-5 分钟 | ~3.5 秒 | ~4× speedup |
| 10-20 分钟 | ~10.4 秒（17.4 分钟音频） | ~5.3× speedup |

## 场景推荐

### 选 yt-dlp 字幕提取（💰 免费，最优先）

- **任何 YouTube 视频都先试这一步**
- 英文视频自动字幕覆盖率 >95%
- 中文视频自动字幕覆盖率持续提升
- 零成本、零延迟、SRT 原生输出
- pipeline.sh 已内置：有字幕自动跳过 ASR

### 选 FunASR（💰 免费，中文首选）

- 中文音频，需要**免费方案**
- 需要精确时间戳 + 标点恢复
- 可以本地运行，无需网络
- 安装：`pip install -r requirements-full.txt`（首次运行自动下载 ~1GB 模型）

### 选 faster-whisper（💰 免费，英文/多语言）

- 英文音频，需要**免费方案**
- 比原版 whisper 快 4×
- CPU 可跑（比 whisper.cpp 更好用的 Python API）
- 安装：`pip install -r requirements-full.txt`（首次运行自动下载 ~74MB+ 模型）

### 选 StepFun

- 中文音频，需要**极速转写**，可接受 API 成本
- 下游做翻译/摘要（不需要精确时间戳）
- 搭配 `text_to_srt.py` 桥接到字幕管线

### 选豆包

- 中文音频，需要**最高准确度**，可接受 API 成本
- 正式出片场景

### 选 Whisper API

- 非中文音频，可接受 API 成本
- 需要 word-level 时间戳

## 免费引擎安装

```bash
# 一键安装（含 FunASR + faster-whisper）
pip install -r requirements-full.txt

## StepFun 的限制

1. **不输出时间戳**：只有纯文本，这是本项目的 `text_to_srt.py` 存在的原因
2. **30 分钟上限**：超长音频需用 ffmpeg 分片
3. **beta 阶段**：价格和 API 稳定性可能变化
4. **重复幻觉**：高度重复的音频内容可能产生重复输出——需交叉验证
