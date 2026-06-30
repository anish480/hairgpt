from functools import lru_cache

from google.cloud import secretmanager

from app.config import settings


@lru_cache(maxsize=64)
def get_secret(secret_id: str, version: str = "latest") -> str:
    client = secretmanager.SecretManagerServiceClient()
    name = f"projects/{settings.gcp_project_id}/secrets/{secret_id}/versions/{version}"
    return client.access_secret_version(name=name).payload.data.decode("utf-8").strip()
