"""Authentication helpers for Sonos SMAPI music services."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import quote, urlparse

import requests

from .constants import DEFAULT_URL_SHORTENER, HTTP_REQUEST_TIMEOUT


@dataclass(frozen=True)
class AuthenticationLink:
    """Data needed to finish a DeviceLink or AppLink authentication."""

    code: str
    device_id: str | None
    service: str | None = None


class AuthenticationBroker:
    """Store short-lived SMAPI registration links behind speakable codes."""

    def __init__(
        self,
        base_url: str = DEFAULT_URL_SHORTENER,
        session: requests.Session | Any | None = None,
        timeout: int = HTTP_REQUEST_TIMEOUT,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout

    def create(
        self,
        registration_url: str,
        link_code: str,
        device_id: str | None,
        service: str,
    ) -> str:
        """Create a short URL and return only its speakable path code."""
        response = self.session.post(
            self.base_url,
            json={
                "target": registration_url,
                "extras": {
                    "code": link_code,
                    "device": device_id,
                    "service": service,
                },
            },
            timeout=self.timeout,
        )
        response.raise_for_status()
        link = str(response.json()["link"])
        path = urlparse(link).path if "://" in link else link
        short_code = path.rstrip("/").rsplit("/", maxsplit=1)[-1]
        if not short_code:
            raise ValueError("URL shortener returned an empty link code")
        return short_code

    def resolve(self, short_code: str) -> AuthenticationLink:
        """Resolve a speakable code into the original SMAPI link data."""
        safe_code = quote(short_code, safe="")
        response = self.session.get(
            f"{self.base_url}/{safe_code}/info", timeout=self.timeout
        )
        response.raise_for_status()
        extras = response.json().get("extras")
        if not isinstance(extras, dict) or not extras.get("code"):
            raise ValueError("URL shortener response does not contain link metadata")
        return AuthenticationLink(
            code=str(extras["code"]),
            device_id=extras.get("device"),
            service=extras.get("service"),
        )

    def delete(self, short_code: str) -> None:
        """Remove a completed authentication link from the broker."""
        safe_code = quote(short_code, safe="")
        response = self.session.delete(
            f"{self.base_url}/{safe_code}", timeout=self.timeout
        )
        response.raise_for_status()
