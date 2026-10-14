import os
import sys
import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.api.deps import get_db
from app.core.config import get_settings
from app.main import app

# Configuración de base de datos en memoria para testing
SQLALCHEMY_DATABASE_URL = "sqlite:///:memory:"

engine_test = create_engine(
    SQLALCHEMY_DATABASE_URL,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine_test)


@pytest.fixture(scope="session", autouse=True)
def setup_test_settings():
    """Sobrescribe settings para testing."""
    settings = get_settings()
    settings.ENVIRONMENT = "testing"
    settings.SECRET_KEY = "super-secret-key-for-unit-testing-only"
    settings.TELEGRAM_SECRET_TOKEN = "test-secret-token"
    settings.META_APP_SECRET = "test-meta-app-secret"
    settings.ADMIN_USERNAME = "admin"
    settings.ADMIN_PASSWORD = "testpassword123"
    settings.ADMIN_API_KEY = "test-api-key"
    return settings


@pytest.fixture(autouse=True)
def init_test_db():
    """Crea y destruye tablas por test."""
    Base.metadata.create_all(bind=engine_test)
    yield
    Base.metadata.drop_all(bind=engine_test)


@pytest.fixture
def db_session():
    """Sesión de prueba de base de datos."""
    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_session):
    """Cliente HTTP de pruebas para FastAPI."""
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
