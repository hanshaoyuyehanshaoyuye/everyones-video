# Changelog

All notable changes to Everyones Video will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [6.2.0] — Unreleased

### Security
- **realtime_server.py 加固**: 体大小限制 (100KB→413)、费率限制 (/translate 100/min, /batch 20/min)、文本长度限制 (500/200chars)、语言码白名单、安全头。

### Added
- **多语种实时翻译**: 日🇯🇵 韩🇰🇷 俄🇷🇺 德🇩🇪 法🇫🇷 西🇪🇸 葡🇧🇷 阿🇸🇦, 12 语种互通。
  - `popup.html/js`: 源语言选择 + "自动检测", 源/目标语言冲突提示。
  - `content.js`: Unicode 范围自动检测 (CJK/Hangul/Kana/Cyrillic/Arabic/Latin), 采样前 5 条字幕。
  - `realtime_server.py --detect-lang`: 服务端语言检测端点, 置信度评分。
  - LLM prompt 语言无关化: 自动适配任意语言对的长度/风格约束。

### Changed
- Extension 不再硬编码源语言 (之前 YouTube=en, Bilibili=zh), 全面切换为 auto。
- `/detect-lang` POST endpoint: 接收字幕文本数组, 返回 `{lang, confidence}`。

## [6.1.0] — Unreleased

### Changed
- **Extension 多平台支持**: 不再只限 YouTube。
  - `content.js`: 平台检测层 + 4 种字幕源适配器。
  - **YouTube**: timedtext XML 拦截 (原有)。
  - **Bilibili**: player.getCaptions() API + subtitle API 代理。
  - **&lt;track&gt; WebVTT**: 任意 `<video>` + `<track kind="subtitles">` 自动拉取 WebVTT (Vimeo/Coursera/…)。
  - **通用 fetch**: 拦截所有 XHR/fetch 中 SRT/VTT/JSON 字幕响应, 兜底未知平台。
  - `manifest.json`: host_permissions 放宽到 `https://*/*`。
- JSON 字幕解析: 支持 5 种常见格式 (YouTube JSON / Bilibili body / WebVTT / SRT / word-level)。

## [6.0.0] — Unreleased

### Added
- **Chrome Extension** (`extension/`): YouTube 实时双语字幕, MIT 开源, 零下载零等待。
  - `content.js`: 三阶段 — 拦截 YouTube timedtext API → 解析 XML 预翻译 → rAF 轮询播放时间匹配 cue → DOM 叠加双语字幕。
  - `popup.html/js`: 开关 / 11 语种切换 / 服务器状态指示。
  - `overlay.css`: 半透明黑底金字叠加层, 不干扰视频控制。
- **realtime_server.py**: 极简 HTTP 后端 (127.0.0.1:8739)。
  - `POST /translate`: 单条翻译, TM 命中 <1ms, LLM 回退 ~300ms。
  - `POST /translate/batch`: 批量预翻译, 拦截 timedtext 后一次性送译。
  - 复用现有 TM + call_llm, 无额外依赖。
  - TM 自动落盘, 同视频复看 100% 缓存命中。

## [5.2.0] — Unreleased

### Added
- **Translation Memory (TM)**: `integration/tm.py` — JSON-based translation memory, zero extra dependencies.
  - Exact match: reuses cached translations, saves API calls.
  - Fuzzy match: difflib.SequenceMatcher ≥80% threshold, includes best matches as few-shot examples in LLM prompt.
  - Auto-stores new translations after each batch.
  - CLI: `python integration/tm.py stats|export|import|clear`.
- `translate_srt.py --tm-path` / `--no-tm` flags: control TM behavior.
- `translate_srt.py` batch flow: pre-filters exact TM hits before LLM call, reports cache hit count.
- **Docker ghcr.io push**: CI auto-builds + pushes to `ghcr.io/hanshaoyuyehanshaoyuye/everyones-video` on main push.

### Changed
- `Dockerfile`: added edge-tts, WhisperX opt-in build arg, TM volume, HF_TOKEN env.
- `docker-compose.yml`: added TM volume mount, HF_TOKEN passthrough.

## [5.1.0] — Unreleased

### Added
- **faster-whisper speaker diarization**: `faster_whisper_run.py --diarize` via WhisperX + pyannote.audio. English multi-speaker scenarios now have speaker-labeled SRT output.
- `faster_whisper_run.py --hf-token`: HuggingFace token for pyannote model access.
- `pipeline.sh --diarize` now works with `--engine faster-whisper` (was FunASR-only).

### Changed
- `requirements-full.txt`: added `whisperx>=3.1.1` for diarization.
- `docs/ASR_COMPARISON.md`: updated comparison table with speaker diarization row.

## [5.0.0] — Unreleased

### Added
- **Speaker diarization**: `funasr_run.py --diarize` + `pipeline.sh --diarize` (FunASR cam++ model). Multi-speaker scenarios now separate who said what.
- **Translation reflection loop**: `reflect_fix.py` — GEMBA-MQM evaluate → LLM fix bad cues → re-evaluate. `pipeline.sh --reflect` flag.
- `integration/reflect_fix.py`: automatic translation quality repair (max 3 rounds, threshold configurable).

### Changed
- `plugin.json`: v4.0.0 → v5.0.0
- Pipeline banner reflects all active flags (diarize, reflect)
- README comparison table: speaker diarization ✅, added VideoLingo column

## [4.0.0] — 2026-06-24

