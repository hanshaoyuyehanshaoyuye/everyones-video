#!/usr/bin/env bash
# smoke_test.sh — 冒烟测试：验证管线核心模块可用
# 用法: bash smoke_test.sh
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASS=0
FAIL=0
TOTAL=0

pass() { echo "  ✅ $1"; PASS=$((PASS + 1)); TOTAL=$((TOTAL + 1)); }
fail() { echo "  ❌ $1: $2"; FAIL=$((FAIL + 1)); TOTAL=$((TOTAL + 1)); }
skip() { echo "  ⚠ $1: $2 (跳过)"; TOTAL=$((TOTAL + 1)); }

echo "═══ 冒烟测试 — everyones-video ═══"
echo ""

echo "── Python 模块 ──"
for mod in translate_srt text_to_srt eval eval_quality tts_dub funasr_run faster_whisper_run; do
    if python3 -c "
import sys; sys.path.insert(0, '$PROJECT_DIR/integration')
import importlib; importlib.import_module('$mod'.replace('-','_'))
" 2>/dev/null; then
        pass "$mod"
    else
        fail "$mod" "import 失败"
    fi
done

echo ""
echo "── 脚本语法 ──"
for script in integration/pipeline.sh integration/batch_pipeline.sh skills/setup.sh smoke_test.sh; do
    if bash -n "$PROJECT_DIR/$script" 2>/dev/null; then
        pass "$script"
    else
        fail "$script" "语法错误"
    fi
done

echo ""
echo "── 外部工具 ──"
for cmd in python3; do
    if command -v "$cmd" &>/dev/null; then
        pass "$cmd"
    else
        fail "$cmd" "未安装"
    fi
done
if command -v ffmpeg &>/dev/null; then pass "ffmpeg"; else skip "ffmpeg" "未安装 (可选)"; fi

echo ""
echo "── 可选依赖 ──"
for pkg in yt-dlp funasr faster_whisper edge_tts; do
    mod="${pkg//-/_}"
    if python3 -c "import $mod" 2>/dev/null; then pass "$pkg"; else skip "$pkg" "未安装 (可选)"; fi
done

echo ""
echo "── 单元测试 ──"
if python3 -m pytest "$PROJECT_DIR/tests/" -q 2>/dev/null || rtk proxy python3 -m pytest "$PROJECT_DIR/tests/" -q 2>/dev/null; then
    pass "pytest (58 tests)"
else
    fail "pytest" "测试失败"
fi

echo ""
echo "── 功能测试 ──"
# Text → SRT
if echo "你好。世界。" | python3 "$PROJECT_DIR/integration/text_to_srt.py" --stdin --lang zh 2>/dev/null | grep -q "00:00:00"; then
    pass "text_to_srt.py stdin"
else
    fail "text_to_srt.py stdin" "转换失败"
fi

# SRT roundtrip
if SMOKE_INTEGRATION="$PROJECT_DIR/integration" SMOKE_DEMO="$PROJECT_DIR/examples/demo_en.srt" python3 << 'PYEOF' 2>/dev/null
import sys, tempfile, os
sys.path.insert(0, os.environ['SMOKE_INTEGRATION'])
from translate_srt import parse_srt, format_srt
demo = os.environ['SMOKE_DEMO']
cues = parse_srt(demo)
assert len(cues) == 10
f = format_srt(cues)
with tempfile.NamedTemporaryFile(mode='w', suffix='.srt', delete=False, encoding='utf-8') as tf:
    tf.write(f)
    tmp = tf.name
r = parse_srt(tmp)
assert len(r) == 10
os.unlink(tmp)
print("OK")
PYEOF
then
    pass "translate_srt roundtrip"
else
    fail "translate_srt roundtrip" "解析-格式化不一致"
fi

# pipeline.sh --dry-run (bypass rtk)
if bash "$PROJECT_DIR/integration/pipeline.sh" --dry-run "$PROJECT_DIR/examples/demo_en.srt" 2>&1 | python3 -c "import sys; t=sys.stdin.read(); sys.exit(0 if 'DRY RUN' in t or '[DRY' in t else 1)"; then
    pass "pipeline.sh --dry-run"
else
    fail "pipeline.sh --dry-run" "预览失败"
fi

# batch_pipeline.sh --dry-run
if bash "$PROJECT_DIR/integration/batch_pipeline.sh" "$PROJECT_DIR/examples/" --pattern "*.srt" --dry-run 2>&1 | python3 -c "import sys; t=sys.stdin.read(); sys.exit(0 if 'DRY RUN' in t or '[DRY' in t else 1)"; then
    pass "batch_pipeline.sh --dry-run"
else
    fail "batch_pipeline.sh --dry-run" "批量预览失败"
fi

echo ""
echo "═══ 结果: $PASS 通过, $FAIL 失败, $TOTAL 总计 ═══"
[ "$FAIL" -gt 0 ] && exit 1 || exit 0
