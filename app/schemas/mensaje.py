from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from app.models.enums import TipoMensaje, TipoContenido


class MensajeResponse(BaseModel):
    id: int
    conversacion_id: int
    tipo_mensaje: TipoMensaje
    tipo_contenido: TipoContenido
    contenido: str
    archivo_media_id: Optional[int] = None
    fecha_creacion: datetime

    model_config = {"from_attributes": True}


class DocumentoConocimientoCrear(BaseModel):
    titulo: str
    categoria: Optional[str] = None
    contenido: str


class DocumentoConocimientoActualizar(BaseModel):
    titulo: Optional[str] = None
    categoria: Optional[str] = None
    contenido: Optional[str] = None
    activo: Optional[bool] = None


class DocumentoConocimientoResponse(BaseModel):
    id: int
    titulo: str
    categoria: Optional[str] = None
    contenido: str
    activo: bool
    fecha_creacion: datetime

    model_config = {"from_attributes": True}