### Added
- `integration/tts_dub.py`: SRT → TTS dubbing audio via Edge-TTS (free, 100+ languages, neural quality).
- `pipeline.sh --dub` flag: generate dubbed audio from translated SRT, auto-fed to `render.py --dub`.
- `wjs-dubbing-video` skill: Claude Code TTS dubbing with Edge-TTS backend.
- `integration/batch_pipeline.sh`: batch processing for content teams with parallelism and logging.
- `integration/eval_quality.py`: GEMBA-MQM translation quality scoring via LLM.
- `smoke_test.sh`: environment verification and core module sanity check.
- `SECURITY.md` / `CODE_OF_CONDUCT.md` / `SUPPORT.md`: community health files.

### Changed
- **Dependency split**: `requirements.txt` (lightweight, ~20MB, no model downloads) + `requirements-full.txt` (adds FunASR ~1GB + faster-whisper ~74MB+ for offline ASR). 80% users only need core.
- README: competitive comparison table, batch+quality usage, 10 scenarios, two-tier install guide.
- `skills/setup.sh`: core vs optional tiers, heavy ASR deps no longer count as missing.
- `plugin.json`: v3.0.0→v4.0.0, 3 skills→4, keywords added (dubbing/tts/batch/quality).
- `CONTRIBUTING.md`: updated to use requirements.txt and smoke_test.sh.

## [3.0.0] — 2026-06-24

### Added
- `funasr_run.py`: Free Chinese ASR via Alibaba FunASR (local, ~1GB model).
- `faster_whisper_run.py`: Free English ASR via faster-whisper CTranslate2 (local).
- `text_to_srt.py`: Renamed from `stepfun_to_srt.py` — generic text→SRT converter.
- `pipeline.sh --engine auto|funasr|faster-whisper|stepfun` flag for ASR engine selection.
- `translate_srt.py --engine auto|deepseek|ollama` flag for translation backend selection.
- Ollama local translation fallback: when `DEEPSEEK_API_KEY` is absent, auto-detects local Ollama.
- `pipeline.sh --burn` now auto-downloads video for YouTube URL inputs.
- `.dockerignore`: excludes `.git/`, `__pycache__/`, media files from Docker build context.
- GitHub Actions CI: pytest matrix (3.10/3.11/3.12) + shellcheck + docker build.

### Changed
- `render.py`: SHA256 verification for evermeet.cx ffmpeg download; retry with exponential backoff.
- `translate_srt.py` API Server: token masked in console, CORS restricted to localhost, 10MB body limit, rate-map periodic cleanup, `secrets.compare_digest` for token comparison, server refuses to start without `DEEPSEEK_API_KEY`.
- `Dockerfile`: removed broken `STEPFUN_ASR_PATH`, added non-root `pipeline` user.
- `docker-compose.yml`: `api` port binds 127.0.0.1, requires `DEEPSEEK_API_KEY`+`TRANSLATE_API_TOKEN`, separate work dirs for pipeline/api.
- `README.md`: install methods reordered — git clone promoted to #1, ClawHub/marketplace tagged `[即将上线]`.
- `SKILL.md`: updated description to reflect free-first engine routing.
- `plugin.json`: version 2.1.0 → 3.0.0, description updated.
- `stepfun_to_srt.py`: now a thin wrapper importing from `text_to_srt.py` (backward compatible).
- `pipeline.sh`: stderr logging to `*.log` files instead of `/dev/null` suppression; `local`+command-substitution trap fixed; `STATE_FILE` content validated.

### Fixed
- Supply-chain: `render.py` no longer executes unsigned binary from evermeet.cx without warning.
- `pipeline.sh --burn` + YouTube URL now works (auto-downloads video).
- `pipeline.sh` Step 2 no longer crashes when FunASR/faster-whisper is the only engine installed.
- `translate_srt.py` API Server: token leak, DoS via body size, memory leak via rate-map.

## [2.1.0] — 2026-06-23

### Added
- Claude Code community skill packaging: `.claude-plugin/plugin.json` + `SKILL.md`.
- `CONTRIBUTING.md` with contribution guidelines.

## [2.0.0] — 2026-06-23

### Added
- Standalone `translate_srt.py`: independent SRT translation (no Claude Code dependency).
- `pipeline.sh` local-first pipeline orchestrator.
- Docker support: multi-stage `Dockerfile` + `docker-compose.yml`.
- REST API server: `translate_srt.py --server` with token auth and rate limiting.
- `integration/eval.py`: workflow evaluation with engine recording and recommendation.
- 5 new workflow scenarios: podcast transcript, live clip, multi-language, offline-only, quick start.
- `examples/`: demo SRT files (Chinese + English).
- `workflow_eval.json`: engine evaluation database.
- `SKILL.md` path alignment for Claude Code auto-discovery.

### Fixed
- Hardcoded `--to zh-CN` in pipeline: replaced with dynamic target from `--lang`.
- Burn URL guard: added detection for URL inputs with clear error message.
- Debug residue: removed all `print("DEBUG"` and `FIXME` markers.
- HTTP error handling: 3 retries with exponential backoff for API calls.
- Missing `scripts/` directory: skills subdirectories verified.

## [1.0.0] — 2026-06-22

### Added
- Initial release: Claude Code video subtitle pipeline.
- Three bundled skills: `wjs-transcribing-audio`, `wjs-translating-subtitles`, `wjs-burning-subtitles`.
- `stepfun_to_srt.py`: StepFun plain-text to SRT converter.
- `skills/setup.sh`: environment check script.
- P0-P3 security fixes (18 items): API auth, rate limiting, Docker security, path env-varization, Ollama local fallback, multi-stage build, `--resume` flag.
- 17 test cases (`tests/test_core.py`).
- Documentation: `README.md`, `docs/ARCHITECTURE.md`, `docs/ASR_COMPARISON.md`, `docs/OPTIMIZATION.md`, `docs/WORKFLOWS.md`.

### Fixed
- 5 bugs from guard-deep review: hardcoded target language, burn URL detection, debug residue, HTTP error handling, missing scripts directory.
