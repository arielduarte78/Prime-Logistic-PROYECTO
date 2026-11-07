import main

DEV_OPERATOR = {"client_id": "dev_operator", "client_secret": "ZGV2X3NlY3JldF8xMjM="}


def test_sin_registro_configurado_no_hay_clientes(monkeypatch):
    """Si falta ABBEY_CLIENT_REGISTRY el registro queda vacío (antes habilitaba dev_operator / dev_admin)."""
    monkeypatch.delenv("ABBEY_CLIENT_REGISTRY", raising=False)
    assert main._load_client_registry() == {}


def test_auth_token_rechaza_dev_operator_sin_registro(test_client, monkeypatch):
    monkeypatch.delenv("ABBEY_CLIENT_REGISTRY", raising=False)
    monkeypatch.setattr(main, "_client_registry", main._load_client_registry())
    r = test_client.post("/auth/token", json=DEV_OPERATOR)
    assert r.status_code == 401


def test_auth_token_con_registro_configurado(test_client, monkeypatch):
    monkeypatch.setattr(main, "_client_registry", {
        "cliente1": {"secret": "secreto-largo-123", "name": "Cliente 1", "role": "operator"}})
    ok = test_client.post("/auth/token", json={"client_id": "cliente1", "client_secret": "secreto-largo-123"})
    mal = test_client.post("/auth/token", json={"client_id": "cliente1", "client_secret": "secreto-largo-124"})
    assert ok.status_code == 200 and "access_token" in ok.json()
    assert mal.status_code == 401


def test_secreto_con_caracteres_raros_no_rompe(test_client, monkeypatch):
    """compare_digest con str no-ASCII lanza TypeError; hay que comparar bytes."""
    monkeypatch.setattr(main, "_client_registry", {
        "c": {"secret": "secreto-largo-123", "name": "C", "role": "operator"}})
    r = test_client.post("/auth/token", json={"client_id": "c", "client_secret": "contraseñaÑ-largo"})
    assert r.status_code == 401


def test_clave_legacy_x_api_key_sigue_funcionando(test_client):
    """La ruta que usa el frontend no se toca."""
    body = {"vehicles": [{"id": "t", "origin_lat": 0.0, "origin_lon": 0.0, "capacity_tons": 1.0}],
            "destinations": [{"id": "d", "lat": -34.61, "lon": -58.38, "demand_tons": 1.0}]}
    r = test_client.post("/fleet", json=body, headers={"x-api-key": "test_key_123"})
    assert r.status_code == 400  # pasó la autenticación y cayó en la validación de coordenadas
    r = test_client.post("/fleet", json=body, headers={"x-api-key": "clave-mala"})
    assert r.status_code == 401
