"""Reads `docker compose config --format json` on stdin. Exit 1 if a container would see a secret it must not.

GPU engines run third-party model code: no secrets at all. Render workers run LLM-written scene code in Chrome: they
need the database and object store, but never API keys or passwords.
"""
import json
import sys

ENGINE_SECRETS = {"DATABASE_URL", "POSTGRES_PASSWORD", "S3_ACCESS_KEY", "S3_SECRET_KEY", "PIPELINE_API_KEY",
                  "ANTHROPIC_API_KEY", "SESSION_SECRET", "MINIO_ROOT_PASSWORD", "OPENROUTER_API_KEY",
                  "STUDIO_PASSWORD", "STUDIO_SECRET", "NCERT_DATABASE_URL"}
RENDER_SECRETS = (ENGINE_SECRETS - {"DATABASE_URL", "S3_ACCESS_KEY", "S3_SECRET_KEY"}) | {"HF_TOKEN"}

bad = {}
for name, svc in json.load(sys.stdin)["services"].items():
    if name.startswith(("tts-", "asr-")):
        banned = ENGINE_SECRETS
    elif name.startswith("render-worker"):
        banned = RENDER_SECRETS
    else:
        continue
    leaked = sorted(banned & set(svc.get("environment") or {}))
    if leaked:
        bad[name] = leaked
for k, v in bad.items():
    print(f"{k}: sees {', '.join(v)}")
print("engine/render env OK" if not bad else f"{len(bad)} container(s) see secrets")
sys.exit(1 if bad else 0)
