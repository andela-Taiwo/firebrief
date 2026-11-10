"""Sending the link.

A port, because delivery is a deployment concern. Tests record; production sends.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Protocol

logger = logging.getLogger(__name__)


class EmailSender(Protocol):
    async def send_magic_link(self, *, to: str, token: str) -> None: ...


@dataclass
class RecordingEmailSender:
    sent: list[tuple[str, str]] = field(default_factory=list)

    async def send_magic_link(self, *, to: str, token: str) -> None:
        self.sent.append((to, token))


@dataclass
class NullEmailSender:
    """Swallows the link. For a deployment that has not configured delivery yet."""

    async def send_magic_link(self, *, to: str, token: str) -> None:
        logger.warning("no email sender configured; the link was not sent")
