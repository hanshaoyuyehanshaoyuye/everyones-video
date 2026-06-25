#!/usr/bin/env python3
"""
tm.py — Translation Memory with SQLite backend (v7.0→v8.0 P0-4)

SQLite + FTS5 全文索引。零外部依赖 (Python stdlib sqlite3)。
API 与旧 JSON 版完全兼容。

Storage: ~/.everyones-video/translation_memory.db
Auto-migrates old JSON TM on first access.

Usage:
  from tm import TranslationMemory
  tm = TranslationMemory()                                # default path
  tm = TranslationMemory("~/.everyones-video/tm.db")      # custom path
  hit = tm.lookup_exact("你好", "zh", "en")                # → "Hello" or None
  fuzzy = tm.lookup_fuzzy("你好世界", "zh", "en")          # → [("你好","Hello",0.95), ...]
  tm.store("你好", "Hello", "zh", "en")                    # persist immediately
  tm.store_batch([("A","B"), ("C","D")], "en", "zh")      # batch with transaction
  tm.stats()                                               # → {"zh→en": 1234}
"""

import json
import os
import sqlite3
import sys
import threading
from difflib import SequenceMatcher
from pathlib import Path

try:
    from rapidfuzz import process as _rf_process, fuzz as _rf_fuzz
    _has_rapidfuzz = True
except ImportError:
    _has_rapidfuzz = False

_DB_VERSION = 1


