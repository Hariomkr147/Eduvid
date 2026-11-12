import re

from speech_api.auth import hash_key, new_key

pytestmark = __import__("pytest").mark.anyio


def test_key_format():
    k = new_key()
    assert re.fullmatch(r"ev_[A-Za-z0-9_-]{32}", k)
    assert hash_key(k) != k and len(hash_key(k)) == 64


async def test_no_key_401(gateway):
    r = await gateway.post("/v1/audio/speech", json={"model": "kokoro", "input": "hi", "voice": "am_michael"})
    assert r.status_code == 401
    assert r.json()["error"]


async def test_bad_key_401(gateway):
    r = await gateway.post("/v1/audio/speech", headers={"Authorization": "Bearer ev_nope"},
                           json={"model": "kokoro", "input": "hi", "voice": "am_michael"})
    assert r.status_code == 401


async def test_wrong_scope_403(gateway, make_key):
    key = make_key(scopes=["stt"])
    r = await gateway.post("/v1/audio/speech", headers={"Authorization": f"Bearer {key}"},
                           json={"model": "kokoro", "input": "hi", "voice": "am_michael"})
    assert r.status_code == 403
    assert "tts" in r.json()["error"]


async def test_revoked_key_401(gateway, make_key, db):
    key = make_key()
    db.execute("UPDATE api_keys SET revoked_at = now() WHERE hash = %s", (hash_key(key),))
    r = await gateway.get("/v1/models", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 401


async def test_rate_limit_429(gateway, make_key):
    key = make_key(rate_limit=2)
    h = {"Authorization": f"Bearer {key}"}
    codes = [(await gateway.get("/v1/models", headers=h)).status_code for _ in range(3)]
    assert codes == [200, 200, 429]
