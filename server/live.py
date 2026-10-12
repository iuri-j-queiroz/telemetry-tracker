"""F1TV access and live timing capture. See plan.md, section 10.

The auth flow copies the fastf1 flow, but it runs in the background:
  1. Start a local callback server on a free port.
  2. Give the user the login URL https://f1login.fastf1.dev?port=<port>.
  3. The F1 login page sends the token back to the local server.
  4. Verify the token and write it to the fastf1 auth file.

Live capture uses fastf1's SignalRClient with a clean stop.
This module depends on fastf1 internals. The version is pinned in uv.lock.
"""

from __future__ import annotations

import contextlib
import json
import logging
import threading
import time
import urllib.parse
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import jwt
from fastf1.internals import f1auth
from fastf1.livetiming.client import SignalRClient

from server import catalog
from server.config import LIVE_DIR

LOG = logging.getLogger(__name__)

AUTH_URL_TEMPLATE = "https://f1login.fastf1.dev?port={port}"
CAPTURE_TIMEOUT_S = 300


class LiveError(Exception):
    """The live request cannot run."""


def credential_status() -> dict:
    """Read the stored F1TV token and report its state. No network access."""
    try:
        token = f1auth.AUTH_DATA_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        token = ""
    if not token:
        return {
            "has_credentials": False,
            "state": "missing",
            "expires": None,
            "product": None,
            "subscription": None,
        }
    try:
        claims = jwt.decode(token, options={"verify_signature": False})
    except jwt.PyJWTError:
        return {
            "has_credentials": False,
            "state": "invalid",
            "expires": None,
            "product": None,
            "subscription": None,
        }
    expires = claims.get("exp")
    expired = bool(expires and expires < datetime.now(UTC).timestamp())
    return {
        "has_credentials": not expired,
        "state": "expired" if expired else "valid",
        "expires": datetime.fromtimestamp(expires, UTC).isoformat() if expires else None,
        "product": claims.get("SubscribedProduct"),
        "subscription": claims.get("SubscriptionStatus"),
    }


class AuthSession:
    """Run the F1TV browser login with a local callback server."""

    def __init__(self) -> None:
        self.state = "idle"  # idle | waiting | done | error
        self.url: str | None = None
        self.error: str | None = None
        self._token: str | None = None
        self._server: HTTPServer | None = None

    def info(self) -> dict:
        return {"state": self.state, "url": self.url, "error": self.error}

    def start(self) -> dict:
        """Start the callback server and return the login URL."""
        if self.state == "waiting":
            return self.info()
        self.state = "idle"
        self.error = None
        self._token = None
        try:
            self._server = HTTPServer(("127.0.0.1", 0), self._make_handler())
        except OSError as error:
            self.state = "error"
            self.error = f"cannot start the callback server: {error}"
            return self.info()
        self.url = AUTH_URL_TEMPLATE.format(port=self._server.server_port)
        self.state = "waiting"
        threading.Thread(target=self._serve, args=(self._server,), daemon=True).start()
        return self.info()

    def cancel(self) -> dict:
        self._stop_server()
        if self.state == "waiting":
            self.state = "idle"
        return self.info()

    def _serve(self, server: HTTPServer) -> None:
        try:
            server.serve_forever()
        finally:
            server.server_close()

    def _stop_server(self) -> None:
        server = self._server
        self._server = None
        if server is not None:
            # shutdown() must run in a different thread than serve_forever().
            threading.Thread(target=server.shutdown, daemon=True).start()

    def _make_handler(self):
        session = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):  # noqa: ARG002 - keep the console quiet
                pass

            def _cors_headers(self) -> None:
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")

            def do_OPTIONS(self) -> None:  # noqa: N802 - HTTP method name
                self.send_response(200)
                self._cors_headers()
                self.end_headers()

            def do_POST(self) -> None:  # noqa: N802 - HTTP method name
                if self.path != "/auth":
                    self.send_response(404)
                    self.end_headers()
                    return
                length = int(self.headers.get("Content-Length", "0"))
                raw = self.rfile.read(length).decode("utf-8")
                token = None
                try:
                    cookie = json.loads(raw).get("loginSession", "")
                    parsed = json.loads(urllib.parse.unquote(str(cookie)))
                    token = parsed.get("data", {}).get("subscriptionToken")
                except (ValueError, TypeError):
                    token = None
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self._cors_headers()
                self.end_headers()
                self.wfile.write(b'{"status": "ok"}')
                session._receive(token)

        return Handler

    def _receive(self, token: str | None) -> None:
        """Called from the callback handler thread."""
        self._token = token
        threading.Thread(target=self._finalize, daemon=True).start()

    def _finalize(self) -> None:
        if not self._token:
            self.state = "error"
            self.error = "the login page sent no token"
        else:
            try:
                f1auth._verify_jwt(self._token, f1auth.JWKS_URL)  # noqa: SLF001
            except Exception as error:  # noqa: BLE001 - report any verify problem
                self.state = "error"
                self.error = f"token verification failed: {error}"
            else:
                f1auth.AUTH_DATA_FILE.write_text(self._token, encoding="utf-8")
                self.state = "done"
        self._stop_server()


