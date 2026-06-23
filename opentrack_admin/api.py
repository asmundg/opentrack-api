"""Thin OpenTrack REST API client (token auth).

OpenTrack exposes a Django REST Framework API. A director-level token can read
and update (PATCH/PUT) existing competitions, events and competitors, which is
enough to set event start times and seed PB/SB data without driving a browser.
Creating competitions/events and merging events are not available to a director
token (POST is rejected), so those stay on the Playwright path.

Authentication: POST {base}/api/get-auth-token/ with username+password to obtain
a token, then send it as ``Authorization: Token <token>``.
"""

import logging
from urllib.parse import urlparse

import requests

logger = logging.getLogger(__name__)


class OpenTrackAPIError(RuntimeError):
    """An OpenTrack API call returned a non-success status."""


def api_base_from_url(url: str) -> str:
    """Return the API origin (``scheme://host``) for a competition or base URL.

    Deriving the origin from the competition URL means pointing a command at a
    ``test-*`` host transparently targets the matching test API.
    """
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Cannot derive API base from {url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


class OpenTrackAPI:
    """Minimal client covering the read/update calls the ported commands need."""

    def __init__(self, base: str, token: str):
        self.base = base.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update(
            {
                "Authorization": f"Token {token}",
                "Referer": self.base + "/",
            }
        )

    @classmethod
    def from_credentials(
        cls, base_or_url: str, username: str, password: str
    ) -> "OpenTrackAPI":
        """Authenticate and return a client. ``base_or_url`` may be a bare host
        URL or any page/competition URL on that host."""
        base = api_base_from_url(base_or_url)
        resp = requests.post(
            f"{base}/api/get-auth-token/",
            data={"username": username, "password": password},
        )
        token = resp.json().get("token") if resp.headers.get(
            "content-type", ""
        ).startswith("application/json") else None
        if resp.status_code != 200 or not token:
            raise OpenTrackAPIError(
                f"Authentication failed ({resp.status_code}): {resp.text[:200]}"
            )
        return cls(base, token)

    def _url(self, path: str) -> str:
        return f"{self.base}/api/{path.lstrip('/')}"

    def _request(self, method: str, url: str, **kwargs) -> requests.Response:
        resp = self.session.request(method, url, **kwargs)
        if not resp.ok:
            raise OpenTrackAPIError(
                f"{method} {url} -> {resp.status_code}: {resp.text[:300]}"
            )
        return resp

    def _get_paginated(self, path: str, **params) -> list[dict]:
        """GET a list endpoint, following DRF ``next`` links."""
        results: list[dict] = []
        url: str | None = self._url(path)
        first = True
        while url:
            resp = self._request("GET", url, params=params if first else None)
            data = resp.json()
            results.extend(data.get("results", []))
            url = data.get("next")
            first = False
        return results

    def my_competitions(self) -> list[dict]:
        """Competitions the authenticated user manages (id, url, role, ...)."""
        resp = self._request("GET", self._url("my-competitions/"))
        return resp.json().get("competitions", [])

    def resolve_competition_id(self, url_or_slug: str) -> str:
        """Map a public competition URL (or bare slug) to its API competition id.

        The events/competitors endpoints key off this id, which equals the
        ``id`` returned by ``my-competitions`` (not always the same UUID as the
        ``/api/competitions/{uuid}/`` resource).
        """
        slug = url_or_slug.rstrip("/").split("/")[-1]
        for comp in self.my_competitions():
            comp_slug = comp.get("url", "").rstrip("/").split("/")[-1]
            if comp_slug == slug:
                return comp["id"]
        raise OpenTrackAPIError(
            f"No managed competition matches slug {slug!r}. Check the URL and "
            f"that you have director access."
        )

    def get_competitors(self, comp_id: str, limit: int = 500) -> list[dict]:
        return self._get_paginated("competitors/", competition=comp_id, limit=limit)

    def put_competitor(self, competitor: dict) -> None:
        url = self._url(f"competitors/{competitor['id']}/")
        self._request("PUT", url, json=competitor)

    def get_events(self, comp_id: str, limit: int = 200) -> list[dict]:
        return self._get_paginated("events/", competition=comp_id, limit=limit)

    def patch_event(self, event: dict, **fields) -> None:
        self._request("PATCH", event["url"], json=fields)
