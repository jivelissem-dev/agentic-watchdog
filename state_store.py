"""
state_store.py

Lightweight SQLite persistence for the watchdog. Two tables:

  runs   -- one row per pipeline execution
  events -- one row per step attempt (success, failure, remediation applied,
            escalation)

SQLite is used instead of Airtable/Supabase so this repo runs standalone
with zero external accounts. Swapping the functions below for Airtable
or Supabase calls is a drop-in change -- the rest of the codebase only
calls these four functions.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).parent / "watchdog.db"


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db():
    conn = _connect()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS runs (
            run_id TEXT PRIMARY KEY,
            started_at TEXT,
            ended_at TEXT,
            status TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_id TEXT,
            step TEXT,
            event_type TEXT,
            error_signature TEXT,
            remediation_tried TEXT,
            outcome TEXT,
            timestamp TEXT
        )
    """)
    conn.commit()
    conn.close()


def start_run():
    run_id = str(uuid.uuid4())[:8]
    conn = _connect()
    conn.execute(
        "INSERT INTO runs (run_id, started_at, status) VALUES (?, ?, ?)",
        (run_id, datetime.now(timezone.utc).isoformat(), "Running"),
    )
    conn.commit()
    conn.close()
    return run_id


def end_run(run_id, status):
    conn = _connect()
    conn.execute(
        "UPDATE runs SET ended_at = ?, status = ? WHERE run_id = ?",
        (datetime.now(timezone.utc).isoformat(), status, run_id),
    )
    conn.commit()
    conn.close()


def log_event(run_id, step, event_type, error_signature=None,
              remediation_tried=None, outcome=None):
    conn = _connect()
    conn.execute(
        """INSERT INTO events
           (run_id, step, event_type, error_signature, remediation_tried, outcome, timestamp)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (run_id, step, event_type, error_signature, remediation_tried, outcome,
         datetime.now(timezone.utc).isoformat()),
    )
    conn.commit()
    conn.close()
