# Build context: repo root.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /srv/speech-api
COPY common /opt/common
RUN pip install --no-cache-dir "/opt/common[service]"
COPY services/speech-api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY db /app/db
COPY services/speech-api/ .
ENV PYTHONUNBUFFERED=1
EXPOSE 8000
# one worker: the fair scheduler is per process
CMD ["uvicorn", "speech_api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers"]
