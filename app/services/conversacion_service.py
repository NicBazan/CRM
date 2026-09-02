from sqlalchemy.orm import Session
from app.models.cliente import Cliente
from app.models.conversacion import Conversacion
from app.models.enums import ModoAtencion, CanalOrigen
from app.channels.base import MensajeEntrante
from datetime import datetime, timezone


class ConversacionService:
    """Gestión de conversaciones y lógica de handoff."""

    def __init__(self, db: Session):
        self.db = db

    def obtener_o_crear(self, mensaje: MensajeEntrante) -> Conversacion:
        """
        Busca una conversación activa para este id_externo + canal.
        Si no existe, crea el cliente y la conversación.
        """
        canal_enum = CanalOrigen(mensaje.canal)

        # Buscar conversación existente
        conversacion = (
            self.db.query(Conversacion)
            .filter(
                Conversacion.id_externo == mensaje.id_externo,
                Conversacion.canal == canal_enum,
                Conversacion.activa == True,
            )
            .first()
        )

        if conversacion:
            # Actualizar timestamp
            conversacion.fecha_ultimo_mensaje = datetime.now(timezone.utc)
            self.db.commit()
            return conversacion

        # No existe — crear cliente + conversación
        cliente = Cliente(nombre=mensaje.nombre_remitente)
        self.db.add(cliente)
        self.db.flush()  # Para obtener el ID antes del commit

        conversacion = Conversacion(
            cliente_id=cliente.id,
            canal=canal_enum,
            id_externo=mensaje.id_externo,
            modo_atencion=ModoAtencion.IA,
            fecha_ultimo_mensaje=datetime.now(timezone.utc)
        )
        self.db.add(conversacion)
        self.db.commit()
        self.db.refresh(conversacion)

        return conversacion

    def cambiar_modo(
        self, conv_id: int, nuevo_modo: ModoAtencion, usuario_id: int | None = None
    ) -> Conversacion | None:
        """Cambia el modo de atención de una conversación (IA ↔ HUMANO)."""
        conv = self.db.query(Conversacion).get(conv_id)
        if not conv:
            return None

        conv.modo_atencion = nuevo_modo
        conv.atendido_por_usuario_id = usuario_id if nuevo_modo == ModoAtencion.HUMANO else None
        self.db.commit()
        self.db.refresh(conv)
        return conv
