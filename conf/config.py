from typing import List

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    BIND_IP: str
    BIND_PORT: int
    DB_URL: str

    DB_HOST: str = 'web_db'
    DB_PORT: int = 5432
    DB_USERNAME: str = 'postgres'
    DB_PASSWORD: str = 'postgres'
    DB_NAME: str = 'main_db'

    JWT_SECRET_SALT: str

    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_PASSWORD: str
    REDIS_SIRIUS_CACHE_PREFIX: str = 'sirius'

    RABBIT_SIRIUS_USER_PREFIX: str = 'user_memes'

    LOG_LEVEL: str = 'debug'

    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_HOST: str
    MINIO_PORT: str

    BUCKET_NAME: str = 'memes-storage'


settings = Settings()
