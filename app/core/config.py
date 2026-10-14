import logging
from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """
    Configuración centralizada del CRM.
    Lee automáticamente del archivo .env en la raíz del proyecto.
    """

    # --- Entorno de Ejecución ---
    ENVIRONMENT: str = "development"  # "development" | "production" | "testing"
    ENABLE_DEV_ROUTES: bool = True

    # --- Base de datos ---
    DATABASE_URL: str = "sqlite:///./basedatos.db"

    # --- Telegram ---
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_SECRET_TOKEN: str = ""  # Token secreto enviado por Telegram en el header X-Telegram-Bot-Api-Secret-Token

    # --- Meta (WhatsApp Cloud API & Facebook Messenger) ---
    META_VERIFY_TOKEN: str = "token_de_verificacion_crm"
    META_APP_SECRET: str = ""
    META_GRAPH_API_VERSION: str = "v21.0"
    WHATSAPP_API_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ARGENTINA_STRIP_9: bool = False
    FACEBOOK_PAGE_ACCESS_TOKEN: str = ""
    FACEBOOK_PAGE_ID: str = ""

    # --- LLM (Agente IA) ---
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: str = ""
    GEMINI_MODEL: str = "gemini-3.5-flash-lite"
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o-mini"

    # --- CORS ---
    CORS_ORIGINS: list[str] = ["http://localhost:5173"]

    # --- Autenticación y Seguridad (JWT & API Key) ---
    SECRET_KEY: str = "cambiar-en-produccion"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24  # 24 horas por defecto
    ADMIN_USERNAME: str = "admin"
    ADMIN_PASSWORD: str = "admin123"
    ADMIN_API_KEY: str = ""

    @model_validator(mode="after")
    def validar_seguridad_produccion(self):
        """Valida que no se utilicen valores inseguros por defecto en producción."""
        if self.ENVIRONMENT.lower() == "production":
            if self.SECRET_KEY in ("cambiar-en-produccion", "", "secret"):
                raise ValueError(
                    "❌ ERROR CRÍTICO DE SEGURIDAD: En entorno 'production', SECRET_KEY debe ser una cadena aleatoria y segura, no el valor por defecto."
                )
            if not self.META_APP_SECRET:
                logger.warning("⚠️ PRODUCCIÓN: META_APP_SECRET no está configurado. Los webhooks de Meta serán rechazados por seguridad.")
            if not self.TELEGRAM_SECRET_TOKEN:
                logger.warning("⚠️ PRODUCCIÓN: TELEGRAM_SECRET_TOKEN no está configurado. Los webhooks de Telegram serán rechazados por seguridad.")
        return self

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton cacheado de la configuración.
    Se lee del .env una sola vez al iniciar la app.
    """
    return Settings()
