"""
Servicio del agente IA.
Responsabilidades:
  - Construir el prompt con system prompt + RAG + historial
  - Llamar a la API del LLM (Gemini o OpenAI)
  - Devolver la respuesta como texto plano
"""
import logging
import httpx
import json
import asyncio
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models.conversacion import Conversacion
from app.models.mensaje import Mensaje
from app.models.enums import TipoMensaje
from app.services.conocimiento_service import ConocimientoService
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)
settings = get_settings()

# ======================================================
# SYSTEM PROMPT — La "personalidad" y las reglas de la IA
# ======================================================
SYSTEM_PROMPT = """\
Eres el asistente virtual de Ciclo Confort, una empresa de servicios \
de mantenimiento de aires acondicionados y plomería.

REGLAS INQUEBRANTABLES:
1. Respondé SIEMPRE en español argentino, con tono amable y profesional.
2. Usá "vos" en lugar de "tú".
3. NUNCA inventes información que no esté en el CONOCIMIENTO DEL NEGOCIO de abajo. \
Si no sabés algo, decí: "No tengo esa información ahora, pero voy a consultar con \
el equipo y te respondo a la brevedad."
4. NUNCA menciones que sos una IA, un bot o un asistente virtual. \
Comportate como un empleado real de Ciclo Confort.
5. Si el cliente manda un audio, vas a recibir la transcripción. Respondé normalmente.
6. Si el cliente manda una foto, vas a recibir una descripción de la imagen. \
Preguntá si necesita presupuesto o asistencia con lo que se ve en la imagen.
7. Podés agendar visitas técnicas, dar presupuestos orientativos basados en el \
conocimiento del negocio, y responder preguntas frecuentes.
8. Si el cliente está enojado o el caso es complejo, respondé con empatía y decí: \
"Voy a derivar tu consulta a un supervisor para que te atienda personalmente."
9. Mantené las respuestas concisas (máximo 3-4 oraciones) a menos que te pidan \
más detalle.
10. Usá emojis con moderación para dar calidez (máximo 1-2 por mensaje).
11. Si el cliente pregunta por disponibilidad, visitas a domicilio, turnos o plazos de atención y no hay información específica en el contexto: Respondé de forma cordial indicando que las visitas técnicas se coordinan habitualmente dentro de las 24 a 48 hs hábiles. Luego, solicitá al cliente su disponibilidad de preferencia (mañana o tarde) y un número de teléfono de contacto para que el equipo confirme la franja horaria exacta.
12. EXCEPCIÓN A LA REGLA 3 (Toma de turnos): Si el cliente pide o confirma una fecha/turno específico (ej: "mañana a la mañana", "el viernes"), NO digas "no tengo esa información". En su lugar, confirmá que su preferencia de horario quedó registrada en su ficha y aclarale que el área técnica se pondrá en contacto a primera hora (al teléfono brindado) para ratificar el horario exacto de llegada del especialista.

CONOCIMIENTO DEL NEGOCIO:
{contexto_rag}

FICHA DEL CLIENTE:
{ficha_cliente}
"""

RESPUESTA_ERROR_TECNICO = (
    "¡Muchas gracias por contactarnos! Ya registramos tu consulta y tus datos. Un asesor técnico de Ciclo Confort se va a comunicar con vos a la brevedad para coordinar la visita y pasarte el presupuesto. 😊"
)


