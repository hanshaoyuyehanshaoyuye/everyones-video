#!/usr/bin/env python3
"""
subtitle_quality.py — 字幕质量引擎（SQI: Subtitle Quality Index）

解决可乐鸡翅提出的五大问题：
  1. 字幕重叠检测修复  — overlap detection & fix
  2. 最大显示时长上限    — max cue duration (防一直显示)
  3. 最小显示时长强制    — min cue duration (防闪屏)
  4. 间距桥接合并        — gap bridging (间距过短合并，间距过长截断)
  5. 可读性 CPS 检查     — chars-per-second validation

用法:
  from subtitle_quality import enforce, diagnose
  fixed_cues, report = enforce(cues, lang="zh")
  issues = diagnose(cues)

独立 CLI:
  python3 subtitle_quality.py input.srt [--lang zh] [--fix] [--output fixed.srt]
"""

import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

# ── 质量阈值 ──────────────────────────────────────────

MAX_CUE_DURATION = 7.0   # 单条字幕最长显示秒数（≥此值截断到上一字幕结束+此值）
MIN_CUE_DURATION = 0.8   # 单条字幕最短显示秒数（<此值拉长或用间距补齐）
MAX_GAP_BRIDGE   = 0.15  # 间距小于此值 → 合并前一条字幕
MAX_GAP_FREEZE   = 2.0   # 间距大于此值 → 截断前一条字幕（不跨长沉默显示）

# 可读性阈值
MAX_CPS_ZH = 8.0   # 中文最大字/秒（阅读舒适区：4-6，极限：8-10）
MAX_CPS_EN = 20.0  # 英文最大字符/秒（含空格）

# 格式硬上限
MAX_CHARS_PER_LINE = 42  # 单行字幕最多字符数

# ── 数据结构 ──────────────────────────────────────────

@dataclass
class QualityReport:
    """修改前/后的诊断报告"""
    fixed_overlaps: int = 0
    capped_durations: int = 0
    boosted_durations: int = 0
    merged_gaps: int = 0
    frozen_gaps: int = 0
    cps_warnings: int = 0
    multi_line_warnings: int = 0
    issues: list[str] = field(default_factory=list)

    def healthy(self) -> bool:
        return not self.issues

    def summary(self) -> str:
        lines = []
        if self.fixed_overlaps: lines.append(f"{self.fixed_overlaps} 处重叠已修复")
        if self.capped_durations: lines.append(f"{self.capped_durations} 条超长字幕已截断")
        if self.boosted_durations: lines.append(f"{self.boosted_durations} 条过短字幕已拉长")
        if self.merged_gaps: lines.append(f"{self.merged_gaps} 处间距已合并")
        if self.frozen_gaps: lines.append(f"{self.frozen_gaps} 处长间隔已截断")
        if self.cps_warnings: lines.append(f"{self.cps_warnings} 条 CPS 超标（不阻断）")
        if self.multi_line_warnings: lines.append(f"{self.multi_line_warnings} 条多行/过长")
        return "；".join(lines) if lines else "✅ 字幕质量检查通过"


# ── 时间戳工具 ────────────────────────────────────────

def ts_to_sec(ts: str) -> float:
    h, m, s = ts.replace(",", ".").split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def sec_to_ts(sec: float) -> str:
    sec = max(sec, 0.0)
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = sec % 60
    return f"{h:02d}:{m:02d}:{s:06.3f}".replace(".", ",")


# ── 可读性检测 ───────────────────────────────────────

def _cps(cue: dict, lang: str) -> float:
    """计算这条字幕的字符/秒"""
    dur = ts_to_sec(cue["end"]) - ts_to_sec(cue["start"])
    if dur <= 0:
        return float("inf")
    if lang.startswith("zh") or lang in ("ja", "ko"):
        return len(cue["text"].replace(" ", "")) / dur
    return len(cue["text"]) / dur


