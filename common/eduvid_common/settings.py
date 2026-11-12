"""Service settings. Values come only from the environment (compose injects .env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    database_url: str
    s3_endpoint: str = "http://minio:9000"
    s3_bucket: str = "eduvid"
    s3_access_key: str = ""
    s3_secret_key: str = ""
    speech_api_url: str = "http://speech-api:8000"
    engine_omnivoice_url: str = "http://tts-omnivoice:8000"
    engine_kokoro_url: str = "http://tts-kokoro:8000"
    engine_asr_url: str = "http://asr-whisperx:8000"
    scratch_dir: str = "/data/scratch"
    domain: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
