"""FastMCP server entry point for embed-debug-mcp.

Registers all serial/SSH/device/connection tools and resources.
"""

from __future__ import annotations

import argparse
import sys

from fastmcp import FastMCP

from .connection_pool import get_pool
from .device_config import DeviceConfig
from .filters import DEFAULT_PATTERNS

# Initialize lazily so CLI args can configure before tools run
_pool = None
_device_config: DeviceConfig | None = None


def _pool():
    global _pool
    if _pool is None:
        _pool = get_pool()
    return _pool


def _devices():
    global _device_config
    if _device_config is None:
        _device_config = DeviceConfig()
    return _device_config


def _resolve_device(device: str | None, conn_type: str) -> dict:
    """Resolve device name to connection params, or return direct params."""
    if device:
        profile = _devices().get(device)
        if profile is None:
            raise ValueError(f"Device '{device}' not found in devices.yaml")
        if profile.type != conn_type:
            raise ValueError(
                f"Device '{device}' is type '{profile.type}', expected '{conn_type}'"
            )
        return _devices().to_open_kwargs(profile)
    return {}


def create_server() -> FastMCP:
    mcp = FastMCP("embed-debug-mcp")

    # ── Serial Tools ──────────────────────────────────────────────

    @mcp.tool()
    def serial_read(
        device: str | None = None,
        port: str | None = None,
        baudrate: int = 115200,
        lines: int = 50,
        filter: str | None = None,
        auto_connect: bool = True,
    ) -> dict:
        """Read serial log lines. Auto-connects if needed."""
        try:
            dev_kwargs = _resolve_device(device, "serial")
            if port:
                dev_kwargs["port"] = port
            if not dev_kwargs.get("port"):
                return {"status": "error", "message": "Must specify port or device name"}

            p = dev_kwargs["port"]
            b = dev_kwargs.get("baudrate", baudrate)
            conn = _pool().get_or_open_serial(
                port=p, baudrate=b, auto_connect=auto_connect
            )
            return conn.read(lines=lines, filter=filter)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def serial_write(
        device: str | None = None,
        port: str | None = None,
        baudrate: int = 115200,
        data: str = "",
        auto_connect: bool = True,
    ) -> dict:
        """Write data to serial port. Auto-connects if needed."""
        try:
            dev_kwargs = _resolve_device(device, "serial")
            if port:
                dev_kwargs["port"] = port
            if not dev_kwargs.get("port"):
                return {"status": "error", "message": "Must specify port or device name"}

            p = dev_kwargs["port"]
            b = dev_kwargs.get("baudrate", baudrate)
            conn = _pool().get_or_open_serial(
                port=p, baudrate=b, auto_connect=auto_connect
            )
            return conn.write(data)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def serial_open(
        device: str | None = None,
        port: str = "",
        baudrate: int = 115200,
    ) -> dict:
        """Explicitly open a serial port connection."""
        try:
            dev_kwargs = _resolve_device(device, "serial")
            if port:
                dev_kwargs["port"] = port
            if not dev_kwargs.get("port"):
                return {"status": "error", "message": "Must specify port or device name"}

            p = dev_kwargs["port"]
            b = dev_kwargs.get("baudrate", baudrate)
            conn = _pool().get_or_open_serial(port=p, baudrate=b, auto_connect=True)
            return {"status": "ok", "port": conn.port, "baudrate": conn.baudrate}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def serial_close(port: str | None = None) -> dict:
        """Close serial connection(s). No port = close all serial connections."""
        try:
            if port:
                return _pool().close(f"serial:{port}")
            else:
                closed = _pool().close_all()
                serial_closed = [k for k in closed if k.startswith("serial:")]
                return {"status": "ok", "closed": serial_closed}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def serial_list() -> dict:
        """List available serial ports on the system."""
        try:
            import serial.tools.list_ports

            ports = serial.tools.list_ports.comports()
            return {
                "status": "ok",
                "ports": [
                    {"device": p.device, "description": p.description, "hwid": p.hwid}
                    for p in ports
                ],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── SSH Tools ─────────────────────────────────────────────────

    @mcp.tool()
    def ssh_read(
        device: str | None = None,
        host: str | None = None,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_file: str | None = None,
        lines: int = 50,
        filter: str | None = None,
        auto_connect: bool = True,
    ) -> dict:
        """Read SSH shell output. Auto-connects if needed."""
        try:
            dev_kwargs = _resolve_device(device, "ssh")
            if host:
                dev_kwargs["host"] = host
            if not dev_kwargs.get("host"):
                return {"status": "error", "message": "Must specify host or device name"}

            h = dev_kwargs["host"]
            kwargs = {
                "port": dev_kwargs.get("port", port),
                "username": dev_kwargs.get("username", username),
            }
            if "password" in dev_kwargs:
                kwargs["password"] = dev_kwargs["password"]
            elif password:
                kwargs["password"] = password
            if "key_file" in dev_kwargs:
                kwargs["key_file"] = dev_kwargs["key_file"]
            elif key_file:
                kwargs["key_file"] = key_file

            conn = _pool().get_or_open_ssh(host=h, auto_connect=auto_connect, **kwargs)
            return conn.read(lines=lines, filter=filter)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def ssh_exec(
        device: str | None = None,
        host: str | None = None,
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_file: str | None = None,
        command: str = "",
        auto_connect: bool = True,
    ) -> dict:
        """Execute a command via SSH shell. Output goes to buffer."""
        try:
            dev_kwargs = _resolve_device(device, "ssh")
            if host:
                dev_kwargs["host"] = host
            if not dev_kwargs.get("host"):
                return {"status": "error", "message": "Must specify host or device name"}

            h = dev_kwargs["host"]
            kwargs = {
                "port": dev_kwargs.get("port", port),
                "username": dev_kwargs.get("username", username),
            }
            if "password" in dev_kwargs:
                kwargs["password"] = dev_kwargs["password"]
            elif password:
                kwargs["password"] = password
            if "key_file" in dev_kwargs:
                kwargs["key_file"] = dev_kwargs["key_file"]
            elif key_file:
                kwargs["key_file"] = key_file

            conn = _pool().get_or_open_ssh(host=h, auto_connect=auto_connect, **kwargs)
            return conn.exec(command)
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def ssh_open(
        device: str | None = None,
        host: str = "",
        port: int = 22,
        username: str = "root",
        password: str | None = None,
        key_file: str | None = None,
    ) -> dict:
        """Explicitly open an SSH connection."""
        try:
            dev_kwargs = _resolve_device(device, "ssh")
            if host:
                dev_kwargs["host"] = host
            if not dev_kwargs.get("host"):
                return {"status": "error", "message": "Must specify host or device name"}

            h = dev_kwargs["host"]
            kwargs = {
                "port": dev_kwargs.get("port", port),
                "username": dev_kwargs.get("username", username),
            }
            if "password" in dev_kwargs:
                kwargs["password"] = dev_kwargs["password"]
            elif password:
                kwargs["password"] = password
            if "key_file" in dev_kwargs:
                kwargs["key_file"] = dev_kwargs["key_file"]
            elif key_file:
                kwargs["key_file"] = key_file

            conn = _pool().get_or_open_ssh(host=h, auto_connect=True, **kwargs)
            return {"status": "ok", "host": conn.host, "port": conn.port}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def ssh_close(host: str | None = None) -> dict:
        """Close SSH connection(s). No host = close all SSH connections."""
        try:
            if host:
                return _pool().close(f"ssh:{host}")
            else:
                closed = _pool().close_all()
                ssh_closed = [k for k in closed if k.startswith("ssh:")]
                return {"status": "ok", "closed": ssh_closed}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def ssh_list() -> dict:
        """List active SSH connections."""
        try:
            conns = _pool().list_connections()
            ssh_conns = [c for c in conns if c["type"] == "ssh"]
            return {"status": "ok", "connections": ssh_conns}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── Device Tools ──────────────────────────────────────────────

    @mcp.tool()
    def device_list() -> dict:
        """List configured device profiles from devices.yaml."""
        try:
            devices = _devices().list_all()
            return {
                "status": "ok",
                "devices": [
                    {
                        "name": d.name,
                        "type": d.type,
                        "config": {
                            "port": d.port,
                            "baudrate": d.baudrate,
                            "host": d.host,
                            "ssh_port": d.ssh_port,
                            "username": d.username,
                        }
                        if d.type == "serial"
                        else {
                            "host": d.host,
                            "ssh_port": d.ssh_port,
                            "username": d.username,
                            "key_file": d.key_file,
                        },
                    }
                    for d in devices
                ],
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def device_status() -> dict:
        """Show connection status for all active connections."""
        try:
            conns = _pool().list_connections()
            return {"status": "ok", "devices": conns}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── Connection Management ─────────────────────────────────────

    @mcp.tool()
    def connection_list() -> dict:
        """List all active connections (serial + SSH)."""
        try:
            conns = _pool().list_connections()
            return {"status": "ok", "connections": conns}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    @mcp.tool()
    def connection_close_all() -> dict:
        """Close all connections and flush logs."""
        try:
            closed = _pool().close_all()
            return {"status": "ok", "closed": closed}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # ── Resources ─────────────────────────────────────────────────

    @mcp.resource("serial://{port}/log")
    def serial_log_resource(port: str) -> str:
        """Real-time serial log stream for subscription."""
        try:
            conn = _pool().get_or_open_serial(port=port, auto_connect=True)
            entries = conn.buffer.get_lines(n=100)
            return "\n".join(txt for _, txt in entries)
        except Exception as e:
            return f"Error: {e}"

    @mcp.resource("ssh://{host}/shell")
    def ssh_shell_resource(host: str) -> str:
        """Real-time SSH shell output stream for subscription."""
        try:
            conn = _pool().get_or_open_ssh(host=host, auto_connect=True)
            entries = conn.buffer.get_lines(n=100)
            return "\n".join(txt for _, txt in entries)
        except Exception as e:
            return f"Error: {e}"

    return mcp


def main():
    parser = argparse.ArgumentParser(description="Embed Debug MCP Server")
    parser.add_argument(
        "--devices",
        type=str,
        default=None,
        help="Path to devices.yaml config file",
    )
    parser.add_argument(
        "--idle-timeout",
        type=float,
        default=300,
        help="Idle timeout in seconds before auto-closing connections (default: 300)",
    )
    parser.add_argument(
        "--transport",
        type=str,
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode: stdio (default, for local) or sse (for remote)",
    )
    parser.add_argument(
        "--host",
        type=str,
        default="127.0.0.1",
        help="Host to bind (only for sse transport, default: 127.0.0.1)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8765,
        help="Port to listen on (only for sse transport, default: 8765)",
    )
    args = parser.parse_args()

    # Initialize device config from CLI args
    global _device_config, _pool
    if args.devices:
        _device_config = DeviceConfig(args.devices)

    # Initialize pool with custom timeout
    _pool = get_pool(idle_timeout=args.idle_timeout)

    server = create_server()

    if args.transport == "sse":
        server.run(transport="sse", host=args.host, port=args.port)
    else:
        server.run()


if __name__ == "__main__":
    main()
