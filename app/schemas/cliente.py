from pydantic import BaseModel
from typing import Optional
from datetime import datetime


class ClienteCrear(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None


class ClienteActualizar(BaseModel):
    nombre: Optional[str] = None
    email: Optional[str] = None
    notas_internas: Optional[str] = None
    activo: Optional[bool] = None


class ClienteResponse(BaseModel):
    id: int
    nombre: Optional[str] = None
    email: Optional[str] = None
    telefono: Optional[str] = None
    metadatos: Optional[dict] = None
    notas_internas: Optional[str] = None
    activo: bool
    fecha_creacion: datetime
    fecha_actualizacion: datetime

    model_config = {"from_attributes": True}
