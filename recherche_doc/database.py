"""Base de données cachée des catégories et tags de chaque fichier (SQLite)."""

import json
import os
import sqlite3
from contextlib import contextmanager
from typing import Iterable, List, Optional, Set, Tuple


class DocumentDB:
    def __init__(self, path: str):
        self.path = path
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        # répertoire caché
        if os.path.dirname(path):
            parent = os.path.dirname(path)
            base = os.path.basename(parent.rstrip("/\\")) or parent
            hidden = ("." + base) if not base.startswith(".") else base
            self.path = os.path.join(os.path.dirname(parent), hidden, os.path.basename(path))
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._init_schema()

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self):
        with self._conn() as c:
            c.executescript(
                """
                CREATE TABLE IF NOT EXISTS files (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    filename TEXT UNIQUE NOT NULL,
                    extension TEXT,
                    category TEXT NOT NULL,
                    tags TEXT NOT NULL,
                    main_date TEXT,
                    recipient TEXT,
                    emetteur TEXT,
                    classified_by TEXT NOT NULL DEFAULT 'lexical'
                );
                CREATE INDEX IF NOT EXISTS idx_files_category ON files(category);
                CREATE INDEX IF NOT EXISTS idx_files_recipient ON files(recipient);
                CREATE INDEX IF NOT EXISTS idx_files_emetteur ON files(emetteur);
                CREATE INDEX IF NOT EXISTS idx_files_date ON files(main_date);
                CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
                    filename, category, recipient, emetteur, tags
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                );
                """
            )

    def upsert_file(self, filename: str, extension: str, category: str,
                    tags: Iterable[str], main_date: Optional[str] = None,
                    recipient: Optional[str] = None, emetteur: Optional[str] = None,
                    classified_by: str = "lexical") -> int:
        tags_s = json.dumps(sorted(tags), ensure_ascii=False)
        with self._conn() as c:
            c.execute(
                "INSERT INTO files (filename, extension, category, tags, main_date, recipient, emetteur, classified_by) "
                "VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(filename) DO UPDATE SET "
                "extension=excluded.extension, category=excluded.category, tags=excluded.tags, "
                "main_date=excluded.main_date, recipient=excluded.recipient, "
                "emetteur=excluded.emetteur, classified_by=excluded.classified_by",
                (filename, extension, category, tags_s, main_date, recipient, emetteur, classified_by),
            )
            row = c.execute("SELECT id FROM files WHERE filename=?", (filename,)).fetchone()
            fid = row["id"]
            c.execute("DELETE FROM files_fts WHERE rowid=(SELECT rowid FROM files_fts WHERE filename=? LIMIT 1)", (filename,))
            c.execute(
                "INSERT INTO files_fts (rowid, filename, category, recipient, emetteur, tags) VALUES (?,?,?,?,?,?)",
                (fid, filename, category, recipient or "", emetteur or "", tags_s),
            )
        return fid

    def get_file(self, filename: str) -> Optional[dict]:
        with self._conn() as c:
            row = c.execute("SELECT * FROM files WHERE filename=?", (filename,)).fetchone()
            if not row:
                return None
            d = dict(row)
            d["tags"] = json.loads(d["tags"])
            return d

    def delete_file(self, filename: str) -> bool:
        with self._conn() as c:
            row = c.execute("SELECT id FROM files WHERE filename=?", (filename,)).fetchone()
            if not row:
                return False
            c.execute("DELETE FROM files WHERE id=?", (row["id"],))
            c.execute("DELETE FROM files_fts WHERE rowid=?", (row["id"],))
        return True

    def list_all(self) -> List[dict]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM files ORDER BY filename").fetchall()
        out = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"])
            out.append(d)
        return out

    def set_setting(self, key: str, value: str):
        with self._conn() as c:
            c.execute(
                "INSERT INTO settings (key, value) VALUES (?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (key, value),
            )

    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._conn() as c:
            row = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return row["value"] if row else default

    def close(self):
        pass
