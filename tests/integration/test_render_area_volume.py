"""Live: draft render of area-volume on a GPU render worker, using the voice data from the voice/words test."""
import json
import subprocess
import tempfile
from pathlib import Path

import pytest

from eduvid_common import jobs, storage
from tests.integration.helpers import wait_job
from tests.integration.seed import seed, upload_project

pytestmark = pytest.mark.gpu


def ffprobe(path: Path) -> dict:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type,width,height:format=duration",
                          "-of", "json", str(path)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def render(quality: str, timeout_s: float) -> tuple[dict, dict]:
    s = seed()
    assert storage.exists(s["out_prefix"] + "words.json"), "run test_voice_area_volume.py first"
    d = seed(quality=quality)
    jid = jobs.enqueue("render", {"render_id": d["render_id"], "project_key": upload_project(),
                                  "data_prefix": s["out_prefix"], "quality": quality,
                                  "out_prefix": s["out_prefix"]}, render_id=d["render_id"])
    return wait_job(jid, timeout_s), s


def test_draft_render_on_gpu():
    r, s = render("draft", 600)
    assert r["status"] == "done", (r, storage.get_bytes(r["log_key"]).decode()[-3000:] if r["log_key"] else "")
    res = r["result"]
    print(f"\ndraft in {r['seconds']} s, gpu_seconds {res['gpu_seconds']}, webgl {res['webgl_renderer']}")
    assert r["seconds"] < 600 and "NVIDIA" in res["webgl_renderer"]
    lines = json.loads(storage.get_bytes(s["out_prefix"] + "lines.json"))
    with tempfile.TemporaryDirectory() as d:
        mp4 = storage.get_file(res["video_key"], Path(d) / "draft.mp4")
        info = ffprobe(mp4)
    video = [x for x in info["streams"] if x["codec_type"] == "video"][0]
    assert (video["width"], video["height"]) == (1080, 1920)
    assert any(x["codec_type"] == "audio" for x in info["streams"])
    assert abs(float(info["format"]["duration"]) - lines["duration"]) < 0.5
    check = storage.get_bytes(s["out_prefix"] + "check.txt").decode()
    print(check.splitlines()[-1])
    assert "CHECK OK" in check
