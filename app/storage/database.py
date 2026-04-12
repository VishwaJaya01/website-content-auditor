"""Small SQLite initialization layer for the scaffold application."""

import sqlite3
from pathlib import Path


def get_connection(db_path: str) -> sqlite3.Connection:
    """Create a SQLite connection configured for dictionary-like row access."""

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db(db_path: str) -> None:
    """Initialize the minimal database schema used by the scaffold API."""

    database_path = Path(db_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)

    with get_connection(str(database_path)) as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY,
                input_url TEXT NOT NULL,
                normalized_url TEXT NOT NULL,
                status TEXT NOT NULL,
                progress REAL NOT NULL DEFAULT 0,
                cache_key TEXT,
                request_config_json TEXT,
                error_message TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS audit_results (
                job_id TEXT PRIMARY KEY,
                result_json TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY (job_id) REFERENCES jobs(job_id)
            );

            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                normalized_url TEXT NOT NULL,
                config_hash TEXT NOT NULL,
                job_id TEXT,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        _ensure_column(
            connection,
            table_name="jobs",
            column_name="request_config_json",
            column_definition="TEXT",
        )


def _ensure_column(
    connection: sqlite3.Connection,
    *,
    table_name: str,
    column_name: str,
    column_definition: str,
) -> None:
    columns = {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
    }
    if column_name not in columns:
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )
