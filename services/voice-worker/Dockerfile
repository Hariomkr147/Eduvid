# Build context: repo root. CPU only: it calls the speech gateway.
FROM python:3.11-slim
WORKDIR /srv/voice-worker
COPY common /opt/common
RUN pip install --no-cache-dir "/opt/common[service]"
COPY services/voice-worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && pip check
COPY services/voice-worker/ .
ENV PYTHONUNBUFFERED=1
CMD ["python", "-m", "voice_worker.main"]
