import logging
import httpx
from app.channels.base import ChannelAdapter, UnifiedMessage, MensajeSaliente
from app.channels.whatsapp import FueraDeVentana24HorasError
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class FacebookMessengerError(Exception):
    """Excepción base para errores de Facebook Messenger."""
    pass


class FacebookMessengerAdapter(ChannelAdapter):
    """
    Adaptador para Facebook Messenger / Meta Graph API.
    Soporta mensajes de texto, quick replies (botones interactivos), postbacks
    y adjuntos multimedia.
    """

    def __init__(self):
        self.settings = get_settings()
        self.token = self.settings.FACEBOOK_PAGE_ACCESS_TOKEN
        self.version = self.settings.META_GRAPH_API_VERSION or "v21.0"
        self.base_url = f"https://graph.facebook.com/{self.version}"

    def parsear_entrada(self, payload: dict) -> UnifiedMessage | None:
        """
        Convierte un payload de webhook de Facebook Messenger en un UnifiedMessage.
        Descarta ecos (mensajes propios) y eventos de entrega/lectura.
        """
        entries = payload.get("entry", [])
        if not entries:
            return None

        messaging_events = entries[0].get("messaging", [])
        if not messaging_events:
            return None

        event = messaging_events[0]

        # Descartar eventos de entrega (delivery) y lectura (read)
        if "delivery" in event or "read" in event:
            return None

        sender = event.get("sender", {})
        sender_id = str(sender.get("id", ""))
        if not sender_id:
            return None

        # Si viene un mensaje
        message = event.get("message")
        postback = event.get("postback")

        if message:
            # Descartar ecos (mensajes enviados por la propia página o bot)
            if message.get("is_echo", False):
                return None

            id_mensaje_canal = message.get("mid")
            resultado = UnifiedMessage(
                canal="facebook",
                id_externo=sender_id,
                nombre_remitente="Cliente Messenger",
                id_mensaje_canal=id_mensaje_canal,
                payload_crudo=payload,
            )

            # 1. Quick Reply (botón presionado)
            if "quick_reply" in message:
                quick_reply = message["quick_reply"]
                resultado.texto = quick_reply.get("payload") or message.get("text", "")

            # 2. Texto común
            elif "text" in message:
                resultado.texto = message["text"]

            # 3. Adjuntos multimedia
            attachments = message.get("attachments", [])
            if attachments:
                primero = attachments[0]
                tipo_att = primero.get("type")
                payload_att = primero.get("payload", {})
                url_att = payload_att.get("url")

                if tipo_att in ("audio", "voice"):
                    resultado.audio_url = url_att
                elif tipo_att == "image":
                    resultado.imagen_url = url_att

            return resultado

        # 4. Postback (botón fijo o menú persistente presionado)
        elif postback:
            resultado = UnifiedMessage(
                canal="facebook",
                id_externo=sender_id,
                nombre_remitente="Cliente Messenger",
                id_mensaje_canal=f"fb_postback_{postback.get('mid') or sender_id}",
                texto=postback.get("title") or postback.get("payload", ""),
                payload_crudo=payload,
            )
            return resultado

        return None

    async def obtener_url_archivo(self, file_id: str) -> str | None:
        """
        Para Facebook Messenger, la URL de adjuntos generalmente viene pública o semi-pública
        dentro del payload. Si file_id es una URL, se retorna directamente.
        """
        if file_id.startswith("http://") or file_id.startswith("https://"):
            return file_id
        return None

    async def descargar_archivo(self, file_id: str) -> tuple[bytes, str] | None:
        """Descarga el archivo a partir de la URL de Facebook."""
        url = await self.obtener_url_archivo(file_id)
        if not url:
            return None

        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(url)
            if resp.status_code == 200:
                mime_type = resp.headers.get("content-type", "application/octet-stream")
                return resp.content, mime_type
        return None

    async def enviar_mensaje(self, mensaje: MensajeSaliente) -> bool:
        """
        Envía un mensaje al usuario de Facebook Messenger.
        Soporta quick replies si se especifican opciones en el mensaje.
        """
        if not self.token:
            logger.error("No se ha configurado FACEBOOK_PAGE_ACCESS_TOKEN")
            return False

        endpoint = f"{self.base_url}/me/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        opciones = mensaje.obtener_opciones_planas()

        message_obj = {
            "text": mensaje.texto,
        }

        # Si hay botones/opciones, formatear como Quick Replies (hasta 13 permitidas)
        if opciones:
            quick_replies = []
            for i, opt in enumerate(opciones[:13]):
                titulo = opt.strip()
                if len(titulo) > 20:
                    titulo = titulo[:20].strip()
                quick_replies.append({
                    "content_type": "text",
                    "title": titulo,
                    "payload": opt,
                })
            message_obj["quick_replies"] = quick_replies

        payload = {
            "recipient": {"id": mensaje.id_destino},
            "messaging_type": "RESPONSE",
            "message": message_obj,
        }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)

            if resp.status_code in (200, 201):
                logger.info("✅ Mensaje enviado a Facebook Messenger (%s)", mensaje.id_destino)
                return True

            try:
                error_data = resp.json().get("error", {})
                error_code = error_data.get("code")
                error_subcode = error_data.get("error_subcode")
                error_message = error_data.get("message", resp.text)

                # Detección de ventana de 24 horas en Facebook Messenger
                if error_code in (10, 2018278) or "outside" in error_message.lower():
                    logger.warning(
                        "⚠️ Facebook Error: Fuera de la ventana de 24 horas para %s: %s",
                        mensaje.id_destino,
                        error_message,
                    )
                    raise FueraDeVentana24HorasError(
                        f"No se puede responder a {mensaje.id_destino} en Messenger: La ventana estándar de 24 horas ha expirado."
                    )

                logger.error(
                    "❌ Error enviando a Facebook Messenger (%s): Code %s, Subcode %s - %s",
                    resp.status_code,
                    error_code,
                    error_subcode,
                    error_message,
                )
            except FueraDeVentana24HorasError:
                raise
            except Exception:
                logger.error("❌ Error enviando a Facebook Messenger (%s): %s", resp.status_code, resp.text)

            return False
