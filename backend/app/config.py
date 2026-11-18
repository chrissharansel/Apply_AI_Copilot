from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    copilot_bin: str = "copilot"               # GitHub Copilot CLI executable
    copilot_model: str = ""                    # empty = Copilot's default; or e.g. "auto" or a model id
    copilot_timeout: int = 240
    copilot_concurrency: int = 2               # parallel CLI processes
    copilot_github_token: str = ""             # optional; otherwise use `copilot` /login or gh auth
    copilot_extra_args: str = ""

    mongodb_uri: str = "mongodb://localhost:27017"
    database_name: str = "applyai"

    secret_key: str = ""
    jwt_expire_minutes: int = 60 * 24
    encryption_key: str = ""                    # Fernet key; empty = files stored unencrypted

    storage_dir: str = "storage"
    cors_origins: str = "http://localhost:5173"
    headless: bool = False
    max_resume_mb: int = 5
    max_concurrent_sessions: int = 3
    similarity_threshold: float = 0.75          # lexical similarity for reusing a saved answer


settings = Settings()
