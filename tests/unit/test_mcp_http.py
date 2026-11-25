import json
import logging
from collections.abc import Iterator
from typing import Any

import pytest
from starlette.testclient import TestClient
from test_mcp_lectura import RID, Repo

from actas.mcp_guarda import hash_token, nuevo_token
from actas.mcp_servidor import crear_app_mcp

HOST = "actas-panel.actas.svc.cluster.local:8081"
TOKEN = nuevo_token()
ACEPTA = "application/json, text/event-stream"


class Auditable(Repo):
    def __init__(self) -> None:
        super().__init__()
        self.auditoria: list[tuple[str, str, int]] = []
        self.fallar = False

    def auditar_mcp(self, herramienta: str, resultado: str, duracion_ms: int) -> None:
        if self.fallar:
            raise RuntimeError("la base no responde: Failing row contains (secreto)")
        self.auditoria.append((herramienta, resultado, duracion_ms))


@pytest.fixture
def repo() -> Auditable:
    return Auditable()


@pytest.fixture
def cliente(repo: Auditable) -> Iterator[TestClient]:
    with TestClient(crear_app_mcp(repo, (HOST,), hash_token(TOKEN)), base_url=f"http://{HOST}") as c:  # type: ignore[arg-type]
        yield c


def cab(**extra: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {TOKEN}", "Accept": ACEPTA, "Content-Type": "application/json"} | extra


def rpc(c: TestClient, metodo: str, params: dict[str, Any] | None = None, **extra: str) -> Any:
    return c.post(
        "/mcp", content=json.dumps({"jsonrpc": "2.0", "id": 1, "method": metodo, "params": params or {}}), headers=cab(**extra)
    )


def llamar(c: TestClient, herramienta: str, **args: Any) -> dict[str, Any]:
    r = rpc(c, "tools/call", {"name": herramienta, "arguments": args})
    assert r.status_code == 200, r.text
    resultado: dict[str, Any] = r.json()["result"]
    return resultado


def test_sin_token_401(cliente: TestClient) -> None:
    r = cliente.post("/mcp", content="{}", headers={"Accept": ACEPTA})
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer" and r.headers["cache-control"] == "no-store"


@pytest.mark.parametrize("auth", ["Bearer tmcp_otro", "Bearer ", "Basic abc", f"Token {TOKEN}", TOKEN])
def test_token_distinto_401(cliente: TestClient, auth: str) -> None:
    assert cliente.post("/mcp", content="{}", headers={"Authorization": auth, "Accept": ACEPTA}).status_code == 401


@pytest.mark.parametrize("esquema", ["Basic", "Aaa", "Zzz", "Digest", "bearer", "BEARER", "Bearer"])
def test_solo_el_esquema_bearer_entra(cliente: TestClient, esquema: str) -> None:
    r = cliente.post("/mcp", content="{}", headers={"Authorization": f"{esquema} {TOKEN}", "Accept": ACEPTA})
    assert (r.status_code == 401) == (esquema.lower() != "bearer")


@pytest.mark.parametrize("metodo", ["GET", "PUT", "DELETE", "PATCH", "OPTIONS"])
def test_lo_que_no_es_post_405(cliente: TestClient, metodo: str) -> None:
    r = cliente.request(metodo, "/mcp", headers=cab())
    assert r.status_code == 405 and r.headers["allow"] == "POST"


def test_host_y_origin(cliente: TestClient) -> None:
    for host in ("actas.cenitdigital.es", "evil.example", "actas-panel.actas.svc.cluster.local", HOST.upper()):
        assert rpc(cliente, "tools/list", Host=host).status_code == 403
    assert rpc(cliente, "tools/list", Origin="https://actas.cenitdigital.es").status_code == 403


def test_cuerpo_con_tope_y_sin_redireccion(cliente: TestClient) -> None:
    assert cliente.post("/mcp", content=b"x" * (65 * 1024), headers=cab()).status_code == 413
    r = rpc(cliente, "tools/list")
    assert r.status_code == 200 and not r.history


def test_solo_existe_mcp(cliente: TestClient) -> None:
    assert cliente.post("/", content="{}", headers=cab()).status_code == 404
    assert cliente.post("/mcp/otra", content="{}", headers=cab()).status_code == 404


def test_tres_herramientas_de_solo_lectura(cliente: TestClient) -> None:
    herramientas = rpc(cliente, "tools/list").json()["result"]["tools"]
    assert sorted(h["name"] for h in herramientas) == ["buscar_en_actas", "leer_acta", "listar_reuniones"]
    for h in herramientas:
        assert h["annotations"]["readOnlyHint"] is True and h["annotations"]["destructiveHint"] is False
    assert rpc(cliente, "resources/list").json()["result"]["resources"] == []
    assert rpc(cliente, "prompts/list").json()["result"]["prompts"] == []


def test_initialize_sin_estado(cliente: TestClient) -> None:
    r = rpc(
        cliente, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "h", "version": "1"}}
    )
    assert r.status_code == 200 and r.json()["result"]["serverInfo"]["name"] == "actas"
    assert "mcp-session-id" not in r.headers


