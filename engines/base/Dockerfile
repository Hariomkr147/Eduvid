# Shared base for GPU engines: CUDA 12.4 (driver 550) + Python 3.11 venv + ffmpeg (eduvid_common is installed per engine, after its heavy deps, to keep layer caching).
# Build context: repo root.   docker build -t eduvid/engine-base:1 -f engines/base/Dockerfile .
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.11 python3.11-venv python3.11-dev build-essential git curl ca-certificates \
      ffmpeg libsndfile1 espeak-ng \
    && rm -rf /var/lib/apt/lists/*
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH HF_HOME=/models/hf TORCH_HOME=/models/torch XDG_CACHE_HOME=/models/cache
RUN pip install --upgrade "pip<25" "setuptools<76" wheel \
 && pip install fastapi==0.115.6 "uvicorn[standard]==0.32.1" python-multipart==0.0.19 \
      soundfile==0.12.1 pytest==8.3.4 httpx==0.28.1
WORKDIR /srv/engine
EXPOSE 8000
