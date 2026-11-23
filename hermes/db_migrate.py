from __future__ import annotations

from sqlalchemy import inspect, text

from hermes.db import get_engine


LEAD_COLUMNS = {
    "record_kind": "VARCHAR(32) DEFAULT 'listing'",
    "posted_at": "DATETIME",
    "expires_at": "DATETIME",
    "expired": "BOOLEAN DEFAULT 0",
    "phone_captured": "VARCHAR(64)",
}


def migrate_schema() -> list[str]:
    """Add new columns to existing SQLite DBs without wiping data."""
    engine = get_engine()
    applied: list[str] = []
    insp = inspect(engine)
    existing = {c["name"] for c in insp.get_columns("leads")} if "leads" in insp.get_table_names() else set()
    with engine.begin() as conn:
        for col, ddl in LEAD_COLUMNS.items():
            if col not in existing:
                conn.execute(text(f"ALTER TABLE leads ADD COLUMN {col} {ddl}"))
                applied.append(f"leads.{col}")
        # Normalize legacy stages → listing vocabulary
        conn.execute(
            text(
                "UPDATE leads SET record_kind='listing' "
                "WHERE record_kind IS NULL OR record_kind=''"
            )
        )
        conn.execute(
            text(
                "UPDATE leads SET stage='listing' "
                "WHERE stage IN ('signal','lead','qualified') AND "
                "(record_kind IS NULL OR record_kind='listing')"
            )
        )
        conn.execute(
            text(
                "UPDATE leads SET record_kind='lead' "
                "WHERE stage IN ('outreach','replied','negotiation','won','contacted')"
            )
        )
    return applied
