"""Build pipeline (spec 2026-11-12 §3): script → review → voice → words → (code) → render per variant → publish.

Scripts and LLM scene code run in background threads in this process. Voice, words and render run in the existing
workers through the jobs table; `tick()` (every few seconds) advances each video when its job is done. All state
lives in studio_videos, so a restart picks up where it left off.
"""
import io
import json
import logging
import re
import subprocess
import tarfile
import tempfile
import threading
import traceback
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from pydantic import ValidationError

from eduvid_common import jobs
from eduvid_common import storage

from . import llm, ncert, prompts, store
from .schema import REVOLVES, UNROLLS, Script, voice_script

log = logging.getLogger("studio.pipeline")
ENGINE = Path(__file__).resolve().parents[1] / "engine"      # mounted/copied: styles/nce-lesson + shared/tools
STYLE = ENGINE / "styles" / "nce-lesson"
TOOLS = ENGINE / "shared" / "tools"
DEFAULT_VOICE = {"hinglish": "indicf5:ref-female", "hindi": "indicf5:ref-female", "english": "kokoro:am_michael"}
_running: set[str] = set()
_lock = threading.Lock()


def prefix(vid: str) -> str:
    return f"studio/{vid}/"


def variants_for(mode: str) -> list[str]:
    return {"template": ["template"], "llm": ["llm"], "both": ["template", "llm"]}.get(mode, ["template"])


def _thread(key: str, fn, *args) -> bool:
    with _lock:
        if key in _running:
            return False
        _running.add(key)

    def run():
        try:
            fn(*args)
        finally:
            with _lock:
                _running.discard(key)
    threading.Thread(target=run, daemon=True, name=key).start()
    return True


class CapReached(RuntimeError):
    pass


def _cap(settings: dict) -> float:
    return float(settings.get("cap_usd") or 0)


def _spend(vid: str, usd: float, settings: dict) -> None:
    total = store.add_cost(vid, usd)
    cap = _cap(settings)
    if cap and total >= cap:
        raise CapReached(f"spending cap ${cap:.2f} reached (spent ${total:.2f})")


def _ask(vid: str, settings: dict, model: str, messages: list[dict], **kw):
    """One JSON LLM call under the video's spending cap: refused before the call once the cap is used up, and
    what it costs is recorded even when it fails (paid empty replies, a reply that was not JSON)."""
    cap = _cap(settings)
    if cap and (spent := store.cost(vid)) >= cap:
        raise CapReached(f"spending cap ${cap:.2f} reached (spent ${spent:.2f})")
    try:
        obj, cost = llm.chat_json(model, messages, **kw)
    except llm.LLMError as e:
        if e.cost:
            store.add_cost(vid, e.cost)
        raise
    _spend(vid, cost, settings)
    return obj


# ---------- 1. script ----------

def start_script(vid: str) -> None:
    _thread(f"script:{vid}", write_script, vid)


def structure_problems(s: Script, settings: dict) -> list[str]:
    """A script that is too short or ignores the builder settings is sent back to the model."""
    out = []
    minutes = float(settings.get("minutes", 3))
    target = minutes * (115 if s.language != "english" else 135)
    words = sum(len(ln.say.split()) for sc in s.scenes for ln in sc.lines)
    if words < 0.5 * target:
        out.append(f"the script is far too short: {words} spoken words, but a {minutes:g}-minute lesson needs about "
                   f"{target:.0f}. Write the complete lesson: about {prompts.scene_target(minutes)} scenes, each with "
                   "2-6 lines, teaching everything in the NCERT material")
    if len(s.scenes) < min(4, prompts.scene_target(minutes)):
        out.append(f"only {len(s.scenes)} scene(s): write about {prompts.scene_target(minutes)}")
    kinds = settings.get("kinds") or []
    bad = sorted({sc.kind for sc in s.scenes} - set(kinds)) if kinds else []
    if bad:
        out.append(f"scene kinds {bad} are switched off: use only {kinds}")
    for sc in s.scenes:
        out += opening_problems(sc)
        said = " ".join(ln.en or ln.caps for ln in sc.lines)
        if sc.kind in ("concept", "figure") and "solid" in kinds and _SHAPE_ACTION.search(said) and _SOLID_NAME.search(said):
            out.append(f"{sc.id} ({sc.kind}) describes a 3D shape being formed, opened up, filled or cut: make it a "
                       "\"solid\" scene with the matching moves (revolve, unroll, fill, cut)")
    for sc in s.scenes:
        if sc.kind != "solid" or sc.solid is None:
            continue
        for m in sc.moves:
            if m.do == "unroll" and sc.solid.shape not in UNROLLS:
                out.append(f"{sc.id}: 'unroll' works only for a cylinder or a cone, not a {sc.solid.shape}")
            if m.do == "revolve" and sc.solid.shape not in REVOLVES:
                out.append(f"{sc.id}: 'revolve' does not make a {sc.solid.shape}: use show, fill, cut or orbit")
    want = int(settings.get("checks", 0)) if "check" in kinds else 0
    have = sum(sc.kind == "check" for sc in s.scenes)
    if have != want:
        out.append(f"include exactly {want} check scene(s) (there are {have})")
    return out


# a line that shows a 3D shape being made, opened, filled or cut (English track of each line)
_SHAPE_ACTION = re.compile(r"\b(spin|spins|spinning|spun|rotat\w*|revolv\w*|unroll\w*|unfold\w*|open(?:s|ed)? it (?:up|out)|"
                           r"cut (?:it|the \w+) (?:open|along)|fill(?:s|ed)? (?:it|the \w+) with|pour\w*)\b", re.I)
_SOLID_NAME = re.compile(r"\b(cylinder|cone|sphere|hemisphere|cuboid|cube|frustum|triangle|rectangle|semicircle)s?\b", re.I)


def opening_problems(sc) -> list[str]:
    """Scenes whose only visuals are points / steps / shapes must show the first one at the start of line 0
    (on "" or one of the first four spoken words), or the screen sits empty while the narrator talks."""
    if sc.kind not in ("concept", "board", "figure"):
        return []
    items = [*sc.points, *sc.steps, *sc.shapes]
    if not items:
        return [f"{sc.id} ({sc.kind}) has nothing to show: give it points, steps or shapes"]
    def early(it) -> bool:
        if it.line != 0:
            return False
        if not it.word:
            return True
        words = sc.lines[0].say.split()
        return any(w.startswith(it.word) or it.word.startswith(w) for w in words[:4])
    if not any(early(it) for it in items):
        return [f"{sc.id} ({sc.kind}): nothing appears until later in the scene, so the screen starts empty; anchor "
                "the first point / step / shape to line 0 with word \"\" (or one of its first four words)"]
    return []


def _validate(obj: dict, settings: dict) -> tuple[Script | None, list[str]]:
    obj.setdefault("language", settings.get("language", "hinglish"))
    obj.setdefault("screen_lang", settings.get("screen_lang", "en"))
    try:
        s = Script(**obj)
    except ValidationError as e:
        return None, [f"{'.'.join(map(str, err['loc']))}: {err['msg']}" for err in e.errors()[:30]]
    return s, structure_problems(s, settings) + s.speakable_problems()


