"""EduVid Studio: builder + library + player pages and their API, all under /studio (Caddy proxies /studio/*)."""
import hashlib
import hmac
import logging
import os
import re
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool

from eduvid_common import storage

from . import llm, ncert, pipeline, store
from .schema import Script

log = logging.getLogger("studio")
STATIC = Path(__file__).resolve().parents[1] / "static"
COOKIE = "eduvid_studio"
SESSION_S = 14 * 24 * 3600
UUID = re.compile(r"^[0-9a-f-]{36}$")


def _secret() -> bytes:
    base = os.environ.get("STUDIO_SECRET") or (os.environ.get("STUDIO_PASSWORD", "") + os.environ.get("PIPELINE_API_KEY", ""))
    return hashlib.sha256(("studio|" + base).encode()).digest()


def _token(exp: int) -> str:
    return f"{exp}.{hmac.new(_secret(), str(exp).encode(), hashlib.sha256).hexdigest()}"


def _valid(tok: str | None) -> bool:
    if not tok or "." not in tok:
        return False
    exp, _, sig = tok.partition(".")
    if not exp.isdigit() or int(exp) < time.time():
        return False
    return hmac.compare_digest(_token(int(exp)), tok)


def authed(request: Request) -> None:
    if not os.environ.get("STUDIO_PASSWORD"):
        raise HTTPException(503, "STUDIO_PASSWORD is not set in .env")
    if not _valid(request.cookies.get(COOKIE)):
        raise HTTPException(401, "login required")


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop = threading.Event()
    if os.environ.get("STUDIO_PIPELINE", "1") == "1":
        threading.Thread(target=pipeline.loop, args=(stop,), daemon=True, name="pipeline").start()
    yield
    stop.set()


