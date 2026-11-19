"""ASGI app factory. FastAPI is imported only here, only when `create_app` is called, so the core and its
tests run without the web server. The gateway (PLT-024) must pass the SSE response through unbuffered."""
from __future__ import annotations

from .core import Dependencies, handle_request

PATH = "/v1/agent/stream"


def create_app(deps: Dependencies):
    from fastapi import FastAPI, Request
    from fastapi.responses import Response, StreamingResponse

    app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

    @app.api_route(PATH, methods=["POST", "GET", "PUT", "DELETE", "PATCH"])
    async def stream(request: Request):
        body = await request.body() if request.method == "POST" else b""
        host = (request.headers.get("host") or "").split(":")[0]
        res = handle_request(deps, method=request.method, headers=dict(request.headers), host=host, body=body)
        headers = dict(res.headers)
        media = headers.pop("content-type", "application/json")
        if res.status == 200:
            return StreamingResponse(res.body, media_type=media, headers=headers)
        return Response(b"".join(res.body), status_code=res.status, media_type=media, headers=headers)

    return app
