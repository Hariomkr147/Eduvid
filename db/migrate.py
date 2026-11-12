"""Apply db/migrations/*.sql in filename order, each in its own transaction.

Applied filenames are recorded in schema_migrations; already-applied files are skipped.
Usage: python db/migrate.py   (DATABASE_URL from the environment)
"""
import os
import sys
from pathlib import Path

import psycopg

MIGRATIONS = Path(__file__).resolve().parent / "migrations"

BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    id bigserial PRIMARY KEY,
    created_at timestamptz NOT NULL DEFAULT now(),
    filename text NOT NULL UNIQUE
)"""


def migrate(url: str, directory: Path = MIGRATIONS) -> list[str]:
    applied_now: list[str] = []
    with psycopg.connect(url) as conn:
        conn.execute(BOOTSTRAP)
        conn.commit()
        done = {r[0] for r in conn.execute("SELECT filename FROM schema_migrations")}
        for path in sorted(directory.glob("*.sql")):
            if path.name in done:
                continue
            with conn.transaction():
                conn.execute(path.read_text())
                conn.execute("INSERT INTO schema_migrations (filename) VALUES (%s)", (path.name,))
            applied_now.append(path.name)
            print(f"applied {path.name}")
    return applied_now


if __name__ == "__main__":
    url = os.environ.get("DATABASE_URL")
    if not url:
        sys.exit("DATABASE_URL is not set")
    names = migrate(url)
    print(f"migrations up to date ({len(names)} applied now)")
