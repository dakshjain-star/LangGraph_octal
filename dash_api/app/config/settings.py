"""Configuration settings for the Dash SaaS API."""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Application
    app_name: str = "Dash SaaS API"
    app_version: str = "1.0.0"
    environment: str = "development"
    debug: bool = True
    api_prefix: str = "/api/v1"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8001
    
    # MongoDB
    mongodb_url: str = "mongodb+srv://octaldaksh:octal123@cluster0.5xt6n.mongodb.net/"
    mongodb_db_name: str = "dash_saas"
    mongodb_min_pool_size: int = 10
    mongodb_max_pool_size: int = 50
    
    # JWT
    jwt_secret_key: str = "your-super-secret-jwt-key-change-this-in-production"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 7
    
    # CORS
    cors_origins: str = "https://nexus-esw7.onrender.com,http://localhost:3000,http://localhost:5173,http://127.0.0.1:3000,http://127.0.0.1:5173"
    cors_credentials: bool = True
    cors_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_headers: str = "Content-Type,Authorization"
    
    # Email (SMTP)
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_username: str = ""
    smtp_password: str = ""
    smtp_from_email: str = "noreply@dashsaas.com"
    smtp_from_name: str = "Dash SaaS"
    smtp_use_tls: bool = True
    
    # Password Reset
    password_reset_token_expire_hours: int = 24
    
    # File Upload
    max_upload_size_mb: int = 5
    allowed_upload_extensions: str = ".jpg,.jpeg,.png,.gif"
    
    # Rate Limiting
    rate_limit_per_minute: int = 100
    
    # Logging
    log_level: str = "INFO"
    
    # Internal API secret for chatbot communication
    internal_api_secret: str = "chatbot-internal-secret"
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        return [origin.strip() for origin in self.cors_origins.split(",")]
    
    @property
    def allowed_extensions_list(self) -> List[str]:
        """Parse allowed file extensions from comma-separated string."""
        return [ext.strip() for ext in self.allowed_upload_extensions.split(",")]


# Global settings instance
settings = Settings()
