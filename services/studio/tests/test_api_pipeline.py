"""Studio API and pipeline behaviour with the database, storage and OpenRouter replaced by fakes."""
import copy
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from studio import app as studio_app
from studio import llm, pipeline


class FakeStore:
    """The parts of studio.store the pipeline and API use, in memory."""

    def __init__(self):
        self.videos, self.jobs, self.events, self.cancelled, self.costs = {}, {}, [], [], []

    def add(self, **v):
        vid = v.setdefault("id", str(uuid.uuid4()))
        v.setdefault("stage", {})
        v.setdefault("variants", [])
        v.setdefault("settings", {})
        v.setdefault("cost_usd", 0.0)
        v.setdefault("script", {"language": "hinglish", "scenes": []})
        v.setdefault("error", None)
        self.videos[vid] = v
        return vid

    def get(self, vid):
        return copy.deepcopy(self.videos.get(vid))

    def update(self, vid, **cols):
        self.videos[vid].update(copy.deepcopy(cols))

    def merge_stage(self, vid, **kv):
        self.videos[vid]["stage"].update(kv)

    def event(self, vid, step, status, message=""):
        self.events.append((vid, step, status, message))

    def add_cost(self, vid, usd):
        self.costs.append(usd)
        self.videos[vid]["cost_usd"] += usd
        return self.videos[vid]["cost_usd"]

    def cost(self, vid):
        return self.videos[vid]["cost_usd"]

    def job(self, jid):
        return self.jobs.get(jid)

    def active(self, statuses):
        return [copy.deepcopy(v) for v in self.videos.values() if v["status"] in statuses]

    def cancel_jobs(self, ids):
        self.cancelled += ids
        return len(ids)

    def delete(self, vid):
        self.videos.pop(vid, None)


@pytest.fixture
def fake(monkeypatch):
    s = FakeStore()
    monkeypatch.setattr(pipeline, "store", s)
    monkeypatch.setattr(studio_app, "store", s)
    return s


# ---------- range requests ----------

@pytest.mark.parametrize("header,want", [
    (None, None), ("", None), ("bytes=0-99", (0, 99)), ("bytes=100-", (100, 999)), ("bytes=-100", (900, 999)),
    ("bytes=900-5000", (900, 999)), ("bytes=-5000", (0, 999)), ("bytes=1000-", "unsatisfiable"),
    ("bytes=-0", "unsatisfiable"), ("bytes=500-100", None), ("bytes=0-1,5-6", None), ("items=0-9", None),
    ("bytes=-", None),
])
def test_parse_range(header, want):
    assert studio_app.parse_range(header, 1000) == want


# ---------- input validation ----------

def test_settings_are_typed_and_unknown_keys_dropped():
    s = studio_app.VideoSettings(mode="both", minutes=4, kinds=["title", "solid"], junk={"x": 1})
    assert s.mode == "both" and "junk" not in s.model_dump()
    for bad in ({"mode": "rm -rf"}, {"aspect": "4:3"}, {"cap_usd": -1}, {"kinds": ["nope"]}, {"checks": 99},
                {"instructions": "x" * 5000}):
        with pytest.raises(ValidationError):
            studio_app.VideoSettings(**bad)


def test_target_rejects_bad_unit_ids():
    ok = str(uuid.uuid4())
    assert studio_app.Target(unit_ids=[ok], chapter="Mensuration").unit_ids == [ok]
    with pytest.raises(ValidationError):
        studio_app.Target(unit_ids=["1; drop table x"])


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("STUDIO_PASSWORD", "right-password")
    monkeypatch.setattr(studio_app.time, "sleep", lambda s: None)
    studio_app._fails.clear()
    c = TestClient(studio_app.app, base_url="https://testserver")    # no `with`: the pipeline thread stays off
    yield c
    studio_app._fails.clear()


def _login(c):
    c.cookies.set(studio_app.COOKIE, studio_app._token(int(time.time()) + 600), path="/studio")


def test_login_locks_an_ip_out_after_repeated_wrong_passwords(client):
    for _ in range(studio_app.LOGIN_MAX_PER_IP):
        assert client.post("/studio/api/login", json={"password": "guess"}).status_code == 401
    r = client.post("/studio/api/login", json={"password": "right-password"})
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0


def test_a_good_login_clears_earlier_failures(client):
    for _ in range(studio_app.LOGIN_MAX_PER_IP - 1):
        client.post("/studio/api/login", json={"password": "guess"})
    assert client.post("/studio/api/login", json={"password": "right-password"}).status_code == 200
    assert client.post("/studio/api/login", json={"password": "guess"}).status_code == 401


