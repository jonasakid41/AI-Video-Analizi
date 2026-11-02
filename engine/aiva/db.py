"""SQLite veritabanı: data/aiva.sqlite. Her iş parçacığı kendi bağlantısını kullanır."""

from __future__ import annotations

import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from . import paths

_local = threading.local()
_db_path: Path | None = None

SCHEMA_V1 = """
CREATE TABLE cases(
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE evidence(
  id INTEGER PRIMARY KEY,
  case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  original_name TEXT NOT NULL,
  source_path TEXT NOT NULL DEFAULT '',
  sha256 TEXT NOT NULL DEFAULT '',
  size INTEGER NOT NULL DEFAULT 0,
  camera TEXT NOT NULL DEFAULT '',
  status TEXT NOT NULL DEFAULT 'beklemede',
  status_detail TEXT NOT NULL DEFAULT '',
  sniff TEXT, strategy TEXT, probe TEXT,
  duration REAL, width INTEGER, height INTEGER, fps REAL, codec TEXT,
  has_proxy INTEGER NOT NULL DEFAULT 0,
  analyzed INTEGER NOT NULL DEFAULT 0,
  analysis_info TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE time_mappings(
  id INTEGER PRIMARY KEY,
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  version INTEGER NOT NULL,
  data TEXT NOT NULL,
  reason TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL
);
CREATE TABLE activity(
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  t REAL NOT NULL, score REAL NOT NULL
);
CREATE INDEX ix_activity ON activity(evidence_id, t);
CREATE TABLE segments(
  id INTEGER PRIMARY KEY,
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  kind TEXT NOT NULL, t0 REAL NOT NULL, t1 REAL NOT NULL, info TEXT
);
CREATE TABLE tracks(
  id INTEGER PRIMARY KEY,
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  cls TEXT NOT NULL, t0 REAL NOT NULL, t1 REAL NOT NULL,
  n INTEGER NOT NULL, best_conf REAL NOT NULL,
  thumb TEXT, colors TEXT, plate TEXT, plate_conf REAL,
  face_count INTEGER NOT NULL DEFAULT 0,
  embedding BLOB, path TEXT, rois TEXT
);
CREATE INDEX ix_tracks ON tracks(evidence_id, t0);
CREATE TABLE detections(
  id INTEGER PRIMARY KEY,
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  track_id INTEGER, t REAL NOT NULL, cls TEXT NOT NULL, conf REAL NOT NULL,
  x REAL NOT NULL, y REAL NOT NULL, w REAL NOT NULL, h REAL NOT NULL
);
CREATE INDEX ix_det ON detections(evidence_id, t);
CREATE TABLE frame_embeddings(
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  t REAL NOT NULL, embedding BLOB NOT NULL
);
CREATE INDEX ix_femb ON frame_embeddings(evidence_id, t);
CREATE TABLE faces(
  id INTEGER PRIMARY KEY,
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  track_id INTEGER, t REAL NOT NULL,
  x REAL NOT NULL, y REAL NOT NULL, w REAL NOT NULL, h REAL NOT NULL,
  score REAL NOT NULL, quality REAL NOT NULL DEFAULT 0,
  thumb TEXT, embedding BLOB, cluster INTEGER
);
CREATE INDEX ix_faces ON faces(evidence_id, t);
CREATE TABLE plates(
  id INTEGER PRIMARY KEY,
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  track_id INTEGER, t REAL NOT NULL,
  text TEXT NOT NULL, raw TEXT NOT NULL, conf REAL NOT NULL,
  valid_tr INTEGER NOT NULL DEFAULT 0, thumb TEXT
);
CREATE INDEX ix_plates ON plates(evidence_id, t);
CREATE TABLE ocr_readings(
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  t REAL NOT NULL, text TEXT NOT NULL, parsed TEXT
);
CREATE TABLE rois(
  id INTEGER PRIMARY KEY,
  evidence_id INTEGER NOT NULL REFERENCES evidence(id) ON DELETE CASCADE,
  name TEXT NOT NULL, kind TEXT NOT NULL, points TEXT NOT NULL,
  created_at TEXT NOT NULL
);
CREATE TABLE queries(
  id INTEGER PRIMARY KEY,
  case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  question TEXT NOT NULL, options TEXT, plan TEXT,
  status TEXT NOT NULL DEFAULT 'beklemede',
  results TEXT, answer TEXT,
  cost REAL NOT NULL DEFAULT 0, tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
  error TEXT, created_at TEXT NOT NULL, finished_at TEXT
);
CREATE TABLE ai_calls(
  id INTEGER PRIMARY KEY,
  case_id INTEGER, query_id INTEGER,
  role TEXT NOT NULL, model TEXT NOT NULL,
  request TEXT, response TEXT,
  tokens_in INTEGER NOT NULL DEFAULT 0, tokens_out INTEGER NOT NULL DEFAULT 0,
  cost REAL NOT NULL DEFAULT 0, ok INTEGER NOT NULL DEFAULT 1,
  created_at TEXT NOT NULL
);
CREATE TABLE findings(
  id INTEGER PRIMARY KEY,
  case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  evidence_id INTEGER REFERENCES evidence(id) ON DELETE SET NULL,
  t REAL, title TEXT NOT NULL, note TEXT NOT NULL DEFAULT '',
  source TEXT NOT NULL DEFAULT 'elle', confidence REAL,
  image TEXT, status TEXT NOT NULL DEFAULT 'aday', data TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE history(
  id INTEGER PRIMARY KEY,
  case_id INTEGER, evidence_id INTEGER,
  action TEXT NOT NULL, detail TEXT,
  created_at TEXT NOT NULL
);
CREATE INDEX ix_history ON history(case_id, id);
CREATE TABLE jobs(
  id INTEGER PRIMARY KEY,
  case_id INTEGER, evidence_id INTEGER,
  kind TEXT NOT NULL, status TEXT NOT NULL,
  progress REAL NOT NULL DEFAULT 0, message TEXT NOT NULL DEFAULT '',
  params TEXT, result TEXT, error TEXT,
  created_at TEXT NOT NULL, started_at TEXT, finished_at TEXT
);
"""

