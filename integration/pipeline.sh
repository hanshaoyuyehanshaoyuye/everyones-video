#!/usr/bin/env bash
# pipeline.sh — 视频字幕全管线一键脚本
# 用法:
#   bash pipeline.sh "https://youtube.com/watch?v=VIDEO_ID"       # YouTube → 中文字幕
#   bash pipeline.sh ~/audio.mp3                                   # 本地音频 → 字幕
#   bash pipeline.sh ~/audio.mp3 --lang en                         # 英文
#   bash pipeline.sh ~/audio.mp3 --lang zh --translate --burn      # 翻译+烧录
#   bash pipeline.sh ~/audio.mp3 --engine funasr                   # 指定免费引擎
#   bash pipeline.sh ~/audio.mp3 --step 2                          # 从第2步开始
# 引擎选择:
#   --engine auto            自动选择 (默认): 中文→FunASR, 英文→faster-whisper
#   --engine funasr          阿里达摩院 FunASR (免费本地, 中文最佳)
#   --engine faster-whisper  faster-whisper (免费本地, 英文最佳)
#   --engine stepfun         StepFun API (付费, 极速, 需 STEPFUN_API_KEY)
set -euo pipefail

# ── 配置 ──
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
WORK_DIR="${PIPELINE_WORK_DIR:-$HOME/.subtitle_pipeline_work}"
SRT_CONVERTER="$PROJECT_DIR/integration/text_to_srt.py"
TRANSLATE_SCRIPT="$PROJECT_DIR/integration/translate_srt.py"
FUNASR_SCRIPT="$PROJECT_DIR/integration/funasr_run.py"
FWHISPER_SCRIPT="$PROJECT_DIR/integration/faster_whisper_run.py"
TTS_DUB_SCRIPT="$PROJECT_DIR/integration/tts_dub.py"
REFLECT_SCRIPT="$PROJECT_DIR/integration/reflect_fix.py"
STATE_FILE="$WORK_DIR/.pipeline_step"

LANG="zh"
ASR_ENGINE="auto"
DO_TRANSLATE=false
DO_DUB=false
DO_BURN=false
DO_DIARIZE=false
DO_REFLECT=false
START_STEP=1
RESUME=false
DRY_RUN=false
VERBOSE=true
INPUT=""

# ── 解析参数 ──
while [ $# -gt 0 ]; do
    case "$1" in
        --lang) LANG="$2"; shift 2 ;;
        --engine) ASR_ENGINE="$2"; shift 2 ;;
        --translate) DO_TRANSLATE=true; shift ;;
        --dub) DO_DUB=true; shift ;;
        --diarize) DO_DIARIZE=true; shift ;;
        --reflect) DO_REFLECT=true; shift ;;
        --burn) DO_BURN=true; shift ;;
        --step) START_STEP="$2"; shift 2 ;;
        --resume) RESUME=true; shift ;;
        --dry-run) DRY_RUN=true; shift ;;
        --quiet) VERBOSE=false; shift ;;
        --help|-h)
            echo "用法: pipeline.sh <YouTube URL | 音频文件> [选项]"
            echo ""
            echo "选项:"
            echo "  --lang zh|en        源语言 (默认: zh)"
            echo "  --engine auto|funasr|faster-whisper|stepfun"
            echo "                      ASR 引擎 (默认: auto)"
            echo "  --translate          翻译为目标语言"
            echo "  --dub                TTS 配音 (Edge-TTS 免费)"
            echo "  --diarize            说话人分离 (FunASR cam++ / faster-whisper WhisperX)"
            echo "  --reflect            翻译反思修复 (GEMBA-MQM, 自动改进)"
            echo "  --burn               烧录字幕到视频"
            echo "  --step N             从第N步开始 (1-6)"
            echo ""
            echo "管线步骤:"
            echo "  Step 1: 音频提取 + YouTube字幕检查"
            echo "  Step 2: ASR 转写 (免费引擎优先)"
            echo "  Step 3: 文本 → SRT"
            echo "  Step 4: 翻译字幕 (--translate)"
            echo "  Step 5: TTS 配音 (--dub, 需先 --translate)"
            echo "  Step 6: 烧录字幕+配音 → 成品视频 (--burn)"
            echo "  --resume             从上次失败处继续"
            echo "  --dry-run            仅预览步骤，不执行"
            echo "  --quiet              减少输出"
            echo "  --help               显示帮助"
            exit 0
            ;;
        *) INPUT="$1"; shift ;;
    esac
done

