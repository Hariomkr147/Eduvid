"""Manage speech API keys.

  python manage_keys.py create --name X --scopes tts,stt [--pipeline] [--rate-limit 60]
  python manage_keys.py list
  python manage_keys.py revoke --name X | --id N

Run inside the stack: docker compose run --rm speech-api python manage_keys.py ...
The key is printed once and never stored (only its sha256).
"""
import argparse
import os
import sys

import psycopg

from speech_api.auth import create_key


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("create")
    c.add_argument("--name", required=True)
    c.add_argument("--scopes", required=True, help="comma list of tts,stt")
    c.add_argument("--pipeline", action="store_true", help="internal pipeline key (scheduled first)")
    c.add_argument("--rate-limit", type=int, default=None, help="requests/minute (default 60; pipeline 100000)")
    sub.add_parser("list")
    r = sub.add_parser("revoke")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--name")
    g.add_argument("--id", type=int)
    a = p.parse_args(argv)

    url = os.environ["DATABASE_URL"]
    if a.cmd == "create":
        rate = a.rate_limit if a.rate_limit is not None else (100000 if a.pipeline else 60)
        try:
            key = create_key(url, a.name, [s.strip() for s in a.scopes.split(",") if s.strip()], a.pipeline, rate)
        except ValueError as e:
            print(e, file=sys.stderr)
            return 2
        print(key)
        return 0
    with psycopg.connect(url) as conn:
        if a.cmd == "list":
            rows = conn.execute(
                "SELECT id, name, prefix, scopes, rate_limit, pipeline, created_at::date, last_used_at, revoked_at "
                "FROM api_keys ORDER BY id").fetchall()
            for row in rows:
                print(*row, sep="\t")
            return 0
        where, val = ("name", a.name) if a.name else ("id", a.id)
        n = conn.execute(f"UPDATE api_keys SET revoked_at = now() WHERE {where} = %s AND revoked_at IS NULL",
                         (val,)).rowcount
        print(f"revoked {n} key(s)")
        return 0 if n else 1


if __name__ == "__main__":
    sys.exit(main())
