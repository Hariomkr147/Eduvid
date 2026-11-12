"""Test helpers shared by every service's test suite."""
import os
from pathlib import Path

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo

TEST_DB = "eduvid_test"


def _find_migrate():
    for base in (Path(__file__).resolve().parents[2], Path("/app")):
        p = base / "db" / "migrate.py"
        if p.exists():
            return p
    raise FileNotFoundError("db/migrate.py not found (mount the repo at /app)")


def fresh_test_db(url: str | None = None) -> str:
    """Drop, recreate and migrate a throwaway database on the same server; return its URL.

    Also points DATABASE_URL at it and resets cached settings/pools, so code under test uses it.
    """
    url = url or os.environ["DATABASE_URL"]
    if conninfo_to_dict(url).get("dbname") != TEST_DB:
        with psycopg.connect(make_conninfo(url, dbname="postgres"), autocommit=True) as admin:
            admin.execute("SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname=%s", (TEST_DB,))
            admin.execute(f"DROP DATABASE IF EXISTS {TEST_DB}")
            admin.execute(f"CREATE DATABASE {TEST_DB}")
        url = make_conninfo(url, dbname=TEST_DB)
    import importlib.util

    spec = importlib.util.spec_from_file_location("eduvid_migrate", _find_migrate())
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    mod.migrate(url)

    os.environ["DATABASE_URL"] = url
    from . import db
    from .settings import get_settings

    get_settings.cache_clear()
    db.close_pool()
    return url
