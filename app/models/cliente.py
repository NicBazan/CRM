from sqlalchemy import Column, Integer, String, DateTime, Boolean, JSON
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base


class Cliente(Base):
    __tablename__ = "clientes"

    id = Column(Integer, primary_key=True, index=True)
    nombre = Column(String(100), nullable=True)
    email = Column(String(200), nullable=True)
    servicio_interes = Column(String(200), nullable=True)
    zona = Column(String(200), nullable=True)
    telefono = Column(String(50), nullable=True)
    metadatos = Column(JSON, default=dict)
    notas_internas = Column(String(1000), nullable=True)
    activo = Column(Boolean, default=True)
    fecha_creacion = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_actualizacion = Column(
        DateTime,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relaciones
    conversaciones = relationship("Conversacion", back_populates="cliente")
