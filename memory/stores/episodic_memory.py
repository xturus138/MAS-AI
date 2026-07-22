import sqlite3
import datetime
import os
from typing import List
from memory.schemas import EpisodicEntry


class EpisodicMemoryStore:
    """
    Stores time-stamped events in order — the agent's living activity log.
    Backed by SQLite with FTS5 for keyword search.
    """

    def __init__(self, session_id: str, output_dir: str):
        db_dir = os.path.join(output_dir, "memory")
        os.makedirs(db_dir, exist_ok=True)
        self._db_path = os.path.join(db_dir, "episodic.db")
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._create_tables()

    def _create_tables(self):
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS episodes (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type  TEXT NOT NULL,
                summary     TEXT NOT NULL,
                details     TEXT,
                actor       TEXT,
                timestamp   TEXT,
                step        INTEGER DEFAULT 0
            )
        """)
        self._conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS episodes_fts
            USING fts5(summary, details, content='episodes', content_rowid='id')
        """)
        self._conn.execute("""
            CREATE TRIGGER IF NOT EXISTS episodes_ai AFTER INSERT ON episodes BEGIN
                INSERT INTO episodes_fts(rowid, summary, details)
                VALUES (new.id, new.summary, new.details);
            END
        """)
        self._conn.commit()

    def write(self, entry: dict):
        """
        entry keys: event_type, summary, details, actor, step
        """
        now = datetime.datetime.now().isoformat(timespec="seconds")
        self._conn.execute(
            "INSERT INTO episodes (event_type, summary, details, actor, timestamp, step) "
            "VALUES (?,?,?,?,?,?)",
            (
                entry.get("event_type", "unknown"),
                entry.get("summary", ""),
                entry.get("details", ""),
                entry.get("actor", "system"),
                entry.get("timestamp", now),
                entry.get("step", 0),
            ),
        )
        self._conn.commit()

    def search(self, topic: str, max_results: int = 5) -> List[EpisodicEntry]:
        results = []
        try:
            cur = self._conn.execute(
                "SELECT e.event_type, e.summary, e.details, e.actor, e.timestamp, e.step "
                "FROM episodes e "
                "JOIN episodes_fts f ON e.id = f.rowid "
                "WHERE episodes_fts MATCH ? "
                "ORDER BY e.id DESC LIMIT ?",
                (self._fts_query(topic), max_results),
            )
            for row in cur.fetchall():
                results.append(EpisodicEntry(*row))
        except Exception:
            pass

        needed = max_results - len(results)
        if needed > 0:
            cur = self._conn.execute(
                "SELECT event_type, summary, details, actor, timestamp, step "
                "FROM episodes ORDER BY id DESC LIMIT ?",
                (needed,),
            )
            seen = {(r.actor, r.step, r.event_type) for r in results}
            for row in cur.fetchall():
                entry = EpisodicEntry(*row)
                key = (entry.actor, entry.step, entry.event_type)
                if key not in seen:
                    results.append(entry)
                    seen.add(key)

        return results

    def last(self, n: int = 5) -> List[EpisodicEntry]:
        cur = self._conn.execute(
            "SELECT event_type, summary, details, actor, timestamp, step "
            "FROM episodes ORDER BY id DESC LIMIT ?",
            (n,),
        )
        return [EpisodicEntry(*row) for row in cur.fetchall()]

    def last_by_actor(self, actor: str) -> EpisodicEntry | None:
        cur = self._conn.execute(
            "SELECT event_type, summary, details, actor, timestamp, step "
            "FROM episodes WHERE actor=? ORDER BY id DESC LIMIT 1",
            (actor,),
        )
        row = cur.fetchone()
        return EpisodicEntry(*row) if row else None

    def all_as_dicts(self) -> list:
        cur = self._conn.execute(
            "SELECT event_type, summary, details, actor, timestamp, step FROM episodes ORDER BY id"
        )
        cols = ["event_type", "summary", "details", "actor", "timestamp", "step"]
        return [dict(zip(cols, row)) for row in cur.fetchall()]

    def close(self):
        self._conn.close()

    @staticmethod
    def _fts_query(topic: str) -> str:
        words = [w.strip('"') for w in topic.split() if len(w) > 2]
        if not words:
            return '""'
        return " OR ".join(f'"{w}"' for w in words[:8])
