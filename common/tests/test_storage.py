import os
import uuid

import pytest

from eduvid_common import storage

pytestmark = pytest.mark.skipif(not os.environ.get("S3_ENDPOINT"), reason="S3_ENDPOINT not set")


@pytest.fixture
def key():
    k = f"test/{uuid.uuid4().hex}/blob.bin"
    yield k
    storage.delete(k)


def test_put_get_roundtrip(tmp_path, key):
    data = os.urandom(4096)
    storage.put_bytes(key, data, "application/octet-stream")
    assert storage.exists(key)
    out = storage.get_file(key, tmp_path / "sub" / "out.bin")
    assert out.read_bytes() == data


def test_put_file_and_missing(tmp_path, key):
    src = tmp_path / "in.txt"
    src.write_text("hello")
    storage.put_file(key, src)
    assert storage.exists(key)
    assert not storage.exists(key + ".missing")


def test_presigned_url(key):
    storage.put_bytes(key, b"x", "text/plain")
    url = storage.presigned_url(key, expires_s=60)
    assert key in url and "X-Amz-Signature" in url