def write_script(vid: str) -> None:
    v = store.get(vid)
    st, tg = v["settings"], v["target"]
    model = v["model"]
    store.update(vid, status="scripting", error=None)
    store.event(vid, "script", "running", f"Writing the script with {model}")
    try:
        units = ncert.units(tg.get("unit_ids") or [])
        subject = (units[0].get("subject") if units else tg.get("subject")) or ""
        gl = store.glossary(subject) if subject else []
        msgs = prompts.script_prompt(units, tg.get("text", ""), st, gl)
        obj = _ask(vid, st, model, msgs, temperature=float(st.get("temperature", 0.4)), max_tokens=24000)
        script, problems = _validate(obj, st)
        for round_ in range(2):
            if not problems:
                break
            store.event(vid, "script", "info", f"Fixing {len(problems)} problem(s): {problems[0]}")
            obj = _ask(vid, st, model, prompts.fix_prompt(msgs, obj, problems), temperature=0.2, max_tokens=24000)
            script, problems = _validate(obj, st)
        if script is None:
            raise RuntimeError("the model's script did not match the schema: " + "; ".join(problems[:5]))
        if any(p.startswith(("the script is far too short", "only ")) for p in problems):
            raise RuntimeError("the model wrote an incomplete script even after 2 fix rounds: "
                               + problems[0] + ". Try a stronger model.")
        problems = script.speakable_problems()
        data = script.model_dump()
        note = f" ({len(problems)} line(s) still not speakable: they are highlighted for you)" if problems else ""
        store.update(vid, script=data, status="review", title=script.title.en or script.title.hi)
        store.merge_stage(vid, speakable=problems)
        store.event(vid, "script", "done", f"{len(script.scenes)} scenes, "
                    f"{sum(len(s.lines) for s in script.scenes)} lines{note}")
    except Exception as e:
        log.exception("script %s", vid)
        store.update(vid, status="failed", error=str(e))
        store.event(vid, "script", "failed", str(e))


def regenerate_scene(vid: str, index: int, note: str) -> dict:
    v = store.get(vid)
    st = v["settings"]
    units = ncert.units(v["target"].get("unit_ids") or [])
    msgs = prompts.scene_regen_prompt(v["script"], index, note, units, v["script"]["language"])
    obj = _ask(vid, st, v["model"], msgs, temperature=float(st.get("temperature", 0.4)), max_tokens=8000)
    if isinstance(obj, dict) and "scenes" in obj:
        obj = obj["scenes"][0]
    script = dict(v["script"])
    scenes = list(script["scenes"])
    scenes[index] = obj
    script["scenes"] = scenes
    s, problems = _validate(script, st)
    if s is None:
        raise ValueError("; ".join(problems[:5]))
    store.update(vid, script=s.model_dump())
    voice_is_stale(vid)
    store.event(vid, "script", "info", f"Scene {index + 1} rewritten" + (f" ({len(problems)} speakable issue(s))"
                                                                         if problems else ""))
    return s.model_dump()


# ---------- 2. approve → voice ----------

def approve(vid: str) -> None:
    v = store.get(vid)
    st = v["settings"]
    script = Script(**v["script"])
    problems = script.speakable_problems()
    if problems:
        raise ValueError("fix these lines first: " + "; ".join(problems[:5]))
    lang = script.language
    voice = st.get("voice") or DEFAULT_VOICE[lang]
    p = prefix(vid)
    vs = voice_script(script, music=st.get("music", "none"))
    storage.put_bytes(p + "voice-in.json", json.dumps(vs, ensure_ascii=False).encode(), "application/json")
    jid = jobs.enqueue("voice", {"script_key": p + "voice-in.json", "language": lang, "voice": voice,
                                 "out_prefix": p + "voice/"}, priority=50)
    modes = variants_for(st.get("mode", "template"))
    store.update(vid, status="voicing", error=None,
                 variants=[{"mode": m, "status": "waiting"} for m in modes])
    store.merge_stage(vid, voice_job=jid, words_job=None, render_jobs={}, code_done="llm" not in modes)
    store.event(vid, "voice", "running", f"Recording {len(vs['lines'])} lines with {voice}")
    if "llm" in modes:
        start_code(vid)


# ---------- 3. LLM scene code ----------

def start_code(vid: str) -> None:
    _thread(f"code:{vid}", write_code, vid)


