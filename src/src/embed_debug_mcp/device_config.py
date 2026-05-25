"""Device profile configuration loader from YAML."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class DeviceProfile:
    name: str
    type: str  # "serial" | "ssh"
    # Serial fields
    port: str | None = None
    baudrate: int = 115200
    # SSH fields
    host: str | None = None
    ssh_port: int = 22
    username: str = "root"
    password: str | None = None
    key_file: str | None = None


class DeviceConfig:
    """Load and manage device profiles from YAML."""

    def __init__(self, config_path: str | None = None):
        self._profiles: dict[str, DeviceProfile] = {}
        if config_path:
            self.load(config_path)

    def load(self, path: str) -> None:
        p = Path(path).expanduser()
        if not p.exists():
            return
        with open(p) as f:
            data = yaml.safe_load(f)
        if not data or "devices" not in data:
            return
        for name, cfg in data["devices"].items():
            self._profiles[name] = DeviceProfile(name=name, **cfg)

    def get(self, name: str) -> DeviceProfile | None:
        return self._profiles.get(name)

    def list_all(self) -> list[DeviceProfile]:
        return list(self._profiles.values())

    def to_open_kwargs(self, profile: DeviceProfile) -> dict[str, Any]:
        """Convert a profile to kwargs for ConnectionPool open calls."""
        if profile.type == "serial":
            return {
                "port": profile.port,
                "baudrate": profile.baudrate,
            }
        else:
            kwargs: dict[str, Any] = {
                "host": profile.host,
                "port": profile.ssh_port,
                "username": profile.username,
            }
            if profile.password:
                kwargs["password"] = profile.password
            if profile.key_file:
                kwargs["key_file"] = profile.key_file
            return kwargs
