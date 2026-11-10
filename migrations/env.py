"""Alembic environment, async.

The database URL comes from DATABASE_URL. Tests point it at the *_test database;
deployments point it at the environment's database. Migrations run as the owner
role, never as the runtime role.
"""

from __future__ import annotations

import asyncio
import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy.ext.asyncio import async_engine_from_config
from sqlalchemy.pool import NullPool

from firebrief.db.models import Base

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata

DEFAULT_URL = "postgresql+asyncpg://firebrief:firebrief_dev@127.0.0.1:55433/firebrief_test"


def _url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


def run_migrations_offline() -> None:
    context.configure(
        url=_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


IGNORED_INDEXES = {"ix_chunks_fts"}


def include_object(object_, name, type_, reflected, compare_to) -> bool:  # type: ignore[no-untyped-def]
    """The full-text index is an expression index created in raw SQL.

    Autogenerate cannot represent it, so it would otherwise appear as drift on
    every check. It is excluded by name, and its definition is asserted by the
    retrieval tests.
    """
    return not (type_ == "index" and name in IGNORED_INDEXES)


def _do_run(connection) -> None:  # type: ignore[no-untyped-def]
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = _url()
    engine = async_engine_from_config(configuration, prefix="sqlalchemy.", poolclass=NullPool)
    try:
        async with engine.connect() as connection:
            await connection.run_sync(_do_run)
    finally:
        await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