def _one_scene(vid: str, model: str, script: dict, i: int, aspect: str, settings: dict) -> tuple[int, str | None, str]:
    sc = script["scenes"][i]
    err = ""
    for attempt in range(2):
        obj = _ask(vid, settings, model, prompts.custom_prompt(script, sc, aspect, err),
                   temperature=float(settings.get("code_temperature", 0.5)), max_tokens=12000)
        code = (obj or {}).get("code", "") if isinstance(obj, dict) else ""
        code = prompts.fix_tex_literals(code)
        problems = prompts.code_problems(code) if code else ["no code returned"]
        if not problems:
            return i, code, ""
        err = "; ".join(problems)
    return i, None, err


def write_code(vid: str) -> None:
    v = store.get(vid)
    st = v["settings"]
    model = st.get("code_model") or v["model"]
    script = v["script"]
    # check scenes stay templates (the player pauses on them); solid scenes are drawn by the engine in 3D
    targets = [i for i, s in enumerate(script["scenes"]) if s["kind"] not in ("check", "solid") and not s.get("custom_code")]
    store.event(vid, "code", "running", f"Writing animation code for {len(targets)} scenes with {model}")
    done, failed = 0, []
    try:
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = {i: ex.submit(_one_scene, vid, model, script, i, st.get("aspect", "16:9"), st) for i in targets}
            for i, f in futs.items():
                try:
                    _, code, err = f.result()
                except CapReached:
                    raise
                except Exception as e:                       # one scene's failure falls back to its template
                    code, err = None, f"{type(e).__name__}: {e}"
                if code:
                    script["scenes"][i]["custom_code"] = code
                    done += 1
                else:
                    failed.append({"id": script["scenes"][i]["id"], "reason": f"no usable code: {err}"[:300]})
        store.update(vid, script=script)
        store.merge_stage(vid, code_failed=failed)
        msg = f"{done}/{len(targets)} scenes animated"
        if failed:
            msg += "; template used for " + ", ".join(_scene_name(script, f["id"]) for f in failed)
        store.event(vid, "code", "done", msg)
    except Exception as e:
        log.exception("code %s", vid)
        store.event(vid, "code", "failed", f"{e} (templates will be used)")
    store.merge_stage(vid, code_done=True)


def _scene_name(script: dict, sid: str) -> str:
    sc = next((s for s in script["scenes"] if s["id"] == sid), None)
    title = (sc or {}).get("title") or {}
    name = (title.get("en") or title.get("hi")) if isinstance(title, dict) else str(title)
    return f"{sid} “{name}”" if name else sid


# one line per scene in the render's check.txt, written by capture.mjs from OP.shots():
#   "s3      32.85 →  48.27  (15.42 s)  figure · TEMPLATE FALLBACK: <error>"   or  "… board · llm animation"
_SHOT = re.compile(r"^(\S+)\s+[\d.]+\s+→\s+[\d.]+\s+\(\s*[\d.]+ s\)\s+(\w+)(?:\s+·\s+(.*))?$")


def llm_report(check_txt: str, script: dict, code_failed: list[dict] | None = None) -> dict:
    """Which scenes of an LLM-animation render really used LLM code, and why the others fell back to the template.
    A scene is a fallback when the studio got no usable code for it (code_failed) or the engine rejected the code
    at boot (TEMPLATE FALLBACK in check.txt). Check scenes are always templates (the player pauses on them) and
    solid scenes are drawn in 3D by the engine: neither counts."""
    ids = {s["id"] for s in script["scenes"]}
    why = {f["id"]: f["reason"] for f in (code_failed or [])}
    animatable, animated, fallbacks = 0, 0, []
    for raw in check_txt.splitlines():
        m = _SHOT.match(raw.strip())
        if not m or m.group(1) not in ids or m.group(2) in ("check", "solid"):
            continue
        sid, note = m.group(1), m.group(3) or ""
        animatable += 1
        if note.startswith("llm animation"):
            animated += 1
            continue
        reason = (note.split("TEMPLATE FALLBACK:", 1)[1].strip() if "TEMPLATE FALLBACK:" in note
                  else why.get(sid, "no animation code was written for this scene"))
        fallbacks.append({"id": sid, "name": _scene_name(script, sid), "reason": reason[:300]})
    return {"animatable": animatable, "animated": animated, "fallbacks": fallbacks}


