from __future__ import annotations

import sqlite3

import app.config as config

FACTS_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS redeem_facts (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL,
  business_day TEXT NOT NULL,
  event_id INTEGER NOT NULL,
  batch_id INTEGER,
  status TEXT NOT NULL DEFAULT 'open',
  fact_kind TEXT NOT NULL DEFAULT 'redeem',
  compensates_fact_id INTEGER,
  compensates_batch_id INTEGER
);
'''

BATCHES_TABLE_SQL = '''
CREATE TABLE IF NOT EXISTS redeem_batches (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  business_day TEXT NOT NULL,
  status TEXT NOT NULL,
  fact_count INTEGER NOT NULL DEFAULT 0,
  total_amount REAL NOT NULL DEFAULT 0,
  sealed_at TEXT,
  note TEXT NOT NULL DEFAULT '',
  batch_kind TEXT NOT NULL DEFAULT 'redeem',
  compensates_batch_id INTEGER
);
'''

BASE_SCHEMA = '''
CREATE TABLE IF NOT EXISTS settings (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS campaigns (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL UNIQUE,
  title TEXT NOT NULL,
  face_value REAL NOT NULL,
  min_spend REAL NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS coupon_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  coupon_code TEXT NOT NULL,
  campaign_code TEXT NOT NULL,
  amount REAL NOT NULL DEFAULT 0,
  business_day TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  note TEXT NOT NULL DEFAULT '',
  compensates_fact_id INTEGER,
  created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
''' + FACTS_TABLE_SQL + BATCHES_TABLE_SQL

INDEXES = '''
CREATE INDEX IF NOT EXISTS idx_facts_day_kind
  ON redeem_facts(business_day, fact_kind, status);
CREATE INDEX IF NOT EXISTS idx_facts_coupon
  ON redeem_facts(coupon_code);
CREATE INDEX IF NOT EXISTS idx_facts_compensates_batch
  ON redeem_facts(compensates_batch_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_redeem_fact_per_coupon
  ON redeem_facts(coupon_code) WHERE fact_kind='redeem';
CREATE UNIQUE INDEX IF NOT EXISTS uq_return_fact_per_redeem
  ON redeem_facts(compensates_fact_id) WHERE fact_kind='return';
CREATE INDEX IF NOT EXISTS idx_events_compensates_fact
  ON coupon_events(compensates_fact_id);
CREATE INDEX IF NOT EXISTS idx_batches_kind_day
  ON redeem_batches(batch_kind, business_day);
CREATE INDEX IF NOT EXISTS idx_batches_compensates
  ON redeem_batches(compensates_batch_id);
'''


def connect(immediate: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    if immediate:
        conn.execute("BEGIN IMMEDIATE")
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone()
    return row is not None


def _table_sql(conn: sqlite3.Connection, name: str) -> str:
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return str(row["sql"] or "") if row else ""


def _columns(conn: sqlite3.Connection, name: str) -> list[str]:
    return [str(r["name"]) for r in conn.execute(f"PRAGMA table_info({name})").fetchall()]


def _add_missing_columns(
    conn: sqlite3.Connection, table: str, columns: dict[str, str]
) -> None:
    existing = set(_columns(conn, table))
    for name, ddl in columns.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}")


def _migrate_coupon_events(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "coupon_events"):
        return
    _add_missing_columns(conn, "coupon_events", {"compensates_fact_id": "INTEGER"})


def _migrate_redeem_facts(conn: sqlite3.Connection) -> None:
    """Move the original one-fact-per-coupon table to the compensating model.

    The first version of ``redeem_facts`` had ``coupon_code UNIQUE`` and no
    return-side columns.  A return fact has to coexist with the redeem fact of
    the same coupon, therefore the table-level unique constraint is replaced by
    a partial unique index over redeem facts only.  SQLite cannot drop an
    inline UNIQUE constraint, so the table is rebuilt once.
    """
    if not _table_exists(conn, "redeem_facts"):
        return

    old_columns = _columns(conn, "redeem_facts")
    old_sql = _table_sql(conn, "redeem_facts")
    needs_rebuild = "fact_kind" not in old_columns or "UNIQUE" in old_sql.upper()
    if not needs_rebuild:
        _add_missing_columns(
            conn,
            "redeem_facts",
            {
                "fact_kind": "TEXT NOT NULL DEFAULT 'redeem'",
                "compensates_fact_id": "INTEGER",
                "compensates_batch_id": "INTEGER",
            },
        )
        return

    conn.execute("ALTER TABLE redeem_facts RENAME TO redeem_facts_legacy")
    conn.execute(FACTS_TABLE_SQL)
    copyable = [
        c
        for c in (
            "id",
            "coupon_code",
            "campaign_code",
            "amount",
            "business_day",
            "event_id",
            "batch_id",
            "status",
            "fact_kind",
            "compensates_fact_id",
            "compensates_batch_id",
        )
        if c in old_columns
    ]
    cols = ", ".join(copyable)
    conn.execute(
        f"INSERT INTO redeem_facts({cols}) SELECT {cols} FROM redeem_facts_legacy"
    )
    conn.execute("DROP TABLE redeem_facts_legacy")


def _migrate_redeem_batches(conn: sqlite3.Connection) -> None:
    if not _table_exists(conn, "redeem_batches"):
        return
    _add_missing_columns(
        conn,
        "redeem_batches",
        {
            "batch_kind": "TEXT NOT NULL DEFAULT 'redeem'",
            "compensates_batch_id": "INTEGER",
        },
    )


def _migrate(conn: sqlite3.Connection) -> None:
    _migrate_coupon_events(conn)
    _migrate_redeem_facts(conn)
    _migrate_redeem_batches(conn)


def init_db() -> None:
    conn = connect()
    try:
        conn.executescript(BASE_SCHEMA)
        _migrate(conn)
        conn.executescript(INDEXES)
        conn.commit()
    finally:
        conn.close()
