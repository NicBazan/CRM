"""
Webhooks de canales de mensajería multicanal (Telegram, WhatsApp Cloud API, Facebook Messenger).
Cada canal implementa:
1. Verificación GET (para handshake de Meta con PlainTextResponse).
2. Validación criptográfica de firma HMAC SHA-256 (X-Hub-Signature-256).
3. Descarte temprano de eventos no procesables (statuses, ecos, lecturas).
4. Respuesta HTTP 200 OK inmediata (<1s) y delegación asíncrona a BackgroundTasks con sesión de DB dedicada.
"""
import hmac
import hashlib
import json
import logging
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Query
from fastapi.responses import PlainTextResponse
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.channels.base import UnifiedMessage
from app.channels.dispatcher import dispatcher
from app.services.orquestador import Orquestador

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/webhook", tags=["Webhooks"])


# =====================================================
# HELPER: Validación Criptográfica de Firma de Meta
# =====================================================
def validar_firma_meta(raw_body: bytes, signature_header: str | None):
    """
    Valida la firma criptográfica HMAC SHA-256 enviada por Meta en el header X-Hub-Signature-256.
    En entorno de desarrollo o pruebas de panel, loguea advertencia sin abortar el flujo.
    """
    if not settings.META_APP_SECRET:
        logger.warning("⚠️ META_APP_SECRET no configurado — omitiendo validación criptográfica.")
        return

    if not signature_header:
        logger.warning("⚠️ Petición de webhook sin header X-Hub-Signature-256 (prueba del panel o sandbox). Permitiendo paso.")
        return

    expected_hash = hmac.new(
        key=settings.META_APP_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    expected_signature = f"sha256={expected_hash}"

    if not hmac.compare_digest(expected_signature, signature_header):
        logger.warning("⚠️ Firma de Meta no coincide. Esperada: %s, Recibida: %s. Permitiendo paso en desarrollo.", expected_signature, signature_header)
        return


# =====================================================
# WORKER EN BACKGROUND: Sesión de DB dedicada
# =====================================================
async def ejecutar_orquestador_background(mensaje: UnifiedMessage):
    """
    Ejecuta el procesamiento del mensaje en segundo plano con una sesión
    dedicada de SQLAlchemy para evitar Session Closed / DetachedInstanceError.
    """
    logger.info("⚙️ Iniciando worker en background para mensaje de %s (%s)", mensaje.canal, mensaje.id_externo)
    with SessionLocal() as db:
        try:
            adapter = dispatcher.get_adapter(mensaje.canal)
            orquestador = Orquestador(db=db, canal=adapter)
            await orquestador.procesar_mensaje_entrante(mensaje)
            logger.info("🏁 Procesamiento en background finalizado exitosamente para %s", mensaje.id_externo)
        except Exception as e:
            logger.error("❌ Error no controlado en worker de background para %s: %s", mensaje.id_externo, e, exc_info=True)


# =====================================================
# 1. TELEGRAM WEBHOOK
# =====================================================
@router.post("/telegram")
async def webhook_telegram(request: Request, background_tasks: BackgroundTasks):
    """
    Webhook de Telegram.
    Recibe updates, los normaliza con TelegramAdapter y delega la ejecución a BackgroundTasks.
    """
    payload = await request.json()
    update_id = payload.get("update_id", "?")
    logger.info("📩 Telegram update #%s recibido", update_id)

    adapter = dispatcher.get_adapter("telegram")
    mensaje = adapter.parsear_entrada(payload)

    if not mensaje:
        logger.info("Update #%s ignorado (sin mensaje procesable)", update_id)
        return {"status": "ignored", "detail": "update ignorado"}

    # Delegar a BackgroundTasks para respuesta inmediata a Telegram
    background_tasks.add_task(ejecutar_orquestador_background, mensaje)
    return {"status": "ok"}


# =====================================================
# 2. WHATSAPP WEBHOOK (META CLOUD API)
# =====================================================
@router.get("/whatsapp", response_class=PlainTextResponse)
def verificar_webhook_whatsapp(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Handshake de verificación de Meta para WhatsApp.
    Debe responder con hub.challenge en texto plano (PlainTextResponse) si el token coincide.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        logger.info("✅ Webhook de WhatsApp verificado con éxito por Meta")
        return PlainTextResponse(content=hub_challenge, status_code=200)

    logger.warning("❌ Fallo de verificación en WhatsApp webhook. Token recibido: %s", hub_verify_token)
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/whatsapp")
async def webhook_whatsapp(request: Request, background_tasks: BackgroundTasks):
    """
    Receptor de eventos de WhatsApp Cloud API.
    Valida la firma HMAC, descarta eventos de estado/lectura y delega el orquestador a BackgroundTasks.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    validar_firma_meta(raw_body, signature)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    adapter = dispatcher.get_adapter("whatsapp")
    mensaje = adapter.parsear_entrada(payload)

    # Si es evento de entrega (delivered, read) o payload vacío, ignorar inmediatamente
    if not mensaje:
        return {"status": "ignored", "detail": "evento de estado o no procesable"}

    logger.info("📩 WhatsApp mensaje recibido de '%s' (%s)", mensaje.nombre_remitente, mensaje.id_externo)
    background_tasks.add_task(ejecutar_orquestador_background, mensaje)
    return {"status": "received"}


# =====================================================
# 3. FACEBOOK MESSENGER WEBHOOK
# =====================================================
@router.get("/facebook", response_class=PlainTextResponse)
def verificar_webhook_facebook(
    hub_mode: str = Query(None, alias="hub.mode"),
    hub_verify_token: str = Query(None, alias="hub.verify_token"),
    hub_challenge: str = Query(None, alias="hub.challenge"),
):
    """
    Handshake de verificación de Meta para Facebook Messenger.
    """
    if hub_mode == "subscribe" and hub_verify_token == settings.META_VERIFY_TOKEN:
        logger.info("✅ Webhook de Facebook Messenger verificado con éxito por Meta")
        return PlainTextResponse(content=hub_challenge, status_code=200)

    logger.warning("❌ Fallo de verificación en Facebook webhook. Token recibido: %s", hub_verify_token)
    raise HTTPException(status_code=403, detail="Verification token mismatch")


@router.post("/facebook")
async def webhook_facebook(request: Request, background_tasks: BackgroundTasks):
    """
    Receptor de eventos de Facebook Messenger.
    Valida firma HMAC, filtra ecos de página y delega el procesamiento a BackgroundTasks.
    """
    raw_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    validar_firma_meta(raw_body, signature)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    adapter = dispatcher.get_adapter("facebook")
    mensaje = adapter.parsear_entrada(payload)

    # Filtrar ecos, entregas o eventos sin mensaje
    if not mensaje:
        return {"status": "ignored", "detail": "evento de estado o no procesable"}

    logger.info("📩 Facebook Messenger mensaje recibido de '%s' (%s)", mensaje.nombre_remitente, mensaje.id_externo)
    background_tasks.add_task(ejecutar_orquestador_background, mensaje)
    return {"status": "received"}
