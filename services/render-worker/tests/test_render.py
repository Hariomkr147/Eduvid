"""Render worker logic with Chrome/ffmpeg/S3/Postgres replaced by fakes."""
import io
import tarfile
from pathlib import Path

import pytest

from eduvid_common.jobs import Job
from render_worker import main, render


class Store(dict):
    def put_bytes(self, key, data, content_type):
        self[key] = data

    def put_file(self, key, path, content_type=None):
        self[key] = Path(path).read_bytes()

    def get_bytes(self, key):
        return self[key]

    def get_file(self, key, dest):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(self[key])
        return Path(dest)


def project_tar() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        for name, data in {"index.html": b"<html>", "script.json": b'{"lines": []}',
                           "tools/capture.mjs": b"//", "tools/mix.py": b"#"}.items():
            info = tarfile.TarInfo(name)
            info.size = len(data)
            t.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def job(quality="draft", jid=42):
    return Job(id=jid, type="render", attempts=1, priority=100, render_id=5, payload={
        "render_id": 5, "project_key": "p/project.tar.gz", "data_prefix": "d/", "quality": quality,
        "out_prefix": "o/"})


class FakeTools:
    """Stands in for node/python/ffmpeg: records each step and writes what that step would write."""

    def __init__(self, check_output="CHECK OK"):
        self.steps, self.envs, self.check_output = [], [], check_output

    def __call__(self, cmd, cwd, env, timeout):
        self.steps.append(cmd)
        self.envs.append(env)
        cwd = Path(cwd)
        assert (cwd / "index.html").exists() and (cwd / "data/words.json").exists()
        if cmd[:3] == ["node", "tools/capture.mjs", "check"]:
            return 0 if "CHECK OK" in self.check_output else 1, self.check_output
        if cmd[:3] == ["node", "tools/capture.mjs", "sheet"]:
            (cwd / cmd[3]).parent.mkdir(parents=True, exist_ok=True)
            (cwd / cmd[3]).write_bytes(b"jpg")
        if cmd[:3] == ["node", "tools/capture.mjs", "video"]:
            (cwd / cmd[3]).parent.mkdir(parents=True, exist_ok=True)
            (cwd / cmd[3]).write_bytes(b"mp4")
        if cmd[:2] == ["python", "tools/mix.py"]:
            (cwd / "data/mix.wav").write_bytes(b"wav")
        return 0, f"ran {' '.join(cmd)}"


@pytest.fixture
def store(monkeypatch):
    s = Store({"p/project.tar.gz": project_tar(), "d/narration.wav": b"RIFF", "d/lines.json": b"{}",
               "d/words.json": b"[]"})
    monkeypatch.setattr(render, "storage", s)
    monkeypatch.setattr(main, "storage", s)
    return s


def test_webgl_flags_picks_first_nvidia():
    seen = []

    def probe(flags):
        seen.append(flags)
        return "ANGLE (NVIDIA Corporation, NVIDIA L4)" if flags == render.FLAG_SETS[1] else "ANGLE (Google, SwiftShader)"

    assert render.webgl_flags(probe) == render.FLAG_SETS[1]
    assert seen == render.FLAG_SETS[:2]
    assert render.webgl_flags(lambda f: "SwiftShader") == ""


def test_gl_egl_is_tried_before_vulkan():
    # Vulkan loses the WebGL context once a 2nd Chrome shares the GPU; GL-EGL handles JOBS=3
    assert render.FLAG_SETS[0] == "--use-gl=angle --use-angle=gl-egl"
    assert render.webgl_flags(lambda f: "ANGLE (NVIDIA, …)") == "--use-gl=angle --use-angle=gl-egl"


def test_draft_steps_and_uploads(store, tmp_path):
    tools = FakeTools()
    out = render.run(job("draft"), tmp_path, "--use-angle=vulkan", runner=tools, renderer="NVIDIA L4")
    names = [" ".join(c[:3]) for c in tools.steps]
    assert names == ["node tools/capture.mjs check", "node tools/capture.mjs cues", "python tools/mix.py .",
                     "node tools/capture.mjs sheet", "node tools/capture.mjs video"]
    assert tools.steps[3][3:] == ["review/all.jpg", "0.5", "10"]
    assert tools.steps[4][3:] == ["renders/draft.mp4", "--draft", "--nvenc"]
    assert all(e["CHROME_FLAGS"] == "--use-angle=vulkan" and e["JOBS"] == "3" for e in tools.envs)
    assert out["video_key"] == "o/draft.mp4" and out["sheet_key"] == "o/sheet.jpg"
    assert out["webgl_renderer"] == "NVIDIA L4" and out["gpu_seconds"] >= 0
    assert {"o/draft.mp4", "o/sheet.jpg", "o/check.txt", "o/mix.wav"} <= set(store)
    assert b"CHECK OK" in store["o/check.txt"]


