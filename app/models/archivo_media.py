from sqlalchemy import Column, Integer, String, DateTime, Enum
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base
from app.models.enums import TipoContenido


class ArchivoMedia(Base):
    __tablename__ = "archivos_media"

    id = Column(Integer, primary_key=True, index=True)
    tipo = Column(Enum(TipoContenido), nullable=False)
    nombre_original = Column(String(255), nullable=True)
    ruta_almacenamiento = Column(String(500), nullable=False)
    # ^^^ Path local o URL de S3/GCS
    mime_type = Column(String(100), nullable=True)
    tamano_bytes = Column(Integer, nullable=True)

    # Resultado del procesamiento
    texto_extraido = Column(String(5000), nullable=True)
    # ^^^ Transcripción del audio o descripción de la imagen

    fecha_creacion = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relación inversa
    mensaje = relationship("Mensaje", back_populates="archivo_media", uselist=False)