app = FastAPI(title="EduVid Studio", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/studio/static", StaticFiles(directory=STATIC), name="static")
api = APIRouter(prefix="/studio/api")
priv = APIRouter(prefix="/studio/api", dependencies=[Depends(authed)])


def _page(name: str) -> FileResponse:
    return FileResponse(STATIC / name, headers={"Cache-Control": "no-cache"})


# ---------- pages ----------

@app.get("/studio")
def studio_root():
    return RedirectResponse("/studio/", 308)


@app.get("/studio/")
def builder_page(request: Request):
    if not _valid(request.cookies.get(COOKIE)):
        return RedirectResponse("/studio/login", 303)
    return _page("builder.html")


@app.get("/studio/library")
def library_page(request: Request):
    if not _valid(request.cookies.get(COOKIE)):
        return RedirectResponse("/studio/login", 303)
    return _page("library.html")


@app.get("/studio/compare")
def compare_page(request: Request):
    if not _valid(request.cookies.get(COOKIE)):
        return RedirectResponse("/studio/login", 303)
    return _page("compare.html")


@app.get("/studio/login")
def login_page():
    return _page("login.html")


@app.get("/studio/watch/{vid}")
def watch_page(vid: str):
    if not UUID.match(vid):
        raise HTTPException(404)
    return _page("player.html")


@app.get("/studio/healthz")
def healthz():
    return {"ok": True}


# ---------- auth ----------

class Login(BaseModel):
    password: str


@api.post("/login")
def login(body: Login):
    pw = os.environ.get("STUDIO_PASSWORD", "")
    if not pw:
        raise HTTPException(503, "STUDIO_PASSWORD is not set in .env")
    time.sleep(0.4)                                                     # slow down guessing
    if not hmac.compare_digest(body.password.encode(), pw.encode()):
        raise HTTPException(401, "wrong password")
    r = JSONResponse({"ok": True})
    r.set_cookie(COOKIE, _token(int(time.time()) + SESSION_S), max_age=SESSION_S, httponly=True, secure=True,
                 samesite="lax", path="/studio")
    return r


@api.post("/logout")
def logout():
    r = JSONResponse({"ok": True})
    r.delete_cookie(COOKIE, path="/studio")
    return r


# ---------- config, NCERT, models, voices ----------

def _gateway() -> tuple[str, dict]:
    return (os.environ.get("SPEECH_API_URL", "http://speech-api:8000").rstrip("/"),
            {"Authorization": f"Bearer {os.environ.get('PIPELINE_API_KEY', '')}"})


@priv.get("/status")
def status():
    out = {"openrouter": bool(llm.key()), "balance_usd": llm.balance(), "ncert": False, "voices": False}
    try:
        out["ncert"] = bool(ncert.books())
    except Exception as e:
        out["ncert_error"] = str(e)[:200]
    try:
        base, h = _gateway()
        out["voices"] = httpx.get(f"{base}/v1/voices", headers=h, timeout=5).status_code == 200
    except httpx.HTTPError:
        pass
    return out


@priv.get("/ncert/books")
def books():
    return ncert.books()


@priv.get("/ncert/chapters")
def chapters(book: str):
    return ncert.chapters(book)


@priv.get("/ncert/sections")
def sections(chapter: str):
    return ncert.sections(chapter)


@priv.get("/ncert/unit/{uid}")
def unit(uid: str):
    u = ncert.preview(uid)
    if not u:
        raise HTTPException(404)
    return u


@priv.get("/models")
def models():
    try:
        return llm.models()
    except httpx.HTTPError as e:
        raise HTTPException(502, f"OpenRouter model list: {e}")


@priv.get("/voices")
def voices():
    base, h = _gateway()
    r = httpx.get(f"{base}/v1/voices", headers=h, timeout=10)
    if r.status_code >= 400:
        raise HTTPException(502, r.text[:300])
    return r.json()


class Preview(BaseModel):
    voice: str
    text: str


@priv.post("/voice-preview")
def voice_preview(body: Preview):
    model, _, vid = body.voice.partition(":")
    base, h = _gateway()
    r = httpx.post(f"{base}/v1/audio/speech", headers=h, timeout=120, json={
        "model": model, "voice": vid, "input": body.text[:300], "response_format": "mp3"})
    if r.status_code >= 400:
        raise HTTPException(502, r.text[:300])
    return Response(r.content, media_type="audio/mpeg")


# ---------- videos ----------

class NewVideo(BaseModel):
    target: dict
    settings: dict
    model: str
    compare_model: str | None = None


@priv.post("/videos")
def create_video(body: NewVideo):
    if not llm.key():
        raise HTTPException(400, "OPENROUTER_API_KEY is not set in .env")
    if not (body.target.get("unit_ids") or (body.target.get("text") or "").strip()):
        raise HTTPException(400, "pick at least one teaching unit or paste some text")
    title = body.target.get("label") or "Untitled lesson"
    models_ = [body.model] + ([body.compare_model] if body.compare_model and body.compare_model != body.model else [])
    cid = None
    out = []
    for m in models_:
        v = store.create(title=title, target=body.target, settings={**body.settings, "model": m}, model=m,
                         status="scripting", compare_id=cid)
        if len(models_) > 1 and cid is None:
            cid = v["id"]
            store.update(v["id"], compare_id=cid)
        pipeline.start_script(v["id"])
        out.append(v["id"])
    return {"ids": out}


@priv.get("/videos")
def list_videos():
    return store.listing()


def _video(vid: str) -> dict:
    if not UUID.match(vid):
        raise HTTPException(404)
    v = store.get(vid)
    if not v:
        raise HTTPException(404)
    return v


@priv.get("/videos/{vid}")
def get_video(vid: str):
    return _video(vid)


@priv.get("/videos/{vid}/events")
def video_events(vid: str, after: int = 0):
    v = _video(vid)
    return {"status": v["status"], "cost_usd": v["cost_usd"], "variants": v["variants"], "error": v["error"],
            "events": store.events(vid, after)}


class ScriptBody(BaseModel):
    script: dict


@priv.put("/videos/{vid}/script")
def save_script(vid: str, body: ScriptBody):
    v = _video(vid)
    if v["status"] not in ("review", "failed"):
        raise HTTPException(409, f"the script can't change while the video is {v['status']}")
    try:
        s = Script(**body.script)
    except ValidationError as e:
        raise HTTPException(422, "; ".join(f"{'.'.join(map(str, x['loc']))}: {x['msg']}" for x in e.errors()[:10]))
    store.update(vid, script=s.model_dump(), title=s.title.en or s.title.hi)
    return {"script": s.model_dump(), "speakable": s.speakable_problems()}


class Regen(BaseModel):
    note: str = ""


@priv.post("/videos/{vid}/scenes/{index}/regenerate")
async def regen_scene(vid: str, index: int, body: Regen):
    v = _video(vid)
    if v["status"] != "review" or not v["script"] or not 0 <= index < len(v["script"]["scenes"]):
        raise HTTPException(409, "only scenes of a script in review can be rewritten")
    try:
        script = await run_in_threadpool(pipeline.regenerate_scene, vid, index, body.note)
    except (llm.LLMError, ValueError, pipeline.CapReached) as e:
        raise HTTPException(502, str(e))
    return {"script": script, "speakable": Script(**script).speakable_problems()}


@priv.post("/videos/{vid}/approve")
def approve(vid: str):
    v = _video(vid)
    if v["status"] != "review":
        raise HTTPException(409, f"video is {v['status']}")
    try:
        pipeline.approve(vid)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"ok": True}


