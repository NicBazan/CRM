# Importar todos los modelos para que Base.metadata.create_all() los detecte
from app.models.cliente import Cliente
from app.models.conversacion import Conversacion
from app.models.mensaje import Mensaje
from app.models.archivo_media import ArchivoMedia
from app.models.documento_conocimiento import DocumentoConocimiento
from app.models.enums import ModoAtencion, TipoMensaje, TipoContenido, CanalOrigen

__all__ = [
    "Cliente",
    "Conversacion",
    "Mensaje",
    "ArchivoMedia",
    "DocumentoConocimiento",
    "ModoAtencion",
    "TipoMensaje",
    "TipoContenido",
    "CanalOrigen",
]
