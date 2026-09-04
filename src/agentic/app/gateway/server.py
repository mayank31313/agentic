import logging
import os

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from starlette.responses import JSONResponse

from agentic.app.gateway.adapters import (
    InboundMessage,
    OutboundMessage,
)
from agentic.app.gateway.adapters.websockets import WebSocketConnectionManager
from agentic.app.gateway.config import Gateway

logger = logging.getLogger(__name__)

def get_adapter_gateway(
    gateway: Gateway,
    connection_manager: WebSocketConnectionManager,
    agentic_bot=None,
) -> FastAPI:
    app = FastAPI()

    @app.websocket("/ws/{chat_id}")
    async def websocket_endpoint(websocket: WebSocket, chat_id: str):
        await websocket.accept()
        await connection_manager.connect(chat_id, websocket)
        try:
            while True:
                data = await websocket.receive_text()
                inbound_message = InboundMessage(
                    message_id="websocket",
                    channel="websocket",
                    chat_id=chat_id,
                    user_id=chat_id,
                    text=data,
                )
                response = await gateway.route_to_backend(inbound_message)
                outbound_message = OutboundMessage(
                    chat_id=chat_id,
                    text="AGENT",
                    channel="websocket",
                    metadata=dict(response=response),
                )
                await gateway.deliver_to_channel(outbound_message)

        except WebSocketDisconnect:
            logger.error(f"WebSocket disconnected for chat_id: {chat_id}")

        await connection_manager.disconnect(chat_id)

    @app.get("/health")
    async def health_check():
        return {"status": "ok"}

    @app.post("/admin/tools/reload")
    async def reload_tools(request: Request):
        """Refresh MCP/sub-agent/agent-authored custom tools and rebuild the
        compiled agent graph, without a full process restart.

        Guarded by the `AGENTIC_ADMIN_TOKEN` env var when set (compared
        against the `X-Admin-Token` header); if unset, the endpoint is left
        open, which is only appropriate for local/dev use — set the token
        in any deployment reachable beyond localhost.
        """
        admin_token = os.environ.get("AGENTIC_ADMIN_TOKEN")
        if admin_token and request.headers.get("X-Admin-Token") != admin_token:
            return JSONResponse({"error": "unauthorized"}, status_code=401)

        if agentic_bot is None:
            return JSONResponse(
                {"error": "tool reload is not available (no bot wired into the gateway)"},
                status_code=503,
            )
        try:
            summary = agentic_bot.reload_tools()
        except Exception as e:
            logger.exception("Failed to reload tools")
            return JSONResponse({"error": str(e)}, status_code=500)
        return {"ok": True, "reloaded": summary}

    @app.post("/webhook/{chat_id}/send")
    async def send_message(chat_id: str, message: OutboundMessage):
        message.chat_id = chat_id
        await gateway.deliver_to_channel(message)
        return {"ok": True}

    @app.post("/webhook/forward")
    async def generic_webhook(request: Request):
        payload = await request.json()
        outbound_message  = OutboundMessage.model_validate(payload)
        return await gateway.deliver_to_channel(outbound_message)

    return app
