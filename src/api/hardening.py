# Cross-cutting HTTP hardening (Etapa 7, ADR-0015 API hardening). Pure
# transport-layer concerns — no domain logic, registered once in src/main.py.
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

# Comfortably above the largest legitimate body (product_name <=200 chars +
# description <=300 chars, schemas.py) and comfortably below anything that
# could meaningfully exhaust memory. Pydantic's max_length only rejects an
# oversized field *after* the whole body is buffered into memory; this
# middleware rejects a declared oversized body before that ever happens.
MAX_BODY_BYTES = 10_000


class PayloadSizeLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > MAX_BODY_BYTES:
            return JSONResponse(status_code=413, content={"detail": "Payload too large."})
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """No-downside defense-in-depth for a stateless JSON API.

    CSP is deliberately not set: this service never renders HTML, so a
    content-security-policy has nothing to constrain.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        # Reinforces Fly.io's force_https (fly.toml) at the app level too —
        # harmless locally over plain HTTP, browsers only honor it over HTTPS.
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
        return response
