"""Load FastF1 sessions in the background. Track the state of each session."""

from __future__ import annotations

import logging
import threading

import fastf1

from server.config import CACHE_DIR

LOG = logging.getLogger(__name__)
fastf1.Cache.enable_cache(str(CACHE_DIR))

STATE_ABSENT = "absent"
STATE_LOADING = "loading"
STATE_READY = "ready"
STATE_ERROR = "error"


class SessionNotReadyError(Exception):
    """The session is not ready for analysis yet."""

    def __init__(self, key: tuple, state: str, error: str | None = None):
        self.key = key
        self.state = state
        self.error = error
        message = f"session {key} is {state}"
        if error:
            message = f"{message}: {error}"
        super().__init__(message)


class SessionManager:
    """Keep one loaded session for each (year, round, code) key."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: dict[tuple, dict] = {}

    @staticmethod
    def key(year: int, round_number: int, session_code: str) -> tuple:
        return (int(year), int(round_number), str(session_code).upper())

    def status(self, key: tuple) -> dict:
        entry = self._entries.get(key)
        if entry is None:
            return {"state": STATE_ABSENT, "error": None}
        return {"state": entry["state"], "error": entry["error"]}

    def prepare(self, key: tuple) -> dict:
        """Start a background load if necessary. Return the current status."""
        with self._lock:
            entry = self._entries.get(key)
            if entry is None or entry["state"] == STATE_ERROR:
                self._entries[key] = {"state": STATE_LOADING, "error": None, "session": None}
                thread = threading.Thread(target=self._load, args=(key,), daemon=True)
                thread.start()
            return self.status(key)

    def get(self, key: tuple):
        """Return the loaded session if ready. Return None otherwise."""
        entry = self._entries.get(key)
        if entry is None or entry["state"] != STATE_READY:
            return None
        return entry["session"]

    def require(self, key: tuple):
        """Return the loaded session. Raise SessionNotReadyError otherwise."""
        entry = self._entries.get(key)
        if entry is None:
            raise SessionNotReadyError(key, STATE_ABSENT)
        if entry["state"] != STATE_READY:
            raise SessionNotReadyError(key, entry["state"], entry["error"])
        return entry["session"]

    def _load(self, key: tuple) -> None:
        year, round_number, code = key
        LOG.info("loading session %s", key)
        try:
            session = fastf1.get_session(year, round_number, code)
            session.load(telemetry=True, weather=False, messages=False)
        except Exception as exc:  # noqa: BLE001 - report every load error to the UI
            LOG.exception("session load failed: %s", key)
            with self._lock:
                self._entries[key] = {"state": STATE_ERROR, "error": str(exc), "session": None}
            return
        with self._lock:
            self._entries[key] = {"state": STATE_READY, "error": None, "session": session}
        LOG.info("session ready %s", key)


MANAGER = SessionManager()