def _line_count(cue: dict, lang: str) -> int:
    text = cue["text"]
    if "\n" in text:
        return text.count("\n") + 1
    max_line = MAX_CHARS_PER_LINE
    if lang.startswith("zh") or lang in ("ja", "ko"):
        # 中文大约 1字符=1宽度单位，英文半宽
        return max(1, -(-len(text) // max_line))  # ceiling division
    return max(1, -(-len(text) // max_line))


# ── 核心修正 ──────────────────────────────────────────

def enforce(cues: list[dict], lang: str = "zh") -> tuple[list[dict], QualityReport]:
    """
    对字幕列表执行全套质量修正，返回 (修正后字幕, 报告)。
    idempotent — safe to call multiple times.
    """
    report = QualityReport()
    if not cues:
        return cues, report

    out = [dict(c) for c in cues]  # deep copy
    max_cps = MAX_CPS_ZH if (lang.startswith("zh") or lang in ("ja", "ko")) else MAX_CPS_EN

    # ── Pass 1: 重叠修复 ──
    for i in range(1, len(out)):
        prev_end = ts_to_sec(out[i - 1]["end"])
        curr_start = ts_to_sec(out[i]["start"])
        if curr_start < prev_end:
            # 重叠：后一条的 start 推到前一条的 end
            out[i]["start"] = sec_to_ts(prev_end)
            # 如果这条时长因此变负/零，至少给 0.5s
            if ts_to_sec(out[i]["end"]) <= prev_end:
                out[i]["end"] = sec_to_ts(prev_end + MIN_CUE_DURATION)
            report.fixed_overlaps += 1
            report.issues.append(
                f"#{i+1} 与 #{i} 重叠 {prev_end - curr_start:.2f}s → 已推后"
            )

    # ── Pass 2: 间距处理（桥接 + 冻结） ──
    merged = []
    skip_next = False
    for i in range(len(out)):
        if skip_next:
            skip_next = False
            continue

        cue = dict(out[i])
        if i < len(out) - 1:
            gap = ts_to_sec(out[i + 1]["start"]) - ts_to_sec(cue["end"])

            if 0 < gap < MAX_GAP_BRIDGE:
                # 间距过短 → 合并到下一条
                next_cue = out[i + 1]
                merged_text = cue["text"] + " " + next_cue["text"]
                merged.append({
                    "index": len(merged) + 1,
                    "start": cue["start"],
                    "end": next_cue["end"],
                    "text": merged_text,
                })
                skip_next = True
                report.merged_gaps += 1
                report.issues.append(
                    f"#{i+1}↔#{i+2} 间距 {gap:.2f}s < {MAX_GAP_BRIDGE}s → 已合并"
                )
                continue

        # ── 间距过大 → 截断当前字幕结尾 ──
        if i < len(out) - 1:
            dur = ts_to_sec(cue["end"]) - ts_to_sec(cue["start"])
            gap_to_next = ts_to_sec(out[i + 1]["start"]) - ts_to_sec(cue["start"])
            if gap_to_next > MAX_GAP_FREEZE and dur > MAX_CUE_DURATION:
                # 字幕结束后还有长间隔 → 截断
                cue["end"] = sec_to_ts(ts_to_sec(cue["start"]) + MAX_CUE_DURATION)
                report.frozen_gaps += 1
                report.capped_durations += 1  # 长间隔截断也计入时长上限
                report.issues.append(
                    f"#{i+1} 后间距 {gap_to_next:.1f}s > {MAX_GAP_FREEZE}s → 截断"
                )
            elif gap_to_next > MAX_GAP_FREEZE and dur <= MAX_CUE_DURATION:
                # 字幕已够短但间距长 → 稍微延后结束时间
                # 不额外拉长字幕本身，但也不额外截断
                pass

        merged.append(cue)

    out = merged

    # ── Pass 3: 最大/最小持续时间 ──
    for i, cue in enumerate(out):
        dur = ts_to_sec(cue["end"]) - ts_to_sec(cue["start"])

        # 最小持续时间
        if dur < MIN_CUE_DURATION:
            stretch = MIN_CUE_DURATION - dur
            new_end = ts_to_sec(cue["end"]) + stretch
            # 不能推到下一条的 start
            if i < len(out) - 1:
                next_start = ts_to_sec(out[i + 1]["start"])
                if new_end > next_start:
                    new_end = next_start - 0.02  # 留 20ms 间距
            cue["end"] = sec_to_ts(new_end)
            report.boosted_durations += 1
            dur = ts_to_sec(cue["end"]) - ts_to_sec(cue["start"])  # recalc

        # 最大持续时间
        if dur > MAX_CUE_DURATION:
            cue["end"] = sec_to_ts(ts_to_sec(cue["start"]) + MAX_CUE_DURATION)
            report.capped_durations += 1
            report.issues.append(
                f"#{i+1} 持续 {dur:.1f}s > {MAX_CUE_DURATION}s → 截断"
            )

    # ── Pass 4: CPS 可读性检查（仅报告，不阻断） ──
    for i, cue in enumerate(out):
        cps_val = _cps(cue, lang)
        lines = _line_count(cue, lang)
        if cps_val > max_cps:
            report.cps_warnings += 1
            report.issues.append(
                f"⚠ #{i+1} CPS={cps_val:.1f} (阈值 {max_cps}) — 可能阅读困难"
            )
        if lines > 2:
            report.multi_line_warnings += 1
            report.issues.append(
                f"⚠ #{i+1} 等效 {lines} 行 — 建议换行或拆分"
            )

    # ── 重新编号 ──
    for i, cue in enumerate(out):
        cue["index"] = i + 1

    return out, report


def diagnose(cues: list[dict], lang: str = "zh") -> list[str]:
    """只诊断不修改，返回问题列表"""
    _, report = enforce(cues, lang)
    return report.issues


# ── SRT 读写 ───────────────────────────────────────────

def parse_srt(path: str) -> list[dict]:
    """Parse SRT file → [{index, start, end, text}]"""
    raw = Path(path).read_text(encoding="utf-8")
    blocks = re.split(r"\n\n+", raw.strip())
    cues = []
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        ts_match = re.match(r"(\S+)\s*-->\s*(\S+)", lines[1])
        if not ts_match:
            continue
        cues.append({
            "index": int(lines[0]) if lines[0].isdigit() else len(cues) + 1,
            "start": ts_match.group(1),
            "end": ts_match.group(2),
            "text": "\n".join(lines[2:]),
        })
    return cues


def format_srt(cues: list[dict]) -> str:
    """Format cues → SRT string"""
    parts = []
    for c in cues:
        parts.append(str(c["index"]))
        parts.append(f"{c['start']} --> {c['end']}")
        parts.append(c["text"])
        parts.append("")
    return "\n".join(parts)


# ── CLI ────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="字幕质量检查与修复 (SQI)")
    parser.add_argument("input", help="输入 SRT 文件")
    parser.add_argument("--lang", default="zh", help="语言 (zh/en/ja/ko)")
    parser.add_argument("--fix", action="store_true", help="自动修复并输出")
    parser.add_argument("--output", "-o", help="修复后输出文件（默认覆盖原文件）")
    parser.add_argument("--check-only", action="store_true", help="仅诊断，不修改")
    args = parser.parse_args()

    cues = parse_srt(args.input)
    fixed, report = enforce(cues, args.lang)

    if args.check_only:
        if report.healthy():
            print("✅ 字幕质量检查通过")
        else:
            print(f"❌ 发现 {len(report.issues)} 个问题:")
            for issue in report.issues:
                print(f"  {issue}")
    elif args.fix:
        out_path = args.output or args.input
        srt = format_srt(fixed)
        Path(out_path).write_text(srt, encoding="utf-8")
        print(f"✅ 已修复 → {out_path}")
        print(report.summary())
    else:
        # 默认：报告模式
        print(report.summary())
        if report.issues:
            for issue in report.issues:
                print(f"  {issue}")


if __name__ == "__main__":
    main()
