from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    anthropic_api_key: str = ""
    jwt_secret_key: str = "insecure-dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_hours: int = 8

    database_url: str = "sqlite:////app/data/law_firm.db"
    chroma_persist_path: str = "/app/data/chroma"
    uploads_path: str = "/app/data/uploads"
    library_path: str = "/app/data/library"

    admin_email: str = "admin@lawfirm.com"
    admin_password: str = "ChangeMe123!"

    slack_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    notification_email_to: str = ""

    backend_url: str = "http://backend:8000"


settings = Settings()
