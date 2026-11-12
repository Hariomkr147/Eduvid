"""Reads `docker compose config --format json` on stdin. Exit 1 if a GPU engine container would see a secret."""
import json
import sys

SECRETS = {"DATABASE_URL", "POSTGRES_PASSWORD", "S3_ACCESS_KEY", "S3_SECRET_KEY", "PIPELINE_API_KEY",
           "ANTHROPIC_API_KEY", "SESSION_SECRET", "MINIO_ROOT_PASSWORD"}
bad = {}
for name, svc in json.load(sys.stdin)["services"].items():
    if name.startswith(("tts-", "asr-")):
        leaked = sorted(SECRETS & set(svc.get("environment") or {}))
        if leaked:
            bad[name] = leaked
for k, v in bad.items():
    print(f"{k}: sees {', '.join(v)}")
print("engine env OK" if not bad else f"{len(bad)} engine(s) see secrets")
sys.exit(1 if bad else 0)
