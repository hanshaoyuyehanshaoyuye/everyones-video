#!/usr/bin/env bash
# batch_pipeline.sh — 批量视频字幕处理
# 用法:
#   bash batch_pipeline.sh videos/ --lang zh --translate
#   bash batch_pipeline.sh videos/ --lang en --translate --dub --burn --parallel 4
#   bash batch_pipeline.sh videos/ --pattern "*.mp4" --dry-run
set -euo pipefail

BATCH_DIR=""
PATTERN="*.mp4"
PARALLEL=2
LANG="zh"
EXTRA_ARGS=()
DRY_RUN=false
FAIL_FAST=false
LOG_DIR=""

while [ $# -gt 0 ]; do
    case "$1" in
        --lang) LANG="$2"; shift 2 ;;
        --pattern) PATTERN="$2"; shift 2 ;;
        --parallel) PARALLEL="$2"; shift 2 ;;
        --dry-run) DRY_RUN=true; shift ;;
        --fail-fast) FAIL_FAST=true; shift ;;
        --log-dir) LOG_DIR="$2"; shift 2 ;;
        --translate|--dub|--burn|--quiet|--diarize|--reflect) EXTRA_ARGS+=("$1"); shift ;;
        --engine|--step) EXTRA_ARGS+=("$1" "$2"); shift 2 ;;
        --help|-h)
            echo "用法: batch_pipeline.sh <目录> [选项]"
            echo ""
            echo "批量处理目录中的视频文件。"
            echo ""
            echo "选项:"
            echo "  --lang zh|en         源语言 (默认: zh)"
            echo "  --pattern GLOB        文件匹配模式 (默认: *.mp4)"
            echo "  --parallel N          并行数 (默认: 2)"
            echo "  --dry-run             仅列出文件，不执行"
            echo "  --fail-fast           首个失败即停止"
            echo "  --log-dir DIR         日志目录 (默认: <目录>/batch_logs/)"
            echo ""
            echo "管线参数 (透传给 pipeline.sh):"
            echo "  --translate --dub --burn --diarize --reflect --engine --quiet --step"
            exit 0
            ;;
        *) BATCH_DIR="$1"; shift ;;
    esac
done

[ -z "$BATCH_DIR" ] && { echo "用法: batch_pipeline.sh <目录> [选项]"; exit 1; }
[ -d "$BATCH_DIR" ] || { echo "错误: 目录不存在: $BATCH_DIR"; exit 1; }

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIPELINE="$PROJECT_DIR/integration/pipeline.sh"
[ -z "$LOG_DIR" ] && LOG_DIR="$BATCH_DIR/batch_logs"
mkdir -p "$LOG_DIR"

# Collect files
mapfile -t FILES < <(find "$BATCH_DIR" -maxdepth 1 -name "$PATTERN" -type f | sort)
if [ ${#FILES[@]} -eq 0 ]; then
    echo "未找到匹配 '$PATTERN' 的视频文件"
    exit 1
fi

echo "═══ 批量字幕处理 ═══"
echo " 目录: $BATCH_DIR"
echo " 匹配: $PATTERN → ${#FILES[@]} 个文件"
echo " 语言: $LANG | 并行: $PARALLEL"
echo " 参数: ${EXTRA_ARGS[*]:-无}"
$DRY_RUN && echo " 模式: DRY RUN"
echo " 日志: $LOG_DIR"
echo ""

if $DRY_RUN; then
    for f in "${FILES[@]}"; do
        echo "  → $(basename "$f")"
    done
    echo ""
    echo "[DRY RUN] 以上 ${#FILES[@]} 个文件将被处理"
    exit 0
fi

# Process files with controlled parallelism
BATCH_START=$(date +%s)
SUCCESS=0
FAILED=0
TOTAL=${#FILES[@]}
FAILED_FILES=()

process_one() {
    local f="$1" idx="$2" log="$LOG_DIR/$(basename "$f").log"
    echo "[$idx/$TOTAL] $(basename "$f") ..."

    if bash "$PIPELINE" "$f" --lang "$LANG" "${EXTRA_ARGS[@]}" >"$log" 2>&1; then
        echo "  ✅ 完成"
        echo "$f" >> "$LOG_DIR/succeeded.txt"
        return 0
    else
        echo "  ❌ 失败 → $log"
        printf '%s\n' "$f" >> "$LOG_DIR/failed.txt"
        return 1
    fi
}

trap 'kill 0; exit 1' INT TERM

# Simple job pool with background processes
running=0
idx=0
for f in "${FILES[@]}"; do
    idx=$((idx + 1))

    # Wait if at capacity
    while [ "$running" -ge "$PARALLEL" ]; do
        wait -n 2>/dev/null || true
        running=$((running - 1))
    done

    process_one "$f" "$idx" &
    running=$((running + 1))

    $FAIL_FAST && wait && break
done

# Wait for remaining jobs
wait

# Collect results
if [ -f "$LOG_DIR/succeeded.txt" ]; then
    SUCCESS=$(wc -l < "$LOG_DIR/succeeded.txt")
else
    SUCCESS=0
fi
if [ -f "$LOG_DIR/failed.txt" ]; then
    mapfile -t FAILED_FILES < "$LOG_DIR/failed.txt"
    FAILED=${#FAILED_FILES[@]}
else
    FAILED=0
fi

BATCH_END=$(date +%s)
DURATION=$((BATCH_END - BATCH_START))

echo ""
echo "═══ 批量完成 ═══"
echo " 成功: $SUCCESS | 失败: $FAILED | 总计: $TOTAL"
echo " 耗时: ${DURATION}s (${PARALLEL} 并行)"
if [ "$FAILED" -gt 0 ]; then
    echo " 失败文件:"
    for f in "${FAILED_FILES[@]}"; do
        echo "   - $f → $LOG_DIR/$f.log"
    done
fi
echo " 日志: $LOG_DIR"
