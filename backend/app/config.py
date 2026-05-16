from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    gcp_project_id: str = "hairgpt-496305"
    gcp_location: str = "asia-south1"

    shopify_shop: str = "moxie-dev-store-soqsybgm"
    shopify_api_version: str = "2026-07"
    shopify_client_id_secret: str = "shopify-client-id"
    shopify_client_secret_secret: str = "shopify-client-secret"

    db_instance: str = "hairgpt-496305:asia-south1:hairgpt-db"
    db_name: str = "hairgpt"
    db_user: str = "hairgpt-app"
    db_password_secret: str = "db-app-password"


settings = Settings()
