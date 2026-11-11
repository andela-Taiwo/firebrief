"""The schema, as models.

Migrations are generated from these and then read by a person. The models are
deliberately plain: the tenant rules live in SQL (policies, triggers), because
that is where they must be enforced.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

import uuid6
from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    MetaData,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

ROLES = ("owner", "inspector", "viewer")


def new_id() -> uuid.UUID:
    """UUIDv7: unguessable in URLs, time-ordered so indexes stay compact."""
    return uuid6.uuid7()


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampsMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Maintained by a BEFORE UPDATE trigger, never by application code, so bulk
    # updates and raw SQL move it too and it cannot be backdated.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class Tenant(TimestampsMixin, Base):
    __tablename__ = "tenants"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200), nullable=False)


class User(TimestampsMixin, Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)

    __table_args__ = (
        Index("uq_users_tenant_email_lower", "tenant_id", func.lower(text("email")), unique=True),
        # The target of the composite foreign key below. A plain foreign key
        # from memberships would let one tenant point at another tenant's user:
        # referential integrity checks run as the owner and bypass RLS.
        UniqueConstraint("tenant_id", "id", name="uq_users_tenant_id_id"),
    )


class Membership(TimestampsMixin, Base):
    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False)

    __table_args__ = (
        CheckConstraint("role in ('owner', 'inspector', 'viewer')", name="role_allowed"),
        UniqueConstraint("tenant_id", "user_id", name="uq_memberships_tenant_user"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_memberships_tenant_user",
        ),
    )


class Document(TimestampsMixin, Base):
    """A guidance document. Global, not tenant-owned: the corpus is shared."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(200), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    source_url: Mapped[str] = mapped_column(String(1000), nullable=False)


class DocumentVersion(Base):
    """One immutable snapshot of a document.

    Identity is the hash of the parsed sections plus the reviewed metadata
    (licence and edition), so a corrected edition is a new version rather than a
    silent no-op. The title is snapshotted here: a citation should say what the
    document was called when it was read, not what it is called today.
    """

    __tablename__ = "document_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id"), nullable=False, index=True
    )
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    source_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    licence: Mapped[str] = mapped_column(String(50), nullable=False)
    edition: Mapped[str] = mapped_column(String(100), nullable=False)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint("document_id", "content_hash", name="uq_document_versions_content"),
    )


class Section(Base):
    """A section of one version. Append-only, like the version it belongs to."""

    __tablename__ = "sections"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False)
    heading: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (UniqueConstraint("version_id", "ordinal", name="uq_sections_ordinal"),)


class Chunk(Base):
    """A retrievable piece of one section of one version.

    `section_id` and the character offsets are what make a citation resolvable:
    `heading_path` alone is ambiguous when a document has two "Notes" sections.
    The embedding model and the chunker configuration are both part of the key, so
    a new model or a new budget adds a complete set rather than mixing ordinals.
    """

    __tablename__ = "chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_versions.id"), nullable=False, index=True
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("sections.id"), nullable=False, index=True
    )
    embedding_model: Mapped[str] = mapped_column(String(100), nullable=False)
    chunker: Mapped[str] = mapped_column(String(100), nullable=False)
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    heading_path: Mapped[str] = mapped_column(Text, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    char_start: Mapped[int] = mapped_column(Integer, nullable=False)
    char_end: Mapped[int] = mapped_column(Integer, nullable=False)
    token_estimate: Mapped[int] = mapped_column(Integer, nullable=False)
    dimensions: Mapped[int] = mapped_column(Integer, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(ARRAY(Float), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        UniqueConstraint(
            "version_id",
            "embedding_model",
            "chunker",
            "ordinal",
            name="uq_chunks_version_model_chunker_ordinal",
        ),
        CheckConstraint("dimensions > 0", name="chunk_dimensions_positive"),
        CheckConstraint("array_length(embedding, 1) = dimensions", name="chunk_dimensions_match"),
        CheckConstraint("char_start >= 0 and char_end >= char_start", name="chunk_offsets_ordered"),
    )


class AuthMagicLink(Base):
    """A single-use login token. Only its hash is stored."""

    __tablename__ = "auth_magic_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ended_reason: Mapped[str | None] = mapped_column(String(20), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "token_hash", name="uq_auth_links_tenant_hash"),
        CheckConstraint(
            "ended_reason in ('used', 'superseded', 'unknown')", name="ended_reason_allowed"
        ),
        CheckConstraint(
            "(consumed_at is null) = (ended_reason is null)", name="consumed_with_reason"
        ),
        # The user must belong to the same tenant: RLS does not apply to RI checks.
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_auth_links_tenant_user",
        ),
    )


class AuthSession(Base):
    """A login session. Only its hash is stored."""

    __tablename__ = "auth_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False, index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint("tenant_id", "token_hash", name="uq_auth_sessions_tenant_hash"),
        ForeignKeyConstraint(
            ["tenant_id", "user_id"],
            ["users.tenant_id", "users.id"],
            name="fk_auth_sessions_tenant_user",
        ),
    )


class BudgetCounter(Base):
    """A counter per (scope, period, period start). The durable form of the budget."""

    __tablename__ = "budget_counters"

    scope_type: Mapped[str] = mapped_column(String(16), primary_key=True)
    scope_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    period: Mapped[str] = mapped_column(String(16), primary_key=True)
    period_start: Mapped[date] = mapped_column(Date, primary_key=True)
    reserved: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    spent: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")

    __table_args__ = (
        CheckConstraint("reserved >= 0", name="reserved_not_negative"),
        CheckConstraint("spent >= 0", name="spent_not_negative"),
    )


class BudgetReservation(Base):
    """One row per request, so a restart can still settle or sweep it."""

    __tablename__ = "budget_reservations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    model: Mapped[str] = mapped_column(String(80), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    keys: Mapped[list[dict[str, str]]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="pending")

    __table_args__ = (
        CheckConstraint("amount >= 0", name="amount_not_negative"),
        CheckConstraint("state in ('pending', 'settled', 'released')", name="state_allowed"),
        Index("ix_budget_reservations_pending", "state", "expires_at"),
    )
