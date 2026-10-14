"""
Webhooks de canales de mensajería multicanal (Telegram, WhatsApp Cloud API, Facebook Messenger).
Reciben eventos, validan firmas criptográficas y delegan el procesamiento al orquestador en BackgroundTasks.
"""
import hmac
import hashlib
import json
import logging
from fastapi import APIRouter, Request, BackgroundTasks, HTTPException, Query, Header
from fastapi.responses import PlainTextResponse

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.channels.dispatcher import dispatcher
from app.channels.base import UnifiedMessage
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
    En producción rechaza con HTTP 403 Forbidden si falta el secreto, falta la firma o no coincide.
    En desarrollo, si META_APP_SECRET está configurado, valida estrictamente.
    """
    is_prod = settings.ENVIRONMENT.lower() == "production"

    if not settings.META_APP_SECRET:
        if is_prod:
            logger.error("❌ META_APP_SECRET no configurado en entorno de producción. Rechazando petición.")
            raise HTTPException(status_code=403, detail="Firma de Meta requerida pero no configurada")
        logger.warning("⚠️ META_APP_SECRET no configurado — omitiendo validación criptográfica en desarrollo.")
        return

    if not signature_header:
        logger.warning("❌ Petición de webhook de Meta sin header X-Hub-Signature-256.")
        raise HTTPException(status_code=403, detail="Header X-Hub-Signature-256 ausente")

    expected_hash = hmac.new(
        key=settings.META_APP_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    expected_signature = f"sha256={expected_hash}"

    if not hmac.compare_digest(expected_signature, signature_header):
        logger.warning("❌ Firma de Meta no coincide. Esperada: %s, Recibida: %s.", expected_signature, signature_header)
        raise HTTPException(status_code=403, detail="Firma criptográfica de Meta inválida")


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
async def webhook_telegram(
    request: Request,
    background_tasks: BackgroundTasks,
    x_telegram_bot_api_secret_token: str | None = Header(None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    """
    Webhook de Telegram.
    Verifica el header X-Telegram-Bot-Api-Secret-Token si TELEGRAM_SECRET_TOKEN está configurado.
    En producción, el secret_token es obligatorio y se rechaza con 403 si no coincide.
    """
    is_prod = settings.ENVIRONMENT.lower() == "production"

    if settings.TELEGRAM_SECRET_TOKEN:
        if not x_telegram_bot_api_secret_token or not hmac.compare_digest(
            settings.TELEGRAM_SECRET_TOKEN, x_telegram_bot_api_secret_token
        ):
            logger.warning("❌ Token secreto de Telegram inválido o ausente en header X-Telegram-Bot-Api-Secret-Token.")
            raise HTTPException(status_code=403, detail="Telegram secret token inválido")
    elif is_prod:
        logger.error("❌ TELEGRAM_SECRET_TOKEN no configurado en producción. Rechazando webhook.")
        raise HTTPException(status_code=403, detail="TELEGRAM_SECRET_TOKEN obligatorio en producción")

    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

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
    Debe responder con hub.challenge en texto plano si el token coincide.
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
