import os
import sys
import time
import subprocess
import shutil
from pathlib import Path

if not os.environ.get("KAGGLE_API_TOKEN"):
    sys.exit("set KAGGLE_API_TOKEN in the environment")

KID = "hariom1407/fs-area-volume-render"
PROJ = Path("videos/area-volume").resolve()
OUT_DIR = PROJ / "kaggle_out"
OUT_DIR.mkdir(parents=True, exist_ok=True)

print(f"Monitoring {KID}...")
start_time = time.time()

while True:
    try:
        r = subprocess.run(
            [sys.executable, "-m", "kaggle.cli", "kernels", "status", KID],
            capture_output=True,
            text=True,
            timeout=30
        )
        status_line = (r.stdout + r.stderr).strip()
    except Exception as e:
        status_line = f"Network retry ({e})"

    elapsed_min = int((time.time() - start_time) / 60)
    print(f"[{elapsed_min}m] {status_line}", flush=True)

    if "COMPLETE" in status_line.upper():
        print("\n=== Kernel execution COMPLETE! Downloading output... ===")
        try:
            r = subprocess.run(
                [sys.executable, "-m", "kaggle.cli", "kernels", "output", KID, "-p", str(OUT_DIR), "-o"],
                capture_output=True,
                text=True,
                timeout=300
            )
            print(r.stdout)
            if r.stderr:
                print(r.stderr)
        except Exception as e:
            print(f"Error during output download: {e}")

        # Check for nested 'out' directory
        src_dir = OUT_DIR
        if (OUT_DIR / "out").is_dir():
            src_dir = OUT_DIR / "out"

        renders_dir = PROJ / "renders"
        review_dir = PROJ / "review"
        data_dir = PROJ / "data"

        renders_dir.mkdir(parents=True, exist_ok=True)
        review_dir.mkdir(parents=True, exist_ok=True)
        data_dir.mkdir(parents=True, exist_ok=True)

        # Copy renders
        for f in ["area-volume.mp4", "area-volume-share.mp4"]:
            p = src_dir / f
            if p.exists():
                shutil.copy2(p, renders_dir / f)
                print(f"Copied {f} to {renders_dir / f} ({p.stat().st_size / 1e6:.2f} MB)")

        # Copy review
        for f in ["all.jpg", "check.txt"]:
            p = src_dir / f
            if p.exists():
                shutil.copy2(p, review_dir / f)
                print(f"Copied {f} to {review_dir / f}")

        # Copy data
        for f in ["narration.wav", "lines.json", "words.json", "words.txt", "cues.json", "mix.wav"]:
            p = src_dir / f
            if p.exists():
                shutil.copy2(p, data_dir / f)
                print(f"Copied {f} to {data_dir / f}")

        print("\nALL OUTPUT FILES SUCCESSFULLY SYNCED!")
        break

    if "ERROR" in status_line.upper() or "CANCEL" in status_line.upper():
        print(f"\nKernel execution FAILED with status: {status_line}")
        try:
            r = subprocess.run(
                [sys.executable, "-m", "kaggle.cli", "kernels", "output", KID, "-p", str(OUT_DIR)],
                capture_output=True,
                text=True,
                timeout=120
            )
            print(r.stdout)
            print(r.stderr)
        except Exception:
            pass
        sys.exit(1)

    time.sleep(25)
