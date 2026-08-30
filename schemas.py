from pydantic import BaseModel
from typing import Optional

class ClienteCrear(BaseModel):
    telefono: str
    nombre: Optional[str] = None