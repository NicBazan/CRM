import logging
from sqlalchemy import create_engine, inspect, text
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
    Crea las tablas si no existen y aplica migraciones ligeras
    para columnas nuevas (como id_mensaje_canal) sin romper bases de datos preexistentes.
    """
    Base.metadata.create_all(bind=engine)

    try:
        inspector = inspect(engine)
        if "mensajes" in inspector.get_table_names():
            columnas = [c["name"] for c in inspector.get_columns("mensajes")]
            if "id_mensaje_canal" not in columnas:
                logger.info("Aplicando migración: agregando id_mensaje_canal a la tabla mensajes...")
                with engine.connect() as conn:
                    conn.execute(
                        text("ALTER TABLE mensajes ADD COLUMN id_mensaje_canal VARCHAR(150)")
                    )
                    conn.commit()
                logger.info("✅ Columna id_mensaje_canal agregada exitosamente.")
    except Exception as e:
        logger.warning("No se pudo verificar o aplicar la migración de schema en init_db: %s", e)
