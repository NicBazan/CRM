from fastapi import APIRouter, HTTPException, Depends, status
from pydantic import BaseModel
from app.core.config import get_settings
from app.core.security import create_access_token, verify_password
from app.api.deps import get_current_user

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["Autenticación"])


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    username: str


@router.post("/login", response_model=TokenResponse)
def login(datos: LoginRequest):
    """
    Inicia sesión y genera un JWT Bearer token para el panel del CRM.
    """
    if datos.username != settings.ADMIN_USERNAME or not verify_password(datos.password, settings.ADMIN_PASSWORD):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Usuario o contraseña incorrectos",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = create_access_token({"sub": datos.username, "rol": "admin"})
    return TokenResponse(access_token=token, username=datos.username)


@router.get("/me")
def obtener_perfil(current_user: dict = Depends(get_current_user)):
    """Retorna los datos del usuario autenticado actual."""
    return current_user
