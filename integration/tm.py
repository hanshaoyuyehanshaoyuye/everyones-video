#!/usr/bin/env python3
"""
tm.py — Translation Memory for subtitle reuse (zero-dependency).

Stores source→target pairs as nested JSON:
  {source_lang: {target_lang: {source_text: target_text}}}

Fuzzy matching via difflib.SequenceMatcher (stdlib, no extra deps).

Usage:
  from tm import TranslationMemory
  tm = TranslationMemory("~/.everyones-video/translation_memory.json")
  hit = tm.lookup_exact("你好", "zh", "en")           # → "Hello" or None
  fuzzy = tm.lookup_fuzzy("你好世界", "zh", "en")     # → [("你好","Hello",0.67), ...]
  tm.store("你好", "Hello", "zh", "en")               # persist new pair
  tm.stats()                                          # → {"zh→en": 1234, "en→zh": 567}
"""

import json
import os
from difflib import SequenceMatcher
from pathlib import Path


class TranslationMemory:
    def __init__(self, path: str | None = None):
        default = os.path.join(
            os.path.expanduser("~"), ".everyones-video", "translation_memory.json"
        )
        self.path = Path(path or os.environ.get("TM_PATH", default))
        self._data: dict = {}
        self._dirty = False
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        if self.path.exists():
            try:
                raw = self.path.read_text(encoding="utf-8")
                self._data = json.loads(raw) if raw.strip() else {}
            except (json.JSONDecodeError, OSError):
                self._data = {}
        self._loaded = True

    def _save(self):
        if not self._dirty:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic write: temp file → rename
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps(self._data, ensure_ascii=False, indent=1), encoding="utf-8"
        )
        tmp.replace(self.path)
        self._dirty = False

    def lookup_exact(self, source_text: str, source_lang: str, target_lang: str) -> str | None:
        """Return exact match or None."""
        self._load()
        key = self._normalize(source_text)
        return (
            self._data.get(source_lang, {}).get(target_lang, {}).get(key)
        )

    def lookup_fuzzy(
        self, source_text: str, source_lang: str, target_lang: str,
        threshold: float = 0.80, max_results: int = 5,
    ) -> list[tuple[str, str, float]]:
        """Return [(source_text, target_text, ratio), ...] above threshold, sorted best-first."""
        self._load()
        pairs = self._data.get(source_lang, {}).get(target_lang, {})
        if not pairs:
            return []
        norm = self._normalize(source_text)
        results = []
        for src, tgt in pairs.items():
            ratio = SequenceMatcher(None, norm, src).ratio()
            if ratio >= threshold:
                results.append((src, tgt, ratio))
        results.sort(key=lambda x: -x[2])
        return results[:max_results]

    def store(self, source_text: str, target_text: str, source_lang: str, target_lang: str):
        """Store a new translation pair (auto-saves after batch)."""
        self._load()
        key = self._normalize(source_text)
        self._data.setdefault(source_lang, {}).setdefault(target_lang, {})[key] = target_text
        self._dirty = True

    def store_batch(self, pairs: list[tuple[str, str]], source_lang: str, target_lang: str):
        """Store multiple pairs at once, then save."""
        self._load()
        for src, tgt in pairs:
            key = self._normalize(src)
            self._data.setdefault(source_lang, {}).setdefault(target_lang, {})[key] = tgt
        self._dirty = True
        self._save()

    def flush(self):
        """Save pending changes to disk."""
        self._save()

    def stats(self) -> dict:
        """Return per-language-pair counts."""
        self._load()
        result = {}
        for src_lang, targets in self._data.items():
            for tgt_lang, pairs in targets.items():
                result[f"{src_lang}→{tgt_lang}"] = len(pairs)
        return result

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for comparison: strip, collapse whitespace."""
        return " ".join(text.strip().split())


def main():
    """CLI for TM inspection and management."""
    import argparse

    parser = argparse.ArgumentParser(description="Translation Memory management")
    parser.add_argument("action", nargs="?", default="stats",
                        choices=["stats", "export", "import", "clear"])
    parser.add_argument("--path", default=None, help="TM file path")
    parser.add_argument("--file", default=None, help="JSON file for import/export")
    parser.add_argument("--lang-pair", default=None, help="Filter: zh-en or zh→en")
    args = parser.parse_args()

    tm = TranslationMemory(args.path)

    if args.action == "stats":
        s = tm.stats()
        if not s:
            print("TM is empty.")
            print(f"Path: {tm.path}")
        else:
            total = sum(s.values())
            print(f"TM: {total} entries across {len(s)} language pairs")
            print(f"Path: {tm.path}")
            for pair, count in sorted(s.items()):
                print(f"  {pair}: {count}")

    elif args.action == "export":
        tm._load()
        data = tm._data
        if args.lang_pair:
            src, tgt = args.lang_pair.replace("→", "-").split("-")
            data = {src: {tgt: tm._data.get(src, {}).get(tgt, {})}}
        out = args.file or "tm_export.json"
        Path(out).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        pairs = sum(len(v) for s in data.values() for v in s.values())
        print(f"Exported {pairs} entries → {out}")

    elif args.action == "import":
        infile = args.file or "tm_export.json"
        if not Path(infile).exists():
            sys.exit(f"File not found: {infile}")
        incoming = json.loads(Path(infile).read_text(encoding="utf-8"))
        tm._load()
        count = 0
        for src_lang, targets in incoming.items():
            for tgt_lang, pairs in targets.items():
                for src, tgt in pairs.items():
                    tm.store(src, tgt, src_lang, tgt_lang)
                    count += 1
        tm.flush()
        print(f"Imported {count} entries → {tm.path}")

    elif args.action == "clear":
        tm._data = {}
        tm._dirty = True
        tm.flush()
        print(f"Cleared all entries from {tm.path}")


if __name__ == "__main__":
    import sys
    main()
