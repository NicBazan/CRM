from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """
    Configuración centralizada del CRM.
    Lee automáticamente del archivo .env en la raíz del proyecto.
    """

    # --- Base de datos ---
    DATABASE_URL: str = "sqlite:///./basedatos.db"

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = ""

    # --- LLM (Agente IA) ---
    LLM_PROVIDER: str = "gemini"    # Modelos (con soporte para nuevos modelos de Gemini 3.5 Lite para evitar cuotas limitadas y 404s)
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # --- JWT (futuro) ---
    SECRET_KEY: str = "cambiar-en-produccion"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton cacheado de la configuración.
    Se lee del .env una sola vez al iniciar la app.
    """
    return Settings()
