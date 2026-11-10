"""The HTTP surface.

Three rules hold across every route:

- The session is a cookie, never a bearer token in a URL, and it is `HttpOnly`.
- The question is never logged. Access lines carry the method, path, status, duration and
  request id; the body is not touched.
- A state-changing request with a cookie must come from an allowed origin, because
  `SameSite=Lax` alone does not stop a cross-site form post.
"""

from __future__ import annotations

import logging
import time
import uuid

from fastapi import Depends, FastAPI, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncEngine

from firebrief.answer import FixedJudge, answer_question
from firebrief.answer.judge import SupportJudge
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
    LinkNotUsable,
    LoginResult,
    login_with_magic_link,
    request_magic_link,
    resolve_session,
    revoke_session,
)
from firebrief.auth.email import EmailSender
from firebrief.db.session import tenant_session
from firebrief.ingest.embed import Embedder
from firebrief.llm import Provider

logger = logging.getLogger("firebrief.api")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def create_app(
    *,
    engine: AsyncEngine,
    embedder: Embedder,
    provider: Provider,
    judge: SupportJudge | None = None,
    sender: EmailSender | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    settings = settings or Settings()
    app = FastAPI(title="Firebrief", version="0.1.0")
    app.state.engine = engine
    app.state.embedder = embedder
    app.state.provider = provider
    app.state.judge = judge or FixedJudge()
    app.state.sender = sender
    app.state.settings = settings

    @app.middleware("http")
    async def context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        request.state.request_id = request_id
        started = time.perf_counter()

        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if origin is not None and origin not in settings.allowed_origins:
                return _json(403, {"detail": "origin not allowed"}, request_id)

        response = await call_next(request)
        response.headers["x-request-id"] = request_id
        logger.info(
            "request method=%s path=%s status=%s duration_ms=%d request_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            int((time.perf_counter() - started) * 1000),
            request_id,
        )
        return response

    async def current_session(request: Request) -> AuthContext:
        token = request.cookies.get(settings.session_cookie)
        if not token:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="no session")
        context = await resolve_session(engine, token)
        if context is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="no session")
        return context

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/auth/magic-link", status_code=status.HTTP_202_ACCEPTED)
    async def magic_link(body: MagicLinkRequest) -> dict[str, str]:
        if sender is None:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="email")
        await request_magic_link(
            engine,
            tenant_id=body.tenant_id,
            email=body.email,
            sender=sender,
        )
        # The same answer whether or not the address exists.
        return {"status": "sent"}

    @app.post("/v1/auth/verify", response_model=SessionResponse)
    async def verify(body: VerifyRequest, response: Response) -> SessionResponse:
        try:
            login: LoginResult = await login_with_magic_link(engine, body.token)
        except LinkNotUsable as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="link not usable"
            ) from exc
        response.set_cookie(
            settings.session_cookie,
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
        token = request.cookies.get(settings.session_cookie)
        if token:
            await revoke_session(engine, token)
        response.delete_cookie(settings.session_cookie, path="/")

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
                judge=app.state.judge,
                # One id across the access log, the response and the audit record.
                request_id=request.state.request_id,
            )
        return AnswerResponse.from_result(result)

    return app


def _json(status_code: int, body: dict[str, str], request_id: str):  # type: ignore[no-untyped-def]
    from fastapi.responses import JSONResponse

    return JSONResponse(body, status_code=status_code, headers={"x-request-id": request_id})
