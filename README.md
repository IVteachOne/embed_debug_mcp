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

## Remote SSE Deployment (跨机器使用)

当 MCP Server 运行在一台机器上（如 Windows 接串口），Client 在另一台机器上（如 Ubuntu 写代码）时，使用 SSE transport。

### 架构图

```
Ubuntu (写代码)                     Windows (接设备)
┌──────────────────┐                ┌────────────────────┐
│  Claude Code     │                │  embed-debug-mcp   │
│                  │   HTTP SSE     │  --transport sse   │
│  settings.json:  │   over LAN     │  --host 0.0.0.0    │
│    "url": "http://│──────────────►│  --port 8765       │
│     192.168.1.50 │   :8765/sse   │  pyserial → COM3   │
│     :8765/sse"   │                │  paramiko → SSH    │
└──────────────────┘                └────────────────────┘
```

### Server 端（Windows）

```powershell
# 1. 安装依赖
cd embed_debug_mcp/src
uv sync

# 2. 查看本机 IP
ipconfig
# 假设得到 192.168.1.50

# 3. 启动 SSE 模式（监听所有网卡）
uv run embed-debug-mcp --transport sse --host 0.0.0.0 --port 8765

# 4. 可选：同时加载设备配置
uv run embed-debug-mcp --transport sse --host 0.0.0.0 --port 8765 --devices devices.yaml
```

### Windows 防火墙放行

```powershell
# 以管理员权限运行
New-NetFirewallRule -DisplayName "Embed Debug MCP" -Direction Inbound -LocalPort 8765 -Protocol TCP -Action Allow
```

### Client 端（Ubuntu）

Claude Code `~/.claude/settings.json`：

```json
{
  "mcpServers": {
    "embed-debug": {
      "url": "http://192.168.1.50:8765/sse"
    }
  }
}
```

Cursor `.vscode/mcp.json`：

```json
{
  "servers": {
    "embed-debug": {
      "url": "http://192.168.1.50:8765/sse"
    }
  }
}
```

### 安全注意

- SSE 模式默认**无认证**，仅限受信任的内网环境
- 如需认证，建议部署在 Nginx/反向代理后面加 Bearer Token
- 或使用 Tailscale/ZeroTier 等 VPN 方案，不暴露到公网

## CLI Options

```
--devices PATH      Path to devices.yaml config file
--idle-timeout SEC  Auto-close idle connections after N seconds (default: 300)
--transport MODE    Transport: "stdio" (default, local) or "sse" (remote)
--host ADDR         Host to bind (only for sse, default: 127.0.0.1)
--port PORT         Port to listen (only for sse, default: 8765)
```

## Architecture

See [embed_debug_tool_design.md](./embed_debug_tool_design.md) for full design documentation.
