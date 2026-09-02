from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from datetime import datetime, timezone
from app.core.database import Base


class DocumentoConocimiento(Base):
    __tablename__ = "documentos_conocimiento"

    id = Column(Integer, primary_key=True, index=True)
    titulo = Column(String(200), nullable=False)
    categoria = Column(String(100), nullable=True)
    # ^^^ "servicios", "horarios", "precios", "politicas", "faq"
    contenido = Column(Text, nullable=False)
    # ^^^ El texto plano del conocimiento del negocio
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_actualizacion = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )
