"""
Webhooks de canales de mensajería.
Cada canal tiene su propio endpoint que recibe payloads crudos,
los normaliza con un Adapter y los pasa al Orquestador.
"""
import logging
from fastapi import APIRouter, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from app.api.deps import get_db
from app.channels.telegram import TelegramAdapter
from app.services.orquestador import Orquestador

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


@router.post("/telegram")
async def webhook_telegram(request: Request, db: Session = Depends(get_db)):
    """
    Webhook de Telegram.
    Recibe updates, los normaliza con TelegramAdapter y los pasa al Orquestador.
    """
    payload = await request.json()

    # Log mínimo para debug (no loguear el payload completo en producción)
    update_id = payload.get("update_id", "?")
    logger.info("📩 Telegram update #%s recibido", update_id)

    adaptador = TelegramAdapter()
    mensaje = adaptador.parsear_entrada(payload)

    if not mensaje:
        logger.info("Update #%s ignorado (sin mensaje procesable)", update_id)
        return {"status": "ok", "detail": "update ignorado"}

    logger.info(
        "📝 Mensaje de '%s' (chat:%s): tipo=%s, texto=%s",
        mensaje.nombre_remitente,
        mensaje.id_externo,
        "audio" if mensaje.audio_file_id else "imagen" if mensaje.imagen_file_id else "texto",
        (mensaje.texto[:50] + "...") if mensaje.texto and len(mensaje.texto) > 50 else mensaje.texto,
    )

    try:
        orquestador = Orquestador(db=db, canal=adaptador)
        await orquestador.procesar_mensaje_entrante(mensaje)
    except Exception as e:
        logger.error("❌ Error procesando update #%s: %s", update_id, e, exc_info=True)
        # No re-raise: Telegram reintenta si recibe error, causando duplicados
        return {"status": "error", "detail": "error interno procesando mensaje"}

    return {"status": "ok"}


# =====================================================
# Futuro: WhatsApp webhook
# =====================================================
# @router.post("/whatsapp")
# async def webhook_whatsapp(request: Request, db: Session = Depends(get_db)):
#     payload = await request.json()
#     adaptador = WhatsAppAdapter()
#     mensaje = adaptador.parsear_entrada(payload)
#     if mensaje:
#         orquestador = Orquestador(db=db, canal=adaptador)
#         await orquestador.procesar_mensaje_entrante(mensaje)
#     return {"status": "ok"}