@priv.post("/videos/{vid}/retry")
def retry(vid: str):
    v = _video(vid)
    if v["status"] != "failed":
        raise HTTPException(409, f"video is {v['status']}")
    if not v["script"]:
        pipeline.start_script(vid)
    else:
        store.update(vid, status="review", error=None)
        store.event(vid, "script", "info", "Back to review: press Build to try again")
    return {"ok": True}


@priv.patch("/videos/{vid}/settings")
def patch_settings(vid: str, body: dict):
    v = _video(vid)
    if v["status"] not in ("review", "failed"):
        raise HTTPException(409, f"video is {v['status']}")
    allowed = {"mode", "aspect", "voice", "quality", "burn_captions", "chrome", "grid", "bk", "music", "sfx", "pace",
               "code_model", "cap_usd"}
    st = {**v["settings"], **{k: x for k, x in body.items() if k in allowed}}
    store.update(vid, settings=st)
    return st


@priv.delete("/videos/{vid}")
def delete_video(vid: str):
    _video(vid)
    store.delete(vid)
    return {"ok": True}


@priv.get("/videos/{vid}/{mode}/log")
def render_log(vid: str, mode: str):
    v = _video(vid)
    var = next((x for x in v["variants"] if x["mode"] == mode), None)
    key = (var or {}).get("log_key") or pipeline.prefix(vid) + f"{mode}/log.txt"
    try:
        return Response(storage.get_bytes(key)[-200000:], media_type="text/plain; charset=utf-8")
    except Exception:
        raise HTTPException(404, "no log yet")


# ---------- public: player data + media ----------

def _variant(v: dict, mode: str | None) -> dict:
    done = [x for x in v["variants"] if x.get("status") == "done"]
    if not done:
        raise HTTPException(404, "this video is not ready yet")
    return next((x for x in done if x["mode"] == mode), done[0])


@api.get("/watch/{vid}")
def watch_data(vid: str, mode: str | None = None):
    v = _video(vid)
    var = _variant(v, mode)
    import json
    man = json.loads(storage.get_bytes(var["manifest_key"]))
    man["modes"] = [x["mode"] for x in v["variants"] if x.get("status") == "done"]
    man["mode"] = var["mode"]
    man["video_url"] = f"/studio/media/{vid}/{var['mode']}/video.mp4"
    man["poster_url"] = f"/studio/media/{vid}/{var['mode']}/poster.jpg" if var.get("poster_key") else None
    return man


RANGE = re.compile(r"bytes=(\d*)-(\d*)")


@app.get("/studio/media/{vid}/{mode}/{name}")
def media(vid: str, mode: str, name: str, request: Request):
    v = _video(vid)
    var = next((x for x in v["variants"] if x["mode"] == mode and x.get("status") in ("done", "rendered")), None)
    if not var:
        raise HTTPException(404)
    if name == "sheet.jpg":
        authed(request)
    key = {"video.mp4": var.get("video_key"), "poster.jpg": var.get("poster_key"),
           "sheet.jpg": var.get("sheet_key")}.get(name)
    if not key:
        raise HTTPException(404)
    s3, bucket = storage.client(), storage.get_settings().s3_bucket
    head = s3.head_object(Bucket=bucket, Key=key)
    size, ctype = head["ContentLength"], head.get("ContentType") or "application/octet-stream"
    h = {"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"}
    rng = request.headers.get("range")
    if rng and (m := RANGE.match(rng)):
        a, b = m.group(1), m.group(2)
        start = int(a) if a else max(0, size - int(b or 0))
        end = min(int(b), size - 1) if (a and b) else size - 1
        if start >= size:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{size}"})
        obj = s3.get_object(Bucket=bucket, Key=key, Range=f"bytes={start}-{end}")
        return StreamingResponse(obj["Body"].iter_chunks(256 * 1024), 206, media_type=ctype, headers={
            **h, "Content-Range": f"bytes {start}-{end}/{size}", "Content-Length": str(end - start + 1)})
    obj = s3.get_object(Bucket=bucket, Key=key)
    return StreamingResponse(obj["Body"].iter_chunks(256 * 1024), media_type=ctype,
                             headers={**h, "Content-Length": str(size)})


app.include_router(api)
app.include_router(priv)
