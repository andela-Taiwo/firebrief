#!/usr/bin/env python3
"""Send one test message through the configured sender and show what happened.

The API deliberately swallows delivery failures so an unknown address cannot be detected.
That makes a misconfigured sender invisible from the outside — this script is the opposite:
it prints the provider's answer and exits non-zero.
"""

from __future__ import annotations

import asyncio
import sys

from firebrief.api.dev import build_sender
from firebrief.auth.resend import EmailDeliveryError


async def main(to: str) -> int:
    sender = build_sender()
    print(f"sender: {type(sender).__name__}")
    if hasattr(sender, "from_address"):
        print(f"from:   {sender.from_address}")
    print(f"to:     {to}")
    try:
        # A deliberately unusable token: this checks delivery, not sign-in.
        # Deliberately unusable: this checks delivery, not sign-in.
        placeholder = "test-token-from-check-email"
        await sender.send_magic_link(to=to, token=placeholder)
    except EmailDeliveryError as exc:
        print(f"\nFAILED: {exc}")
        print(
            "\nResend only sends from a domain you have verified, and "
            "onboarding@resend.dev only delivers to the account owner."
        )
        return 1
    print("\nsent: the provider accepted the message")
    return 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: check_email.py you@example.com")
    raise SystemExit(asyncio.run(main(sys.argv[1])))
