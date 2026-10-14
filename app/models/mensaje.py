from sqlalchemy import Column, Integer, String, Text, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base
from app.models.enums import TipoMensaje, TipoContenido


class Mensaje(Base):
    __tablename__ = "mensajes"

    id = Column(Integer, primary_key=True, index=True)
    conversacion_id = Column(
        Integer, ForeignKey("conversaciones.id"), nullable=False, index=True
    )

    tipo_mensaje = Column(Enum(TipoMensaje), nullable=False)
    # ^^^ "cliente", "ia", "humano", "sistema"

    tipo_contenido = Column(Enum(TipoContenido), default=TipoContenido.TEXTO)
    # ^^^ "texto", "audio", "imagen", "documento"

    # Contenido textual (el mensaje en sí, o la transcripción del audio,
    # o la descripción de la imagen)
    contenido = Column(Text, nullable=False)

    # Si fue audio/imagen, referencia al archivo original
    archivo_media_id = Column(
        Integer, ForeignKey("archivos_media.id"), nullable=True
    )

    # Metadata cruda del canal (JSON serializado) — para debugging
    metadata_canal = Column(Text, nullable=True)

    # ID único del mensaje emitido por la plataforma (wamid, mid, update_id:message_id) para garantizar idempotencia
    id_mensaje_canal = Column(String(150), unique=True, index=True, nullable=True)

    fecha_creacion = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relaciones
    conversacion = relationship("Conversacion", back_populates="mensajes")
    archivo_media = relationship("ArchivoMedia", back_populates="mensaje")
