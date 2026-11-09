"""Database layer: models, sessions and the role safety check."""

from firebrief.db.models import Base, Membership, Tenant, TimestampsMixin, User, new_id
from firebrief.db.roles import UnsafeDatabaseRole, assert_safe_database_role, verify_database_role
from firebrief.db.session import MissingTenantError, apply_tenant, make_engine, tenant_session

__all__ = [
    "Base",
    "Membership",
    "MissingTenantError",
    "Tenant",
    "TimestampsMixin",
    "UnsafeDatabaseRole",
    "User",
    "apply_tenant",
    "assert_safe_database_role",
    "make_engine",
    "new_id",
    "tenant_session",
    "verify_database_role",
]
