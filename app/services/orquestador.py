"""
Orquestador Central.
Recibe un mensaje normalizado del adapter y coordina todo el flujo:

1. Obtener o crear la conversación.
2. Resolver multimedia (audio → texto, imagen → descripción).
3. Guardar el mensaje del cliente en la DB.
4. Decidir quién responde (IA vs Humano).
5. Si IA: generar respuesta, guardarla y enviarla.
6. Notificar al panel React en tiempo real.
"""
import logging
from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified
from app.channels.base import ChannelAdapter, MensajeEntrante, MensajeSaliente
from app.models.enums import ModoAtencion, TipoMensaje, TipoContenido, EstadoOnboarding
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
# ======================================================
TRIAGE_STEPS = [
    {
        "clave": "intencion",
        "pregunta": "¡Hola {nombre}! Para brindarte una mejor atención, ¿en qué servicio estás interesado?",
        "teclado": [["❄️ Aire Acondicionado"], ["🔧 Plomería"], ["Otro"]],
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
    Agnóstico al canal — recibe MensajeEntrante normalizados.
    """

    def __init__(self, db: Session, canal: ChannelAdapter):
        self.db = db
        self.canal = canal
        self.conv_service = ConversacionService(db)
        self.media = MediaService(db)
        self.agente_ia = AgenteIAService(db)
        self.notificacion = NotificacionService()

    async def procesar_mensaje_entrante(self, mensaje: MensajeEntrante):
        """
        Flujo principal de procesamiento de un mensaje entrante.
        """
        # 1. Obtener o crear conversación
        conversacion = self.conv_service.obtener_o_crear(mensaje)
        logger.info(
            "🔄 Conv #%d | Cliente: %s | Canal: %s | Modo: %s",
            conversacion.id,
            mensaje.nombre_remitente,
            mensaje.canal,
            conversacion.modo_atencion.value,
        )

        # 2. Procesar multimedia si aplica
        texto_para_ia = mensaje.texto
        tipo_contenido = TipoContenido.TEXTO
        archivo_media_id = None

        if mensaje.audio_file_id:
            tipo_contenido = TipoContenido.AUDIO
            try:
                audio_url = await self.canal.obtener_url_archivo(
                    mensaje.audio_file_id
                )
                if audio_url:
                    resultado = await self.media.procesar_audio(audio_url)
                    texto_para_ia = resultado.texto_extraido
                    archivo_media_id = resultado.archivo_id
                    logger.info("🎤 Audio transcrito: '%s...'", texto_para_ia[:60])
            except Exception as e:
                logger.error("Error procesando audio: %s", e, exc_info=True)
                texto_para_ia = "[Audio recibido — no se pudo procesar]"

        elif mensaje.imagen_file_id:
            tipo_contenido = TipoContenido.IMAGEN
            try:
                imagen_url = await self.canal.obtener_url_archivo(
                    mensaje.imagen_file_id
                )
                if imagen_url:
                    resultado = await self.media.procesar_imagen(imagen_url, prompt_adicional=mensaje.texto)
                    texto_para_ia = resultado.texto_extraido
                    archivo_media_id = resultado.archivo_id
                    logger.info("📷 Imagen analizada: '%s...'", texto_para_ia[:60])
            except Exception as e:
                logger.error("Error procesando imagen: %s", e, exc_info=True)
                texto_para_ia = "[Imagen recibida — no se pudo procesar]"

        # Si no hay texto ni multimedia procesado, usar placeholder
        if not texto_para_ia:
            texto_para_ia = "[Mensaje sin contenido procesable]"

        # 3. Guardar mensaje del cliente en la DB
        msg_cliente = Mensaje(
            conversacion_id=conversacion.id,
            tipo_mensaje=TipoMensaje.CLIENTE,
            tipo_contenido=tipo_contenido,
            contenido=texto_para_ia,
            archivo_media_id=archivo_media_id,
        )
        self.db.add(msg_cliente)
        self.db.commit()
        self.db.refresh(msg_cliente)

        # 4. Notificar al panel React (siempre, sin importar quién atiende)
        await self.notificacion.nuevo_mensaje(conversacion.id, msg_cliente)

        # ================================================
        # 5. DECISIÓN CLAVE: ¿Quién responde?
        # ================================================
        if conversacion.modo_atencion == ModoAtencion.IA:
            if conversacion.estado_onboarding != EstadoOnboarding.FINALIZADO:
                logger.info("📋 Conv #%d → Procesando Triage (Estado: %s)", conversacion.id, conversacion.estado_onboarding)
                await self._procesar_onboarding(conversacion, mensaje, texto_para_ia)
            else:
                logger.info("🤖 Conv #%d → Respondiendo con IA", conversacion.id)
                await self._responder_con_ia(conversacion, mensaje, texto_para_ia)

        elif conversacion.modo_atencion == ModoAtencion.HUMANO:
            # NO hacer nada automático.
            # El mensaje ya se guardó y se notificó al panel.
            # El humano responderá desde la interfaz.
            logger.info(
                "👤 Conv #%d → Modo HUMANO, esperando respuesta del gerente",
                conversacion.id,
            )

        elif conversacion.modo_atencion == ModoAtencion.PAUSADO:
            logger.info("⏸️ Conv #%d → Conversación pausada, sin respuesta", conversacion.id)

    async def _procesar_onboarding(self, conversacion, mensaje: MensajeEntrante, texto_para_ia: str):
        """Maneja el flujo determinístico de triage dinámico."""
        cliente = conversacion.cliente
        paso_actual = conversacion.paso_onboarding

        # Si ya estábamos en un paso, guardar la respuesta del usuario en los metadatos
        if paso_actual > 0 and paso_actual <= len(TRIAGE_STEPS):
            paso_previo = TRIAGE_STEPS[paso_actual - 1]
            clave_previa = paso_previo["clave"]
            
            # Inicializar dict si es None
            if not cliente.metadatos:
                cliente.metadatos = {}
            
            cliente.metadatos = {**cliente.metadatos, clave_previa: texto_para_ia}
            flag_modified(cliente, "metadatos")
            
            # Compatibilidad con columnas nativas
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
            
            # Disparamos la respuesta IA con la FICHA DEL CLIENTE
            await self._responder_con_ia(conversacion, mensaje, texto_para_ia, remover_teclado=True)
            return

        # Obtener el paso a preguntar ahora
        paso_siguiente = TRIAGE_STEPS[paso_actual]
        respuesta_texto = paso_siguiente["pregunta"].format(nombre=mensaje.nombre_remitente or "visitante")
        teclado = paso_siguiente.get("teclado")
        remover_teclado = paso_siguiente.get("remover_teclado", False)

        # Avanzar el puntero para la próxima vez
        conversacion.paso_onboarding += 1

        self.db.commit()

        # Guardar respuesta del sistema en la DB (para historial)
        msg_sistema = Mensaje(
            conversacion_id=conversacion.id,
            tipo_mensaje=TipoMensaje.SISTEMA,
            tipo_contenido=TipoContenido.TEXTO,
            contenido=respuesta_texto,
        )
        self.db.add(msg_sistema)
        self.db.commit()
        self.db.refresh(msg_sistema)

        # Enviar por el canal
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

        # Notificar al panel
        await self.notificacion.nuevo_mensaje(conversacion.id, msg_sistema)

    async def _responder_con_ia(
        self, conversacion, mensaje: MensajeEntrante, texto_para_ia: str, remover_teclado: bool = False
    ):
        """Genera una respuesta con el agente IA y la envía al cliente."""
        # Verificar que hay una API key configurada
        tiene_llm = (
            (settings.LLM_PROVIDER == "gemini" and settings.GEMINI_API_KEY)
            or (settings.LLM_PROVIDER == "openai" and settings.OPENAI_API_KEY)
        )

        if not tiene_llm:
            # Fallback: respuesta genérica si no hay LLM configurado
            logger.warning(
                "⚠️ No hay API key de %s configurada — usando fallback",
                settings.LLM_PROVIDER,
            )
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

        # Guardar respuesta de la IA en la DB
        msg_ia = Mensaje(
            conversacion_id=conversacion.id,
            tipo_mensaje=TipoMensaje.IA,
            tipo_contenido=TipoContenido.TEXTO,
            contenido=respuesta_texto,
        )
        self.db.add(msg_ia)
        self.db.commit()
        self.db.refresh(msg_ia)

        logger.info(
            "✅ Conv #%d → IA respondió: '%s...'",
            conversacion.id,
            respuesta_texto[:60],
        )

        # Enviar por el canal correspondiente
        enviado = await self.canal.enviar_mensaje(
            MensajeSaliente(
                id_destino=mensaje.id_externo,
                texto=respuesta_texto,
                remover_teclado=remover_teclado,
            )
        )

        if not enviado:
            logger.error("❌ Error enviando respuesta por %s a %s", mensaje.canal, mensaje.id_externo)

        # Notificar al panel
        await self.notificacion.nuevo_mensaje(conversacion.id, msg_ia)
