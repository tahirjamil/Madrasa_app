# test/test_middleware.py
import sys
import pytest
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from httpx import AsyncClient, ASGITransport

from utils.helpers.improved_functions import get_project_root

# Adjust this import to wherever your middleware classes are defined
sys.path.append(str(get_project_root()))
from app import XSSProtectionMiddleware, RequestLoggingMiddleware
import utils.helpers.fastapi_helpers as ru

MAX_JSON_BODY = ru.MAX_JSON_BODY

def set_max_json_body(n: int) -> None:
    """Tests can call this to set the module-level limit."""
    global MAX_JSON_BODY
    MAX_JSON_BODY = int(n)

@pytest.fixture(autouse=True)
def small_limit():
    """Temporarily reduce MAX_JSON_BODY for these tests (and restore afterwards)."""
    old = ru.MAX_JSON_BODY
    set_max_json_body(8)   # tiny limit for testing 413 behavior
    yield
    set_max_json_body(old)

@pytest.mark.anyio
async def test_middlewares_preserve_body():
    app = FastAPI()
    app.add_middleware(XSSProtectionMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        data = await request.json()
        return JSONResponse(content=data)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/echo", json={"a": "1"})
    assert r.status_code == 200
    assert r.json() == {"a": "1"}

@pytest.mark.anyio
async def test_middlewares_reject_oversize():
    app = FastAPI()
    app.add_middleware(XSSProtectionMiddleware)
    app.add_middleware(RequestLoggingMiddleware)

    @app.post("/echo")
    async def echo(request: Request):
        data = await request.json()
        return JSONResponse(content=data)

    transport = ASGITransport(app=app)
    payload = {"long": "value"}  # serialized > 8 bytes
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        r = await ac.post("/echo", json=payload)
    assert r.status_code == 413
