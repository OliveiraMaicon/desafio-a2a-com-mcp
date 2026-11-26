"""Observa os campos de contexto antes da validação, sem alterar o request."""

import json
import sys


class RequestLog:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] != "/mcp" or scope["method"] != "POST":
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

        method = request_id = traceparent = None
        try:
            body = json.loads(b"".join(chunks))
            if isinstance(body, dict):
                method = body.get("method")
                request_id = body.get("id")
                params = body.get("params")
                meta = params.get("_meta") if isinstance(params, dict) else None
                if isinstance(meta, dict):
                    traceparent = meta.get("traceparent")
        except (ValueError, UnicodeDecodeError):
            pass
        # Tipos compostos não são identificadores e poderiam conter segredos.
        method = method if isinstance(method, str) else None
        request_id = request_id if isinstance(request_id, (str, int)) else None
        traceparent = traceparent if isinstance(traceparent, str) else None
        print(json.dumps({"method": method, "id": request_id, "traceparent": traceparent}, ensure_ascii=True), file=sys.stderr, flush=True)

        async def replay():
            if messages:
                return messages.pop(0)
            return await receive()

        await self.app(scope, replay, send)