class AgenteIAService:
    """
    Servicio central del agente de IA.
    Orquesta: system prompt + knowledge base (RAG) + historial conversacional + LLM.
    """

    def __init__(self, db: Session):
        self.db = db
        self.conocimiento = ConocimientoService(db)

    async def generar_respuesta(
        self,
        conversacion: Conversacion,
        mensaje_actual: str,
    ) -> str:
        """
        Genera una respuesta del agente IA para el mensaje actual.

        Args:
            conversacion: La conversación activa (para cargar historial).
            mensaje_actual: El texto del mensaje del cliente (o transcripción/descripción).

        Returns:
            El texto de la respuesta generada por la IA.
        """
        # 1. Cargar el conocimiento del negocio (RAG)
        contexto_rag = self.conocimiento.obtener_contexto_relevante(mensaje_actual)
        logger.info(
            "RAG: %d caracteres de contexto cargados para conv #%d",
            len(contexto_rag),
            conversacion.id,
        )

        # 2. Construir el system prompt con el conocimiento inyectado y datos del cliente
        cliente = conversacion.cliente
        ficha = json.dumps(cliente.metadatos, indent=2, ensure_ascii=False) if cliente.metadatos else "{}"
        
        system = SYSTEM_PROMPT.format(
            contexto_rag=contexto_rag,
            ficha_cliente=ficha
        )

        # 3. Obtener los últimos N mensajes como contexto conversacional
        historial = self._construir_historial(conversacion, limite=20)
        logger.info(
            "Historial: %d mensajes previos para conv #%d",
            len(historial),
            conversacion.id,
        )

        # 4. (Omitido) El mensaje actual ya está en el historial porque se guardó en la DB antes de llamar a este método.

        # 5. Llamar al LLM
        try:
            respuesta = await self._llamar_llm(
                system_prompt=system, mensajes=historial
            )
            logger.info(
                "LLM respondió con %d caracteres para conv #%d",
                len(respuesta),
                conversacion.id,
            )
            return respuesta
        except Exception as e:
            logger.error("Error llamando al LLM para conv #%d: %s", conversacion.id, e, exc_info=True)
            return RESPUESTA_ERROR_TECNICO

    def _construir_historial(
        self, conversacion: Conversacion, limite: int = 20
    ) -> list[dict]:
        """
        Carga los últimos N mensajes y los convierte al formato
        que espera la API del LLM (role: user/assistant).
        """
        mensajes_db = (
            self.db.query(Mensaje)
            .filter(Mensaje.conversacion_id == conversacion.id)
            .order_by(Mensaje.fecha_creacion.desc())
            .limit(limite)
            .all()
        )
        # Invertir para orden cronológico
        mensajes_db.reverse()

        historial = []
        for msg in mensajes_db:
            if msg.tipo_mensaje == TipoMensaje.CLIENTE:
                historial.append({"role": "user", "content": msg.contenido})
            elif msg.tipo_mensaje in (TipoMensaje.IA, TipoMensaje.HUMANO):
                historial.append({"role": "assistant", "content": msg.contenido})
            # TipoMensaje.SISTEMA se omite del historial del LLM
        return historial

    async def _llamar_llm(
        self, system_prompt: str, mensajes: list[dict]
    ) -> str:
        """
        Llama a la API del LLM configurado (Gemini o OpenAI).
        Este método es el ÚNICO punto de contacto con el proveedor.
        """

        if settings.LLM_PROVIDER == "gemini":
            return await self._llamar_gemini(system_prompt, mensajes)
        elif settings.LLM_PROVIDER == "openai":
            return await self._llamar_openai(system_prompt, mensajes)
        else:
            raise ValueError(f"LLM_PROVIDER no soportado: {settings.LLM_PROVIDER}")

    async def _llamar_gemini(
        self, system_prompt: str, mensajes: list[dict]
    ) -> str:
        """Llamada a Google Gemini API usando el SDK oficial (google-genai)."""
        
        modelo_actual = settings.GEMINI_MODEL
        if not modelo_actual:
            modelo_actual = "gemini-3.5-flash-lite"

        # Gemini requiere que el historial empiece con "user"
        # y alterne user/model. Limpiar mensajes consecutivos del mismo rol.
        mensajes_limpios = self._limpiar_historial_gemini(mensajes)

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        
        contents = []
        for m in mensajes_limpios:
            contents.append(
                types.Content(
                    role="user" if m["role"] == "user" else "model",
                    parts=[types.Part.from_text(text=m["content"])]
                )
            )

        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=0.7,
            max_output_tokens=1000,
        )

        for intento in range(2):
            try:
                # La llamada generate_content_async permite asincronía en el nuevo SDK
                response = await client.aio.models.generate_content(
                    model=modelo_actual,
                    contents=contents,
                    config=config,
                )
                return response.text if response.text else RESPUESTA_ERROR_TECNICO
            except Exception as e:
                error_str = str(e)
                es_error_reintentable = any(
                    x in error_str for x in ["429", "503", "UNAVAILABLE", "high demand"]
                )
                if es_error_reintentable and intento == 0:
                    logger.warning("Recibido %s de Gemini. Esperando 3 segundos para reintentar...", "429/503")
                    await asyncio.sleep(3)
                    continue
                logger.error("Error en SDK de Gemini: %s", e, exc_info=True)
                return RESPUESTA_ERROR_TECNICO

    def _limpiar_historial_gemini(self, mensajes: list[dict]) -> list[dict]:
        """
        Gemini requiere que el historial alterne entre user y model,
        y que empiece con user. Este método fusiona mensajes consecutivos
        del mismo rol si ocurren.
        """
        if not mensajes:
            return mensajes

        resultado = [mensajes[0]]
        for msg in mensajes[1:]:
            if msg["role"] == resultado[-1]["role"]:
                # Fusionar con el anterior
                resultado[-1] = {
                    "role": msg["role"],
                    "content": resultado[-1]["content"] + "\n" + msg["content"],
                }
            else:
                resultado.append(msg)

        # Asegurar que empiece con "user"
        if resultado and resultado[0]["role"] != "user":
            resultado = resultado[1:]

        return resultado

    async def _llamar_openai(
        self, system_prompt: str, mensajes: list[dict]
    ) -> str:
        """Llamada a OpenAI Chat Completions API."""
        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {settings.OPENAI_API_KEY}"}
        payload = {
            "model": settings.OPENAI_MODEL,
            "messages": [
                {"role": "system", "content": system_prompt},
                *mensajes,
            ],
            "temperature": 0.7,
            "max_tokens": 500,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()

            choices = data.get("choices", [])
            if not choices:
                logger.warning("OpenAI devolvió respuesta sin choices")
                return RESPUESTA_ERROR_TECNICO

            return choices[0].get("message", {}).get("content", RESPUESTA_ERROR_TECNICO)
