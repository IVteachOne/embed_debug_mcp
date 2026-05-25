"""Global connection pool with auto-connect and idle timeout cleanup."""

from __future__ import annotations

import threading
import time
from typing import Any

from .serial_conn import SerialConnection
from .ssh_conn import SSHConnection


class ConnectionPool:
    """Manages all active serial and SSH connections.

    Supports auto-connect on first use and automatic cleanup of idle connections.
    """

    def __init__(self, idle_timeout: float = 300):
        self._connections: dict[str, SerialConnection | SSHConnection] = {}
        self._lock = threading.Lock()
        self._idle_timeout = idle_timeout
        self._cleanup_thread = self._start_cleanup_thread()

    def get_or_open_serial(
        self,
        port: str,
        auto_connect: bool = True,
        **kwargs: Any,
    ) -> SerialConnection:
        """Get existing or auto-open serial connection."""
        key = self._make_key("serial", port)
        with self._lock:
            conn = self._connections.get(key)
            if conn and isinstance(conn, SerialConnection) and conn.is_open():
                conn.update_activity()
                return conn

        if auto_connect:
            conn = SerialConnection(port=port, **kwargs)
            result = conn.open()
            if result["status"] != "ok":
                raise RuntimeError(result.get("message", "Unknown error"))
            with self._lock:
                self._connections[key] = conn
            return conn

        raise RuntimeError(f"No active connection for {key}")

    def get_or_open_ssh(
        self,
        host: str,
        auto_connect: bool = True,
        **kwargs: Any,
    ) -> SSHConnection:
        """Get existing or auto-open SSH connection."""
        key = self._make_key("ssh", host)
        with self._lock:
            conn = self._connections.get(key)
            if conn and isinstance(conn, SSHConnection) and conn.is_open():
                conn.update_activity()
                return conn

        if auto_connect:
            conn = SSHConnection(host=host, **kwargs)
            result = conn.open()
            if result["status"] != "ok":
                raise RuntimeError(result.get("message", "Unknown error"))
            with self._lock:
                self._connections[key] = conn
            return conn

        raise RuntimeError(f"No active connection for {key}")

    def close(self, key: str) -> dict:
        """Close a specific connection."""
        with self._lock:
            conn = self._connections.pop(key, None)
        if conn:
            return conn.close()
        return {"status": "error", "message": f"No connection: {key}"}

    def close_all(self) -> list[str]:
        """Close all connections. Return list of closed keys."""
        closed = []
        with self._lock:
            keys = list(self._connections.keys())
            conns = list(self._connections.values())
            self._connections.clear()
        for key, conn in zip(keys, conns):
            conn.close()
            closed.append(key)
        return closed

    def list_connections(self) -> list[dict]:
        """List all active connections with status."""
        with self._lock:
            result = []
            for key, conn in self._connections.items():
                conn_type = "serial" if isinstance(conn, SerialConnection) else "ssh"
                identifier = conn.port if isinstance(conn, SerialConnection) else conn.host
                result.append({
                    "key": key,
                    "type": conn_type,
                    "identifier": identifier,
                    "connected": conn.is_open(),
                    "idle_seconds": round(conn.idle_seconds, 1),
                    "buffer_lines": conn.buffer.line_count,
                })
            return result

    def cleanup_idle(self) -> list[str]:
        """Close connections idle longer than timeout."""
        to_close = []
        with self._lock:
            for key, conn in self._connections.items():
                if conn.idle_seconds > self._idle_timeout:
                    to_close.append(key)
            for key in to_close:
                conn = self._connections.pop(key)
                # Flush last buffer lines before closing
                conn.close()
        return to_close

    def _make_key(self, conn_type: str, identifier: str) -> str:
        return f"{conn_type}:{identifier}"

    def _start_cleanup_thread(self) -> threading.Thread:
        """Daemon thread that periodically cleans up idle connections."""
        def loop():
            while True:
                time.sleep(60)
                try:
                    self.cleanup_idle()
                except Exception:
                    pass

        t = threading.Thread(target=loop, daemon=True, name="conn-pool-cleanup")
        t.start()
        return t


# Global singleton
_pool: ConnectionPool | None = None


def get_pool(idle_timeout: float = 300) -> ConnectionPool:
    """Get or create the global connection pool."""
    global _pool
    if _pool is None:
        _pool = ConnectionPool(idle_timeout=idle_timeout)
    return _pool
