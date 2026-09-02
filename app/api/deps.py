"""
Dependencias compartidas para inyección en las rutas.
"""
from app.core.database import SessionLocal


def get_db():
    """
    Generador que crea una sesión de base de datos por request
    y la cierra automáticamente al finalizar.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
