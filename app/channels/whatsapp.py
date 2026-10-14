import logging
import httpx
from app.channels.base import ChannelAdapter, UnifiedMessage, MensajeSaliente
from app.core.config import get_settings

logger = logging.getLogger(__name__)


class WhatsAppError(Exception):
    """Excepción base para errores de WhatsApp Cloud API."""
    pass


class FueraDeVentana24HorasError(WhatsAppError):
    """Lanzada cuando Meta rechaza el mensaje por haber superado la ventana de 24 horas."""
    pass


class WhatsAppAdapter(ChannelAdapter):
    """
    Adaptador para WhatsApp Business Cloud API (Meta Graph API).
    Soporta mensajes de texto, botones interactivos, listas, audios e imágenes,
    así como descarga autenticada en dos pasos.
    """

    def __init__(self):
        self.settings = get_settings()
        self.token = self.settings.WHATSAPP_API_TOKEN
        self.phone_number_id = self.settings.WHATSAPP_PHONE_NUMBER_ID
        self.version = self.settings.META_GRAPH_API_VERSION or "v21.0"
        self.base_url = f"https://graph.facebook.com/{self.version}"

    def normalizar_telefono(self, telefono: str) -> str:
        """
        Limpia caracteres especiales y opcionalmente maneja la particularidad
        del prefijo móvil argentino (549 vs 54) en sandboxes de Meta.
        """
        # Eliminar +, espacios y guiones
        limpio = "".join(c for c in str(telefono) if c.isdigit())

        # Manejo de Argentina (549... vs 54...):
        # En el sandbox de Meta a menudo se registra el número sin el 9 después de 54
        if self.settings.WHATSAPP_ARGENTINA_STRIP_9:
            if limpio.startswith("549") and len(limpio) >= 12:
                limpio = "54" + limpio[3:]
                logger.debug("Número argentino normalizado para sandbox: %s", limpio)

        return limpio

    def parsear_entrada(self, payload: dict) -> UnifiedMessage | None:
        """
        Convierte el payload del webhook de WhatsApp Cloud API en un UnifiedMessage.
        Descarta eventos de estado (delivered, read, sent).
        """
        # Extraer el 'value' soportando formato webhook de producción (entry.changes.value)
        # y formato de pruebas del panel de Meta (field=messages, value={...})
        value = {}
        if "entry" in payload and payload["entry"]:
            changes = payload["entry"][0].get("changes", [])
            if changes:
                value = changes[0].get("value", {})
        elif "value" in payload and isinstance(payload["value"], dict):
            value = payload["value"]
        elif "messages" in payload:
            value = payload
        else:
            return None

        # Si el webhook solo contiene 'statuses' (entregado, leído), no es un mensaje entrante
        if "statuses" in value and "messages" not in value:
            return None

        messages = value.get("messages", [])
        if not messages:
            return None

        msg = messages[0]
        id_mensaje_canal = msg.get("id")
        remitente = msg.get("from")

        if not remitente:
            return None

        # Extraer nombre del contacto si viene en el payload
        contacts = value.get("contacts", [])
        nombre = "Cliente WhatsApp"
        if contacts:
            nombre = contacts[0].get("profile", {}).get("name", "Cliente WhatsApp")

        resultado = UnifiedMessage(
            canal="whatsapp",
            id_externo=remitente,
            nombre_remitente=nombre,
            id_mensaje_canal=id_mensaje_canal,
            payload_crudo=payload,
        )

        tipo = msg.get("type")

        # 1. Mensaje de Texto estándar
        if tipo == "text":
            resultado.texto = msg.get("text", {}).get("body", "")

        # 2. Respuesta Interactiva (Botones o Listas)
        elif tipo == "interactive":
            interactive = msg.get("interactive", {})
            tipo_interactivo = interactive.get("type")

            if tipo_interactivo == "button_reply":
                button_reply = interactive.get("button_reply", {})
                resultado.texto = button_reply.get("title") or button_reply.get("id")
            elif tipo_interactivo == "list_reply":
                list_reply = interactive.get("list_reply", {})
                resultado.texto = list_reply.get("title") or list_reply.get("id")

        # 3. Mensaje de Audio / Nota de Voz
        elif tipo in ("audio", "voice"):
            audio_obj = msg.get(tipo, {})
            resultado.audio_file_id = audio_obj.get("id")

        # 4. Mensaje de Imagen
        elif tipo == "image":
            image_obj = msg.get("image", {})
            resultado.imagen_file_id = image_obj.get("id")
            resultado.texto = image_obj.get("caption")

        return resultado

    async def obtener_url_archivo(self, file_id: str) -> str | None:
        """
        Paso 1 de Meta: Obtiene la URL temporal de descarga del archivo a partir de su media_id.
        """
        if not self.token:
            logger.error("No se ha configurado WHATSAPP_API_TOKEN para obtener media de Meta")
            return None

        url_endpoint = f"{self.base_url}/{file_id}"
        headers = {"Authorization": f"Bearer {self.token}"}

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(url_endpoint, headers=headers)
            if resp.status_code != 200:
                logger.error("Error obteniendo media URL de WhatsApp (%s): %s", resp.status_code, resp.text)
                return None
            data = resp.json()
            return data.get("url")

    async def descargar_archivo(self, file_id: str) -> tuple[bytes, str] | None:
        """
        Descarga autenticada en dos pasos requerida por WhatsApp Cloud API:
        1. Consulta el endpoint de media para obtener la URL temporal y el mime_type.
        2. Descarga el archivo enviando el Bearer Token en el header Authorization.
        Retorna (contenido_bytes, mime_type).
        """
        if not self.token:
            logger.error("Falta WHATSAPP_API_TOKEN para descargar archivos de WhatsApp")
            return None

        headers = {"Authorization": f"Bearer {self.token}"}

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Paso 1: Consultar URL temporal y metadata
            meta_resp = await client.get(f"{self.base_url}/{file_id}", headers=headers)
            if meta_resp.status_code != 200:
                logger.error("Error consultando metadata de WhatsApp Media (%s): %s", meta_resp.status_code, meta_resp.text)
                return None

            meta_data = meta_resp.json()
            download_url = meta_data.get("url")
            mime_type = meta_data.get("mime_type", "application/octet-stream")

            if not download_url:
                logger.error("No se encontró URL de descarga en la respuesta de Meta")
                return None

            # Paso 2: Descargar el archivo con el token
            file_resp = await client.get(download_url, headers=headers)
            if file_resp.status_code != 200:
                logger.error("Error descargando binario de WhatsApp (%s): %s", file_resp.status_code, file_resp.text)
                return None

            return file_resp.content, mime_type

    async def enviar_mensaje(self, mensaje: MensajeSaliente) -> bool:
        """
        Envía un mensaje a través de WhatsApp Cloud API.
        Soporta texto plano, botones interactivos (<= 3 opciones) y listas (4-10 opciones).
        Maneja restricciones estrictas de Meta (máx 20 caracteres por botón).
        """
        if not self.token or not self.phone_number_id:
            logger.error("Faltan credenciales de WhatsApp (WHATSAPP_API_TOKEN o WHATSAPP_PHONE_NUMBER_ID)")
            return False

        destino = self.normalizar_telefono(mensaje.id_destino)
        endpoint = f"{self.base_url}/{self.phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

        opciones = mensaje.obtener_opciones_planas()

        # Caso A: Mensaje Interactivo con Botones (1 a 3 opciones)
        if 1 <= len(opciones) <= 3:
            # Meta exige máximo 20 caracteres estrictos por título de botón
            botones = []
            for i, opt in enumerate(opciones):
                titulo_ajustado = opt.strip()
                if len(titulo_ajustado) > 20:
                    titulo_ajustado = titulo_ajustado[:20].strip()
                botones.append({
                    "type": "reply",
                    "reply": {
                        "id": f"btn_{i+1}",
                        "title": titulo_ajustado,
                    }
                })

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destino,
                "type": "interactive",
                "interactive": {
                    "type": "button",
                    "body": {"text": mensaje.texto},
                    "action": {"buttons": botones},
                }
            }

        # Caso B: Mensaje Interactivo con Lista (4 a 10 opciones)
        elif len(opciones) > 3:
            filas = []
            for i, opt in enumerate(opciones[:10]):  # Meta permite hasta 10 opciones en una sección
                titulo_ajustado = opt.strip()
                if len(titulo_ajustado) > 24:
                    titulo_ajustado = titulo_ajustado[:24].strip()
                filas.append({
                    "id": f"row_{i+1}",
                    "title": titulo_ajustado,
                })

            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destino,
                "type": "interactive",
                "interactive": {
                    "type": "list",
                    "header": {"type": "text", "text": "Opciones disponibles"},
                    "body": {"text": mensaje.texto},
                    "action": {
                        "button": "Seleccionar",
                        "sections": [
                            {
                                "title": "Servicios",
                                "rows": filas,
                            }
                        ]
                    }
                }
            }

        # Caso C: Mensaje de Texto estándar
        else:
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": destino,
                "type": "text",
                "text": {"preview_url": False, "body": mensaje.texto},
            }

        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(endpoint, json=payload, headers=headers)

            if resp.status_code in (200, 201):
                logger.info("✅ Mensaje enviado exitosamente a WhatsApp (%s)", destino)
                return True

            # Manejo de errores de Meta
            try:
                error_data = resp.json().get("error", {})
                error_code = error_data.get("code")
                error_subcode = error_data.get("error_subcode")
                error_message = error_data.get("message", resp.text)

                # Error 131047: Fuera de la ventana de 24 horas
                if error_code == 131047 or error_subcode == 2470001 or "24 hours" in error_message.lower():
                    logger.warning(
                        "⚠️ WhatsApp Error 131047: Mensaje fuera de la ventana de 24 horas para %s. Detalle: %s",
                        destino,
                        error_message,
                    )
                    raise FueraDeVentana24HorasError(
                        f"No se puede enviar mensaje a {destino}: Han transcurrido más de 24 horas desde su último mensaje. Meta exige una plantilla aprobada."
                    )

                logger.error(
                    "❌ Error enviando a WhatsApp (%s) - Code: %s, Subcode: %s: %s",
                    resp.status_code,
                    error_code,
                    error_subcode,
                    error_message,
                )
            except (FueraDeVentana24HorasError, WhatsAppError):
                raise
            except Exception as e:
                logger.error("❌ Error enviando a WhatsApp (%s): %s", resp.status_code, resp.text)

            return False
