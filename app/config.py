from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    github_token: str | None = None

    deepseek_base_url: str | None = None
    deepseek_api_key: str | None = None

    redis_url: str = "redis://localhost:6379/0"

    llm_provider: str = "deepseek"
    model_name: str = "deepseek-v3.2"

    # 提示词配置
    llm_report_prompt_version: str = "v1"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