# ── 断点续跑 ──
if $RESUME && [ -f "$STATE_FILE" ]; then
    saved=$(cat "$STATE_FILE")
    if echo "$saved" | grep -q '^[1-6]$'; then
        START_STEP="$saved"
        echo "↻ 从第 $START_STEP 步继续..."
    else
        echo "↻ 状态文件损坏，从第1步开始"
    fi
fi

save_state() { echo "$1" > "$STATE_FILE"; }

[ -z "$INPUT" ] && { echo "用法: pipeline.sh <YouTube URL | 音频文件>"; exit 1; }

mkdir -p "$WORK_DIR"

# ── Step 1: 下载音频 + 字幕提取 ──
audio_file="$WORK_DIR/audio.mp3"
srt_file="$WORK_DIR/subtitles.srt"
video_file="$WORK_DIR/video.mp4"

step1() {
    echo "═══ Step 1: 提取音频 + 字幕检查 ═══"

    if [[ "$INPUT" =~ ^https?:// ]]; then
        echo "  下载: $INPUT"

        # 先尝试下载已有的自动字幕 (免费！零延迟！)
        echo "  → 检查 YouTube 自动字幕..."
        yt-dlp --write-auto-subs --sub-lang "$LANG,en,zh-Hans,zh" \
            --skip-download --convert-subs srt \
            -o "$WORK_DIR/%(title)s.%(ext)s" "$INPUT" 2>"$WORK_DIR/yt_subs.log" || true

        # 找下载的字幕文件 (separate declaration from assignment for set -e)
        local found_sub
        found_sub=$(ls -t "$WORK_DIR"/*.srt 2>/dev/null | head -1 || true)
        if [ -n "$found_sub" ] && [ -s "$found_sub" ]; then
            cp "$found_sub" "$srt_file"
            echo "  🎯 找到已有字幕！跳过 ASR (省时省钱)"
            local cues
            cues=$(grep -c '-->' "$srt_file" 2>/dev/null || echo 0)
            echo "  → $srt_file ($cues 条字幕)"

            # 如果后续需要烧录，下载视频本体
            if $DO_BURN; then
                echo "  → 下载视频 (后续烧录需要)..."
                yt-dlp -f "best[height<=1080]" \
                    -o "$video_file" "$INPUT" 2>"$WORK_DIR/yt_video.log"
                echo "  → $video_file ($(du -h "$video_file" | cut -f1))"
            fi
            return 0
        fi
        echo "  → 无可用字幕，下载音频做 ASR..."
        $VERBOSE && {
            echo "  → yt-dlp 字幕日志 (最后 5 行):"
            tail -5 "$WORK_DIR/yt_subs.log" 2>/dev/null | sed 's/^/     /' || true
        }

        # 下载音频
        yt-dlp -x --audio-format mp3 --audio-quality 0 \
            -o "$WORK_DIR/audio.%(ext)s" "$INPUT" 2>"$WORK_DIR/yt_audio.log"
        local downloaded
        downloaded=$(ls -t "$WORK_DIR"/audio.* 2>/dev/null | head -1 || true)
        if [ -f "$downloaded" ] && [ "$downloaded" != "$audio_file" ]; then
            ffmpeg -i "$downloaded" -codec:a libmp3lame -qscale:a 2 "$audio_file" -y \
                2>"$WORK_DIR/ffmpeg_step1.log"
        fi

        # 如果后续需要烧录，也下载视频
        if $DO_BURN; then
            echo "  → 下载视频 (后续烧录需要)..."
            yt-dlp -f "best[height<=1080]" \
                -o "$video_file" "$INPUT" 2>"$WORK_DIR/yt_video.log"
            echo "  → $video_file ($(du -h "$video_file" | cut -f1))"
        fi
    else
        # 本地文件，转 mp3
        if [[ "$INPUT" == *.mp3 ]]; then
            cp "$INPUT" "$audio_file"
        else
            ffmpeg -i "$INPUT" -codec:a libmp3lame -qscale:a 2 "$audio_file" -y \
                2>"$WORK_DIR/ffmpeg_step1.log"
        fi
    fi
    echo "  → $audio_file ($(du -h "$audio_file" | cut -f1))"
}

# ── Step 2: ASR 转写 (免费引擎优先!) ──
transcript_file="$WORK_DIR/transcript.txt"

step2() {
    # 如果字幕已从 YouTube 获取，跳过 ASR
    if [ -f "$srt_file" ] && [ -s "$srt_file" ]; then
        echo "═══ Step 2: ASR 转写 — 跳过 (已有字幕) ═══"
        return 0
    fi

    echo "═══ Step 2: ASR 转写 ═══"

    # 决定使用哪个引擎
    local engine="$ASR_ENGINE"
    if [ "$engine" = "auto" ]; then
        if [ "$LANG" = "en" ]; then
            engine="faster-whisper"
        else
            engine="funasr"
        fi
        echo "  → 自动选择: $engine"
    fi

    case "$engine" in
        funasr)
            echo "  → 引擎: FunASR (免费本地, 阿里达摩院)"
            if python3 -c "import funasr" 2>/dev/null; then
                if $DO_DIARIZE; then
                    python3 "$FUNASR_SCRIPT" "$audio_file" --lang "$LANG" --diarize -o "$transcript_file"
                else
                    python3 "$FUNASR_SCRIPT" "$audio_file" --lang "$LANG" -o "$transcript_file"
                fi
            else
                echo "  ⚠ FunASR 未安装。安装: pip install funasr"
                echo "  ⚠ 降级尝试 StepFun..."
                engine="stepfun"
            fi
            ;;
        faster-whisper)
            echo "  → 引擎: faster-whisper (免费本地, CTranslate2)"
            if python3 -c "import faster_whisper" 2>/dev/null; then
                if $DO_DIARIZE; then
                    echo "  → 说话人分离: WhisperX + pyannote"
                    python3 "$FWHISPER_SCRIPT" "$audio_file" --lang "$LANG" --diarize --srt -o "$srt_file"
                else
                    python3 "$FWHISPER_SCRIPT" "$audio_file" --lang "$LANG" -o "$transcript_file"
                fi
            else
                echo "  ⚠ faster-whisper 未安装。安装: pip install faster-whisper"
                echo "  ⚠ 降级尝试 StepFun..."
                engine="stepfun"
            fi
            ;;
        stepfun)
            echo "  → 引擎: StepFun (付费 API, ~0.4元/h)"
            local stepfun_script="${STEPFUN_ASR_PATH:-$HOME/.claude/skills/stepfun-asr/scripts/asr_transcribe.py}"
            if [ -z "${STEPFUN_API_KEY:-}" ]; then
                echo "  ✗ STEPFUN_API_KEY 未设置"
                echo "  设置后重试: export STEPFUN_API_KEY=sk-..."
                echo "  或换免费引擎: --engine funasr (中文) / --engine faster-whisper (英文)"
                exit 1
            fi
            if [ -f "$stepfun_script" ]; then
                python3 "$stepfun_script" "$audio_file" > "$transcript_file"
            else
                echo "  ✗ stepfun-asr 未安装，且无免费引擎可用"
                echo "  安装免费引擎: pip install funasr (中文) 或 pip install faster-whisper (英文)"
                exit 1
            fi
            ;;
        *)
            echo "  ✗ 未知引擎: $engine (可选: auto/funasr/faster-whisper/stepfun)"
            exit 1
            ;;
    esac

    if [ ! -s "$transcript_file" ]; then
        echo "  ✗ 转写失败"
        if [ "$engine" = "stepfun" ]; then
            echo "  建议: pip install funasr && bash pipeline.sh \"$INPUT\" --engine funasr"
        fi
        exit 1
    fi
    echo "  → $(wc -c < "$transcript_file") 字节"
}

# ── Step 3: 文本 → SRT ──
step3() {
    # 已有 SRT (来自 YouTube 字幕) 则跳过
    if [ -f "$srt_file" ] && [ -s "$srt_file" ]; then
        echo "═══ Step 3: 文本 → SRT — 跳过 (已有 SRT) ═══"
        local cues
        cues=$(grep -c '-->' "$srt_file" 2>/dev/null || echo 0)
        echo "  → $cues 条字幕"
        return 0
    fi

    echo "═══ Step 3: 文本 → SRT ═══"
    [ -f "$transcript_file" ] && [ -s "$transcript_file" ] || {
        echo "  ✗ 无转录文本"; exit 1;
    }
    python3 "$SRT_CONVERTER" "$transcript_file" --lang "$LANG" -o "$srt_file"
    local cues
    cues=$(grep -c '-->' "$srt_file" 2>/dev/null || echo 0)
    echo "  → $cues 条字幕"
}

# ── Step 4: 翻译 (可选) ──
translated_srt="$WORK_DIR/subtitles_translated.srt"

step4_translate() {
    echo "═══ Step 4: 翻译字幕 ═══"
    # 目标语言：zh→en, en→zh-CN, 其他→zh-CN
    local target="zh-CN"
    [ "$LANG" = "zh" ] && target="en"
    [ "$LANG" = "en" ] && target="zh-CN"

    if [ ! -f "$TRANSLATE_SCRIPT" ]; then
        echo "  ⚠ translate_srt.py 未找到，跳过"
        echo "  手动: python3 integration/translate_srt.py $srt_file --to $target"
        return
    fi

    # 优先 DeepSeek API，失败回退 Ollama
    if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
        python3 "$TRANSLATE_SCRIPT" "$srt_file" --to "$target" --bilingual -o "$translated_srt"
    elif [ -n "${OLLAMA_HOST:-}" ] || curl -s "http://127.0.0.1:11434" >/dev/null 2>&1; then
        echo "  → DeepSeek key 未设置，尝试 Ollama 本地翻译..."
        python3 "$TRANSLATE_SCRIPT" "$srt_file" --to "$target" --bilingual -o "$translated_srt"
    else
        echo "  ✗ 翻译需要 DEEPSEEK_API_KEY 或本地 Ollama"
        echo "  安装 Ollama: curl -fsSL https://ollama.com/install.sh | sh"
        exit 1
    fi
    echo "  → $translated_srt"
}

# ── Step 4b: 翻译反思修复 (可选) ──
step4_reflect() {
    echo "═══ Step 4b: 翻译反思修复 ═══"

    if [ ! -f "$REFLECT_SCRIPT" ]; then
        echo "  ⚠ reflect_fix.py 未找到，跳过"
        return
    fi
    if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
        echo "  ⚠ 反思修复需要 DEEPSEEK_API_KEY，跳过"
        return
    fi

    local target="zh-CN"
    [ "$LANG" = "zh" ] && target="en"
    [ "$LANG" = "en" ] && target="zh-CN"

    echo "  → 引擎: GEMBA-MQM + LLM 修复"
    echo "  → 最多 3 轮，修复 major 及以上错误"
    python3 "$REFLECT_SCRIPT" "$srt_file" "$translated_srt" \
        --from "$LANG" --to "$target" --max-rounds 3 \
        -o "$translated_srt"  # overwrite with fixed version
    echo "  → $translated_srt"
}

# ── Step 5: TTS 配音 (可选) ──
dub_audio="$WORK_DIR/dub.mp3"

step4_dub() {
    echo "═══ Step 5: TTS 配音 ═══"
    local srt_to_dub="${translated_srt:-$srt_file}"

    if [ ! -f "$TTS_DUB_SCRIPT" ]; then
        echo "  ⚠ tts_dub.py 未找到，跳过"
        return
    fi

    # Determine target language for TTS
    local tts_lang="zh-CN"
    [ "$LANG" = "en" ] && tts_lang="en"
    [ "$LANG" = "zh" ] && tts_lang="zh-CN"

    # Check edge-tts availability
    if ! python3 -c "import edge_tts" 2>/dev/null; then
        echo "  ⚠ edge-tts 未安装。安装: pip install edge-tts"
        echo "  跳过配音步骤"
        return
    fi

    echo "  → 引擎: Edge-TTS (免费)"
    echo "  → 语言: $tts_lang"
    python3 "$TTS_DUB_SCRIPT" "$srt_to_dub" --lang "$tts_lang" -o "$dub_audio"
    echo "  → $dub_audio"
}

# ── Step 6: 烧录 (可选) ──
step5_burn() {
    echo "═══ Step 6: 烧录字幕 ═══"
    local srt_to_burn="${translated_srt:-$srt_file}"
    local render_py="$PROJECT_DIR/skills/wjs-burning-subtitles/scripts/render.py"

    # 确定视频源: 本地文件 > 已下载的 YouTube 视频 > 错误
    local video_src="$INPUT"
    if [[ "$INPUT" =~ ^https?:// ]]; then
        if [ -f "$video_file" ] && [ -s "$video_file" ]; then
            video_src="$video_file"
            echo "  → 使用已下载的视频: $video_src"
        else
            echo "  → 下载视频用于烧录..."
            yt-dlp -f "best[height<=1080]" \
                -o "$video_file" "$INPUT" 2>"$WORK_DIR/yt_burn.log"
            video_src="$video_file"
            echo "  → $video_src ($(du -h "$video_src" | cut -f1))"
        fi
    fi
    if [ ! -f "$video_src" ]; then
        echo "  ✗ 视频文件不存在: $video_src"
        echo "  提示: 先用 yt-dlp 下载视频，或提供本地视频文件"
        return 1
    fi

    if [ -f "$render_py" ] && [ -f "$srt_to_burn" ]; then
        local out_mp4="${video_src%.*}_subtitled.mp4"
        local render_args=(--video "$video_src" --srt "$srt_to_burn" --out "$out_mp4")
        # Include dub audio if available
        if [ -f "$dub_audio" ] && [ -s "$dub_audio" ]; then
            render_args+=(--dub "$dub_audio")
            echo "  → 配音: $dub_audio"
        fi
        python3 "$render_py" "${render_args[@]}"
        echo "  → $out_mp4"
    else
        echo "  ⚠ 缺少依赖: render.py 或 SRT 文件"
        echo "  手动: python3 skills/wjs-burning-subtitles/scripts/render.py"
        echo "        --video <视频> --srt <字幕> --out <输出>"
        return 1
    fi
}

# ── 执行 ──
$VERBOSE && {
    echo "════════════════════════════════════"
    echo " 视频字幕管线"
    echo " 输入: ${INPUT:0:60}..."
    echo " 语言: $LANG | ASR: $ASR_ENGINE"
    echo " 翻译: $DO_TRANSLATE | 反思: $DO_REFLECT | 配音: $DO_DUB | 说话人: $DO_DIARIZE | 烧录: $DO_BURN"
    echo "════════════════════════════════════"
    echo ""
}

if $DRY_RUN; then
    echo "[DRY RUN] 将执行以下步骤:"
    [ "$START_STEP" -le 1 ] && echo "  Step 1: 音频提取 + 字幕检查"
    [ "$START_STEP" -le 2 ] && echo "  Step 2: ASR 转写 (引擎: $ASR_ENGINE)"
    [ "$START_STEP" -le 3 ] && echo "  Step 3: 文本 → SRT"
    $DO_TRANSLATE && echo "  Step 4: 翻译字幕"
    $DO_REFLECT && echo "  Step 4b: 翻译反思修复 (GEMBA-MQM)"
    $DO_DUB && echo "  Step 5: TTS 配音 (Edge-TTS)"
    $DO_BURN && echo "  Step 6: 烧录字幕 → 成品视频"
    echo ""
    echo "[DRY RUN] 推荐引擎:"
    python3 "$PROJECT_DIR/integration/eval.py" recommend --lang "$LANG" 2>/dev/null || true
    exit 0
fi

# Record eval after each step
_eval_record() {
    local engine="$1" step="$2" duration="$3" cues="${4:-0}"
    python3 "$PROJECT_DIR/integration/eval.py" record \
        --engine "$engine" --lang "$LANG" --duration "$duration" \
        --source "pipeline_step${step}" --cues "$cues" 2>/dev/null || true
}

_step1_start=$(date +%s)
[ "$START_STEP" -le 1 ] && { step1; save_state 2; }
_step1_end=$(date +%s)
_step1_dur=$((_step1_end - _step1_start))

_step2_start=$(date +%s)
_had_subs_before_step2=false
[ -f "$srt_file" ] && [ -s "$srt_file" ] && _had_subs_before_step2=true
[ "$START_STEP" -le 2 ] && { step2; save_state 3; }
_step2_end=$(date +%s)
_step2_dur=$((_step2_end - _step2_start))
# Record ASR eval — use yt-dlp_subtitles if YouTube subs were found, else the chosen engine
_cues=$(grep -c '-->' "$srt_file" 2>/dev/null || echo 0)
if $_had_subs_before_step2; then
    _eval_record "yt-dlp_subtitles" "2-ASR" "$_step2_dur" "$_cues"
else
    _eval_record "$ASR_ENGINE" "2-ASR" "$_step2_dur" "$_cues"
fi

_step3_start=$(date +%s)
[ "$START_STEP" -le 3 ] && { step3; save_state 4; }
_step3_end=$(date +%s)

if [ "$DO_TRANSLATE" = true ]; then
    step4_translate; save_state 5
fi

if [ "$DO_REFLECT" = true ] && [ "$DO_TRANSLATE" = true ]; then
    step4_reflect; save_state 6
fi

if [ "$DO_DUB" = true ]; then
    step4_dub; save_state 6
fi

if [ "$DO_BURN" = true ]; then
    step5_burn; save_state done
fi

rm -f "$STATE_FILE"

$VERBOSE && {
    echo ""
    echo "════════════════════════════════════"
    echo " 完成！"
    echo " 音频: $audio_file"
    echo " 文本: $transcript_file"
    echo " SRT:  $srt_file"
    [ "$DO_TRANSLATE" = true ] && echo " 翻译: $translated_srt"
    [ "$DO_DUB" = true ] && echo " 配音: $dub_audio"
    [ "$DO_BURN" = true ] && echo " 成品: ${INPUT%.*}_subtitled.mp4"
    echo "════════════════════════════════════"
}
