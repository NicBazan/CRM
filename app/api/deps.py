"""
Dependencias compartidas para inyección en las rutas y autenticación.
"""
import hmac
from typing import Optional
from fastapi import Depends, HTTPException, Security, status, WebSocket
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials, APIKeyHeader
from app.core.database import SessionLocal
from app.core.config import get_settings
from app.core.security import decode_access_token

settings = get_settings()

# Esquemas de seguridad OpenAPI
bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


def get_db():
    """
    Generador que crea una sesión de base de datos por request
    y la cierra automáticamente al finalizar.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
    api_key: Optional[str] = Security(api_key_header),
) -> dict:
    """
    Valida que la petición tenga un token JWT válido o una API Key válida.
    """
    # 1. Validación por API Key (si está configurada y enviada)
    if api_key and settings.ADMIN_API_KEY:
        if hmac.compare_digest(api_key, settings.ADMIN_API_KEY):
            return {"sub": "api_key_user", "rol": "admin"}

    # 2. Validación por Bearer Token (JWT)
    if credentials:
        payload = decode_access_token(credentials.credentials)
        if payload and "sub" in payload:
            return payload

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Credenciales de autenticación no válidas o ausentes",
        headers={"WWW-Authenticate": "Bearer"},
    )


async def validar_token_websocket(websocket: WebSocket) -> Optional[dict]:
    """
    Valida el token para conexiones WebSocket recibido como query parameter (?token=...)
    o header 'Authorization'. Si es inválido, rechaza la conexión.
    """
    token = websocket.query_params.get("token")
    if not token:
        # Intentar leer del header de autorización si existe
        auth_header = websocket.headers.get("authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header[7:]

    if token:
        # Chequear si es la API Key
        if settings.ADMIN_API_KEY and hmac.compare_digest(token, settings.ADMIN_API_KEY):
            return {"sub": "api_key_user", "rol": "admin"}
        payload = decode_access_token(token)
        if payload and "sub" in payload:
            return payload

    # En caso de token inválido o ausente
    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Autenticación requerida")
    return None
