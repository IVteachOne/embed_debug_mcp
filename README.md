# embed-debug-mcp

MCP Server for embedded device debugging via serial port and SSH. Works with any MCP-compatible client (Claude Code, Cursor, Windsurf, etc.).

## Features

- **Real-time log viewing** — Read serial/SSH output with optional keyword filtering
- **Command execution** — Send commands via serial port or SSH shell
- **Auto-connect** — Connections open on first use, auto-close when idle
- **Device profiles** — Pre-define devices in `devices.yaml` for quick reference
- **Multi-connection** — Multiple serial ports and SSH sessions simultaneously
- **Resource subscription** — Real-time log push via MCP resource subscriptions

## Quick Start

```bash
# Clone / navigate to the project
cd MCP_for_SerialPort_ssh_debug/260525/code

# Install dependencies
uv sync

# Run the MCP server
uv run embed-debug-mcp
```

## Client Configuration

### Claude Code

Add to `~/.claude/settings.json` or project `.claude/settings.json`:

```json
{
  "mcpServers": {
    "embed-debug": {
      "command": "uv",
      "args": ["--directory", "/path/to/MCP_for_SerialPort_ssh_debug/260525/code", "run", "embed-debug-mcp"]
    }
  }
}
```

### Cursor / VS Code

Add to `.vscode/mcp.json`:

```json
{
  "servers": {
    "embed-debug": {
      "command": "uv",
      "args": ["--directory", "${workspaceFolder}/../MCP_for_SerialPort_ssh_debug/260525/code", "run", "embed-debug-mcp"]
    }
  }
}
```

## Device Profiles (Optional)

Copy and edit the example config:

```bash
cp devices.yaml.example devices.yaml
```

```yaml
devices:
  my_board:
    type: serial
    port: /dev/ttyUSB0
    baudrate: 115200
  remote_box:
    type: ssh
    host: 192.168.1.100
    username: root
    key_file: ~/.ssh/id_rsa
```

Start with config:

```bash
uv run embed-debug-mcp --devices devices.yaml
```

## Available Tools

| Tool | Description |
|------|-------------|
| `serial_read` | Read serial log lines (auto-connects) |
| `serial_write` | Send data to serial port |
| `serial_open` | Explicitly open serial port |
| `serial_close` | Close serial port(s) |
| `serial_list` | List available serial ports |
| `ssh_read` | Read SSH shell output (auto-connects) |
| `ssh_exec` | Execute command via SSH |
| `ssh_open` | Explicitly open SSH connection |
| `ssh_close` | Close SSH connection(s) |
| `ssh_list` | List active SSH connections |
| `device_list` | List configured device profiles |
| `device_status` | Show all connection statuses |
| `connection_list` | List all active connections |
| `connection_close_all` | Close all connections |

## Usage Examples

```
# Read serial log (auto-connects)
serial_read(port="/dev/ttyUSB0")

# Watch for kernel panics
serial_read(port="/dev/ttyUSB0", filter="panic|oops|BUG")

# Send a debug command
serial_write(port="/dev/ttyUSB0", data="cat /proc/meminfo")

# SSH to a device and run commands
ssh_exec(host="192.168.1.100", username="root", command="dmesg | tail -20")
ssh_read(host="192.168.1.100", lines=30)

# Use device profile (if configured)
serial_read(device="my_board")
ssh_exec(device="remote_box", command="uptime")
```

## CLI Options

```
--devices PATH      Path to devices.yaml config file
--idle-timeout SEC  Auto-close idle connections after N seconds (default: 300)
```

## Architecture

See [embed_debug_tool_design.md](./embed_debug_tool_design.md) for full design documentation.
