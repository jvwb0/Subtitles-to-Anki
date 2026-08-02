import sqlite3
import json
import os
import threading

_DB_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "word_cache.db")
)


class CacheService:
    _instance = None
    _class_lock = threading.Lock()

    @classmethod
    def get(cls):
        if cls._instance is None:
            with cls._class_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def __init__(self):
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._init_tables()

    def _init_tables(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS definitions (
                word  TEXT NOT NULL,
                lang  TEXT NOT NULL,
                simple TEXT,
                detail TEXT,
                PRIMARY KEY (word, lang)
            );
            CREATE TABLE IF NOT EXISTS translations (
                text        TEXT NOT NULL,
                source_lang TEXT NOT NULL,
                target_lang TEXT NOT NULL,
                result      TEXT NOT NULL,
                PRIMARY KEY (text, source_lang, target_lang)
            );
        """)
        self._conn.commit()

    # ── definitions ──────────────────────────────────────────────────

    def get_definition(self, word: str, lang: str) -> tuple:
        """Returns (simple_dict, detail_dict). Either may be None if not cached."""
        with self._lock:
            row = self._conn.execute(
                "SELECT simple, detail FROM definitions WHERE word=? AND lang=?",
                (word.lower(), lang),
            ).fetchone()
        if not row:
            return None, None
        simple = json.loads(row[0]) if row[0] else None
        detail = json.loads(row[1]) if row[1] else None
        return simple, detail

    def save_simple(self, word: str, lang: str, result: dict):
        with self._lock:
            self._conn.execute(
                """INSERT INTO definitions (word, lang, simple) VALUES (?, ?, ?)
                   ON CONFLICT(word, lang) DO UPDATE SET simple=excluded.simple""",
                (word.lower(), lang, json.dumps(result)),
            )
            self._conn.commit()

    def save_detail(self, word: str, lang: str, result: dict):
        with self._lock:
            self._conn.execute(
                """INSERT INTO definitions (word, lang, detail) VALUES (?, ?, ?)
                   ON CONFLICT(word, lang) DO UPDATE SET detail=excluded.detail""",
                (word.lower(), lang, json.dumps(result)),
            )
            self._conn.commit()

    # ── translations ─────────────────────────────────────────────────

    def get_translation(self, text: str, src: str, tgt: str) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT result FROM translations WHERE text=? AND source_lang=? AND target_lang=?",
                (text.strip(), src, tgt),
            ).fetchone()
        return row[0] if row else None

    def save_translation(self, text: str, src: str, tgt: str, result: str):
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO translations (text, source_lang, target_lang, result) VALUES (?, ?, ?, ?)",
                (text.strip(), src, tgt, result),
            )
            self._conn.commit()

    # ── stats ────────────────────────────────────────────────────────

    def stats(self) -> tuple[int, int]:
        """Returns (n_definitions, n_translations)."""
        with self._lock:
            n_def = self._conn.execute("SELECT COUNT(*) FROM definitions").fetchone()[0]
            n_tr  = self._conn.execute("SELECT COUNT(*) FROM translations").fetchone()[0]
        return n_def, n_tr
