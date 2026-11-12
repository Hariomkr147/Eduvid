import os

import psycopg
import pytest


@pytest.fixture(scope="session")
def pg_url() -> str:
    """A freshly migrated throwaway database on the compose Postgres (never the real one)."""
    if not os.environ.get("DATABASE_URL"):
        pytest.skip("DATABASE_URL not set (run through `make test`)")
    from eduvid_common import db
    from eduvid_common.testing import fresh_test_db

    url = fresh_test_db()
    yield url
    db.close_pool()


@pytest.fixture
def conn(pg_url):
    """A connection whose work is rolled back after the test."""
    with psycopg.connect(pg_url) as c:
        yield c
        c.rollback()
