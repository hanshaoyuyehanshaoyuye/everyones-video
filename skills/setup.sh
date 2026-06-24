#!/usr/bin/env bash
# setup.sh — 依赖安装与检查
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "════════════════════════════════════"
echo " 环境依赖检查 — everyones-video"
echo "════════════════════════════════════"
echo ""

MISSING=0
OK=0

check_cmd() {
    local name="$1" cmd="$2" install_hint="$3"
    if command -v "$cmd" &>/dev/null; then
        echo "  🟢 $name: $(command -v "$cmd")"
        OK=$((OK + 1))
    else
        echo "  🔴 $name: 未安装"
        echo "     安装: $install_hint"
        MISSING=$((MISSING + 1))
    fi
}

check_pip_optional() {
    local name="$1" module="$2" size="$3"
    if python3 -c "import $module" 2>/dev/null; then
        echo "  🟢 $name: 已安装"
        OK=$((OK + 1))
    else
        echo "  ⚪ $name: 未安装 (可选)"
        echo "     pip install $module → 首次运行下载 $size"
    fi
}

check_pip() {
    local name="$1" module="$2"
    if python3 -c "import $module" 2>/dev/null; then
        echo "  🟢 $name: 已安装"
        OK=$((OK + 1))
    else
        echo "  🟡 $name: pip install $module"
        MISSING=$((MISSING + 1))
    fi
}

check_file() {
    local name="$1" path="$2" install_hint="$3"
    if [ -f "$path" ]; then
        echo "  🟢 $name: 已安装"
        OK=$((OK + 1))
    else
        echo "  🟡 $name: 未找到"
        echo "     提示: $install_hint"
        MISSING=$((MISSING + 1))
    fi
}

echo "── 轻量核心 ──"
check_cmd "python3" python3 "winget install python3"
check_cmd "ffmpeg" ffmpeg "winget install ffmpeg"
check_cmd "yt-dlp" yt-dlp "pip install yt-dlp"
check_pip "Edge-TTS (配音)" edge_tts
echo ""

echo "── 项目自带脚本 ──"
check_file "pipeline.sh" "$PROJECT_DIR/integration/pipeline.sh" "项目需完整 clone"
check_file "translate_srt.py" "$PROJECT_DIR/integration/translate_srt.py" "项目需完整 clone"
check_file "text_to_srt.py" "$PROJECT_DIR/integration/text_to_srt.py" "项目需完整 clone"
check_file "funasr_run.py" "$PROJECT_DIR/integration/funasr_run.py" "项目需完整 clone"
check_file "faster_whisper_run.py" "$PROJECT_DIR/integration/faster_whisper_run.py" "项目需完整 clone"
check_file "tts_dub.py" "$PROJECT_DIR/integration/tts_dub.py" "项目需完整 clone"
check_file "eval_quality.py" "$PROJECT_DIR/integration/eval_quality.py" "项目需完整 clone"
check_file "batch_pipeline.sh" "$PROJECT_DIR/integration/batch_pipeline.sh" "项目需完整 clone"
echo ""

echo "── 项目自带技能 ──"
check_file "wjs-transcribing-audio" "$PROJECT_DIR/skills/wjs-transcribing-audio/SKILL.md" "git clone 本仓库"
check_file "wjs-translating-subtitles" "$PROJECT_DIR/skills/wjs-translating-subtitles/SKILL.md" "git clone 本仓库"
check_file "wjs-dubbing-video" "$PROJECT_DIR/skills/wjs-dubbing-video/SKILL.md" "git clone 本仓库"
check_file "wjs-burning-subtitles" "$PROJECT_DIR/skills/wjs-burning-subtitles/SKILL.md" "git clone 本仓库"
echo ""

echo "── API 密钥 ──"
if [ -n "${DEEPSEEK_API_KEY:-}" ]; then
    echo "  🟢 DEEPSEEK_API_KEY: 已设置 (translate_srt.py)"
    OK=$((OK + 1))
else
    echo "  🟡 DEEPSEEK_API_KEY: 未设置 (https://platform.deepseek.com)"
    MISSING=$((MISSING + 1))
fi
if [ -n "${STEPFUN_API_KEY:-}" ]; then
    echo "  🟢 STEPFUN_API_KEY: 已设置"
    OK=$((OK + 1))
else
    echo "  🟡 STEPFUN_API_KEY: 未设置 (https://platform.stepfun.com)"
    MISSING=$((MISSING + 1))
fi
echo ""

echo "── 可选: 本地离线 ASR（按需安装，轻量核心用户跳过）──"
check_pip_optional "FunASR (中文)" funasr "~1GB"
check_pip_optional "faster-whisper (英文)" faster_whisper "~74MB-1.5GB"
echo ""

echo "════════════════════════════════════"
if [ "$MISSING" -eq 0 ]; then
    echo " ✅ 所有依赖就绪 ($OK/$((OK+MISSING)))"
else
    echo " ⚠ $MISSING 项缺失, $OK 项就绪"
    echo ""
    echo "安装缺失依赖后重新运行: bash skills/setup.sh"
fi

exit 0
