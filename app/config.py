from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    postgres_user: str = "smartgarden"
    postgres_password: str = "changeme"
    postgres_db: str = "smartgarden"
    postgres_host: str = "localhost"
    postgres_port: int = 5432

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883

    notification_email: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Auth
    secret_key: str = "canvia-aquesta-clau-en-produccio"
    access_token_expire_days: int = 7
    admin_username: str = "admin"
    admin_password: str = "changeme"

    # OTA — URL accessible des de l'ESP32 per descarregar els binaris
    ota_base_url: str = "http://localhost:8000"

    # Web Push (VAPID)
    vapid_public_key: str = ""
    vapid_private_key: str = ""
    vapid_email: str = "mailto:admin@smartgarden.local"

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def sync_database_url(self) -> str:
        """URL síncrona per a les migracions Alembic (psycopg2)."""
        return (
            f"postgresql+psycopg2://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
