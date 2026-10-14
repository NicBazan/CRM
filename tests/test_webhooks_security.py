import hmac
import hashlib
import json
from app.core.config import get_settings


def test_telegram_webhook_sin_secret_token_falla(client):
    """Verifica que si TELEGRAM_SECRET_TOKEN está configurado, peticiones sin él sean rechazadas con 403."""
    response = client.post(
        "/webhook/telegram",
        json={"update_id": 12345},
    )
    assert response.status_code == 403
    assert "Telegram secret token" in response.json()["detail"]


def test_telegram_webhook_con_secret_token_invalido_falla(client):
    """Verifica que si se envía un secret token incorrecto sea rechazado con 403."""
    response = client.post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": "token-falso-invalido"},
        json={"update_id": 12345},
    )
    assert response.status_code == 403


def test_telegram_webhook_con_secret_token_valido(client):
    """Verifica que con el token secreto correcto la petición sea procesada (o ignorada si no tiene mensaje procesable)."""
    settings = get_settings()
    response = client.post(
        "/webhook/telegram",
        headers={"X-Telegram-Bot-Api-Secret-Token": settings.TELEGRAM_SECRET_TOKEN},
        json={"update_id": 99999, "message": {"message_id": 1, "chat": {"id": 111}, "text": "hola"}},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_meta_webhook_sin_firma_falla(client):
    """Verifica que un webhook de WhatsApp/Meta sin firma sea rechazado con 403 si META_APP_SECRET está configurado."""
    response = client.post(
        "/webhook/whatsapp",
        json={"object": "whatsapp_business_account", "entry": []},
    )
    assert response.status_code == 403


def test_meta_webhook_firma_invalida_falla(client):
    """Verifica que una firma HMAC falsa sea rechazada con 403."""
    response = client.post(
        "/webhook/whatsapp",
        headers={"X-Hub-Signature-256": "sha256=abcdef1234567890"},
        json={"object": "whatsapp_business_account", "entry": []},
    )
    assert response.status_code == 403


def test_meta_webhook_firma_valida(client):
    """Verifica que una petición con firma HMAC SHA-256 válida sea aceptada."""
    settings = get_settings()
    payload = json.dumps({"object": "whatsapp_business_account", "entry": []})
    raw_body = payload.encode("utf-8")

    expected_hash = hmac.new(
        key=settings.META_APP_SECRET.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()

    signature_header = f"sha256={expected_hash}"

    response = client.post(
        "/webhook/whatsapp",
        headers={
            "X-Hub-Signature-256": signature_header,
            "Content-Type": "application/json",
        },
        content=raw_body,
    )
    assert response.status_code == 200
