"""render-worker: one per GPU. Probes WebGL once, then claims `render` jobs.

Scratch hygiene (Review Focus 5): each job works in <scratch>/<job id>, deleted on success, failure, crash, and at
startup (orphans left by a worker that died mid-render). <scratch> is this worker's own folder.
"""
import logging
import os
import shutil
import socket
import tempfile
import threading
import time
import traceback
from pathlib import Path

from eduvid_common import jobs
from eduvid_common import storage as _storage
from eduvid_common.db import pool

from . import render

log = logging.getLogger("render-worker")
storage = _storage
HEARTBEAT_S = 60
LOCK_S = 1800
ENGINE_TOOLS = Path(os.environ.get("ENGINE_TOOLS", "/srv/engine-probe"))

RENDER_COLS = {"status", "video_key", "sheet_key", "gpu_seconds", "webgl_renderer"}


def update_render(render_id: int | None, **cols) -> None:
    if render_id is None or not cols:
        return
    assert set(cols) <= RENDER_COLS, cols
    sets = ", ".join(f"{k} = %({k})s" for k in cols)
    with pool().connection() as conn:
        conn.execute(f"UPDATE renders SET {sets}, updated_at = now() WHERE id = %(rid)s", {**cols, "rid": render_id})


class Worker:
    def __init__(self, name: str, gpu: int, scratch: Path, flags: str, renderer: str, runner=render.run_cmd):
        self.name, self.gpu, self.scratch = name, gpu, Path(scratch)
        self.flags, self.renderer, self.runner = flags, renderer, runner

    def startup(self) -> None:
        self.scratch.mkdir(parents=True, exist_ok=True)
        for p in self.scratch.iterdir():
            shutil.rmtree(p, ignore_errors=True) if p.is_dir() else p.unlink(missing_ok=True)

    def _beat(self, job_id: int, stop: threading.Event) -> None:
        while not stop.wait(HEARTBEAT_S):
            try:
                jobs.heartbeat(job_id, LOCK_S)
            except Exception:
                log.exception("heartbeat failed for job %s", job_id)

    def run_once(self) -> bool:
        job = jobs.claim(["render"], self.name, self.gpu, LOCK_S)
        if job is None:
            return False
        rid = job.payload.get("render_id", job.render_id)
        out_prefix = job.payload.get("out_prefix", "").rstrip("/") + "/"
        stop = threading.Event()
        threading.Thread(target=self._beat, args=(job.id, stop), daemon=True).start()
        try:
            update_render(rid, status="rendering")
            result = render.run(job, self.scratch, self.flags, runner=self.runner, renderer=self.renderer)
            jobs.complete(job.id, result)
            update_render(rid, status="done", **result)
            log.info("job %s done in %.0f s: %s", job.id, result["gpu_seconds"], result["video_key"])
        except Exception as e:
            text = e.log if isinstance(e, render.RenderError) else traceback.format_exc()
            log_key = out_prefix + "log.txt"
            try:
                storage.put_bytes(log_key, text.encode(), "text/plain")
            except Exception:
                log_key = None
            state = jobs.fail(job.id, f"render: {e}", log_key=log_key)
            update_render(rid, status="failed" if state == "failed" else "pending")
            log.error("job %s %s: %s", job.id, state, e)
        finally:
            stop.set()
            shutil.rmtree(self.scratch / str(job.id), ignore_errors=True)
        return True


def probe_flags() -> tuple[str, str]:
    """Probe WebGL with the engine's capture tool on a tiny copy of a project. -> (flags, renderer)."""
    with tempfile.TemporaryDirectory() as d:
        proj = Path(d) / "probe"
        shutil.copytree(ENGINE_TOOLS, proj)
        seen = {}

        def probe(flags: str) -> str:
            seen[flags] = render.probe_renderer(proj, flags)
            log.info("webgl probe [%s] -> %s", flags, seen[flags])
            return seen[flags]

        flags = render.webgl_flags(probe)
    if not flags:
        log.warning("WARNING software GL: no flag set reached the NVIDIA GPU; rendering with SwiftShader")
        return "", "SwiftShader (software)"
    return flags, seen[flags]


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    gpu = int(os.environ.get("GPU_INDEX", "0"))
    name = f"render-gpu{gpu}-{socket.gethostname()}"
    scratch = Path(os.environ.get("SCRATCH_DIR", "/data/scratch")) / f"render-gpu{gpu}"
    flags, renderer = probe_flags()
    w = Worker(name, gpu, scratch, flags, renderer)
    w.startup()
    log.info("%s ready: webgl %s", name, renderer)
    while True:
        try:
            if not w.run_once():
                time.sleep(3)
        except Exception:
            log.exception("worker loop error")
            time.sleep(10)


if __name__ == "__main__":
    main()
