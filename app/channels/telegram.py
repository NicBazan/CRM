import httpx
from app.channels.base import ChannelAdapter, MensajeEntrante, MensajeSaliente
from app.core.config import get_settings


class TelegramAdapter(ChannelAdapter):
    """
    Adaptador para Telegram Bot API.
    Parsea mensajes de texto, audio/voz e imágenes.
    """

    def __init__(self):
        self.settings = get_settings()
        self.base_url = (
            f"https://api.telegram.org/bot{self.settings.TELEGRAM_BOT_TOKEN}"
        )

    def parsear_entrada(self, payload: dict) -> MensajeEntrante | None:
        """Convierte un update de Telegram en un MensajeEntrante normalizado."""
        msg = payload.get("message")
        if not msg:
            return None

        chat_id = str(msg["chat"]["id"])
        nombre = msg.get("from", {}).get("first_name", "Cliente")
        resultado = MensajeEntrante(
            canal="telegram",
            id_externo=chat_id,
            nombre_remitente=nombre,
            payload_crudo=payload,
        )

        # --- Texto ---
        if "text" in msg:
            resultado.texto = msg["text"]

        # --- Audio/Voz ---
        elif "voice" in msg:
            resultado.audio_file_id = msg["voice"]["file_id"]
        elif "audio" in msg:
            resultado.audio_file_id = msg["audio"]["file_id"]

        # --- Imagen ---
        elif "photo" in msg:
            # Telegram envía varias resoluciones; tomamos la más grande
            mejor_foto = msg["photo"][-1]
            resultado.imagen_file_id = mejor_foto["file_id"]

        # --- Caption (texto adjunto a una foto/audio) ---
        if "caption" in msg:
            resultado.texto = msg.get("caption")

        return resultado

    async def obtener_url_archivo(self, file_id: str) -> str:
        """Convierte un file_id de Telegram en una URL de descarga directa."""
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self.base_url}/getFile",
                params={"file_id": file_id},
            )
            data = resp.json()
            file_path = data["result"]["file_path"]
            return (
                f"https://api.telegram.org/file/"
                f"bot{self.settings.TELEGRAM_BOT_TOKEN}/{file_path}"
            )

    async def enviar_mensaje(self, mensaje: MensajeSaliente) -> bool:
        """Envía un mensaje de texto a un chat de Telegram."""
        payload = {
            "chat_id": mensaje.id_destino,
            "text": mensaje.texto,
        }

        if mensaje.teclado:
            # Convierte la lista de listas de strings al formato de Telegram
            keyboard = [[{"text": btn} for btn in fila] for fila in mensaje.teclado]
            payload["reply_markup"] = {
                "keyboard": keyboard,
                "resize_keyboard": True,
                "one_time_keyboard": True,
            }
        elif mensaje.remover_teclado:
            payload["reply_markup"] = {
                "remove_keyboard": True
            }

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self.base_url}/sendMessage",
                json=payload,
            )
            return resp.status_code == 200
