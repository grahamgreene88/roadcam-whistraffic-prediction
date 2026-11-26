"""Shared HTTP client: every request identifies the project and a contact address."""

import logging

import httpx

from whistler_traffic import __version__

log = logging.getLogger(__name__)


def user_agent(contact_email: str) -> str:
    return f"whistler-traffic/{__version__} (non-commercial UBC research; contact {contact_email})"


def make_client(contact_email: str, timeout: float = 20.0, **kwargs) -> httpx.Client:
    return httpx.Client(
        headers={"User-Agent": user_agent(contact_email)},
        timeout=timeout,
        follow_redirects=True,
        **kwargs,
    )


def ping(client: httpx.Client, url: str | None) -> None:
    """Heartbeat ping. Never raises: a monitoring hiccup must not stop logging."""
    if not url:
        return
    try:
        client.get(url, timeout=10.0)
    except httpx.HTTPError as exc:
        log.warning("heartbeat ping failed: %r", exc)
