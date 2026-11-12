# Build context: repo root. GPU render worker: headless Chrome (WebGL on the L4) + ffmpeg (NVENC drafts).
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/pw
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl xz-utils python3.11 python3.11-venv ffmpeg \
      libegl1 libgl1 libgles2 libvulkan1 vulkan-tools mesa-utils \
      fonts-noto-core fonts-noto-color-emoji fonts-deva \
    && rm -rf /var/lib/apt/lists/*
# Node 22 (official binary)
ARG NODE_VERSION=22.12.0
RUN curl -fsSL https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-x64.tar.xz | tar -xJ -C /opt \
    && ln -s /opt/node-v${NODE_VERSION}-linux-x64/bin/node /usr/local/bin/node && node --version
RUN python3.11 -m venv /opt/venv
ENV PATH=/opt/venv/bin:$PATH
COPY services/render-worker/requirements.txt /tmp/req.txt
RUN pip install --no-cache-dir -r /tmp/req.txt \
    && playwright install --with-deps chromium \
    && ln -sf "$(ls -d /opt/pw/chromium-*/chrome-linux/chrome | head -1)" /usr/bin/chromium && /usr/bin/chromium --version
# NVIDIA EGL/Vulkan vendor files (the driver libs themselves are mounted by the container toolkit)
RUN mkdir -p /usr/share/glvnd/egl_vendor.d /usr/share/vulkan/icd.d \
    && printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libEGL_nvidia.so.0"}}\n' > /usr/share/glvnd/egl_vendor.d/10_nvidia.json \
    && printf '{"file_format_version":"1.0.0","ICD":{"library_path":"libGLX_nvidia.so.0","api_version":"1.3"}}\n' > /usr/share/vulkan/icd.d/nvidia_icd.json
ENV CHROME=/usr/bin/chromium
COPY common /opt/common
RUN pip install --no-cache-dir "/opt/common[service]" && pip check
# A small known-good project to probe WebGL with at worker start (capture.mjs gpu)
COPY engine/videos/area-volume /srv/engine-probe
COPY engine/shared/tools/ /srv/engine-probe/tools/
WORKDIR /srv/render-worker
COPY services/render-worker/ .
CMD ["python", "-m", "render_worker.main"]
