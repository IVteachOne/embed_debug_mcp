"""Thread-safe circular log buffer with filtering and subscription support."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from typing import Callable


class LogBuffer:
    """Thread-safe circular log buffer.

    Each line is stored as (timestamp, text) tuple.
    Supports regex filtering and subscriber callbacks for real-time push.
    """

    def __init__(self, max_lines: int = 10000):
        self._buffer: deque[tuple[float, str]] = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._subscribers: dict[str, Callable[[str], None]] = {}
        self._filter_patterns: list[re.Pattern] = []
        self._next_id = 0

    def write(self, line: str) -> None:
        """Append a line and notify subscribers."""
        if not line:
            return
        ts = time.time()
        with self._lock:
            self._buffer.append((ts, line))
            subs = list(self._subscribers.values())
        for cb in subs:
            if self._matches_filter(line):
                try:
                    cb(line.rstrip("\n\r"))
                except Exception:
                    pass

    def get_lines(
        self,
        n: int = 50,
        filter: str | None = None,
        since_timestamp: float | None = None,
    ) -> list[tuple[float, str]]:
        """Return up to n lines, optionally filtered."""
        with self._lock:
            lines = list(self._buffer)

        if since_timestamp is not None:
            lines = [(ts, txt) for ts, txt in lines if ts > since_timestamp]

        if filter:
            try:
                pat = re.compile(filter, re.IGNORECASE)
                lines = [(ts, txt) for ts, txt in lines if pat.search(txt)]
            except re.error:
                pass

        return lines[-n:]

    def subscribe(self, callback: Callable[[str], None]) -> str:
        """Register a subscriber. Returns subscription ID."""
        with self._lock:
            sub_id = f"sub_{self._next_id}"
            self._next_id += 1
            self._subscribers[sub_id] = callback
        return sub_id

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscriber."""
        with self._lock:
            self._subscribers.pop(subscription_id, None)

    def set_filter(self, patterns: list[str]) -> None:
        """Set regex patterns for subscriber filtering."""
        self._filter_patterns = [
            re.compile(p, re.IGNORECASE) for p in patterns
        ]

    def _matches_filter(self, line: str) -> bool:
        if not self._filter_patterns:
            return True
        return any(p.search(line) for p in self._filter_patterns)

    @property
    def line_count(self) -> int:
        with self._lock:
            return len(self._buffer)

    def clear(self) -> None:
        with self._lock:
            self._buffer.clear()