def test_final_uses_best(store, tmp_path):
    tools = FakeTools()
    out = render.run(job("final"), tmp_path, "--use-angle=vulkan", runner=tools, renderer="NVIDIA L4")
    assert tools.steps[-1][3:] == ["renders/final.mp4", "--best"]
    assert out["video_key"] == "o/final.mp4"


def test_software_gl_fallback_env(store, tmp_path):
    tools = FakeTools()
    render.run(job(), tmp_path, "", runner=tools, renderer="SwiftShader")
    env = tools.envs[0]
    assert env["SOFTWARE_GL"] == "1" and env["FPS"] == "24" and env["QS"] == "&res=0.75&aa=2&shadow=1024"


def test_check_failure_fails_job(store, tmp_path, monkeypatch):
    calls = {"fail": [], "complete": []}
    tools = FakeTools(check_output="ERROR at 3.25: Wd('slant') not found in words\nCHECK FAILED")
    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: job())
    monkeypatch.setattr(main.jobs, "fail", lambda jid, error, log_key=None, retry=True:
                        calls["fail"].append((jid, error, log_key, retry)) or "requeued")
    monkeypatch.setattr(main.jobs, "complete", lambda *a, **k: calls["complete"].append(a))
    monkeypatch.setattr(main.jobs, "heartbeat", lambda *a, **k: None)
    monkeypatch.setattr(main, "update_render", lambda *a, **k: None)
    w = main.Worker("rw1", 1, tmp_path, "--use-angle=vulkan", "NVIDIA L4", runner=tools)
    assert w.run_once() is True
    assert calls["complete"] == []
    (jid, error, log_key, retry), = calls["fail"]
    assert jid == 42 and "check" in error and log_key == "o/log.txt"
    assert b"Wd('slant')" in store["o/log.txt"]
    assert len(tools.steps) == 1                                   # nothing rendered after a failed check


def test_scratch_cleaned_on_success_and_failure_and_startup(store, tmp_path, monkeypatch):
    (tmp_path / "999" / "frames").mkdir(parents=True)
    (tmp_path / "999" / "frames" / "f0001.png").write_bytes(b"x")
    monkeypatch.setattr(main.jobs, "heartbeat", lambda *a, **k: None)
    monkeypatch.setattr(main.jobs, "complete", lambda *a, **k: None)
    monkeypatch.setattr(main.jobs, "fail", lambda *a, **k: "requeued")
    monkeypatch.setattr(main, "update_render", lambda *a, **k: None)
    w = main.Worker("rw1", 1, tmp_path, "--use-angle=vulkan", "NVIDIA L4", runner=FakeTools())
    w.startup()
    assert list(tmp_path.iterdir()) == []                          # orphan from a crashed run is gone

    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: job(jid=43))
    w.run_once()
    assert not (tmp_path / "43").exists()                          # success

    w.runner = FakeTools(check_output="CHECK FAILED")
    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: job(jid=44))
    w.run_once()
    assert not (tmp_path / "44").exists()                          # failure

    def boom(*a, **k):
        raise RuntimeError("chrome crashed")
    w.runner = boom
    monkeypatch.setattr(main.jobs, "claim", lambda *a, **k: job(jid=45))
    w.run_once()
    assert not (tmp_path / "45").exists()                          # crash inside the run
    assert list(tmp_path.iterdir()) == []


def test_untrusted_tar_paths_rejected(store, tmp_path):
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as t:
        info = tarfile.TarInfo("../escape.txt")
        info.size = 1
        t.addfile(info, io.BytesIO(b"x"))
    store["p/project.tar.gz"] = buf.getvalue()
    with pytest.raises(render.RenderError):
        render.run(job(), tmp_path, "", runner=FakeTools(), renderer="x")
    assert not (tmp_path.parent / "escape.txt").exists()


def test_timeout_kills_the_whole_process_group(tmp_path):
    # capture.mjs starts Chrome processes; on a step timeout they must die too, not keep the GPU busy
    import os
    import time

    pidfile = tmp_path / "child.pid"
    code, out = render.run_cmd(["bash", "-c", f"sleep 300 & echo $! > {pidfile}; wait"], tmp_path, dict(os.environ),
                               timeout=1)
    assert code == 124 and "TIMEOUT" in out
    pid = int(pidfile.read_text())
    time.sleep(0.3)
    alive = os.path.exists(f"/proc/{pid}") and "Z" not in open(f"/proc/{pid}/stat").read().split()[2]
    assert not alive, f"child {pid} survived the timeout"
