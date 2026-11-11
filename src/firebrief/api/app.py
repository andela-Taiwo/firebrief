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

import logging
import re
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.answer import answer_question
from firebrief.answer.judge import SupportJudge
from firebrief.answer.pipeline import BudgetScope
from firebrief.api.config import Settings
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
    sender: EmailSender,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):  # type: ignore[no-untyped-def]
        # A deployment that cannot keep tenants apart must not start.
        async with engine.begin() as connection:
            await assert_safe_database_role(connection)
        yield

    app = FastAPI(title="Firebrief", version="0.1.0")
    app.state.engine = engine
    app.state.embedder = embedder
    app.state.provider = provider
    app.state.judge = judge
    app.state.budget = budget
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
    async def magic_link(body: MagicLinkRequest) -> dict[str, str]:
        await request_magic_link(engine, tenant_id=body.tenant_id, email=body.email, sender=sender)
        # The same answer whether or not the address exists.
        return {"status": "sent"}

    @app.post("/v1/auth/verify", response_model=SessionResponse)
    async def verify(body: VerifyRequest, response: Response) -> SessionResponse:
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
        context: AuthContext = Depends(current_session),
    ) -> AnswerResponse:
        async with tenant_session(engine, context.tenant_id) as session:
            result = await answer_question(
                session,
                body.question,
                embedder=embedder,
                provider=provider,
                judge=judge,
                budget=budget,
                scope=BudgetScope(
                    org_id=str(context.tenant_id),
                    team_id=str(context.tenant_id),
                    user_id=str(context.user_id),
                ),
                # One id across the access log, the response and the audit record.
                request_id=request.state.request_id,
            )
        return AnswerResponse.from_result(result)

    return app


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

    allowed = {str(request.base_url).rstrip("/"), *settings.allowed_origins}
    origin = request.headers.get("origin")
    if origin is not None:
        return None if origin.rstrip("/") in allowed else "origin not allowed"

    referer = request.headers.get("referer")
    if referer is None:
        return "origin or referer is required"
    return None if any(referer.startswith(url) for url in allowed) else "origin not allowed"


def _json(status_code: int, body: dict[str, str], request_id: str):  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse

    return JSONResponse(body, status_code=status_code, headers={"x-request-id": request_id})
