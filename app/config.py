from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # e.g. postgresql+psycopg2://dairy:dairy_dev_pw@localhost:5432/dairy_shop
    database_url: str
    jwt_secret: str
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 60 * 12  # 12h, so a worker's shift doesn't get logged out

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