def report_message(rep: dict) -> str:
    msg = f"LLM animation: {rep['animated']} of {rep['animatable']} scenes animated"
    if rep["fallbacks"]:
        msg += "; template used for " + "; ".join(f"{f['name']} ({f['reason'][:120]})" for f in rep["fallbacks"])
    return msg


# ---------- 4. project + render ----------

def build_project(vid: str, mode: str) -> bytes:
    v = store.get(vid)
    st = v["settings"]
    script = v["script"]
    lesson = {"script": script, "mode": mode, "aspect": st.get("aspect", "16:9"),
              "captions": bool(st.get("burn_captions", False)), "grid": bool(st.get("grid", True)),
              "bk": bool(st.get("bk", True)), "pace": st.get("pace", "normal"),
              "sfx": bool(st.get("sfx", True)), "chrome": bool(st.get("chrome", False)),
              "camera": bool(st.get("camera", True))}
    vs = json.loads(storage.get_bytes(prefix(vid) + "voice/script.json"))
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        t.add(STYLE, arcname=".", filter=lambda ti: None if "/node_modules" in ti.name else ti)
        for f in ("capture.mjs", "mix.py"):
            t.add(TOOLS / f, arcname=f"tools/{f}")
        for name, obj in (("lesson.json", lesson), ("script.json", vs)):
            data = json.dumps(obj, ensure_ascii=False).encode()
            ti = tarfile.TarInfo(name)
            ti.size = len(data)
            t.addfile(ti, io.BytesIO(data))
    return buf.getvalue()


def start_renders(vid: str) -> None:
    v = store.get(vid)
    st = v["settings"]
    p = prefix(vid)
    rj = dict(v["stage"].get("render_jobs") or {})
    variants = v["variants"]
    quality = st.get("quality", "draft")
    for var in variants:
        if var.get("status") not in ("waiting", "failed", None):
            continue                                   # done / rendered on an earlier attempt: kept
        m = var["mode"]
        key = p + f"{m}/project.tar.gz"
        storage.put_bytes(key, build_project(vid, m), "application/gzip")
        rj[m] = jobs.enqueue("render", {"project_key": key, "data_prefix": p + "voice/", "out_prefix": p + f"{m}/",
                                        "quality": quality, "fps": 30}, priority=60)
        var.update(status="rendering", quality=quality, error=None)
    store.update(vid, status="rendering", variants=variants)
    store.merge_stage(vid, render_jobs=rj)
    store.event(vid, "render", "running", "Rendering " + " + ".join(x["mode"] for x in variants
                                                               if x["status"] == "rendering") + " on the GPU")


# ---------- 5. publish ----------

def _chunks(caps: str, words: list[dict], s: float, e: float) -> list[dict]:
    parts = [c.strip() for c in caps.split("|") if c.strip()] or [caps]
    out, n = [], len(parts)
    for k, part in enumerate(parts):
        anchor = None
        if part.startswith("@"):
            head, _, part = part.partition(" ")
            try:
                anchor = int(head[1:])
            except ValueError:
                anchor = None
        if anchor is not None and anchor < len(words):
            cs = words[anchor]["s"]
        elif words:
            cs = words[min(len(words) - 1, round(k * len(words) / n))]["s"]
        else:
            cs = s + (e - s) * k / n
        out.append({"s": round(cs, 3), "text": part.replace("*", "")})
    for k in range(len(out)):
        out[k]["e"] = round(out[k + 1]["s"] if k + 1 < len(out) else e, 3)
    return out