AUTH = AuthSession()


def start_auth() -> dict:
    return AUTH.start()


def auth_info() -> dict:
    return AUTH.info()


def cancel_auth() -> dict:
    return AUTH.cancel()


def clear_credentials() -> dict:
    f1auth.clear_auth_token()
    return credential_status()


class ManagedSignalRClient(SignalRClient):
    """SignalRClient with a clean stop(). The parent has no stop method."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop_requested = False
        self._closed = False

    def stop(self) -> None:
        self._stop_requested = True
        self._close()

    def _close(self) -> None:
        if self._closed:
            return
        self._closed = True
        with contextlib.suppress(Exception):
            self._connection.stop()
        with contextlib.suppress(Exception):
            self._output_file.close()

    def _supervise(self) -> None:
        self._t_last_message = time.time()
        while not self._stop_requested:
            if self.timeout != 0 and time.time() - self._t_last_message > self.timeout:
                self.logger.warning("No live data for more than %s s. Stop.", self.timeout)
                self._close()
                return
            time.sleep(1)
        self._close()


class Capture:
    """One live timing capture. Record, stop, then load into the session manager."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.state = "idle"  # idle | capturing | done | error
        self.error: str | None = None
        self.file: Path | None = None
        self.session: dict | None = None
        self.started: str | None = None
        self.client: ManagedSignalRClient | None = None

    def info(self) -> dict:
        size = 0
        if self.file is not None and self.file.exists():
            size = self.file.stat().st_size
        return {
            "state": self.state,
            "error": self.error,
            "file": str(self.file) if self.file else None,
            "session": self.session,
            "started": self.started,
            "bytes": size,
        }

    def start(self, session: dict) -> dict:
        status = credential_status()
        if not status["has_credentials"]:
            raise LiveError("F1TV access is required before live timing")
        with self._lock:
            if self.state == "capturing":
                raise LiveError("a live capture is already active")
            stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
            self.file = LIVE_DIR / f"live_{stamp}.txt"
            self.session = session
            self.started = datetime.now(UTC).isoformat()
            self.error = None
            self.state = "capturing"
            self.client = ManagedSignalRClient(
                str(self.file),
                filemode="a",
                timeout=CAPTURE_TIMEOUT_S,
                logger=LOG,
            )
            threading.Thread(target=self._run, daemon=True).start()
        return self.info()

    def stop(self) -> dict:
        with self._lock:
            client = self.client
        if client is not None:
            client.stop()
        return self.info()

    def _run(self) -> None:
        try:
            self.client.start()
        except Exception as error:  # noqa: BLE001 - report every capture problem
            LOG.exception("live capture failed")
            with self._lock:
                self.state = "error"
                self.error = str(error)
            return
        if self.state == "capturing":
            with self._lock:
                self.state = "done"
        self._load()

    def _load(self) -> None:
        """Load the captured file into the session manager."""
        from server.session_manager import MANAGER

        if self.file is None or self.session is None:
            return
        try:
            key = MANAGER.key(self.session["year"], self.session["round"], self.session["code"])
            MANAGER.load_livedata(key, self.file)
            LOG.info("live capture loaded: %s", self.file)
        except Exception as error:  # noqa: BLE001 - report the load problem
            LOG.exception("live capture load failed")
            with self._lock:
                self.state = "error"
                self.error = f"the capture did not load: {error}"


CAPTURE = Capture()


def live_status() -> dict:
    """One status object for the app: credentials, capture, and the live window."""
    credentials = credential_status()
    if CAPTURE.state == "capturing":
        reason = "A live capture is in progress."
    elif credentials["has_credentials"]:
        reason = "F1TV access is ready."
    else:
        reason = "Live timing needs F1TV access. Authenticate first."
    return {
        "has_credentials": credentials["has_credentials"],
        "credentials": credentials,
        "capture": CAPTURE.info(),
        "live_window": catalog.live_window(),
        "reason": reason,
    }


__all__ = [
    "AUTH",
    "CAPTURE",
    "LiveError",
    "auth_info",
    "cancel_auth",
    "clear_credentials",
    "credential_status",
    "live_status",
    "start_auth",
]
