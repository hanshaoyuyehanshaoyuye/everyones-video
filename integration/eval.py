#!/usr/bin/env python3
"""
eval.py — 工作流评估记录与引擎推荐。

每次翻译/转写完成后，追加一条记录到 workflow_eval.json。
分析历史数据，自动推荐最优引擎。

用法:
  python3 integration/eval.py record --engine funasr --duration 120 --lang zh --cost 0
  python3 integration/eval.py recommend --lang zh --budget 0
  python3 integration/eval.py stats
"""
import argparse, json, os, sys, time
from pathlib import Path

EVAL_FILE = Path(__file__).parent.parent / "workflow_eval.json"


def load():
    if EVAL_FILE.exists():
        return json.loads(EVAL_FILE.read_text(encoding="utf-8"))
    return {"records": [], "engines": {}}


def save(data):
    EVAL_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def record(engine, lang, duration, cost, source_type, cues_count=0):
    data = load()
    data["records"].append({
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "engine": engine,
        "lang": lang,
        "duration_sec": duration,
        "cost_yuan": cost,
        "source": source_type,
        "cues": cues_count,
    })
    # Per-engine stats
    if engine not in data["engines"]:
        data["engines"][engine] = {"calls": 0, "total_sec": 0, "total_cost": 0, "total_cues": 0}
    e = data["engines"][engine]
    e["calls"] += 1
    e["total_sec"] += duration
    e["total_cost"] += cost
    e["total_cues"] += cues_count
    save(data)
    return data


def recommend(lang, budget=float("inf"), limit=3):
    """推荐最优引擎：按预算筛，再按速度/成本排序"""
    data = load()
    engines = {
        "yt-dlp_subtitles": {"cost": 0, "speed": 1, "cn_quality": 3, "en_quality": 3, "local": True},
        "funasr":   {"cost": 0, "speed": 15, "cn_quality": 4, "en_quality": 2, "local": True},
        "faster_whisper": {"cost": 0, "speed": 50, "cn_quality": 2, "en_quality": 4, "local": True},
        "stepfun":  {"cost": 0.007, "speed": 90, "cn_quality": 3, "en_quality": 3, "local": False},
        "doubao":   {"cost": 0.015, "speed": 20, "cn_quality": 5, "en_quality": 0, "local": False},
        "whisper_api": {"cost": 0.036, "speed": 15, "cn_quality": 2, "en_quality": 5, "local": False},
        "deepseek_translate": {"cost": 0.0001, "speed": 100, "cn_quality": 4, "en_quality": 4, "local": False},
    }
    results = []
    for name, props in engines.items():
        if props["cost"] > budget:
            continue
        quality_key = "cn_quality" if lang.startswith("zh") else "en_quality"
        quality = props[quality_key]
        hist = data["engines"].get(name, {})
        calls = hist.get("calls", 0)
        # 推荐分数：质量优先，速度快+用时短的加权
        score = quality * 10 + (100 / max(props["speed"], 1)) * 0.5
        if calls > 0:
            score += min(calls, 10) * 0.3  # 经验加分
        results.append({
            "engine": name,
            "cost_yuan_per_min": round(props["cost"] * 60, 4),
            "quality": quality,
            "local": props["local"],
            "calls": calls,
            "score": round(score, 1),
        })
    results.sort(key=lambda r: r["score"], reverse=True)
    return results[:limit]


def stats():
    data = load()
    print(f"=== Workflow Eval ===")
    print(f"Records: {len(data['records'])}")
    if data["records"]:
        latest = data["records"][-1]
        print(f"Latest: {latest['time']} | {latest['engine']} | {latest['lang']} | {latest['duration_sec']}s")
    print()
    if data["engines"]:
        print(f"{'Engine':<22} {'Calls':>5} {'Time':>8} {'Cost':>10}")
        print("-" * 50)
        for name, e in sorted(data["engines"].items()):
            print(f"{name:<22} {e['calls']:>5} {e['total_sec']:>7}s  $ {e['total_cost']:>7.4f}")


def main():
    parser = argparse.ArgumentParser(description="Workflow Eval - record & recommend ASR engines")
    sub = parser.add_subparsers(dest="cmd")

    r = sub.add_parser("record")
    r.add_argument("--engine", required=True)
    r.add_argument("--lang", default="zh")
    r.add_argument("--duration", type=float, required=True, help="duration in seconds")
    r.add_argument("--cost", type=float, default=0)
    r.add_argument("--source", default="audio")
    r.add_argument("--cues", type=int, default=0)

    rec = sub.add_parser("recommend")
    rec.add_argument("--lang", default="zh")
    rec.add_argument("--budget", type=float, default=float("inf"), help="max cost per minute")

    sub.add_parser("stats")

    args = parser.parse_args()
    if args.cmd == "record":
        record(args.engine, args.lang, args.duration, args.cost, args.source, args.cues)
        print(f"[OK] {args.engine} recorded")
    elif args.cmd == "recommend":
        for r in recommend(args.lang, args.budget):
            local = "local" if r["local"] else "API"
            print(f"  {r['engine']:<22} Q{r['quality']}/5  ${r['cost_yuan_per_min']}/min  {local}  score:{r['score']}")
    elif args.cmd == "stats":
        stats()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
