import sqlite3
import datetime
import os
from typing import List
from memory.schemas import SemanticEntry


class SemanticMemoryStore:
    """
    Accumulates abstract, time-independent knowledge about UI elements and
    the application — the agent's evolving understanding of the app under test.
    Backed by SQLite with FTS5 for keyword search.
    """

    def __init__(self, session_id: str, output_dir: str):
        db_dir = os.path.join(output_dir, "memory")
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = os.path.join(db_dir, "semantic.db")
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS knowledge (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                name           TEXT NOT NULL,
                summary        TEXT,
                details        TEXT,
                source         TEXT DEFAULT 'observer',
                screen_context TEXT,
                bounds_json    TEXT DEFAULT '[]',
                updated_at     TEXT
            )
        """)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS knowledge_fts
            USING fts5(name, summary, details, content='knowledge', content_rowid='id')
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS knowledge_ai AFTER INSERT ON knowledge BEGIN
                INSERT INTO knowledge_fts(rowid, name, summary, details)
                VALUES (new.id, new.name, new.summary, new.details);
            END
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS knowledge_au AFTER UPDATE ON knowledge BEGIN
                INSERT INTO knowledge_fts(knowledge_fts, rowid, name, summary, details)
                VALUES ('delete', old.id, old.name, old.summary, old.details);
                INSERT INTO knowledge_fts(rowid, name, summary, details)
                VALUES (new.id, new.name, new.summary, new.details);
            END
        """)
        self._conn.commit()

    def write(self, entries: list):
        """
        entries: list of dicts with keys: name, summary, details, source, screen_context, bounds
        Upserts by name — same widget updated if already known.
        """
        import json
        now = datetime.datetime.now().isoformat(timespec="seconds")
        for e in entries:
            name = e.get("name", "").strip()
            if not name:
                continue
            existing = self._conn.execute(
                "SELECT id FROM knowledge WHERE name=?", (name,)
            ).fetchone()
            if existing:
                self._conn.execute(
                    "UPDATE knowledge SET summary=?, details=?, source=?, "
                    "screen_context=?, bounds_json=?, updated_at=? WHERE id=?",
                    (
                        e.get("summary", ""),
                        e.get("details", ""),
                        e.get("source", "observer"),
                        e.get("screen_context", ""),
                        json.dumps(e.get("bounds", [])),
                        now,
                        existing[0],
                    ),
                )
            else:
                self._conn.execute(
                    "INSERT INTO knowledge (name, summary, details, source, screen_context, bounds_json, updated_at) "
                    "VALUES (?,?,?,?,?,?,?)",
                    (
                        name,
                        e.get("summary", ""),
                        e.get("details", ""),
                        e.get("source", "observer"),
                        e.get("screen_context", ""),
                        json.dumps(e.get("bounds", [])),
                        now,
                    ),
                )
        self._conn.commit()

    def search(self, topic: str, max_results: int = 8) -> List[SemanticEntry]:
        import json
        results = []
        try:
            cur = self._conn.execute(
                "SELECT k.name, k.summary, k.details, k.source, k.screen_context, k.bounds_json "
                "FROM knowledge k "
                "JOIN knowledge_fts f ON k.id = f.rowid "
                "WHERE knowledge_fts MATCH ? "
                "ORDER BY k.updated_at DESC LIMIT ?",
                (self._fts_query(topic), max_results),
            )
            for row in cur.fetchall():
                results.append(SemanticEntry(
                    name=row[0], summary=row[1], details=row[2],
                    source=row[3], screen_context=row[4],
                    bounds=json.loads(row[5] or "[]"),
                ))
        except Exception:
            pass

        if not results:
            cur = self._conn.execute(
                "SELECT name, summary, details, source, screen_context, bounds_json "
                "FROM knowledge ORDER BY updated_at DESC LIMIT ?",
                (max_results,),
            )
            for row in cur.fetchall():
                results.append(SemanticEntry(
                    name=row[0], summary=row[1], details=row[2],
                    source=row[3], screen_context=row[4],
                    bounds=json.loads(row[5] or "[]"),
                ))
        return results

    def close(self):
        self._conn.close()

    @staticmethod
    def _fts_query(topic: str) -> str:
        words = [w.strip('"') for w in topic.split() if len(w) > 2]
        if not words:
            return '""'
        return " OR ".join(f'"{w}"' for w in words[:8])
