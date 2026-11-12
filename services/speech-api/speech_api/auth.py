"""API keys: ev_<32 urlsafe chars>; only sha256(key) is stored."""
import hashlib
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import psycopg
from fastapi import Request

from .errors import ApiError

KEY_PREFIX = "ev_"


def new_key() -> str:
    return KEY_PREFIX + secrets.token_urlsafe(24)  # 24 bytes -> 32 urlsafe chars


def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def create_key(database_url: str, name: str, scopes: list[str], pipeline: bool = False,
               rate_limit: int = 60) -> str:
    bad = set(scopes) - {"tts", "stt"}
    if bad or not scopes:
        raise ValueError(f"scopes must be a non-empty subset of tts,stt (got {scopes})")
    key = new_key()
    with psycopg.connect(database_url) as conn:
        conn.execute(
            "INSERT INTO api_keys (name, prefix, hash, scopes, rate_limit, pipeline) VALUES (%s,%s,%s,%s,%s,%s)",
            (name, key[:8], hash_key(key), scopes, rate_limit, pipeline),
        )
    return key


@dataclass
class Caller:
    key_id: int
    name: str
    scopes: list[str]
    rate_limit: int
    pipeline: bool


class RateLimiter:
    """Sliding 60 s window per key (in-process; the gateway runs one worker)."""

    def __init__(self):
        self._hits: dict[int, deque] = defaultdict(deque)

    def check(self, caller: Caller) -> None:
        now = time.monotonic()
        q = self._hits[caller.key_id]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= caller.rate_limit:
            retry = max(1, int(60 - (now - q[0])) + 1)
            raise ApiError(429, "rate limit exceeded", headers={"Retry-After": str(retry)},
                           limit_per_minute=caller.rate_limit)
        q.append(now)


async def authenticate(request: Request, scope: str | None) -> Caller:
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer ") or not auth[7:].strip():
        raise ApiError(401, "missing api key", headers={"WWW-Authenticate": "Bearer"})
    key = auth[7:].strip()
    st = request.app.state
    async with st.db.connection() as conn:
        row = await (await conn.execute(
            "UPDATE api_keys SET last_used_at = now() WHERE hash = %s AND revoked_at IS NULL "
            "RETURNING id, name, scopes, rate_limit, pipeline",
            (hash_key(key),),
        )).fetchone()
    if row is None:
        raise ApiError(401, "invalid api key", headers={"WWW-Authenticate": "Bearer"})
    caller = Caller(*row)
    if scope and scope not in caller.scopes:
        raise ApiError(403, f"key lacks scope '{scope}'")
    st.limiter.check(caller)
    return caller
