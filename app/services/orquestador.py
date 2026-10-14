"""
Orquestador Central.
Recibe un mensaje normalizado (UnifiedMessage) del adapter y coordina todo el flujo:

1. Verificar idempotencia por id_mensaje_canal (descarte inmediato si ya fue procesado).
2. Obtener o crear la conversación.
3. Resolver multimedia multicanal (audio → texto vía Whisper/Gemini, imagen → descripción).
4. Guardar el mensaje del cliente en la DB con id_mensaje_canal.
5. Decidir quién responde (IA vs Humano).
6. Triage dinámico inteligente (con autocompletado de teléfono en WhatsApp).
7. Notificar al panel React en tiempo real vía WebSockets.
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from sqlalchemy.exc import IntegrityError
from app.channels.base import ChannelAdapter, UnifiedMessage, MensajeSaliente
from app.models.enums import ModoAtencion, TipoMensaje, TipoContenido, EstadoOnboarding, CanalOrigen
from app.models.mensaje import Mensaje
from app.services.agente_ia_service import AgenteIAService
from app.services.media_service import MediaService
from app.services.conversacion_service import ConversacionService
from app.services.notificacion_service import NotificacionService
from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# ======================================================
# CONFIGURACIÓN DEL TRIAGE (ONBOARDING)
# Botones limitados a <= 20 caracteres para compatibilidad con WhatsApp
# ======================================================
TRIAGE_STEPS = [
    {
        "clave": "intencion",
        "pregunta": "¡Hola {nombre}! Para brindarte una mejor atención, ¿en qué servicio estás interesado?",
        "teclado": [["❄️ Climatización"], ["🔧 Plomería"], ["Otro"]],
        "remover_teclado": False
    },
    {
        "clave": "detalle",
        "pregunta": "¡Perfecto! ¿Qué problema estás teniendo específicamente?",
        "teclado": None,
        "remover_teclado": True
    },
    {
        "clave": "ubicacion",
        "pregunta": "¿En qué zona o localidad te encontrás?",
        "teclado": None,
        "remover_teclado": False
    },
    {
        "clave": "telefono",
        "pregunta": "Por último, ¿nos dejás un número de WhatsApp o teléfono de contacto para que el equipo pueda coordinar la visita?",
        "teclado": None,
        "remover_teclado": False
    }
]


class Orquestador:
    """
    Punto de entrada central para procesar mensajes entrantes.
    Agnóstico al canal — opera exclusivamente sobre UnifiedMessage.
    """

    def __init__(self, db: Session, canal: ChannelAdapter):
        self.db = db
        self.canal = canal
        self.conv_service = ConversacionService(db)
        self.media = MediaService(db)
        self.agente_ia = AgenteIAService(db)
        self.notificacion = NotificacionService()

    async def procesar_mensaje_entrante(self, mensaje: UnifiedMessage):
        """
        Flujo principal de procesamiento de un mensaje entrante con idempotencia.
        """
        # 1. Idempotencia: Verificar si el mensaje ya fue procesado
        if mensaje.id_mensaje_canal:
            msg_existente = (
                self.db.query(Mensaje)
                .filter(Mensaje.id_mensaje_canal == mensaje.id_mensaje_canal)
                .first()
            )
            if msg_existente:
                logger.warning(
                    "⚠️ Idempotencia: Mensaje duplicado descartado (%s de %s)",
                    mensaje.id_mensaje_canal,
                    mensaje.canal,
                )
                return

        # 2. Obtener o crear conversación
        conversacion = self.conv_service.obtener_o_crear(mensaje)
        logger.info(
            "🔄 Conv #%d | Cliente: %s | Canal: %s | Modo: %s",
            conversacion.id,
            mensaje.nombre_remitente,
            mensaje.canal,
            conversacion.modo_atencion.value,
        )

        # 3. Procesar multimedia multicanal si aplica
        texto_para_ia = mensaje.texto
        tipo_contenido = TipoContenido.TEXTO
        archivo_media_id = None

        if mensaje.audio_file_id or mensaje.audio_url:
            tipo_contenido = TipoContenido.AUDIO
            resultado_media = None
            try:
                # Intento de descarga autenticada directa en bytes (WhatsApp / Meta)
                if mensaje.audio_file_id:
                    descarga = await self.canal.descargar_archivo(mensaje.audio_file_id)
                    if descarga:
                        contenido_bytes, _ = descarga
                        resultado_media = await self.media.procesar_audio_bytes(contenido_bytes)

                # Fallback a URL pública (Telegram / Facebook attachments)
                if not resultado_media:
                    audio_url = mensaje.audio_url or await self.canal.obtener_url_archivo(mensaje.audio_file_id)
                    if audio_url:
                        resultado_media = await self.media.procesar_audio(audio_url)

                if resultado_media:
                    texto_para_ia = resultado_media.texto_extraido
                    archivo_media_id = resultado_media.archivo_id
                    logger.info("🎤 Audio transcrito: '%s...'", texto_para_ia[:60])
            except Exception as e:
                logger.error("Error procesando audio: %s", e, exc_info=True)
                texto_para_ia = "[Audio recibido — no se pudo procesar]"

        elif mensaje.imagen_file_id or mensaje.imagen_url:
            tipo_contenido = TipoContenido.IMAGEN
            resultado_media = None
            try:
                # Intento de descarga autenticada directa en bytes
                if mensaje.imagen_file_id:
                    descarga = await self.canal.descargar_archivo(mensaje.imagen_file_id)
                    if descarga:
                        contenido_bytes, _ = descarga
                        resultado_media = await self.media.procesar_imagen_bytes(
                            contenido_bytes, prompt_adicional=mensaje.texto
                        )

                # Fallback a URL pública
                if not resultado_media:
                    imagen_url = mensaje.imagen_url or await self.canal.obtener_url_archivo(mensaje.imagen_file_id)
                    if imagen_url:
                        resultado_media = await self.media.procesar_imagen(
                            imagen_url, prompt_adicional=mensaje.texto
                        )

                if resultado_media:
                    texto_para_ia = resultado_media.texto_extraido
                    archivo_media_id = resultado_media.archivo_id
                    logger.info("📷 Imagen analizada: '%s...'", texto_para_ia[:60])
            except Exception as e:
                logger.error("Error procesando imagen: %s", e, exc_info=True)
                texto_para_ia = "[Imagen recibida — no se pudo procesar]"

        # Placeholder si no hay texto ni multimedia procesado
        if not texto_para_ia:
            texto_para_ia = "[Mensaje sin contenido procesable]"

        # 4. Guardar mensaje del cliente en la DB
        msg_cliente = Mensaje(
            conversacion_id=conversacion.id,
            tipo_mensaje=TipoMensaje.CLIENTE,
            tipo_contenido=tipo_contenido,
            contenido=texto_para_ia,
            archivo_media_id=archivo_media_id,
            id_mensaje_canal=mensaje.id_mensaje_canal,
        )
        self.db.add(msg_cliente)
        try:
            self.db.commit()
            self.db.refresh(msg_cliente)
        except IntegrityError:
            self.db.rollback()
            logger.warning(
                "⚠️ Carrera de idempotencia detectada para id_mensaje_canal=%s. Abortando duplicado.",
                mensaje.id_mensaje_canal,
            )
            return

        # 5. Notificar al panel React en tiempo real
        await self.notificacion.nuevo_mensaje(conversacion.id, msg_cliente)

        # 6. Decisión de atención: IA vs Humano vs Pausado
        if conversacion.modo_atencion == ModoAtencion.IA:
            if conversacion.estado_onboarding != EstadoOnboarding.FINALIZADO:
                logger.info("📋 Conv #%d → Procesando Triage (Estado: %s)", conversacion.id, conversacion.estado_onboarding)
                await self._procesar_onboarding(conversacion, mensaje, texto_para_ia)
            else:
                logger.info("🤖 Conv #%d → Respondiendo con IA", conversacion.id)
                await self._responder_con_ia(conversacion, mensaje, texto_para_ia)

        elif conversacion.modo_atencion == ModoAtencion.HUMANO:
            logger.info("👤 Conv #%d → Modo HUMANO, esperando respuesta del gerente", conversacion.id)

        elif conversacion.modo_atencion == ModoAtencion.PAUSADO:
            logger.info("⏸️ Conv #%d → Conversación pausada, sin respuesta", conversacion.id)

    async def _procesar_onboarding(self, conversacion, mensaje: UnifiedMessage, texto_para_ia: str):
        """Maneja el flujo determinístico de triage con UX inteligente para WhatsApp."""
        cliente = conversacion.cliente
        paso_actual = conversacion.paso_onboarding

        # Guardar respuesta previa en los metadatos del cliente
        if 0 < paso_actual <= len(TRIAGE_STEPS):
            paso_previo = TRIAGE_STEPS[paso_actual - 1]
            clave_previa = paso_previo["clave"]

            if not cliente.metadatos:
                cliente.metadatos = {}

            cliente.metadatos = {**cliente.metadatos, clave_previa: texto_para_ia}
            flag_modified(cliente, "metadatos")

            if clave_previa == "telefono":
                cliente.telefono = texto_para_ia
            elif clave_previa == "ubicacion":
                cliente.zona = texto_para_ia
            elif clave_previa == "intencion":
                cliente.servicio_interes = texto_para_ia

        # Verificar si terminamos el triage
        if paso_actual >= len(TRIAGE_STEPS):
            conversacion.estado_onboarding = EstadoOnboarding.FINALIZADO
            logger.info("✅ Conv #%d → Onboarding finalizado. Activando IA.", conversacion.id)
            await self._responder_con_ia(conversacion, mensaje, texto_para_ia, remover_teclado=True)
            return

        # Paso siguiente
        paso_siguiente = TRIAGE_STEPS[paso_actual]

        # === UX Inteligente: Si el usuario escribe desde WhatsApp y el paso es 'telefono', autocompletar ===
        if paso_siguiente["clave"] == "telefono" and mensaje.canal in ("whatsapp", CanalOrigen.WHATSAPP.value):
            if not cliente.metadatos:
                cliente.metadatos = {}
            cliente.telefono = mensaje.id_externo
            cliente.metadatos = {**cliente.metadatos, "telefono": mensaje.id_externo}
            flag_modified(cliente, "metadatos")
            conversacion.estado_onboarding = EstadoOnboarding.FINALIZADO
            self.db.commit()

            logger.info(
                "💡 Conv #%d (WhatsApp) → Teléfono autocompletado (%s). Omitiendo pregunta y finalizando triage.",
                conversacion.id,
                mensaje.id_externo,
            )
            await self._responder_con_ia(conversacion, mensaje, texto_para_ia, remover_teclado=True)
            return

        respuesta_texto = paso_siguiente["pregunta"].format(nombre=mensaje.nombre_remitente or "visitante")
        teclado = paso_siguiente.get("teclado")
        remover_teclado = paso_siguiente.get("remover_teclado", False)

        conversacion.paso_onboarding += 1
        self.db.commit()

        # Guardar mensaje del sistema en la DB
        msg_sistema = Mensaje(
            conversacion_id=conversacion.id,
            tipo_mensaje=TipoMensaje.SISTEMA,
            tipo_contenido=TipoContenido.TEXTO,
            contenido=respuesta_texto,
        )
        self.db.add(msg_sistema)
        self.db.commit()
        self.db.refresh(msg_sistema)

        # Enviar respuesta mediante el adaptador del canal
        enviado = await self.canal.enviar_mensaje(
            MensajeSaliente(
                id_destino=mensaje.id_externo,
                texto=respuesta_texto,
                teclado=teclado,
                remover_teclado=remover_teclado,
            )
        )
        if not enviado:
            logger.error("❌ Error enviando respuesta de triage por %s a %s", mensaje.canal, mensaje.id_externo)

        await self.notificacion.nuevo_mensaje(conversacion.id, msg_sistema)

    async def _responder_con_ia(
        self, conversacion, mensaje: UnifiedMessage, texto_para_ia: str, remover_teclado: bool = False
    ):
        """Genera respuesta con el agente IA y la despacha al cliente."""
        tiene_llm = (
            (settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY)
            or (settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY)
        )

        if not tiene_llm:
            logger.warning("⚠️ No hay API key de %s configurada — usando fallback", settings.LLM_PROVIDER)
            respuesta_texto = (
                "¡Hola! Gracias por comunicarte con Ciclo Confort. "
                "En este momento nuestro asistente no está disponible. "
                "Un representante se pondrá en contacto a la brevedad."
            )
        else:
            respuesta_texto = await self.agente_ia.generar_respuesta(
                conversacion=conversacion,
                mensaje_actual=texto_para_ia,
            )

        # Guardar en DB
        msg_ia = Mensaje(
            conversacion_id=conversacion.id,
            tipo_mensaje=TipoMensaje.IA,
            tipo_contenido=TipoContenido.TEXTO,
            contenido=respuesta_texto,
        )
        self.db.add(msg_ia)
        self.db.commit()
        self.db.refresh(msg_ia)

        logger.info("✅ Conv #%d → IA respondió: '%s...'", conversacion.id, respuesta_texto[:60])

        # Enviar mensaje al canal
        enviado = await self.canal.enviar_mensaje(
            MensajeSaliente(
                id_destino=mensaje.id_externo,
                texto=respuesta_texto,
                remover_teclado=remover_teclado,
            )
        )
        if not enviado:
            logger.error("❌ Error enviando respuesta por %s a %s", mensaje.canal, mensaje.id_externo)

        await self.notificacion.nuevo_mensaje(conversacion.id, msg_ia)