def test_new_video_with_a_bad_unit_id_is_422_not_500(client, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    _login(client)
    r = client.post("/studio/api/videos", json={"target": {"unit_ids": ["not-a-uuid"]}, "settings": {},
                                                "model": "m"})
    assert r.status_code == 422


def test_settings_patch_is_validated(client, fake):
    vid = fake.add(status="review", settings={"mode": "template"})
    _login(client)
    assert client.patch(f"/studio/api/videos/{vid}/settings", json={"mode": "both"}).json()["mode"] == "both"
    assert client.patch(f"/studio/api/videos/{vid}/settings", json={"quality": "4k"}).status_code == 422
    client.patch(f"/studio/api/videos/{vid}/settings", json={"evil": "x"})
    assert "evil" not in fake.videos[vid]["settings"]


def test_delete_cancels_queued_jobs_and_removes_files(client, fake, monkeypatch):
    deleted = []
    monkeypatch.setattr(pipeline.storage, "delete_prefix", lambda p: deleted.append(p) or 7)
    vid = fake.add(status="rendering", stage={"voice_job": 1, "words_job": 2, "render_jobs": {"template": 3}})
    _login(client)
    r = client.delete(f"/studio/api/videos/{vid}")
    assert r.json() == {"ok": True, "files_deleted": 7}
    assert sorted(fake.cancelled) == [1, 2, 3] and deleted == [f"studio/{vid}/"] and vid not in fake.videos


# ---------- spending cap ----------

def test_no_llm_call_once_the_cap_is_spent(fake, monkeypatch):
    vid = fake.add(status="scripting", cost_usd=2.0)
    monkeypatch.setattr(llm, "chat_json", lambda *a, **k: pytest.fail("called the LLM over the cap"))
    with pytest.raises(pipeline.CapReached):
        pipeline._ask(vid, {"cap_usd": 2.0}, "m", [])


def test_a_failed_llm_call_still_records_what_it_cost(fake, monkeypatch):
    vid = fake.add(status="scripting")

    def boom(*a, **k):
        raise llm.LLMError("empty reply", cost=0.25)
    monkeypatch.setattr(llm, "chat_json", boom)
    with pytest.raises(llm.LLMError):
        pipeline._ask(vid, {}, "m", [])
    assert fake.costs == [0.25]


def test_chat_counts_paid_empty_replies(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "k")
    replies = iter([("", 0.1), ('{"ok": 1}', 0.2)])

    class R:
        status_code, text = 200, ""

        def __init__(self):
            self.content, self.cost = next(replies)

        def json(self):
            return {"choices": [{"message": {"content": self.content}, "finish_reason": "stop"}],
                    "usage": {"cost": self.cost}}
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: R())
    text, cost, _ = llm.chat("m", [{"role": "user", "content": "hi"}])
    assert text == '{"ok": 1}' and cost == pytest.approx(0.3)


# ---------- resilience: transient errors, resume ----------

def test_transient_errors_do_not_fail_a_video_at_once(fake, monkeypatch):
    vid = fake.add(status="voicing", stage={"voice_job": 1})

    def down(jid):
        raise ConnectionError("storage restarting")
    monkeypatch.setattr(fake, "job", down)
    for _ in range(pipeline.TICK_ERRORS_MAX - 1):
        pipeline.tick()
    assert fake.videos[vid]["status"] == "voicing"
    pipeline.tick()
    assert fake.videos[vid]["status"] == "failed"


def test_a_good_tick_resets_the_error_count(fake):
    vid = fake.add(status="voicing", stage={"voice_job": 1, "tick_errors": 4})
    fake.jobs[1] = {"status": "running"}
    pipeline.tick()
    assert fake.videos[vid]["stage"]["tick_errors"] == 0 and fake.videos[vid]["status"] == "voicing"


def _failed(fake, voice="done", words="done", variants=None, **settings):
    fake.jobs.update({1: {"status": voice}, 2: {"status": words}})
    return fake.add(status="failed", stage={"voice_job": 1, "words_job": 2, "code_done": True},
                    settings={"mode": "template", "quality": "draft", **settings},
                    variants=variants or [{"mode": "template", "status": "failed"}])


def test_resume_without_narration_goes_back_to_review(fake):
    vid = _failed(fake, voice="failed")
    assert pipeline.resume(vid) == "review" and fake.videos[vid]["status"] == "review"


def test_resume_reuses_narration_and_redoes_word_timing(fake):
    vid = _failed(fake, words="failed")
    assert pipeline.resume(vid) == "words" and fake.videos[vid]["status"] == "voicing"


def test_resume_rerenders_only_what_is_missing(fake):
    vid = _failed(fake, mode="both", variants=[{"mode": "template", "status": "done", "quality": "draft"},
                                               {"mode": "llm", "status": "failed"}])
    assert pipeline.resume(vid) == "render"
    v = fake.videos[vid]
    assert v["status"] == "coding"
    assert [(x["mode"], x["status"]) for x in v["variants"]] == [("template", "done"), ("llm", "waiting")]


def test_resume_rerenders_when_the_quality_changed(fake):
    vid = _failed(fake, quality="final", variants=[{"mode": "template", "status": "done", "quality": "draft"}])
    assert pipeline.resume(vid) == "render"
    assert fake.videos[vid]["variants"] == [{"mode": "template", "status": "waiting"}]


def test_resume_only_republishes_when_every_render_is_done(fake):
    vid = _failed(fake, variants=[{"mode": "template", "status": "rendered", "quality": "draft"}])
    assert pipeline.resume(vid) == "publish" and fake.videos[vid]["status"] == "publishing"


def test_an_edited_script_cannot_reuse_old_narration(fake):
    vid = _failed(fake)
    pipeline.voice_is_stale(vid)
    assert pipeline.resume(vid) == "review"
