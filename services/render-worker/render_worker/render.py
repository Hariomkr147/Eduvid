"""One render job: project tar + voice data from S3 -> check, cues, mix, sheet, video -> S3 (spec §5.6, §9).

Steps run the engine's own tools inside the downloaded project:
  node tools/capture.mjs check          must print CHECK OK
  node tools/capture.mjs cues           data/cues.json
  python tools/mix.py .                 data/mix.wav (-14 LUFS, done by mix.py)
  node tools/capture.mjs sheet review/all.jpg 0.5 10
  node tools/capture.mjs video renders/draft.mp4 --draft --nvenc     (final: renders/final.mp4 --best)
"""
import os
import signal
import subprocess
import tarfile
import time
from collections.abc import Callable
from pathlib import Path

from eduvid_common import storage as _storage
from eduvid_common.jobs import Job

storage = _storage                     # swapped for an in-memory fake in tests

# Probed in this order at worker start (README "WebGL on the L4"). The first whose renderer names NVIDIA wins.
# GL-EGL comes first: with Vulkan, a second Chrome on the same L4 loses its WebGL context ("shaderSource … not of
# type WebGLShader"), so parallel renderers (JOBS > 1) fail. GL-EGL renders 3 in parallel fine (measured 2026-11-11).
FLAG_SETS = [
    "--use-gl=angle --use-angle=gl-egl",
    "--use-angle=vulkan --enable-features=Vulkan --disable-vulkan-surface",
    "--use-gl=egl",
]
SOFTWARE_ENV = {"SOFTWARE_GL": "1", "QS": "&res=0.75&aa=2&shadow=1024", "FPS": "24"}
JOBS = os.environ.get("JOBS", "3")              # Chrome renderers per worker (spec §9: start with 3 per L4)
DATA_FILES = ("narration.wav", "lines.json", "words.json")
STEP_TIMEOUT_S = {"check": 600, "cues": 300, "mix": 600, "sheet": 900, "video": 3600}

Runner = Callable[[list[str], Path, dict, float], tuple[int, str]]


class RenderError(RuntimeError):
    """A step failed. `log` holds everything the steps printed."""

    def __init__(self, msg: str, log: str):
        super().__init__(msg)
        self.log = log


def run_cmd(cmd: list[str], cwd: Path, env: dict, timeout: float) -> tuple[int, str]:
    """Run one step in its own process group. On timeout the whole group is killed: capture.mjs starts Chrome
    renderers and ffmpeg, which would otherwise keep running on the GPU after node is gone."""
    p = subprocess.Popen(cmd, cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         start_new_session=True)
    try:
        out, _ = p.communicate(timeout=timeout)
        return p.returncode, out
    except subprocess.TimeoutExpired:
        try:
            os.killpg(p.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        out, _ = p.communicate()
        return 124, (out or "") + f"\nTIMEOUT after {timeout:.0f} s"


def probe_renderer(project: Path, flags: str, runner: Runner = run_cmd) -> str:
    code, out = runner(["node", "tools/capture.mjs", "gpu"], project, {**os.environ, "CHROME_FLAGS": flags}, 180)
    for line in out.splitlines():
        if line.startswith("WEBGL RENDERER:"):
            return line.split(":", 1)[1].strip()
    return f"probe failed ({code}): {out[-300:]}"


def webgl_flags(probe: Callable[[str], str]) -> str:
    """First flag set whose WebGL renderer is the NVIDIA GPU, or "" (software GL)."""
    for flags in FLAG_SETS:
        if "NVIDIA" in probe(flags):
            return flags
    return ""


def _extract(tar_path: Path, dest: Path) -> None:
    dest = dest.resolve()
    with tarfile.open(tar_path) as t:
        for m in t.getmembers():
            target = (dest / m.name).resolve()
            if not (target == dest or dest in target.parents) or m.issym() or m.islnk() or m.isdev():
                raise RenderError(f"unsafe path in project tar: {m.name}", f"rejected tar member {m.name!r}")
        t.extractall(dest)


def run(job: Job, scratch: Path, flags: str, runner: Runner = run_cmd, renderer: str = "") -> dict:
    p = job.payload
    out_prefix = p["out_prefix"] if p["out_prefix"].endswith("/") else p["out_prefix"] + "/"
    data_prefix = p["data_prefix"] if p["data_prefix"].endswith("/") else p["data_prefix"] + "/"
    final = p.get("quality") == "final"
    work = scratch / str(job.id)
    proj = work / "project"
    proj.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()

    tar = storage.get_file(p["project_key"], work / "project.tar.gz")
    _extract(tar, proj)
    for f in DATA_FILES:
        storage.get_file(data_prefix + f, proj / "data" / f)

    env = {**os.environ, "CHROME_FLAGS": flags, "JOBS": str(JOBS)}
    if not flags:
        env.update(SOFTWARE_ENV)
    if final and p.get("fps"):
        env["FPS"] = str(p["fps"])
    video = "renders/final.mp4" if final else "renders/draft.mp4"
    steps = [
        ("check", ["node", "tools/capture.mjs", "check"]),
        ("cues", ["node", "tools/capture.mjs", "cues"]),
        ("mix", ["python", "tools/mix.py", "."]),
        ("sheet", ["node", "tools/capture.mjs", "sheet", "review/all.jpg", "0.5", "10"]),
        ("video", ["node", "tools/capture.mjs", "video", video, *(["--best"] if final else ["--draft", "--nvenc"])]),
    ]
    log: list[str] = [f"webgl: {renderer or '?'} flags: {flags or 'SOFTWARE_GL'}"]
    check_out = ""
    for name, cmd in steps:
        ts = time.monotonic()
        code, out = runner(cmd, proj, env, STEP_TIMEOUT_S[name])
        log.append(f"$ {' '.join(cmd)}  ({time.monotonic() - ts:.1f} s, exit {code})\n{out.rstrip()}")
        if name == "check":
            check_out = out
            if code != 0 or "CHECK OK" not in out:
                raise RenderError("check failed (no CHECK OK)", "\n".join(log))
        elif code != 0:
            raise RenderError(f"{name} failed (exit {code})", "\n".join(log))

    keys = {"video_key": out_prefix + Path(video).name, "sheet_key": out_prefix + "sheet.jpg"}
    storage.put_file(keys["video_key"], proj / video, "video/mp4")
    storage.put_file(keys["sheet_key"], proj / "review/all.jpg", "image/jpeg")
    storage.put_file(out_prefix + "mix.wav", proj / "data/mix.wav", "audio/wav")
    storage.put_bytes(out_prefix + "check.txt", check_out.encode(), "text/plain")
    storage.put_bytes(out_prefix + "log.txt", "\n".join(log).encode(), "text/plain")
    return {**keys, "gpu_seconds": round(time.monotonic() - t0, 2), "webgl_renderer": renderer}
