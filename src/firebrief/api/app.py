"""The HTTP surface.

Rules that hold across every route:

- The session is an `HttpOnly` cookie; the token never appears in a URL.
- The question is never logged. The access line carries the method, path, status, duration
  and a server-generated request id. The client's id is logged separately, never used.
- A state-changing request must be `application/json` and must come from an allowed origin,
  because `SameSite=Lax` alone does not stop every cross-site post.
- A refusal is a `200` with a reason: it is an answer, not an error.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import time
import uuid
from contextlib import asynccontextmanager
from urllib.parse import urlsplit

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.answer import answer_question
from firebrief.answer.judge import SupportJudge
from firebrief.answer.pipeline import BudgetScope
from firebrief.api.config import DEVELOPMENT_SECRET, Settings
from firebrief.api.schemas import (
    AnswerRequest,
    AnswerResponse,
    MagicLinkRequest,
    SessionResponse,
    VerifyRequest,
)
from firebrief.auth import (
    SESSION_TTL,
    AuthContext,
    InvalidToken,
    LinkNotUsable,
    LoginResult,
    login_with_magic_link,
    request_magic_link,
    resolve_session,
    revoke_session,
)
from firebrief.auth.email import EmailSender
from firebrief.budget import BudgetService
from firebrief.db.roles import assert_safe_database_role
from firebrief.db.session import tenant_session
from firebrief.ingest.embed import Embedder
from firebrief.llm import Provider
from firebrief.ratelimit import Limit, Limiter, key_for

logger = logging.getLogger("firebrief.api")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CLIENT_REQUEST_ID = re.compile(r"^[A-Za-z0-9-]{1,64}$")


def create_app(
    *,
    engine: AsyncEngine,
    embedder: Embedder,
    provider: Provider,
    judge: SupportJudge,
    budget: BudgetService,
    limiter: Limiter,
    sender: EmailSender,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        # A deployment that cannot keep tenants apart must not start.
        async with engine.begin() as connection:
            await assert_safe_database_role(connection)
        if settings.environment == "production":
            if settings.trusted_proxy_hops == 0 and settings.client_ip_header is None:
                raise RuntimeError(
                    "set trusted_proxy_hops or client_ip_header in production: "
                    "every user would otherwise share one rate-limit bucket"
                )
            if settings.rate_limit_secret == DEVELOPMENT_SECRET:
                raise RuntimeError("set rate_limit_secret in production")
            if len(settings.rate_limit_secret) < 32:
                raise RuntimeError("rate_limit_secret must be at least 32 characters")
        yield

    app = FastAPI(title="Firebrief", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    app.state.embedder = embedder
    app.state.provider = provider
    app.state.judge = judge
    app.state.budget = budget
    app.state.limiter = limiter
    app.state.sender = sender
    app.state.settings = settings
    app.state.cookie_name = (
        f"__Host-{settings.session_cookie}" if settings.cookie_secure else settings.session_cookie
    )

    @app.middleware("http")
    async def context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        if request.method not in SAFE_METHODS:
            refused = _origin_refusal(request, settings)
            if refused is not None:
                return _json(403, {"detail": refused}, request_id)

        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        response.headers["x-content-type-options"] = "nosniff"
        if request.url.path.startswith(("/v1/auth", "/v1/answers")):
            response.headers["cache-control"] = "no-store"
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%d request_id=%s client_request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            int((time.perf_counter() - started) * 1000),
            request_id,
            _client_request_id(request) or "-",
        )
        return response

    async def current_session(request: Request) -> AuthContext:
        token = request.cookies.get(app.state.cookie_name)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="no session")
        context = await resolve_session(engine, token)
        if context is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="no session")
        return context

    @app.get("/health")
    async def health() -> dict[str, str]:
        """The process is alive. Says nothing about its dependencies."""
        return {"status": "ok"}

    @app.get("/ready")
    async def ready() -> dict[str, str]:
        """The process can serve: the database answers and the role cannot bypass RLS."""
        try:
            async with engine.begin() as connection:
                await connection.execute(text("select 1"))
                await assert_safe_database_role(connection)
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="not ready"
            ) from exc
        return {"status": "ready"}

    @app.post("/v1/auth/magic-link", status_code=status.HTTP_202_ACCEPTED)
    async def magic_link(body: MagicLinkRequest, request: Request, response: Response) -> object:
        # The IP first: a refused caller must not consume the address's quota.
        limited = await _enforce(
            limiter,
            key_for("link:ip", _client_ip(request, settings), settings.rate_limit_secret),
            Limit(settings.link_ip_limit, settings.link_window_seconds),
            response,
        )
        if limited is not None:
            return limited
        limited = await _enforce(
            limiter,
            key_for("link:email", body.email, settings.rate_limit_secret),
            Limit(settings.link_email_limit, settings.link_window_seconds),
            response,
        )
        if limited is not None:
            return limited

        await request_magic_link(engine, tenant_id=body.tenant_id, email=body.email, sender=sender)
        # The same answer whether or not the address exists.
        return {"status": "sent"}

    @app.post("/v1/auth/verify", response_model=SessionResponse)
    async def verify(
        body: VerifyRequest, request: Request, response: Response
    ) -> SessionResponse | JSONResponse:
        limited = await _enforce(
            limiter,
            key_for("verify:ip", _client_ip(request, settings), settings.rate_limit_secret),
            Limit(settings.verify_ip_limit, settings.verify_window_seconds),
            response,
        )
        if limited is not None:
            return limited
        try:
            login: LoginResult = await login_with_magic_link(engine, body.token)
        except (InvalidToken, LinkNotUsable) as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="link not usable"
            ) from exc
        response.set_cookie(
            app.state.cookie_name,
            login.session_token,
            max_age=int(SESSION_TTL.total_seconds()),
            httponly=True,
            secure=settings.cookie_secure,
            samesite="lax",
            path="/",
        )
        return SessionResponse(
            tenant_id=login.context.tenant_id,
            user_id=login.context.user_id,
            role=login.context.role,
        )

    @app.post("/v1/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
    async def logout(request: Request, response: Response) -> None:
        token = request.cookies.get(app.state.cookie_name)
        if token:
            await revoke_session(engine, token)
        response.delete_cookie(app.state.cookie_name, path="/")

    @app.get("/v1/auth/me", response_model=SessionResponse)
    async def me(context: AuthContext = Depends(current_session)) -> SessionResponse:
        return SessionResponse(
            tenant_id=context.tenant_id, user_id=context.user_id, role=context.role
        )

    @app.post("/v1/answers", response_model=AnswerResponse)
    async def answers(
        request: Request,
        body: AnswerRequest,
        response: Response,
        context: AuthContext = Depends(current_session),
    ) -> AnswerResponse | JSONResponse:
        limited = await _enforce(
            limiter,
            key_for(
                "answer:user",
                f"{context.tenant_id}:{context.user_id}",
                settings.rate_limit_secret,
            ),
            Limit(settings.answer_user_limit, settings.answer_window_seconds),
            response,
        )
        if limited is not None:
            return limited

        async with tenant_session(engine, context.tenant_id) as session:
            result = await answer_question(
                session,
                body.question,
                embedder=embedder,
                provider=provider,
                judge=judge,
                budget=budget,
                # Teams are not modelled yet, so team limits are the organisation's.
                scope=BudgetScope(
                    org_id=str(context.tenant_id),
                    team_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                ),
                # One id across the access log, the response and the audit record.
                request_id=request.state.request_id,
            )
        payload = AnswerResponse.from_result(result)
        status_code = _status_for(result)
        if status_code != status.HTTP_200_OK:
            refusal = JSONResponse(payload.model_dump(mode="json"), status_code=status_code)
            # The rate-limit headers were set on the injected response; keep them.
            for name, value in response.headers.items():
                refusal.headers.setdefault(name, value)
            return refusal
        return payload

    return app


async def _enforce(
    limiter: Limiter, key: str, limit: Limit, response: Response
) -> JSONResponse | None:
    """A limiter that cannot answer must not let traffic through (ADR 0007)."""
    try:
        decision = await limiter.check(key, limit)
    except Exception as exc:
        logger.warning("rate limiter unavailable: %s", type(exc).__name__)
        return JSONResponse(
            {"detail": "rate limiting unavailable"},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            headers={"retry-after": "5"},
        )
    headers = _rate_headers(decision, limit)
    if decision.allowed:
        # Two limits on one route: the tighter one is what the client should see.
        current = response.headers.get("ratelimit-remaining")
        if current is None or decision.remaining < int(current):
            for name, value in headers.items():
                response.headers[name] = value
        return None
    return JSONResponse(
        {"detail": "too many requests"},
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={**headers, "retry-after": str(decision.retry_after_seconds)},
    )


def _rate_headers(decision, limit) -> dict[str, str]:  # type: ignore[no-untyped-def]
    # Reset is an upper bound: the whole window, not the time until a slot frees up.
    return {
        "ratelimit-limit": str(decision.limit),
        "ratelimit-remaining": str(decision.remaining),
        "ratelimit-reset": str(limit.window_seconds),
    }


def _client_ip(request: Request, settings: Settings) -> str:
    """The address the platform saw, never one the client wrote for itself.

    `X-Forwarded-For` grows on the right, so with N trusted proxies the client is the Nth
    entry from the right. The leftmost entries are whatever the caller chose to send.
    """
    if settings.client_ip_header:
        value = request.headers.get(settings.client_ip_header)
        if value:
            return _bucket_ip(value.strip())

    if settings.trusted_proxy_hops > 0:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            parts = [part.strip() for part in forwarded.split(",") if part.strip()]
            if len(parts) >= settings.trusted_proxy_hops:
                return _bucket_ip(parts[-settings.trusted_proxy_hops])

    return _bucket_ip(request.client.host if request.client else "unknown")


def _bucket_ip(value: str) -> str:
    """IPv6 users own a /64, so counting single addresses would not limit them."""
    try:
        address = ipaddress.ip_address(value)
    except ValueError:
        return value
    if address.version == 6:
        return str(ipaddress.ip_network(f"{address}/64", strict=False).network_address)
    return str(address)


def _status_for(result) -> int:  # type: ignore[no-untyped-def]
    """A refusal about the answer is a 200; a capacity condition is not."""
    from firebrief.answer import RefusalReason

    reason = result.refusal.reason if result.refusal is not None else None
    if reason is RefusalReason.BUDGET_EXHAUSTED:
        return status.HTTP_429_TOO_MANY_REQUESTS
    if reason in {RefusalReason.BUDGET_UNAVAILABLE, RefusalReason.MODEL_UNAVAILABLE}:
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_200_OK


def _origin(url: str) -> str:
    """The scheme and host of a URL, so `http://test.evil` cannot match `http://test`."""
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}".lower().rstrip("/")


def _client_request_id(request: Request) -> str | None:
    value = request.headers.get("x-request-id")
    return value if value is not None and CLIENT_REQUEST_ID.match(value) else None


def _origin_refusal(request: Request, settings: Settings) -> str | None:
    """Why this state-changing request may not proceed, or None if it may."""
    # Bodyless requests (logout) carry no content type; a body must be JSON, because a
    # browser cannot send that cross-site without a preflight.
    has_body = request.headers.get("content-length") not in (None, "0") or (
        "transfer-encoding" in request.headers
    )
    if has_body and not request.headers.get("content-type", "").startswith("application/json"):
        return "content type must be application/json"

    allowed = {_origin(str(request.base_url))} | {_origin(url) for url in settings.allowed_origins}
    origin = request.headers.get("origin")
    if origin is not None:
        return None if _origin(origin) in allowed else "origin not allowed"

    referer = request.headers.get("referer")
    if referer is None:
        return "origin or referer is required"
    # Compare the parsed origin: a prefix match would accept a lookalike domain.
    return None if _origin(referer) in allowed else "origin not allowed"


def _json(status_code: int, body: dict[str, str], request_id: str):  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse

    return JSONResponse(
        body,
        status_code=status_code,
        headers={
            "x-request-id": request_id,
            "x-content-type-options": "nosniff",
            "cache-control": "no-store",
        },
    )
