"""
Servicio de procesamiento multimedia.
Descarga archivos de audio/imagen y los procesa:
  - Audio → Whisper API (transcripción a texto)
  - Imagen → Gemini Vision / GPT-4 Vision (descripción textual)
"""
import base64
import logging
import os
import uuid
import httpx
from dataclasses import dataclass
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.archivo_media import ArchivoMedia
from app.models.enums import TipoContenido

settings = get_settings()
logger = logging.getLogger(__name__)

# Directorio para almacenar archivos descargados
MEDIA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "media")


@dataclass
class ResultadoMedia:
    """Resultado del procesamiento de un archivo multimedia."""
    archivo_id: int
    texto_extraido: str


class MediaService:
    """Procesamiento de archivos multimedia (audio e imágenes)."""

    def __init__(self, db: Session):
        self.db = db

    async def procesar_audio(self, audio_url: str) -> ResultadoMedia:
        """Descarga el audio y lo transcribe con Whisper."""
        ruta_local = await self._descargar_archivo(audio_url, extension=".ogg")
        transcripcion = await self._transcribir_audio(ruta_local)

        archivo = ArchivoMedia(
            tipo=TipoContenido.AUDIO,
            ruta_almacenamiento=ruta_local,
            texto_extraido=transcripcion,
        )
        self.db.add(archivo)
        self.db.commit()
        self.db.refresh(archivo)

        return ResultadoMedia(archivo_id=archivo.id, texto_extraido=transcripcion)

    async def procesar_imagen(self, imagen_url: str, prompt_adicional: str = None) -> ResultadoMedia:
        """Descarga la imagen y genera una descripción con Vision API."""
        ruta_local = await self._descargar_archivo(imagen_url, extension=".jpg")
        descripcion = await self._analizar_imagen(ruta_local, prompt_adicional)

        archivo = ArchivoMedia(
            tipo=TipoContenido.IMAGEN,
            ruta_almacenamiento=ruta_local,
            texto_extraido=descripcion,
        )
        self.db.add(archivo)
        self.db.commit()
        self.db.refresh(archivo)

        return ResultadoMedia(archivo_id=archivo.id, texto_extraido=descripcion)

    async def _descargar_archivo(self, url: str, extension: str) -> str:
        """Descarga un archivo a disco local."""
        os.makedirs(MEDIA_DIR, exist_ok=True)
        nombre = f"{uuid.uuid4().hex}{extension}"
        ruta = os.path.join(MEDIA_DIR, nombre)

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            with open(ruta, "wb") as f:
                f.write(resp.content)

        return ruta

    async def _transcribir_audio(self, ruta: str) -> str:
        """Envía el audio a la API de Gemini para transcripción."""
        if settings.GEMINI_API_KEY:
            return await self._audio_gemini(ruta)
        elif settings.OPENAI_API_KEY:
            return await self._transcribir_audio_openai(ruta)
        else:
            return "[Audio recibido — transcripción no disponible: faltan API keys]"

    async def _transcribir_audio_openai(self, ruta: str) -> str:
        """Transcribe audio usando OpenAI Whisper."""
        url = "https://api.openai.com/v1/audio/transcriptions"
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}

        with open(ruta, "rb") as audio_file:
            async with httpx.AsyncClient(timeout=60) as client:
                resp = await client.post(
                    url,
                    headers=headers,
                    data={"model": "whisper-1", "language": "es"},
                    files={"file": ("audio.ogg", audio_file, "audio/ogg")},
                )
                if resp.status_code == 200:
                    return resp.json().get("text", "[audio no procesable]")
                else:
                    print(f"Error Whisper: {resp.status_code} - {resp.text}")
                    return "[Error al transcribir audio con OpenAI]"

    async def _audio_gemini(self, ruta: str) -> str:
        """Transcribe audio usando Gemini Multimodal con SDK google-genai."""
        from google import genai
        from google.genai import types

        with open(ruta, "rb") as f:
            audio_bytes = f.read()

        model_name = settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        try:
            response = await client.aio.models.generate_content(
                model=model_name,
                contents=[
                    types.Part.from_bytes(
                        data=audio_bytes,
                        mime_type="audio/ogg",
                    ),
                    "Transcribe exactamente lo que dice este audio en español, sin comentarios adicionales",
                ]
            )
            if response.text:
                return response.text.strip()
            return "[audio no procesable]"
        except Exception as e:
            logger.error("Error transcribiendo audio con Gemini SDK: %s", e, exc_info=True)
            return "[Error al transcribir audio con Gemini]"

    async def _analizar_imagen(self, ruta: str, prompt_adicional: str = None) -> str:
        """Envía la imagen a un modelo con visión para obtener una descripción."""
        with open(ruta, "rb") as img:
            img_b64 = base64.b64encode(img.read()).decode()

        if settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY:
            return await self._vision_gemini(img_b64, prompt_adicional)
        elif settings.OPENAI_API_KEY:
            return await self._vision_openai(img_b64, prompt_adicional)
        else:
            return "[Imagen recibida — análisis no disponible: falta API key]"

    async def _vision_gemini(self, img_b64: str, prompt_adicional: str = None) -> str:
        """Análisis de imagen con Gemini Vision."""
        model = settings.GEMINI_MODEL or "gemini-3.5-flash-lite"
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent"
            f"?key={settings.GEMINI_API_KEY}"
        )
        texto_prompt = (
            "Describí brevemente qué se ve en esta imagen. "
            "Si parece un equipo de aire acondicionado, cañería "
            "o algo relacionado a servicios del hogar, mencioná "
            "el estado aparente y posibles problemas."
        )
        if prompt_adicional:
            texto_prompt += f"\n\nAdemás, el usuario envió este comentario con la foto: '{prompt_adicional}'\nPor favor, responde a su comentario basándote en la foto."

        payload = {
            "contents": [{
                "parts": [
                    {
                        "inlineData": {
                            "mimeType": "image/jpeg",
                            "data": img_b64,
                        },
                    },
                    {
                        "text": texto_prompt,
                    },
                ],
            }],
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                data = resp.json()
                try:
                    return data["candidates"][0]["content"]["parts"][0]["text"].strip()
                except (KeyError, IndexError):
                    logger.error("Error parseando respuesta Gemini Vision: %s", data)
                    return "[Error: formato de respuesta de Gemini inválido]"
            else:
                logger.error("Error Gemini Vision. Status: %s, Body: %s", resp.status_code, resp.text)
                return "[Error al analizar imagen]"

    async def _vision_openai(self, img_b64: str) -> str:
        """Análisis de imagen con GPT-4 Vision."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        payload = {
            "model": "gpt-4o-mini",
            "messages": [{
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": (
                            "Describí brevemente qué se ve en esta imagen. "
                            "Si parece un equipo de aire acondicionado, cañería "
                            "o algo relacionado a servicios del hogar, mencioná "
                            "el estado aparente y posibles problemas."
                        ),
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{img_b64}",
                        },
                    },
                ],
            }],
            "max_tokens": 300,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                return data["choices"][0]["message"]["content"]
            else:
                print(f"Error OpenAI Vision: {resp.status_code}")
                return "[Error al analizar imagen]"
