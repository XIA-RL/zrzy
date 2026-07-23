from __future__ import annotations

import sqlite3
from pathlib import Path


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS jobs (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  status TEXT NOT NULL,
  stage TEXT NOT NULL,
  input_text TEXT NOT NULL,
  plan_json TEXT,
  steps_json TEXT,
  result_json TEXT,
  error TEXT,
  artifacts_json TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
  id TEXT PRIMARY KEY,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,
  state TEXT NOT NULL,
  messages_json TEXT NOT NULL DEFAULT '[]',
  plan_json TEXT NOT NULL DEFAULT '{}',
  artifacts_json TEXT NOT NULL DEFAULT '{}',
  job_id TEXT,
  prefill_json TEXT
);
"""


def connect(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as conn:
        conn.executescript(SCHEMA_SQL)

        # 兼容旧数据库：jobs 表补列
        jobs_cols = {row[1] for row in conn.execute("PRAGMA table_info(jobs)").fetchall()}
        if "steps_json" not in jobs_cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN steps_json TEXT")

        conn.commit()