SCHEMA_V2 = """
ALTER TABLE queries ADD COLUMN labels TEXT;
CREATE TABLE evaluations(
  id INTEGER PRIMARY KEY,
  case_id INTEGER NOT NULL REFERENCES cases(id) ON DELETE CASCADE,
  query_id INTEGER NOT NULL REFERENCES queries(id) ON DELETE CASCADE,
  models TEXT NOT NULL,
  results TEXT,
  status TEXT NOT NULL DEFAULT 'beklemede',
  error TEXT,
  created_at TEXT NOT NULL,
  finished_at TEXT
);
"""

MIGRATIONS: list[str] = [SCHEMA_V1, SCHEMA_V2]


def init(path: Path | None = None) -> Path:
    """Veritabanını açar ve şemayı günceller."""
    global _db_path
    close_thread_connection()
    _db_path = path or (paths.data_dir() / "aiva.sqlite")
    _db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = _open(_db_path)
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, script in enumerate(MIGRATIONS[version:], start=version + 1):
        conn.executescript(script)
        conn.execute(f"PRAGMA user_version = {i}")
    conn.commit()
    conn.close()
    return _db_path


def _open(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path, timeout=30, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def conn() -> sqlite3.Connection:
    if _db_path is None:
        init()
    c = getattr(_local, "conn", None)
    if c is None or getattr(_local, "path", None) != _db_path:
        c = _open(_db_path)  # type: ignore[arg-type]
        _local.conn = c
        _local.path = _db_path
    return c


def close_thread_connection() -> None:
    c = getattr(_local, "conn", None)
    if c is not None:
        c.close()
        _local.conn = None


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    c = conn()
    try:
        yield c
        c.commit()
    except BaseException:
        c.rollback()
        raise


def row(sql: str, args: tuple | list = ()) -> dict[str, Any] | None:
    r = conn().execute(sql, args).fetchone()
    return dict(r) if r else None


def rows(sql: str, args: tuple | list = ()) -> list[dict[str, Any]]:
    return [dict(r) for r in conn().execute(sql, args).fetchall()]


def execute(sql: str, args: tuple | list = ()) -> int:
    with tx() as c:
        cur = c.execute(sql, args)
        return cur.lastrowid or cur.rowcount


def insert(table: str, data: dict[str, Any]) -> int:
    cols = ", ".join(data)
    marks = ", ".join("?" for _ in data)
    with tx() as c:
        cur = c.execute(f"INSERT INTO {table} ({cols}) VALUES ({marks})", list(data.values()))
        return int(cur.lastrowid)


def update(table: str, id_: int, data: dict[str, Any]) -> None:
    if not data:
        return
    sets = ", ".join(f"{k} = ?" for k in data)
    with tx() as c:
        c.execute(f"UPDATE {table} SET {sets} WHERE id = ?", [*data.values(), id_])
