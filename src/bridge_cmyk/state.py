"""Estado local: anti-duplicata + posição do último sync (SQLite)."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from . import config

STATE_DIR = config.app_dir() / "data"
STATE_DB = STATE_DIR / "state.db"


def _conn() -> sqlite3.Connection:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(STATE_DB))
    con.execute(
        """CREATE TABLE IF NOT EXISTS synced (
            espresso_id TEXT PRIMARY KEY,
            mubisys_id  TEXT,
            value       REAL,
            supplier    TEXT,
            due_date    TEXT,
            synced_at   TEXT
        )"""
    )
    con.execute(
        """CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY, value TEXT
        )"""
    )
    return con


def last_sync() -> str | None:
    con = _conn()
    try:
        row = con.execute("SELECT value FROM meta WHERE key='last_sync'").fetchone()
        return row[0] if row else None
    finally:
        con.close()


def set_last_sync(iso: str) -> None:
    con = _conn()
    try:
        con.execute("INSERT OR REPLACE INTO meta(key,value) VALUES('last_sync',?)", (iso,))
        con.commit()
    finally:
        con.close()


def already_synced(espresso_id: str) -> bool:
    con = _conn()
    try:
        row = con.execute(
            "SELECT 1 FROM synced WHERE espresso_id=?", (espresso_id,)
        ).fetchone()
        return row is not None
    finally:
        con.close()


def mark_synced(espresso_id: str, mubisys_id: str, value: float,
                supplier: str, due: str) -> None:
    con = _conn()
    try:
        con.execute(
            "INSERT OR REPLACE INTO synced VALUES(?,?,?,?,?,?)",
            (espresso_id, mubisys_id, value, supplier, due,
             datetime.now().isoformat()),
        )
        con.commit()
    finally:
        con.close()


def sync_count() -> int:
    con = _conn()
    try:
        return con.execute("SELECT COUNT(*) FROM synced").fetchone()[0]
    finally:
        con.close()
