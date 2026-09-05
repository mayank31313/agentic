import importlib.util
import sys
from types import SimpleNamespace
from pathlib import Path
import types

from fastapi.testclient import TestClient
from pydantic import BaseModel


def _ensure_module(name: str, *, package: bool = False):
    module = sys.modules.get(name)
    if module is None:
        module = types.ModuleType(name)
        if package:
            module.__path__ = []
        sys.modules[name] = module
    return module


def _load_gateway_server_module():
    _ensure_module("agentic", package=True)
    _ensure_module("agentic.app", package=True)
    _ensure_module("agentic.app.gateway", package=True)

    adapters = _ensure_module("agentic.app.gateway.adapters")

    class InboundMessage(BaseModel):
        message_id: str
        channel: str
        chat_id: str
        user_id: str
        text: str

    class OutboundMessage(BaseModel):
        channel: str
        chat_id: str
        text: str
        metadata: dict = {}

    adapters.InboundMessage = InboundMessage
    adapters.OutboundMessage = OutboundMessage

    websockets = _ensure_module("agentic.app.gateway.adapters.websockets")
    websockets.WebSocketConnectionManager = type("WebSocketConnectionManager", (), {})

    config = _ensure_module("agentic.app.gateway.config")
    config.Gateway = type("Gateway", (), {})

    module_path = (
        Path(__file__).resolve().parents[1]
        / "src"
        / "agentic"
        / "app"
        / "gateway"
        / "server.py"
    )
    spec = importlib.util.spec_from_file_location("gateway_server_under_test", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


gateway_server = _load_gateway_server_module()
get_adapter_gateway = gateway_server.get_adapter_gateway


class DummyGateway:
    async def route_to_backend(self, message):
        return []

    async def deliver_to_channel(self, message):
        return {"ok": True}


def test_reload_tools_runs_in_worker_thread(monkeypatch):
    calls = []

    def reload_tools():
        calls.append("reloaded")
        return {"mcp": ["tool-a"]}

    captured = {}

    async def fake_to_thread(func, /, *args, **kwargs):
        captured["func"] = func
        return func(*args, **kwargs)

    monkeypatch.setattr(gateway_server.asyncio, "to_thread", fake_to_thread)
    app = get_adapter_gateway(
        DummyGateway(),
        SimpleNamespace(connect=None, disconnect=None),
        agentic_bot=SimpleNamespace(reload_tools=reload_tools),
    )

    response = TestClient(app).post("/admin/tools/reload")

    assert response.status_code == 200
    assert response.json() == {"ok": True, "reloaded": {"mcp": ["tool-a"]}}
    assert captured["func"] is reload_tools
    assert calls == ["reloaded"]
