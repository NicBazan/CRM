from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class MensajeEntrante:
    """
    Mensaje normalizado con soporte multimedia.
    Independiente del canal de origen.
    """
    canal: str
    id_externo: str
    nombre_remitente: str
    texto: str | None = None

    # === CAMPOS MULTIMEDIA ===
    audio_url: str | None = None
    audio_file_id: str | None = None
    imagen_url: str | None = None
    imagen_file_id: str | None = None

    payload_crudo: dict = field(default_factory=dict)


@dataclass
class MensajeSaliente:
    """Respuesta normalizada que el adaptador convierte al formato del canal."""
    id_destino: str
    texto: str
    teclado: list[list[str]] | None = None
    remover_teclado: bool = False


class ChannelAdapter(ABC):
    """
    Interfaz que cada canal debe implementar.
    Define cómo parsear mensajes entrantes y enviar respuestas.
    """

    @abstractmethod
    def parsear_entrada(self, payload: dict) -> MensajeEntrante | None:
        """Convierte el payload crudo del webhook en un MensajeEntrante normalizado."""
        ...

    @abstractmethod
    async def enviar_mensaje(self, mensaje: MensajeSaliente) -> bool:
        """Envía un mensaje de texto a través de este canal."""
        ...

    async def obtener_url_archivo(self, file_id: str) -> str | None:
        """Obtiene la URL de descarga directa de un archivo del canal."""
        return None