class TranslationMemory:
    """SQLite-backed Translation Memory (API-compatible with JSON v1)."""

    def __init__(self, path: str | None = None):
        default = os.path.join(
            os.path.expanduser("~"), ".everyones-video", "translation_memory.db"
        )
        self.path = Path(path or os.environ.get("TM_PATH", default))
        self.path.parent.mkdir(parents=True, exist_ok=True)

        # Auto-migrate old JSON TM
        _migrate_json_if_needed(self.path)

        self._conn: sqlite3.Connection | None = None
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        """Return thread-local WAL-mode connection."""
        if self._conn is not None:
            return self._conn
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path), check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tm (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    source_lang TEXT NOT NULL,
                    target_lang TEXT NOT NULL,
                    source_text TEXT NOT NULL,
                    target_text TEXT NOT NULL,
                    created_at REAL NOT NULL DEFAULT (julianday('now')),
                    UNIQUE(source_lang, target_lang, source_text)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_tm_lang_pair
                ON tm(source_lang, target_lang)
            """)
            # FTS5 virtual table for fuzzy candidate narrowing
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS tm_fts
                USING fts5(source_text, content='tm', content_rowid='id')
            """)
            # Triggers to keep FTS in sync
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS tm_ai AFTER INSERT ON tm BEGIN
                    INSERT INTO tm_fts(rowid, source_text) VALUES (new.id, new.source_text);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS tm_ad AFTER DELETE ON tm BEGIN
                    INSERT INTO tm_fts(tm_fts, rowid, source_text) VALUES ('delete', old.id, old.source_text);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS tm_au AFTER UPDATE ON tm BEGIN
                    INSERT INTO tm_fts(tm_fts, rowid, source_text) VALUES ('delete', old.id, old.source_text);
                    INSERT INTO tm_fts(rowid, source_text) VALUES (new.id, new.source_text);
                END
            """)
            conn.execute("CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute(
                "INSERT OR IGNORE INTO _meta VALUES ('version', ?)",
                (str(_DB_VERSION),),
            )
            conn.commit()
            self._local.conn = conn
        return conn

    def lookup_exact(self, source_text: str, source_lang: str, target_lang: str) -> str | None:
        norm = self._normalize(source_text)
        row = self._get_conn().execute(
            "SELECT target_text FROM tm WHERE source_lang=? AND target_lang=? AND source_text=?",
            (source_lang, target_lang, norm),
        ).fetchone()
        return row[0] if row else None

    def lookup_fuzzy(
        self, source_text: str, source_lang: str, target_lang: str,
        threshold: float = 0.80, max_results: int = 5,
    ) -> list[tuple[str, str, float]]:
        """Return [(source_text, target_text, ratio), ...] sorted best-first.

        大规模 TM 优先 rapidfuzz（C++，10-50× difflib），回退 difflib。
        FTS5 预筛候选集（O(log n) 而非 O(n)），再对候选做精确 ratio。
        """
        conn = self._get_conn()
        norm = self._normalize(source_text)

        # Count total for scale decision
        total = conn.execute(
            "SELECT COUNT(*) FROM tm WHERE source_lang=? AND target_lang=?",
            (source_lang, target_lang),
        ).fetchone()[0]
        if total == 0:
            return []

        if total <= 30:
            # Small TM — fetch all directly
            rows = conn.execute(
                "SELECT source_text, target_text FROM tm WHERE source_lang=? AND target_lang=?",
                (source_lang, target_lang),
            ).fetchall()
            candidates = [(r[0], r[1]) for r in rows]
        else:
            # Large TM — FTS5 pre-filter with trigram-like fuzzy
            # Quote FTS5 query to avoid syntax errors from punctuation
            fts_query = '"' + norm.replace('"', '""') + '"'
            fts_rows = conn.execute(
                "SELECT source_text, target_text FROM tm_fts "
                "WHERE tm_fts MATCH ? AND source_lang=? AND target_lang=? "
                "LIMIT 200",
                (fts_query, source_lang, target_lang),
            ).fetchall()
            # If FTS gives too few candidates, also fetch some via prefix
            if len(fts_rows) < 10:
                extra = conn.execute(
                    "SELECT source_text, target_text FROM tm "
                    "WHERE source_lang=? AND target_lang=? AND source_text LIKE ? "
                    "LIMIT 50",
                    (source_lang, target_lang, norm[:10] + "%"),
                ).fetchall()
                fts_rows = list(dict.fromkeys(fts_rows + extra))  # dedupe
                fts_rows = fts_rows[:200]
            candidates = [(r[0], r[1]) for r in fts_rows]
            if not candidates:
                # Last resort: fetch all (shouldn't happen often)
                rows = conn.execute(
                    "SELECT source_text, target_text FROM tm WHERE source_lang=? AND target_lang=?",
                    (source_lang, target_lang),
                ).fetchall()
                candidates = [(r[0], r[1]) for r in rows]

        # Exact ratio computation on candidates
        if _has_rapidfuzz and len(candidates) > 20:
            choices = [src for src, _ in candidates]
            matches = _rf_process.extract(
                norm, choices, scorer=_rf_fuzz.ratio,
                score_cutoff=int(threshold * 100), limit=max_results,
            )
            results = []
            for src, score, _ in matches:
                ratio = score / 100.0
                for orig_src, tgt in candidates:
                    if orig_src == src:
                        results.append((orig_src, tgt, ratio))
                        break
            return results
        else:
            results = []
            for src, tgt in candidates:
                ratio = SequenceMatcher(None, norm, src).ratio()
                if ratio >= threshold:
                    results.append((src, tgt, ratio))
            results.sort(key=lambda x: -x[2])
            return results[:max_results]

    def store(self, source_text: str, target_text: str, source_lang: str, target_lang: str):
        """Store immediately (SQLite INSERT OR REPLACE). No need for explicit flush."""
        norm = self._normalize(source_text)
        self._get_conn().execute(
            "INSERT OR REPLACE INTO tm (source_lang, target_lang, source_text, target_text) "
            "VALUES (?, ?, ?, ?)",
            (source_lang, target_lang, norm, target_text),
        )
        self._get_conn().commit()

    def store_batch(self, pairs: list[tuple[str, str]], source_lang: str, target_lang: str):
        """Batch insert/update within a transaction."""
        conn = self._get_conn()
        with conn:
            for src, tgt in pairs:
                norm = self._normalize(src)
                conn.execute(
                    "INSERT OR REPLACE INTO tm (source_lang, target_lang, source_text, target_text) "
                    "VALUES (?, ?, ?, ?)",
                    (source_lang, target_lang, norm, tgt),
                )

    def flush(self):
        """No-op in SQLite mode — every store() is atomic."""
        pass

    def stats(self) -> dict:
        rows = self._get_conn().execute(
            "SELECT source_lang, target_lang, COUNT(*) FROM tm GROUP BY source_lang, target_lang"
        ).fetchall()
        return {f"{s}→{t}": c for s, t, c in rows}

    def export_json(self, out_path: str, lang_pair: str | None = None):
        """Export to JSON (backward compat with old format)."""
        conn = self._get_conn()
        data: dict[str, dict[str, dict[str, str]]] = {}
        rows = conn.execute(
            "SELECT source_lang, target_lang, source_text, target_text FROM tm"
        ).fetchall()
        for sl, tl, st, tt in rows:
            if lang_pair:
                src, tgt = lang_pair.replace("→", "-").split("-")
                if sl != src or tl != tgt:
                    continue
            data.setdefault(sl, {}).setdefault(tl, {})[st] = tt
        Path(out_path).write_text(json.dumps(data, ensure_ascii=False, indent=2))
        count = sum(len(pairs) for src_langs in data.values() for pairs in src_langs.values())
        print(f"Exported {count} entries → {out_path}")

    def import_json(self, in_path: str):
        """Import from JSON TM export."""
        incoming = json.loads(Path(in_path).read_text(encoding="utf-8"))
        conn = self._get_conn()
        count = 0
        with conn:
            for src_lang, targets in incoming.items():
                for tgt_lang, pairs in targets.items():
                    for src, tgt in pairs.items():
                        norm = self._normalize(src)
                        conn.execute(
                            "INSERT OR REPLACE INTO tm "
                            "(source_lang, target_lang, source_text, target_text) "
                            "VALUES (?, ?, ?, ?)",
                            (src_lang, tgt_lang, norm, tgt),
                        )
                        count += 1
        print(f"Imported {count} entries → {self.path}")

    @staticmethod
    def _normalize(text: str) -> str:
        return " ".join(text.strip().split())


# ── Migration ──────────────────────────────────────────

def _migrate_json_if_needed(db_path: Path):
    """Auto-migrate old JSON TM → SQLite on first access."""
    json_path = db_path.with_suffix(".json")
    if not json_path.exists() or db_path.exists():
        return
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    if not data:
        return
    print(f"[TM] Migrating {json_path} → {db_path}...", file=sys.stderr)
    conn = sqlite3.connect(str(db_path))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS tm (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_lang TEXT NOT NULL,
            target_lang TEXT NOT NULL,
            source_text TEXT NOT NULL,
            target_text TEXT NOT NULL,
            created_at REAL NOT NULL DEFAULT (julianday('now')),
            UNIQUE(source_lang, target_lang, source_text)
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tm_lang_pair ON tm(source_lang, target_lang)")
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS tm_fts USING fts5(source_text, content='tm', content_rowid='id')"
    )
    count = 0
    with conn:
        for src_lang, targets in data.items():
            for tgt_lang, pairs in targets.items():
                for src, tgt in pairs.items():
                    norm = " ".join(src.strip().split())
                    conn.execute(
                        "INSERT OR IGNORE INTO tm "
                        "(source_lang, target_lang, source_text, target_text) "
                        "VALUES (?, ?, ?, ?)",
                        (src_lang, tgt_lang, norm, tgt),
                    )
                    count += 1
    conn.execute("CREATE TABLE IF NOT EXISTS _meta (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT OR REPLACE INTO _meta VALUES ('version', ?)", (str(_DB_VERSION),))
    conn.commit()
    conn.close()
    # Rename old JSON so it doesn't trigger migration again
    json_path.rename(json_path.with_suffix(".json.bak"))
    print(f"[TM] Migrated {count} entries. Old file renamed to {json_path.with_suffix('.json.bak')}",
          file=sys.stderr)


# ── CLI ────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Translation Memory management (SQLite)")
    parser.add_argument("action", nargs="?", default="stats",
                        choices=["stats", "export", "import", "clear"])
    parser.add_argument("--path", default=None, help="TM database path")
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
        tm.export_json(args.file or "tm_export.json", args.lang_pair)

    elif args.action == "import":
        infile = args.file or "tm_export.json"
        if not Path(infile).exists():
            sys.exit(f"File not found: {infile}")
        tm.import_json(infile)

    elif args.action == "clear":
        conn = tm._get_conn()
        conn.execute("DELETE FROM tm")
        conn.execute("DELETE FROM tm_fts")
        conn.commit()
        print(f"Cleared all entries from {tm.path}")


if __name__ == "__main__":
    main()
