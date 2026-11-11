"""Running the API locally.

Everything here is a development default, and two of them are deliberately weak:

- `ExtractiveProvider` quotes the first sentence of the best source. It needs no API key and
  is deterministic, but it is not a model: it cannot reason, only quote.
- `FixedJudge` accepts every quote, so the verifier checks that a quote exists in the
  source but not that it supports the claim. The support judge is still to be built.

Set `FIREBRIEF_PROVIDER=anthropic` or `openai` with a key to use a real model. The judge
stays `FixedJudge` either way until that exists; the README says so.
"""

from __future__ import annotations

import logging
import os

import httpx
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from firebrief.answer.judge import FixedJudge
from firebrief.api.app import create_app
from firebrief.api.config import Settings
from firebrief.auth.email import EmailSender
from firebrief.auth.resend import DEFAULT_FROM, ResendSender
from firebrief.budget import (
    BudgetService,
    Limit,
    LimitBook,
    ModelPrice,
    Period,
    PriceTable,
    ScopeType,
)
from firebrief.budget.postgres import PostgresLedger
from firebrief.ingest.embed import BagOfWordsEmbedder, Embedder
from firebrief.llm import AnthropicProvider, OpenAIProvider, Provider
from firebrief.llm.extractive import ExtractiveProvider
from firebrief.ratelimit import InMemoryLimiter

logger = logging.getLogger("firebrief.dev")

DEV_TENANT = "018f0000-0000-7000-8000-0000000000aa"
DEV_USER = "018f0000-0000-7000-8000-0000000000ab"
DEV_EMAIL = "dev@firebrief.local"
DEV_DAILY_MICROS = 10_000_000


class ConsoleEmailSender:
    """Prints the sign-in link instead of sending it. Development only."""

    async def send_magic_link(self, *, to: str, token: str) -> None:
        base = os.environ.get("FIREBRIEF_WEB_URL", "http://127.0.0.1:5173")
        print(
            f"\n  Sign-in link for {to}:\n  {base}/auth/verify#token={token}\n",
            flush=True,
        )


def database_url() -> str:
    """The **runtime** role, not the owner.

    The application refuses to start as the owner: a superuser can drop or replace the
    row-level-security policies, so the tenant isolation would not hold.
    """
    url = os.environ.get(
        "FIREBRIEF_DATABASE_URL",
        "postgresql+asyncpg://firebrief_app:firebrief_app_dev@127.0.0.1:55433/firebrief_dev",
    )
    # The test suite truncates its database between tests. Sharing it with the dev server
    # means every `make check` silently deletes the workspace you are signed into.
    database = make_url(url).database or ""
    if database.endswith("_test"):
        raise SystemExit(
            "refusing to run the development server against a *_test database: "
            "the tests truncate it. Use firebrief_dev (see `make dev-setup`)."
        )
    return url


def build_provider() -> Provider:
    choice = os.environ.get("FIREBRIEF_PROVIDER", "extractive").lower()
    if choice == "anthropic":
        return AnthropicProvider(
            api_key=os.environ["ANTHROPIC_API_KEY"], client=httpx.AsyncClient()
        )
    if choice == "openai":
        return OpenAIProvider(api_key=os.environ["OPENAI_API_KEY"], client=httpx.AsyncClient())
    if choice != "extractive":
        raise SystemExit(f"unknown FIREBRIEF_PROVIDER: {choice}")
    logger.warning("using the extractive baseline provider: it quotes, it does not reason")
    return ExtractiveProvider()


def build_embedder() -> Embedder:
    choice = os.environ.get("FIREBRIEF_EMBEDDINGS", "bag-of-words")
    if choice != "bag-of-words":
        raise SystemExit(f"unsupported FIREBRIEF_EMBEDDINGS: {choice}")
    return BagOfWordsEmbedder()


def build_sender() -> EmailSender:
    """Resend when a key is present, the terminal otherwise.

    Production must use Resend: a deployment that prints sign-in links to a log has no way
    for anyone to sign in, and logs are not a delivery mechanism.
    """
    key = os.environ.get("RESEND_API_KEY")
    environment = os.environ.get("FIREBRIEF_ENVIRONMENT", "development")
    if key:
        sender = ResendSender(
            api_key=key,
            web_url=os.environ.get("FIREBRIEF_WEB_URL", "http://127.0.0.1:5173"),
            from_address=os.environ.get("FIREBRIEF_EMAIL_FROM", DEFAULT_FROM),
        )
        logger.info("sending sign-in links through Resend from %s", sender.from_address)
        return sender
    if environment == "production":
        raise SystemExit("RESEND_API_KEY is required in production")
    logger.warning("RESEND_API_KEY is not set: the sign-in link will be printed, not emailed")
    return ConsoleEmailSender()


def _budget(engine: AsyncEngine) -> BudgetService:
    return BudgetService(
        ledger=PostgresLedger(engine),
        limits=LimitBook([Limit(ScopeType.USER, DEV_USER, Period.DAILY, DEV_DAILY_MICROS)]),
        prices=PriceTable(
            "GBP",
            {"claude-sonnet-4-5-20250929": ModelPrice(3_000_000, 15_000_000)},
        ),
    )


def build_app():  # type: ignore[no-untyped-def]
    engine = create_async_engine(database_url())
    return create_app(
        engine=engine,
        embedder=build_embedder(),
        provider=build_provider(),
        judge=FixedJudge(),
        budget=_budget(engine),
        limiter=InMemoryLimiter(),
        sender=build_sender(),
        settings=Settings(
            cookie_secure=False,
            environment="development",
            # The browser talks to the Vite server, which proxies to this one.
            allowed_origins=("http://127.0.0.1:5173", "http://localhost:5173"),
        ),
    )


app = build_app()
