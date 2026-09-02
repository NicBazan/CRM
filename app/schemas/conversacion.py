from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.enums import ModoAtencion, CanalOrigen


class ConversacionResponse(BaseModel):
    id: int
    cliente_id: int
    canal: CanalOrigen
    id_externo: str
    modo_atencion: ModoAtencion
    atendido_por_usuario_id: Optional[int] = None
    activa: bool
    fecha_inicio: datetime
    fecha_ultimo_mensaje: datetime

    model_config = {"from_attributes": True}


class HandoffRequest(BaseModel):
    """Request para cambiar quién atiende la conversación."""
    modo: ModoAtencion


class RespuestaHumana(BaseModel):
    """Request para que el gerente envíe un mensaje manual."""
    texto: str