def manifest(vid: str) -> dict:
    v = store.get(vid)
    script = v["script"]
    p = prefix(vid)
    lines = json.loads(storage.get_bytes(p + "voice/lines.json"))
    words = json.loads(storage.get_bytes(p + "voice/words.json"))
    L = lines["lines"]
    chapters, captions, checks, gi = [], [], [], 0
    for sc in script["scenes"]:
        first = gi
        for j, ln in enumerate(sc["lines"]):
            lw = [w for w in words if w["line"] == gi]
            s, e = L[gi]["start"], L[gi]["end"]
            for c in _chunks(ln.get("caps") or ln["say"], lw, s, e):
                en = ln.get("en", "")
                captions.append({**c, "line": gi, "en": en})
            gi += 1
        chapters.append({"t": round(L[first]["start"] if first else 0.0, 3), "kind": sc["kind"], "title": sc["title"],
                         "id": sc["id"]})
        if sc["kind"] == "check":
            checks.append({"t": round(L[first]["end"] + 0.15, 3), "resume": round(L[first + 1]["start"], 3),
                           "question": sc["question"], "options": sc["options"], "correct": sc["correct"],
                           "hint": sc["hint"], "explain": sc["explain"], "id": sc["id"]})
    for k in range(len(chapters)):
        chapters[k]["end"] = chapters[k + 1]["t"] if k + 1 < len(chapters) else lines["duration"]
    # English captions per line (one cue per line)
    en_caps, seen = [], set()
    for c in captions:
        if c["line"] in seen or not c["en"]:
            continue
        seen.add(c["line"])
        en_caps.append({"s": L[c["line"]]["start"], "e": L[c["line"]]["end"], "text": c["en"]})
    return {"id": vid, "title": script["title"], "language": script["language"],
            "screen_lang": script.get("screen_lang", "en"), "duration": lines["duration"], "chapters": chapters,
            "captions": {"main": [{k: c[k] for k in ("s", "e", "text")} for c in captions], "en": en_caps},
            "checks": checks, "target": v["target"], "settings": {k: v["settings"].get(k) for k in
                                                                  ("mode", "aspect", "language", "voice", "burn_captions")},
            "model": v["model"]}


def _poster(mp4_key: str, out_key: str, t: float) -> None:
    with tempfile.TemporaryDirectory() as d:
        src = storage.get_file(mp4_key, Path(d) / "v.mp4")
        jpg = Path(d) / "p.jpg"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.2f}", "-i", str(src), "-frames:v", "1",
                        "-vf", "scale=960:-2", "-q:v", "3", str(jpg)], check=True, timeout=120)
        storage.put_file(out_key, jpg, "image/jpeg")


def publish(vid: str) -> None:
    v = store.get(vid)
    p = prefix(vid)
    store.update(vid, status="publishing")
    man = manifest(vid)
    variants = v["variants"]
    for var in variants:
        if var.get("status") != "rendered":
            continue
        m = var["mode"]
        mk = p + f"{m}/manifest.json"
        storage.put_bytes(mk, json.dumps({**man, "mode": m}, ensure_ascii=False).encode(), "application/json")
        var["manifest_key"] = mk
        try:
            pk = p + f"{m}/poster.jpg"
            _poster(var["video_key"], pk, min(2.5, man["duration"] / 3))
            var["poster_key"] = pk
        except Exception as e:                                         # a missing poster is not fatal
            log.warning("poster %s %s: %s", vid, m, e)
        var["status"] = "done"
    ok = [x for x in variants if x["status"] == "done"]
    store.update(vid, variants=variants, duration_s=man["duration"],
                 status="done" if ok else "failed", error=None if ok else "every render failed")
    store.event(vid, "publish", "done" if ok else "failed",
                f"Ready: {', '.join(x['mode'] for x in ok)}" if ok else "every render failed")


# ---------- the loop ----------

def _job_state(jid) -> tuple[str, dict]:
    j = store.job(int(jid)) if jid else None
    if not j:
        return "missing", {}
    return j["status"], j


def _fail(vid: str, step: str, msg: str) -> None:
    store.update(vid, status="failed", error=msg)
    store.merge_stage(vid, failed_step=step, tick_errors=0, publish_errors=0)
    store.event(vid, step, "failed", msg)


TICK_ERRORS_MAX = 10      # consecutive errors (about 30 s at one tick per 3 s) before a video is failed
PUBLISH_ERRORS_MAX = 5


