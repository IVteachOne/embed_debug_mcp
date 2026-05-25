"""Serial port connection manager with background read thread."""

from __future__ import annotations

import threading
import time

import serial

from .log_buffer import LogBuffer


class SerialConnection:
    """Manages a single serial port connection.

    Opens the port in a background daemon thread that continuously reads
    available data into a LogBuffer.
    """

    def __init__(
        self,
        port: str,
        baudrate: int = 115200,
        bytesize: int = 8,
        parity: str = "N",
        stopbits: float = 1,
        timeout: float = 1,
        rtscts: bool = False,
        xonxoff: bool = False,
    ):
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self._timeout = timeout
        self.rtscts = rtscts
        self.xonxoff = xonxoff

        self.buffer = LogBuffer()
        self._serial: serial.Serial | None = None
        self._read_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_activity = time.monotonic()
        self._error: str | None = None

    def open(self) -> dict:
        """Open serial port and start background read thread."""
        try:
            self._serial = serial.Serial(
                port=self.port,
                baudrate=self.baudrate,
                bytesize=self.bytesize,
                parity=self.parity,
                stopbits=self.stopbits,
                timeout=self._timeout,
                rtscts=self.rtscts,
                xonxoff=self.xonxoff,
            )
            self._stop_event.clear()
            self._read_thread = threading.Thread(
                target=self._read_loop, daemon=True, name=f"serial-read-{self.port}"
            )
            self._read_thread.start()
            self._last_activity = time.monotonic()
            self._error = None
            return {"status": "ok", "port": self.port, "baudrate": self.baudrate}
        except serial.SerialException as e:
            self._error = str(e)
            return {"status": "error", "message": f"Failed to open {self.port}: {e}"}

    def close(self) -> dict:
        """Close serial port and stop read thread."""
        self._stop_event.set()
        if self._read_thread and self._read_thread.is_alive():
            self._read_thread.join(timeout=2)
        if self._serial and self._serial.is_open:
            try:
                self._serial.close()
            except Exception:
                pass
        self._serial = None
        self._read_thread = None
        return {"status": "ok", "port": self.port}

    def write(self, data: str) -> dict:
        """Write data to serial port."""
        if not self._serial or not self._serial.is_open:
            return {"status": "error", "message": "Serial port not open"}
        try:
            if not data.endswith("\n"):
                data += "\n"
            self._serial.write(data.encode("utf-8", errors="replace"))
            self._serial.flush()
            self._last_activity = time.monotonic()
            return {"status": "ok", "bytes_sent": len(data)}
        except serial.SerialException as e:
            return {"status": "error", "message": f"Write failed: {e}"}

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
        return self._serial is not None and self._serial.is_open

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity

    def _read_loop(self) -> None:
        """Background read loop — runs in daemon thread."""
        while not self._stop_event.is_set():
            try:
                if self._serial and self._serial.in_waiting:
                    raw = self._serial.readline()
                    if raw:
                        try:
                            line = raw.decode("utf-8", errors="replace")
                            self.buffer.write(line)
                        except Exception:
                            pass
                    self._last_activity = time.monotonic()
                else:
                    time.sleep(0.01)
            except Exception:
                time.sleep(0.1)
