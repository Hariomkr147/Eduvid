# Test / admin runner: python 3.11 + ffmpeg + psql, with eduvid_common installed editable.
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg postgresql-client \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY common/pyproject.toml /app/common/pyproject.toml
COPY common/eduvid_common /app/common/eduvid_common
RUN pip install --no-cache-dir -e "/app/common[service,test]"
