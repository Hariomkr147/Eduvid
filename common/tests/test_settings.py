import pytest
from pydantic import ValidationError

from eduvid_common.settings import get_settings


@pytest.fixture(autouse=True)
def _clear_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db:5432/eduvid")
    monkeypatch.setenv("S3_ENDPOINT", "http://minio:9000")
    s = get_settings()
    assert s.database_url == "postgresql://u:p@db:5432/eduvid"
    assert s.s3_endpoint == "http://minio:9000"
    assert s.s3_bucket == "eduvid"


def test_missing_required_raises(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(ValidationError):
        get_settings()
