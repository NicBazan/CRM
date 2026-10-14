from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class UnifiedMessage:
    """
    Mensaje unificado y normalizado para todas las plataformas (Telegram, WhatsApp, Facebook).
    Independiente del canal de origen.
    """
    canal: str
    id_externo: str
    nombre_remitente: str
    id_mensaje_canal: str | None = None
    texto: str | None = None

    # === CAMPOS MULTIMEDIA ===
    audio_url: str | None = None
    audio_file_id: str | None = None
    imagen_url: str | None = None
    imagen_file_id: str | None = None

    timestamp: datetime | None = None
    payload_crudo: dict = field(default_factory=dict)


# Alias para retrocompatibilidad con código existente
MensajeEntrante = UnifiedMessage


@dataclass
class MensajeSaliente:
    """Respuesta normalizada que el adaptador convierte al formato nativo del canal."""
    id_destino: str
    texto: str
    teclado: list[list[str]] | list[str] | None = None
    remover_teclado: bool = False

    def obtener_opciones_planas(self) -> list[str]:
        """Devuelve una lista plana de strings con las opciones de botones."""
        if not self.teclado:
            return []
        resultado = []
        for fila in self.teclado:
            if isinstance(fila, list):
                for item in fila:
                    if item:
                        resultado.append(str(item))
            elif isinstance(fila, str) and fila:
                resultado.append(fila)
        return resultado


class ChannelAdapter(ABC):
    """
    Interfaz que cada canal debe implementar.
    Define cómo parsear mensajes entrantes, enviar respuestas e interactuar con archivos.
    """

    @abstractmethod
    def parsear_entrada(self, payload: dict) -> UnifiedMessage | None:
        """Convierte el payload crudo del webhook en un UnifiedMessage normalizado."""
        ...

    @abstractmethod
    async def enviar_mensaje(self, mensaje: MensajeSaliente) -> bool:
        """Envía un mensaje a través del canal correspondiente."""
        ...

    async def obtener_url_archivo(self, file_id: str) -> str | None:
        """Obtiene la URL de descarga directa de un archivo del canal."""
        return None

    async def descargar_archivo(self, file_id: str) -> tuple[bytes, str] | None:
        """
        Descarga el binario del archivo autenticado si la plataforma lo requiere (e.g. Meta Graph API).
        Retorna (contenido_bytes, mime_type).
        """
        return None
