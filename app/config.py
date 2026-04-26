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

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )


settings = Settings()
