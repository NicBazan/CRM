import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
import jwt
from app.core.config import get_settings

settings = get_settings()


def hash_password(password: str, salt: str | None = None) -> str:
    """Genera un hash seguro usando PBKDF2-HMAC-SHA256."""
    if not salt:
        salt = secrets.token_hex(16)
    hashed = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return f"{salt}${hashed}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifica una contraseña contra su hash PBKDF2 o texto plano si es la inicial."""
    if "$" not in hashed_password:
        return hmac.compare_digest(plain_password, hashed_password)
    salt, original_hash = hashed_password.split("$", 1)
    new_hash = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt.encode("utf-8"),
        100_000,
    ).hex()
    return hmac.compare_digest(original_hash, new_hash)


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Crea un token JWT firmado."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    return jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict | None:
    """Decodifica y valida un token JWT."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except jwt.PyJWTError:
        return None
