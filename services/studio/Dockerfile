# Build context: repo root. EduVid Studio: builder, library and player pages + the build pipeline (CPU only).
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/studio
COPY common /opt/common
RUN pip install --no-cache-dir "/opt/common[service]"
COPY services/studio/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY services/studio/ .
# the render engine files studio packs into each project (styles/nce-lesson + shared tools)
COPY engine/styles/nce-lesson /srv/studio/engine/styles/nce-lesson
COPY engine/shared/tools /srv/studio/engine/shared/tools
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["uvicorn", "studio.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "*"]
