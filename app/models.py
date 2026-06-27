"""SQLite persistence layer for the bug tracker.

A thin, dependency-free data access layer built on the standard-library
``sqlite3`` module. Two tables: ``bugs`` and ``comments``. Labels and the
status history are stored on the bug row (labels as a JSON-encoded list).
"""
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime, timezone
from typing import Iterable, Optional

# Valid lifecycle states for a bug.
STATUSES = ("open", "in-progress", "closed")

DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "..", "bugtracker.db")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Database:
    """Owns a single SQLite connection and all the queries the app needs."""

    def __init__(self, path: str = ":memory:"):
        self.path = path
        # check_same_thread=False so the FastAPI TestClient / threaded server
        # can share one in-memory connection.
        self.conn = sqlite3.connect(path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._create_schema()

    def _create_schema(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS bugs (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                title       TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                status      TEXT NOT NULL DEFAULT 'open',
                assignee    TEXT,
                labels      TEXT NOT NULL DEFAULT '[]',
                created_at  TEXT NOT NULL,
                updated_at  TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS comments (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                bug_id      INTEGER NOT NULL,
                author      TEXT NOT NULL DEFAULT 'anonymous',
                body        TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                FOREIGN KEY (bug_id) REFERENCES bugs(id) ON DELETE CASCADE
            );
            """
        )
        self.conn.commit()

    # ----- serialization helpers -------------------------------------------------

    @staticmethod
    def _row_to_bug(row: sqlite3.Row) -> dict:
        bug = dict(row)
        bug["labels"] = json.loads(bug["labels"])
        return bug

    # ----- bug CRUD --------------------------------------------------------------

    def create_bug(
        self,
        title: str,
        description: str = "",
        assignee: Optional[str] = None,
        labels: Optional[Iterable[str]] = None,
        status: str = "open",
    ) -> dict:
        if status not in STATUSES:
            raise ValueError(f"invalid status {status!r}; expected one of {STATUSES}")
        ts = _now()
        cur = self.conn.execute(
            """
            INSERT INTO bugs (title, description, status, assignee, labels, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                description,
                status,
                assignee,
                json.dumps(sorted(set(labels or []))),
                ts,
                ts,
            ),
        )
        self.conn.commit()
        return self.get_bug(cur.lastrowid)

    def get_bug(self, bug_id: int) -> Optional[dict]:
        row = self.conn.execute("SELECT * FROM bugs WHERE id = ?", (bug_id,)).fetchone()
        if row is None:
            return None
        bug = self._row_to_bug(row)
        bug["comments"] = self.list_comments(bug_id)
        return bug

    def list_bugs(
        self,
        status: Optional[str] = None,
        assignee: Optional[str] = None,
        label: Optional[str] = None,
    ) -> list[dict]:
        sql = "SELECT * FROM bugs"
        clauses, params = [], []
        if status:
            clauses.append("status = ?")
            params.append(status)
        if assignee:
            clauses.append("assignee = ?")
            params.append(assignee)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id"
        rows = self.conn.execute(sql, params).fetchall()
        bugs = [self._row_to_bug(r) for r in rows]
        if label:
            bugs = [b for b in bugs if label in b["labels"]]
        return bugs

    def update_bug(self, bug_id: int, **fields) -> Optional[dict]:
        """Update any of: title, description, status, assignee, labels."""
        allowed = {"title", "description", "status", "assignee", "labels"}
        sets, params = [], []
        for key, value in fields.items():
            if key not in allowed or value is None:
                continue
            if key == "status" and value not in STATUSES:
                raise ValueError(f"invalid status {value!r}")
            if key == "labels":
                value = json.dumps(sorted(set(value)))
            sets.append(f"{key} = ?")
            params.append(value)
        if not sets:
            return self.get_bug(bug_id)
        sets.append("updated_at = ?")
        params.append(_now())
        params.append(bug_id)
        cur = self.conn.execute(
            f"UPDATE bugs SET {', '.join(sets)} WHERE id = ?", params
        )
        self.conn.commit()
        if cur.rowcount == 0:
            return None
        return self.get_bug(bug_id)

    def set_status(self, bug_id: int, status: str) -> Optional[dict]:
        if status not in STATUSES:
            raise ValueError(f"invalid status {status!r}; expected one of {STATUSES}")
        return self.update_bug(bug_id, status=status)

    def delete_bug(self, bug_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM bugs WHERE id = ?", (bug_id,))
        self.conn.commit()
        return cur.rowcount > 0

    # ----- comments --------------------------------------------------------------

    def add_comment(self, bug_id: int, body: str, author: str = "anonymous") -> Optional[dict]:
        if self.conn.execute("SELECT 1 FROM bugs WHERE id = ?", (bug_id,)).fetchone() is None:
            return None
        ts = _now()
        cur = self.conn.execute(
            "INSERT INTO comments (bug_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (bug_id, author, body, ts),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT * FROM comments WHERE id = ?", (cur.lastrowid,)
        ).fetchone()
        return dict(row)

    def list_comments(self, bug_id: int) -> list[dict]:
        rows = self.conn.execute(
            "SELECT * FROM comments WHERE bug_id = ? ORDER BY id", (bug_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    # ----- corpus for assignee suggestion ---------------------------------------

    def resolved_bugs(self) -> list[dict]:
        """All closed bugs with an assignee — the history we learn from."""
        return self.list_bugs(status="closed")

    def close(self) -> None:
        self.conn.close()
