import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import get_settings
from app.core.database import engine, Base, init_db
from app.api.routes import clientes, webhooks, conversaciones, conocimiento, dev

# Importar todos los modelos para que Base los registre
import app.models  # noqa: F401

# ==========================================
# LOGGING
# ==========================================
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-8s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("crm")

settings = get_settings()


# ==========================================
# LIFECYCLE (startup / shutdown)
# ==========================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Eventos de inicio y cierre de la aplicación."""
    # --- Startup ---
    logger.info("=" * 55)
    logger.info("🚀 CRM Ciclo Confort — Iniciando")
    logger.info("=" * 55)
    logger.info("  Database:  %s", settings.DATABASE_URL)
    logger.info("  LLM:       %s (%s)", settings.LLM_PROVIDER, settings.GEMINI_MODEL if settings.LLM_PROVIDER == "gemini" else settings.OPENAI_MODEL)
    logger.info("  Gemini:    %s", "✅ Configurada" if settings.GEMINI_API_KEY else "❌ Falta API key")
    logger.info("  OpenAI:    %s", "✅ Configurada" if settings.OPENAI_API_KEY else "❌ Falta API key")
    logger.info("  Telegram:  %s", "✅ Configurado" if settings.TELEGRAM_BOT_TOKEN else "❌ Falta token")
    logger.info("  CORS:      %s", settings.CORS_ORIGINS)
    logger.info("=" * 55)

    yield

    # --- Shutdown ---
    logger.info("👋 CRM Ciclo Confort — Apagando")


# ==========================================
# INICIALIZACIÓN DE FASTAPI
# ==========================================
app = FastAPI(
    title="CRM Ciclo Confort",
    version="2.0.0",
    description="API del CRM omnicanal con agente IA y human-in-the-loop",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Crear tablas y aplicar migraciones ligeras
init_db()

# ==========================================
# REGISTRAR ROUTERS
# ==========================================
app.include_router(clientes.router)
app.include_router(webhooks.router)
app.include_router(conversaciones.router)
app.include_router(conocimiento.router)
app.include_router(dev.router)


# ==========================================
# HEALTH CHECK
# ==========================================
@app.get("/", tags=["Health"])
def health_check():
    return {
        "status": "healthy",
        "version": "2.0.0",
        "servicio": "CRM Ciclo Confort",
    }
