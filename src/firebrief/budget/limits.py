"""The budget hierarchy: organisation -> team -> user, with daily and monthly limits."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from firebrief.budget.money import Money


class ScopeType(StrEnum):
    ORG = "org"
    TEAM = "team"
    USER = "user"


class Period(StrEnum):
    DAILY = "daily"
    MONTHLY = "monthly"


_SCOPE_ORDER = {ScopeType.ORG: 0, ScopeType.TEAM: 1, ScopeType.USER: 2}
_PERIOD_ORDER = {Period.DAILY: 0, Period.MONTHLY: 1}


@dataclass(frozen=True, slots=True)
class Limit:
    scope_type: ScopeType
    scope_id: str
    period: Period
    amount: Money

    def __post_init__(self) -> None:
        if not self.scope_id:
            raise ValueError("scope_id must not be empty")
        if self.amount <= 0:
            raise ValueError("a limit must be positive")


class LimitBook:
    """An immutable set of limits, indexed by the scope they belong to."""

    def __init__(self, limits: Iterable[Limit]) -> None:
        index: dict[tuple[ScopeType, str], list[Limit]] = {}
        for limit in limits:
            index.setdefault((limit.scope_type, limit.scope_id), []).append(limit)
        self._index = {key: tuple(sorted(value, key=_order)) for key, value in index.items()}

    def for_ids(self, *, org_id: str, team_id: str, user_id: str) -> tuple[Limit, ...]:
        """Every limit that applies to one request, ordered org, team, user."""
        found: list[Limit] = []
        for scope_type, scope_id in (
            (ScopeType.ORG, org_id),
            (ScopeType.TEAM, team_id),
            (ScopeType.USER, user_id),
        ):
            found.extend(self._index.get((scope_type, scope_id), ()))
        return tuple(sorted(found, key=_order))

    def __len__(self) -> int:
        return sum(len(value) for value in self._index.values())


def _order(limit: Limit) -> tuple[int, int, str]:
    return (_SCOPE_ORDER[limit.scope_type], _PERIOD_ORDER[limit.period], limit.scope_id)
