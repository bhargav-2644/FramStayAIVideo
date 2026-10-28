"""SQLite lead table. Every step reads leads at one status and moves them on.

discovered -> qualified -> video_ready -> approved -> emailed -> replied
          \\-> rejected    \\-> failed                      \\-> opted_out
                                                            \\-> no_reply
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

STATUSES = (
    "discovered", "qualified", "rejected", "video_ready", "failed",
    "approved", "emailed", "replied", "opted_out", "no_reply",
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS leads (
    place_id      TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    region        TEXT NOT NULL,
    address       TEXT,
    rating        REAL,
    review_count  INTEGER,
    photo_count   INTEGER,
    website       TEXT,
    phone         TEXT,
    maps_url      TEXT,
    email         TEXT,
    email_source  TEXT,
    instagram     TEXT,
    score         INTEGER,
    photo_authors TEXT,
    video_path    TEXT,
    status        TEXT NOT NULL DEFAULT 'discovered',
    reason        TEXT,
    touches       INTEGER NOT NULL DEFAULT 0,
    last_sent_at  TEXT,
    replied_at    TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    place_id  TEXT NOT NULL,
    at        TEXT NOT NULL,
    kind      TEXT NOT NULL,
    detail    TEXT
);
CREATE TABLE IF NOT EXISTS opt_outs (
    email     TEXT PRIMARY KEY,
    at        TEXT NOT NULL
);
"""


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class LeadDB:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def add(self, lead: dict) -> bool:
        """Insert a newly discovered lead. Returns False if it was already known."""
        ts = now()
        fields = {**lead, "created_at": ts, "updated_at": ts}
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        cur = self.conn.execute(
            f"INSERT OR IGNORE INTO leads ({cols}) VALUES ({marks})", tuple(fields.values())
        )
        self.conn.commit()
        if cur.rowcount:
            self.log(lead["place_id"], "discovered", lead.get("name"))
        return bool(cur.rowcount)

    def update(self, place_id: str, **fields) -> None:
        if "status" in fields and fields["status"] not in STATUSES:
            raise ValueError(f"unknown status {fields['status']!r}")
        fields["updated_at"] = now()
        sets = ", ".join(f"{k} = ?" for k in fields)
        self.conn.execute(f"UPDATE leads SET {sets} WHERE place_id = ?", (*fields.values(), place_id))
        self.conn.commit()
        if "status" in fields:
            self.log(place_id, fields["status"], fields.get("reason"))

    def get(self, place_id: str) -> sqlite3.Row | None:
        return self.conn.execute("SELECT * FROM leads WHERE place_id = ?", (place_id,)).fetchone()

    def by_status(self, status: str, region: str | None = None, limit: int | None = None) -> list[sqlite3.Row]:
        sql = "SELECT * FROM leads WHERE status = ?"
        args: list = [status]
        if region:
            sql += " AND region = ?"
            args.append(region)
        sql += " ORDER BY score DESC, created_at"
        if limit:
            sql += f" LIMIT {int(limit)}"
        return self.conn.execute(sql, args).fetchall()

    def counts(self, region: str | None = None) -> dict[str, int]:
        sql = "SELECT status, COUNT(*) FROM leads"
        args = []
        if region:
            sql += " WHERE region = ?"
            args.append(region)
        rows = self.conn.execute(sql + " GROUP BY status", args).fetchall()
        return {r[0]: r[1] for r in rows}

    def sent_today(self) -> int:
        today = now()[:10]
        return self.conn.execute(
            "SELECT COUNT(*) FROM events WHERE kind = 'sent' AND substr(at, 1, 10) = ?", (today,)
        ).fetchone()[0]

    def log(self, place_id: str, kind: str, detail: str | None = None) -> None:
        self.conn.execute(
            "INSERT INTO events (place_id, at, kind, detail) VALUES (?, ?, ?, ?)",
            (place_id, now(), kind, detail),
        )
        self.conn.commit()

    def opt_out(self, email: str) -> None:
        self.conn.execute(
            "INSERT OR IGNORE INTO opt_outs (email, at) VALUES (?, ?)", (email.lower(), now())
        )
        self.conn.commit()

    def is_opted_out(self, email: str) -> bool:
        return self.conn.execute(
            "SELECT 1 FROM opt_outs WHERE email = ?", (email.lower(),)
        ).fetchone() is not None
