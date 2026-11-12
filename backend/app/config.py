from functools import lru_cache
from typing import Literal
from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    database_url: str = "postgresql+psycopg://quizeee:quizeee@localhost:5432/quizeee"
    redis_url: str = "redis://localhost:6379/0"
    jwt_secret: str = Field(min_length=32)
    app_origin: str = "http://localhost:3000"
    environment: str = "development"
    access_minutes: int = Field(default=15, ge=1, le=15)
    teacher_access_hours: int = Field(default=24, ge=1, le=24)
    ai_provider: Literal["gemini", "openai"] = "gemini"
    gemini_api_key: SecretStr = SecretStr("")
    gemini_question_model: str = Field(default="gemini-2.5-flash-lite", pattern=r"^[A-Za-z0-9._-]+$", max_length=100)
    openai_api_key: SecretStr = SecretStr("")
    openai_question_model: str = Field(default="gpt-4.1-mini", min_length=1, max_length=100)
    ai_max_questions_per_request: int = Field(default=20, ge=1, le=20)
    ai_max_text_length: int = Field(default=20000, ge=100, le=20000)
    ai_max_image_size_mb: int = Field(default=10, ge=1, le=20)
    ai_request_timeout_seconds: int = Field(default=45, ge=5, le=120)
    ai_max_output_tokens: int = Field(default=8000, ge=1000, le=16000)
    ai_daily_limit_faculty: int = Field(default=50, ge=1)
    ai_daily_limit_admin: int = Field(default=100, ge=1)
    ai_daily_limit_faculty_lite: int = Field(default=10, ge=1)
    ai_requests_per_minute: int = Field(default=5, ge=1)

    document_conversion_url: str = Field(default="", max_length=500)
    document_renderer_url: str = Field(default="", max_length=500)
    document_service_token: SecretStr = SecretStr("")
    import_ai_max_context_chars: int = Field(default=350000, ge=1000, le=500000)

    @model_validator(mode="after")
    def production_settings(self):
        if self.environment == "production" and not self.app_origin.startswith("https://"):
            raise ValueError("Production requires an HTTPS app origin")
        if self.environment == "production" and (not self.database_url.startswith("postgresql") or self.jwt_secret.startswith("replace-")):
            raise ValueError("Production requires PostgreSQL and a unique signing secret")
        return self


@lru_cache
def settings() -> Settings:
    return Settings()