def start_publish(vid: str) -> None:
    _thread(f"publish:{vid}", _publish_safe, vid)


def _publish_safe(vid: str) -> None:
    """Publish off the loop thread (it downloads each video for its poster). A failure is retried on the next ticks
    (storage may be restarting); only repeated failures fail the video."""
    try:
        publish(vid)
    except Exception as e:
        log.exception("publish %s", vid)
        n = int(((store.get(vid) or {}).get("stage") or {}).get("publish_errors", 0)) + 1
        if n >= PUBLISH_ERRORS_MAX:
            _fail(vid, "publish", f"{type(e).__name__}: {e}")
        else:
            store.merge_stage(vid, publish_errors=n)


def voice_is_stale(vid: str) -> None:
    """The script changed: recorded narration and timings no longer match it, so Retry must not reuse them."""
    store.merge_stage(vid, voice_job=None, words_job=None, render_jobs={})


def resume(vid: str) -> str:
    """Retry a failed video from where it stopped, reusing finished narration, timing and renders.
    Returns the step it resumes at: "review" (nothing reusable), "words", "render" or "publish"."""
    v = store.get(vid)
    sg, st = v["stage"], v["settings"]
    voice_ok = _job_state(sg.get("voice_job"))[0] == "done"
    words_ok = voice_ok and _job_state(sg.get("words_job"))[0] == "done"
    store.merge_stage(vid, tick_errors=0, publish_errors=0, failed_step=None)
    if not voice_ok:
        store.update(vid, status="review", error=None)
        store.event(vid, "script", "info", "Back to review: press Build to try again")
        return "review"
    if not words_ok:
        store.update(vid, status="voicing", error=None)          # tick sees the finished voice job, starts words
        store.event(vid, "words", "info", "Retrying from word timing (narration reused)")
        return "words"
    modes = variants_for(st.get("mode", "template"))
    quality = st.get("quality", "draft")
    old = {x["mode"]: x for x in v["variants"]}
    variants = []
    for m in modes:
        x = old.get(m)
        keep = x and x.get("status") in ("done", "rendered") and x.get("quality", "draft") == quality
        variants.append(x if keep else {"mode": m, "status": "waiting"})
    code_done = bool(sg.get("code_done")) or "llm" not in modes or any(
        x["mode"] == "llm" and x["status"] in ("done", "rendered") for x in variants)
    store.merge_stage(vid, code_done=code_done)
    if all(x["status"] in ("done", "rendered") for x in variants):
        store.update(vid, variants=variants, status="publishing", error=None)
        store.event(vid, "publish", "info", "Retrying publishing (renders reused)")
        return "publish"
    store.update(vid, variants=variants, status="coding", error=None)  # tick: code if needed, then renders
    store.event(vid, "render", "info", "Retrying from rendering (narration and timing reused)")
    return "render"


def purge(vid: str) -> int:
    """Everything a deleted video leaves behind: its queued jobs and its files in storage."""
    v = store.get(vid)
    if v:
        sg = v.get("stage") or {}
        ids = [sg.get("voice_job"), sg.get("words_job"), *(sg.get("render_jobs") or {}).values()]
        store.cancel_jobs([int(i) for i in ids if i])
    return storage.delete_prefix(prefix(vid))


