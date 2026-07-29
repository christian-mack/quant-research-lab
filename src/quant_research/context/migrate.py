"""Idempotent schema application for the PCS database.

``migrate.py`` applies ``schema.sql`` inside a single transaction and records the
applied version in ``pcs_schema_version``. Running it repeatedly is a no-op once
the current version is recorded, so it is safe to call on every ``docker compose
up`` or from CI.
"""

from __future__ import annotations

from pathlib import Path

import psycopg

from quant_research.context.config import SCHEMA_VERSION, PCSConfig, get_config

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def _current_version(conn: psycopg.Connection) -> int | None:
    """Return the highest applied schema version, or None if unmigrated."""
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('public.pcs_schema_version')")
        (exists,) = cur.fetchone()
        if exists is None:
            return None
        cur.execute("SELECT COALESCE(MAX(version), 0) FROM pcs_schema_version")
        (version,) = cur.fetchone()
        return int(version)


def migrate(config: PCSConfig | None = None) -> int:
    """Apply the schema if not already at the current version.

    Args:
        config: Optional configuration; defaults to :func:`get_config`.

    Returns:
        The schema version in effect after this call.
    """
    config = config or get_config()
    sql = SCHEMA_PATH.read_text(encoding="utf-8")

    with psycopg.connect(config.dsn()) as conn:
        current = _current_version(conn)
        if current is not None and current >= SCHEMA_VERSION:
            return current
        with conn.transaction():
            conn.execute(sql)
            conn.execute(
                "INSERT INTO pcs_schema_version (version) VALUES (%s) "
                "ON CONFLICT (version) DO NOTHING",
                (SCHEMA_VERSION,),
            )
        return SCHEMA_VERSION


def main() -> None:
    """CLI entry point: apply migrations and print the resulting version."""
    version = migrate()
    print(f"PCS schema at version {version}")


if __name__ == "__main__":
    main()
