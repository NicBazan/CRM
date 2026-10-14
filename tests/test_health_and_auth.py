def test_health_check(client):
    """Verifica que el endpoint de health check responda 200 y status healthy."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert "version" in data


def test_login_exitoso(client):
    """Verifica el login con credenciales correctas."""
    response = client.post("/auth/login", json={"username": "admin", "password": "testpassword123"})
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["username"] == "admin"


def test_login_credenciales_invalidas(client):
    """Verifica que credenciales incorrectas retornen 401 Unauthorized."""
    response = client.post("/auth/login", json={"username": "admin", "password": "wrongpassword"})
    assert response.status_code == 401


def test_ruta_protegida_sin_token(client):
    """Verifica que intentar acceder a rutas del CRM sin token sea rechazado con 401."""
    res_clientes = client.get("/clientes/")
    assert res_clientes.status_code == 401

    res_conversaciones = client.get("/conversaciones/")
    assert res_conversaciones.status_code == 401

    res_conocimiento = client.get("/conocimiento/")
    assert res_conocimiento.status_code == 401


def test_ruta_protegida_con_token(client):
    """Verifica que con un Bearer token válido se pueda acceder a las rutas protegidas."""
    login_res = client.post("/auth/login", json={"username": "admin", "password": "testpassword123"})
    token = login_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    res_clientes = client.get("/clientes/", headers=headers)
    assert res_clientes.status_code == 200
    assert isinstance(res_clientes.json(), list)

    res_me = client.get("/auth/me", headers=headers)
    assert res_me.status_code == 200
    assert res_me.json()["sub"] == "admin"