def tick() -> None:
    for v in store.active(("voicing", "timing", "coding", "rendering", "publishing")):
        vid, sg = v["id"], v["stage"]
        try:
            if v["status"] == "voicing":
                s, j = _job_state(sg.get("voice_job"))
                if s == "done":
                    r = j.get("result") or {}
                    msg = f"{r.get('duration_s', 0):.0f} s of narration, {r.get('retakes', 0)} re-take(s)"
                    if r.get("flagged"):
                        msg += f"; {len(r['flagged'])} sentence(s) flagged by the voice check"
                    store.event(vid, "voice", "done", msg)
                    jid = jobs.enqueue("words", {"out_prefix": prefix(vid) + "voice/",
                                                 "language": v["script"]["language"]}, priority=50)
                    store.merge_stage(vid, words_job=jid)
                    store.update(vid, status="timing")
                    store.event(vid, "words", "running", "Timing every word (forced alignment)")
                elif s in ("failed", "missing"):
                    _fail(vid, "voice", f"voice job failed: {j.get('error') or s}")
            elif v["status"] == "timing":
                s, j = _job_state(sg.get("words_job"))
                if s == "done":
                    r = j.get("result") or {}
                    store.event(vid, "words", "done", f"{r.get('words', 0)} words timed"
                                + (f", {r['unmatched']} estimated" if r.get("unmatched") else ""))
                    if sg.get("code_done"):
                        start_renders(vid)
                    else:
                        store.update(vid, status="coding")
                elif s in ("failed", "missing"):
                    _fail(vid, "words", f"words job failed: {j.get('error') or s}")
            elif v["status"] == "coding":
                if sg.get("code_done"):
                    start_renders(vid)
                else:
                    start_code(vid)                                    # restarts the thread after a restart
            elif v["status"] == "rendering":
                variants, changed = v["variants"], False
                for var in variants:
                    if var["status"] != "rendering":
                        continue
                    s, j = _job_state(sg.get("render_jobs", {}).get(var["mode"]))
                    if s == "done":
                        r = j.get("result") or {}
                        var.update(status="rendered", video_key=r.get("video_key"), sheet_key=r.get("sheet_key"),
                                   gpu_seconds=r.get("gpu_seconds"))
                        store.event(vid, "render", "info", f"{var['mode']} rendered in {r.get('gpu_seconds', 0):.0f} s")
                        if var["mode"] == "llm":                 # never let a template fallback pass silently
                            try:
                                txt = storage.get_bytes(prefix(vid) + "llm/check.txt").decode("utf-8", "replace")
                                var["llm"] = llm_report(txt, v["script"], sg.get("code_failed"))
                                store.event(vid, "render", "info", report_message(var["llm"]))
                            except Exception as e:               # the report is a nicety; the video is fine
                                log.warning("llm report %s: %s", vid, e)
                        changed = True
                    elif s in ("failed", "missing"):
                        var.update(status="failed", error=(j.get("error") or s)[:1000], log_key=j.get("log_key"))
                        store.event(vid, "render", "failed", f"{var['mode']}: {var['error'][:300]}")
                        changed = True
                if changed:
                    store.update(vid, variants=variants)
                if all(x["status"] in ("rendered", "done", "failed") for x in variants):
                    store.event(vid, "render", "done" if any(x["status"] in ("rendered", "done") for x in variants)
                                else "failed", "")
                    store.update(vid, status="publishing")
                    start_publish(vid)
            elif v["status"] == "publishing":
                start_publish(vid)                                      # after a restart, or a failed attempt
            if sg.get("tick_errors"):
                store.merge_stage(vid, tick_errors=0)
        except Exception as e:
            # Storage or the database may be restarting: retry on the next ticks, fail only if it persists.
            n = int(sg.get("tick_errors") or 0) + 1
            log.warning("tick %s: error %d/%d: %s", vid, n, TICK_ERRORS_MAX, e)
            try:
                if n >= TICK_ERRORS_MAX:
                    _fail(vid, "pipeline", f"{type(e).__name__}: {e}\n{traceback.format_exc()[-1500:]}")
                else:
                    store.merge_stage(vid, tick_errors=n)
            except Exception:
                log.exception("tick %s: could not record the error", vid)


def recover() -> None:
    """At startup: scripts cut off by a restart are failed (Retry restarts them)."""
    for v in store.active(("scripting",)):
        store.update(v["id"], status="failed", error="interrupted by a restart: press Retry")
        store.event(v["id"], "script", "failed", "interrupted by a restart")


def loop(stop: threading.Event) -> None:
    recover()
    while not stop.wait(3):
        try:
            tick()
        except Exception:
            log.exception("pipeline loop")
