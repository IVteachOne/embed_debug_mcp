"""SSH connection manager with background read thread."""

from __future__ import annotations

import threading
import time

import paramiko

from .log_buffer import LogBuffer


class SSHConnection:
    """Manages a single SSH connection with interactive shell channel.

    Opens an interactive shell via paramiko and reads output into a LogBuffer
    in a background daemon thread.
    """

    def __init__(
        self,
        host: str,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_file: str | None = None,
        key_password: str | None = None,
        timeout: float = 10,
    ):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.key_file = key_file
        self.key_password = key_password
        self._timeout = timeout

        self.buffer = LogBuffer()
        self._client: paramiko.SSHClient | None = None
        self._channel: paramiko.Channel | None = None
        self._read_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_activity = time.monotonic()
        self._error: str | None = None

    def open(self) -> dict:
        """Connect to host and open interactive shell channel."""
        try:
            self._client = paramiko.SSHClient()
            self._client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

            connect_kwargs: dict = {
                "hostname": self.host,
                "port": self.port,
                "username": self.username,
                "timeout": self._timeout,
                "allow_agent": True,
                "look_for_keys": True,
            }

            if self.password:
                connect_kwargs["password"] = self.password
            if self.key_file:
                connect_kwargs["key_filename"] = self.key_file
                if self.key_password:
                    connect_kwargs["passphrase"] = self.key_password

            self._client.connect(**connect_kwargs)
            self._channel = self._client.invoke_shell(term="vt100", width=200, height=50)
            self._channel.settimeout(0.5)

            self._stop_event.clear()
            self._read_thread = threading.Thread(
                target=self._read_loop, daemon=True, name=f"ssh-read-{self.host}"
            )
            self._read_thread.start()
            self._last_activity = time.monotonic()
            self._error = None
            return {"status": "ok", "host": self.host, "port": self.port}
        except paramiko.AuthenticationException as e:
            self._error = f"Authentication failed for {self.username}@{self.host}"
            return {"status": "error", "message": self._error}
        except Exception as e:
            self._error = str(e)
            return {"status": "error", "message": f"SSH connect failed: {e}"}

    def close(self) -> dict:
        """Close shell channel and SSH connection."""
        self._stop_event.set()
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2)
        if self._channel:
            try:
                self._channel.close()
            except Exception:
                pass
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
        self._channel = None
        self._client = None
        self._read_thread = None
        return {"status": "ok", "host": self.host}

    def exec(self, command: str) -> dict:
        """Send a command via interactive shell channel."""
        if not self._channel or not self._channel.active:
            return {"status": "error", "message": "SSH channel not open"}
        try:
            if not command.endswith("\n"):
                command += "\n"
            self._channel.send(command)
            self._last_activity = time.monotonic()
            return {"status": "ok", "command": command.rstrip()}
        except Exception as e:
            return {"status": "error", "message": f"Command send failed: {e}"}

    def read(
        self, lines: int = 50, filter: str | None = None, since: float | None = None
    ) -> dict:
        """Read latest lines from buffer."""
        entries = self.buffer.get_lines(n=lines, filter=filter, since_timestamp=since)
        self._last_activity = time.monotonic()
        return {
            "status": "ok",
            "lines": [txt for _, txt in entries],
            "total_available": self.buffer.line_count,
        }

    def is_open(self) -> bool:
        return (
            self._client is not None
            and self._channel is not None
            and self._channel.active
        )

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity

    def _read_loop(self) -> None:
        """Background read loop — runs in daemon thread."""
        partial_line = ""
        while not self._stop_event.is_set():
            try:
                if self._channel and self._channel.recv_ready():
                    data = self._channel.recv(4096).decode("utf-8", errors="replace")
                    if data:
                        # Split into lines, handle partial lines across chunks
                        full = partial_line + data
                        parts = full.split("\n")
                        partial_line = parts[-1]
                        for line in parts[:-1]:
                            self.buffer.write(line)
                        self._last_activity = time.monotonic()
                    time.sleep(0.01)
                else:
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.1)
        # Flush remaining partial line
        if partial_line:
            self.buffer.write(partial_line)