def test_llamadas_de_lectura(cliente: TestClient) -> None:
    lista = json.loads(llamar(cliente, "listar_reuniones")["content"][0]["text"])
    assert lista["total"] == 2 and lista["reuniones"][0]["titulo"] == "Socios: llama a ···678"
    acta = json.loads(llamar(cliente, "leer_acta", reunion_id=RID)["content"][0]["text"])
    assert acta["segmentos"][0]["hablante"] == "Pablo" and acta["siguiente"] is None
    buscado = json.loads(llamar(cliente, "buscar_en_actas", consulta="presupuesto")["content"][0]["text"])
    assert buscado["resultados"][0]["fragmento"] == "llama al ···678 & escribe a [correo]"


def test_errores_de_dominio_con_mensaje_fijo(cliente: TestClient) -> None:
    r = llamar(cliente, "leer_acta", reunion_id="no-es-uuid")
    assert r["isError"] is True and "Identificador de reunión no válido" in r["content"][0]["text"]
    r = llamar(cliente, "leer_acta", reunion_id="22222222-2222-2222-2222-222222222222")
    assert r["isError"] is True and "Reunión no encontrada" in r["content"][0]["text"]
    assert llamar(cliente, "buscar_en_actas", consulta="612")["isError"] is True


def test_fallo_interno_generico_y_sin_logs_del_mensaje(
    cliente: TestClient, repo: Auditable, caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)

    def explota(*_: Any) -> Any:
        raise RuntimeError('Failing row contains ("la contraseña es rosebud")')

    repo.ultimas = explota  # type: ignore[method-assign]
    r = llamar(cliente, "listar_reuniones")
    assert r["isError"] is True and r["content"][0]["text"].endswith(": Error interno")
    salida, errores = capfd.readouterr()
    assert "rosebud" not in r["content"][0]["text"] + caplog.text + salida + errores
    assert repo.auditoria[-1][:2] == ("listar_reuniones", "error")


def test_la_busqueda_y_los_argumentos_no_van_a_los_logs(
    cliente: TestClient, caplog: pytest.LogCaptureFixture, capfd: pytest.CaptureFixture[str]
) -> None:
    caplog.set_level(logging.DEBUG)
    llamar(cliente, "buscar_en_actas", consulta="presupuesto-confidencial-zeta")
    llamar(cliente, "listar_reuniones", pagina="valor-secreto-xyz")
    salida, errores = capfd.readouterr()
    assert "confidencial-zeta" not in caplog.text + salida + errores and "valor-secreto-xyz" not in caplog.text + salida + errores


def test_auditoria_sin_argumentos_ni_contenido(cliente: TestClient, repo: Auditable) -> None:
    llamar(cliente, "buscar_en_actas", consulta="dato-sensible")
    llamar(cliente, "leer_acta", reunion_id="no-es-uuid")
    assert [(h, r) for h, r, _ in repo.auditoria] == [("buscar_en_actas", "ok"), ("leer_acta", "error")]
    assert all(ms >= 0 for _, _, ms in repo.auditoria)
    assert "dato-sensible" not in json.dumps(repo.auditoria) and "hola" not in json.dumps(repo.auditoria)


def test_si_no_se_puede_auditar_no_sale_ningun_dato(cliente: TestClient, repo: Auditable) -> None:
    repo.fallar = True
    r = llamar(cliente, "leer_acta", reunion_id=RID)
    assert r["isError"] is True and r["content"][0]["text"].endswith(": No se pudo auditar la llamada")
    assert "hola" not in json.dumps(r) and "secreto" not in json.dumps(r)


def test_el_token_emitido_tiene_la_entropia_documentada() -> None:
    assert len(nuevo_token().removeprefix("tmcp_")) == 43  # 32 bytes en base64url sin relleno


def test_la_guarda_ignora_lo_que_no_es_http() -> None:
    import asyncio

    from actas.mcp_guarda import GuardaMcp

    llamadas: list[str] = []

    async def interior(scope: Any, receive: Any, send: Any) -> None:
        llamadas.append(scope["type"])

    for tipo in ("websocket", "lifespan"):
        asyncio.run(GuardaMcp(interior, (HOST,), hash_token(TOKEN))({"type": tipo}, None, None))  # type: ignore[arg-type]
    assert llamadas == []
