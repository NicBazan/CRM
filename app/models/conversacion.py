from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey, Boolean
from sqlalchemy.orm import relationship
from datetime import datetime, timezone
from app.core.database import Base
from app.models.enums import ModoAtencion, CanalOrigen, EstadoOnboarding


class Conversacion(Base):
    __tablename__ = "conversaciones"

    id = Column(Integer, primary_key=True, index=True)
    cliente_id = Column(Integer, ForeignKey("clientes.id"), nullable=False, index=True)
    canal = Column(Enum(CanalOrigen), nullable=False)
    id_externo = Column(String(100), nullable=False, index=True)
    # ^^^ chat_id de Telegram, phone number de WhatsApp, etc.

    # ============================================
    # CAMPO CRÍTICO: ¿Quién atiende esta conversación?
    # ============================================
    modo_atencion = Column(
        Enum(ModoAtencion),
        default=ModoAtencion.IA,
        nullable=False,
    )
    # ID del usuario gerente que tomó el control (null si es IA)
    atendido_por_usuario_id = Column(Integer, nullable=True)

    estado_onboarding = Column(
        Enum(EstadoOnboarding),
        default=EstadoOnboarding.EN_CURSO,
        nullable=False,
    )
    paso_onboarding = Column(Integer, default=0)

    activa = Column(Boolean, default=True)
    fecha_inicio = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_ultimo_mensaje = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    # Relaciones
    cliente = relationship("Cliente", back_populates="conversaciones")
    mensajes = relationship(
        "Mensaje",
        back_populates="conversacion",
        order_by="Mensaje.fecha_creacion",
    )
