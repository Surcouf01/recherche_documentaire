"""Moteur de recherche par catégorie, tags et mots-clés (FTS5 + filtres)."""

import json
import sqlite3
import unicodedata
from typing import List, Optional


def _norm(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s)
                    if unicodedata.category(c) != "Mn").lower()


class SearchEngine:
    def __init__(self, db):
        self.db = db

    def search(self, category: Optional[str] = None,
               tags: Optional[List[str]] = None,
               query: Optional[str] = None,
               recipient: Optional[str] = None,
               emetteur: Optional[str] = None,
               date: Optional[str] = None) -> List[dict]:
        conn = sqlite3.connect(self.db.path)
        conn.row_factory = sqlite3.Row
        try:
            sql = "SELECT * FROM files WHERE 1=1"
            args: List = []
            if category:
                sql += " AND category = ?"
                args.append(category)
            if recipient:
                sql += " AND recipient LIKE ?"
                args.append(f"%{recipient}%")
            if emetteur:
                sql += " AND recipient LIKE ? OR emetteur LIKE ?"
                args.extend([f"%{emetteur}%", f"%{emetteur}%"])
                sql = sql.replace("recipient LIKE ? OR emetteur LIKE ?",
                                  "(recipient LIKE ? OR emetteur LIKE ?)")
            if date:
                sql += " AND main_date LIKE ?"
                args.append(f"%{date}%")
            if tags:
                for t in tags:
                    sql += " AND (tags LIKE ? OR tags LIKE ? OR recipient LIKE ? OR emetteur LIKE ?)"
                    t_n = _norm(t)
                    args.append(f'%"{t}"%')
                    args.append(f'%"{t_n.title()}"%')
                    args.append(f'%{t_n.title()}%')
                    args.append(f'%{t_n.title()}%')
            if query:
                like = f"%{query}%"
                sql += " AND (filename LIKE ? OR category LIKE ? OR recipient LIKE ? OR emetteur LIKE ? OR tags LIKE ?)"
                args.extend([like, like, like, like, like])
            sql += " ORDER BY main_date DESC, filename"
            rows = conn.execute(sql, args).fetchall()
        finally:
            conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"])
            results.append(d)
        return results

    def search_fulltext(self, query: str) -> List[dict]:
        conn = sqlite3.connect(self.db.path)
        conn.row_factory = sqlite3.Row
        try:
            rows = conn.execute(
                "SELECT f.* FROM files f JOIN files_fts t ON t.rowid=f.id "
                "WHERE files_fts MATCH ? ORDER BY rank", (query,)
            ).fetchall()
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()
        results = []
        for r in rows:
            d = dict(r)
            d["tags"] = json.loads(d["tags"])
            results.append(d)
        return results

    def list_categories(self) -> List[str]:
        conn = sqlite3.connect(self.db.path)
        try:
            rows = conn.execute("SELECT DISTINCT category FROM files ORDER BY category").fetchall()
        finally:
            conn.close()
        return [r[0] for r in rows]
