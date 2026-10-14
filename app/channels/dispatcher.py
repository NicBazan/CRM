import logging
from app.channels.base import ChannelAdapter, MensajeSaliente
from app.channels.telegram import TelegramAdapter
from app.channels.whatsapp import WhatsAppAdapter, FueraDeVentana24HorasError
from app.channels.facebook import FacebookMessengerAdapter
from app.models.enums import CanalOrigen

logger = logging.getLogger(__name__)


class CanalNoSoportadoError(Exception):
    """Excepción cuando se solicita un canal no configurado o soportado."""
    pass


class MessageDispatcher:
    """
    Despachador central multicanal.
    Desacopla el núcleo del CRM (agente IA y operadores humanos) de las APIs
    específicas de cada plataforma (Telegram, WhatsApp, Facebook Messenger).
    """

    def __init__(self):
        # Registro de adaptadores
        self._adapters: dict[str, ChannelAdapter] = {
            CanalOrigen.TELEGRAM.value: TelegramAdapter(),
            CanalOrigen.WHATSAPP.value: WhatsAppAdapter(),
            CanalOrigen.FACEBOOK.value: FacebookMessengerAdapter(),
            CanalOrigen.INSTAGRAM.value: FacebookMessengerAdapter(),  # Instagram comparte la Graph API de Messenger
        }

    def get_adapter(self, canal: CanalOrigen | str) -> ChannelAdapter:
        """Obtiene el adaptador correspondiente a un canal."""
        canal_key = canal.value if isinstance(canal, CanalOrigen) else str(canal).lower()
        adapter = self._adapters.get(canal_key)
        if not adapter:
            logger.error("Intento de acceder a canal no soportado: %s", canal_key)
            raise CanalNoSoportadoError(f"Canal no soportado: {canal_key}")
        return adapter

    async def dispatch_saliente(self, canal: CanalOrigen | str, mensaje: MensajeSaliente) -> bool:
        """
        Envía un mensaje saliente a través del canal correspondiente.
        Propaga FueraDeVentana24HorasError si Meta rechaza el envío por superar las 24 horas.
        """
        adapter = self.get_adapter(canal)
        try:
            return await adapter.enviar_mensaje(mensaje)
        except FueraDeVentana24HorasError:
            # Propagar para que el llamador (controlador de API) notifique al operador
            raise
        except Exception as e:
            logger.error("Error inesperado despachando mensaje por %s: %s", canal, e, exc_info=True)
            return False


# Singleton global
dispatcher = MessageDispatcher()
