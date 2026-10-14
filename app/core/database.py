import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# El connect_args solo es necesario para SQLite (modo multi-thread)
connect_args = {}
if settings.DATABASE_URL.startswith("sqlite"):
    connect_args = {"check_same_thread": False}

engine = create_engine(settings.DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db():
    """
    Crea las tablas iniciales si no existen.
    Las migraciones continuas de esquema se gestionan formalmente con Alembic (`alembic upgrade head`).
    """
    Base.metadata.create_all(bind=engine)
