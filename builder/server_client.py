"""HTTP client for the data server. The builder uses it to register and test."""

from __future__ import annotations

import requests

from builder import config


class ServerError(Exception):
    """The data server refused the request or is not available."""


class ServerClient:
    def __init__(
        self, base_url: str | None = None, token: str | None = None, timeout: int | None = None
    ):
        self.base_url = (base_url or config.SERVER_URL).rstrip("/")
        self.token = token if token is not None else config.BUILDER_TOKEN
        self.timeout = timeout or config.REQUEST_TIMEOUT_S

    def _request(self, method: str, path: str, params=None, payload=None, token=False):
        url = f"{self.base_url}{path}"
        headers = {}
        if token:
            headers["X-Builder-Token"] = self.token
        try:
            response = requests.request(
                method, url, params=params, json=payload, headers=headers, timeout=self.timeout
            )
        except requests.RequestException as error:
            raise ServerError(f"the server is not available: {error}") from error
        try:
            data = response.json()
        except ValueError as error:
            raise ServerError(
                f"the server answered with bad JSON (status {response.status_code})"
            ) from error
        if not response.ok:
            raise ServerError(str(data.get("error", f"status {response.status_code}")))
        return data

    def register(self, instruction: str, source: str, meta: dict) -> dict:
        data = self._request(
            "POST",
            "/api/registry/register",
            payload={"instruction": instruction, "source": source, "meta": meta},
            token=True,
        )
        return data["function"]

    def run(self, function_id: str, params: dict, session: dict) -> dict:
        return self._request(
            "POST",
            f"/api/registry/{function_id}/run",
            payload={"params": params, "session": session},
        )

    def drivers(self, session: dict) -> list[dict]:
        data = self._request(
            "GET",
            f"/api/session/{session['year']}/{session['round']}/{session['code']}/drivers",
        )
        return data["drivers"]

    def laps(self, session: dict, driver: str) -> dict:
        return self._request(
            "GET",
            f"/api/session/{session['year']}/{session['round']}/{session['code']}/laps",
            params={"driver": driver},
        )
