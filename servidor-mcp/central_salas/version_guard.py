"""Rejeita conflito de versão antes do roteamento legado do SDK MCP 2.3."""

import json

from starlette.datastructures import Headers
from starlette.responses import JSONResponse


class ProtocolVersionGuard:
    """Verifica apenas o caso legado que não chega ao validador moderno do SDK."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "POST" or scope["path"] != "/mcp":
            await self.app(scope, receive, send)
            return

        header = Headers(scope=scope).get("mcp-protocol-version")
        if header not in {None, "2024-11-05", "2025-03-26", "2025-06-18", "2025-11-25"}:
            await self.app(scope, receive, send)
            return

        messages = []
        chunks = []
        while True:
            message = await receive()
            messages.append(message)
            if message["type"] != "http.request":
                break
            chunks.append(message.get("body", b""))
            if not message.get("more_body", False):
                break

        try:
            body = json.loads(b"".join(chunks))
            params = body.get("params") if isinstance(body, dict) else None
            meta = params.get("_meta") if isinstance(params, dict) else None
            version = meta.get("io.modelcontextprotocol/protocolVersion") if isinstance(meta, dict) else None
        except (ValueError, UnicodeDecodeError):
            body = None
            version = None

        if version == "2026-07-28" and header != version:
            response = JSONResponse(
                {"jsonrpc": "2.0", "id": body.get("id"), "error": {"code": -32020, "message": "Protocol version header does not match request metadata"}},
                status_code=400,
            )
            await response(scope, receive, send)
            return

        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay, send)
