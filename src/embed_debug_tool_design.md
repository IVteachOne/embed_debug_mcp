# Embed Debug MCP Tool — 设计文档

## 1. 概述

### 1.1 目标

为嵌入式开发调试场景提供一个通用的 MCP Server，使任何支持 MCP 协议的 AI Agent（Claude Code、Cursor、Windsurf 等）能够：

- 实时查看串口或 SSH 连接上的嵌入式设备调试日志
- 通过串口或 SSH 向设备发送调试命令
- 自动管理连接生命周期，降低使用门槛

### 1.2 设计原则

- **MCP 协议原生**：纯 MCP 协议实现，不依赖任何特定 Agent 的私有扩展
- **auto_connect 优先**：Agent 无需显式打开连接，首次读写时自动建立
- **双模式日志获取**：Tool polling（兼容所有客户端）+ Resource subscription（低延迟推送）
- **服务端过滤**：buffer 层做关键词匹配，减少推送给 Agent 的 log 量和 token 成本
- **多连接并发**：支持同时打开多个串口和 SSH 连接，互不干扰

## 2. 架构

```
┌─────────────────────────────────────────────────────────┐
│                    Any MCP Client                        │
│   (Claude Code / Cursor / Windsurf / Custom Agent)       │
└──────────────────────┬──────────────────────────────────┘
                       │  MCP Protocol (stdio/SSE)
                       ▼
┌──────────────────────────────────────────────────────────┐
│              Embed Debug MCP Server                       │
│                    (Python / FastMCP)                      │
│                                                          │
│  ┌────────────┐  ┌────────────┐  ┌────────────────────┐  │
│  │   Tools    │  │ Resources  │  │   Connection Pool  │  │
│  │            │  │            │  │                    │  │
│  │ serial_*   │  │ serial://  │  │  SerialConnection  │  │
│  │ ssh_*      │  │ ssh://     │  │  SSHConnection     │  │
│  │ device_*   │  │            │  │                    │  │
│  └─────┬──────┘  └─────┬──────┘  └────────┬───────────┘  │
│        │               │                   │              │
│        ▼               ▼                   ▼              │
│  ┌───────────────────────────────────────────────────┐   │
│  │               LogBuffer (per connection)           │   │
│  │  - collections.deque (thread-safe)                │   │
│  │  - get_lines(n, filter=None)                      │   │
│  │  - subscription callbacks for resource push       │   │
│  └───────────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────────┘
                       ▼
            ┌──────────┴──────────┐
            ▼                     ▼
     ┌──────────────┐      ┌──────────────┐
     │   pyserial   │      │   paramiko   │
     │ (serial port)│      │  (SSH client)│
     └──────┬───────┘      └──────┬───────┘
            ▼                     ▼
       /dev/ttyUSB0        192.168.1.100:22
     (Embedded Board)     (Embedded Device)
```

## 3. 项目结构

```
MCP_for_SerialPort_ssh_debug/
├── pyproject.toml              # Python 项目配置
├── uv.lock                     # 锁定依赖版本
├── devices.yaml                # 设备 profile 配置（可选）
├── src/
│   └── embed_debug_mcp/
│       ├── __init__.py
│       ├── __main__.py         # python -m embed_debug_mcp 入口
│       ├── main.py             # FastMCP Server 入口
│       ├── log_buffer.py       # 通用环形日志缓冲区
│       ├── serial_conn.py      # 串口连接管理
│       ├── ssh_conn.py         # SSH 连接管理
│       ├── connection_pool.py  # 全局连接池管理
│       ├── device_config.py    # 设备 profile 配置加载
│       └── filters.py          # 日志关键词过滤器
└── README.md                   # 使用说明
```

## 4. 核心模块设计

### 4.1 LogBuffer (`log_buffer.py`)

基于 `collections.deque` 的线程安全环形日志缓冲区。

```python
class LogBuffer:
    """Thread-safe circular log buffer with filtering and subscription."""

    def __init__(self, max_lines: int = 10000):
        self._buffer: deque[str] = deque(maxlen=max_lines)
        self._lock = threading.Lock()
        self._subscribers: list[Callable[[str], None]] = []
        self._filter_patterns: list[re.Pattern] = []

    def write(self, line: str) -> None:
        """Append a line to the buffer, notify subscribers."""

    def get_lines(
        self,
        n: int = 50,
        filter: str | None = None,
        since_timestamp: float | None = None,
    ) -> list[tuple[float, str]]:
        """Return up to n lines, optionally filtered by regex pattern."""

    def subscribe(self, callback: Callable[[str], None]) -> str:
        """Register a subscriber callback. Returns subscription ID."""

    def unsubscribe(self, subscription_id: str) -> None:
        """Remove a subscriber by ID."""

    def set_filter(self, patterns: list[str]) -> None:
        """Set regex patterns for filtering. Empty = no filter."""

    def line_count(self) -> int:
        """Current number of lines in buffer."""
```

**关键设计：**
- `max_lines=10000`：最多保留 10000 行，自动淘汰最旧数据
- 每行带时间戳 `(float, str)` tuple，支持增量读取（`since_timestamp`）
- `subscribe/unsubscribe` 实现 MCP resource subscription 回调机制
- `set_filter` 在服务端做正则过滤，减少无效数据推送

### 4.2 SerialConnection (`serial_conn.py`)

封装 `pyserial`，后台线程持续读取到 `LogBuffer`。

```python
class SerialConnection:
    """Manages a single serial port connection."""

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
        self.buffer = LogBuffer()
        self._serial: serial.Serial | None = None
        self._read_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_activity = time.monotonic()

    def open(self) -> dict:
        """Open serial port. Returns {"status": "ok"|"error", ...}."""

    def close(self) -> dict:
        """Close serial port and stop read thread."""

    def write(self, data: str) -> dict:
        """Write data to serial port. Appends \n if not present."""

    def read(self, lines: int = 50, filter: str | None = None) -> dict:
        """Read latest lines from buffer."""

    def is_open(self) -> bool:
        """Check if port is open and thread is running."""

    # Background read loop (runs in daemon thread)
    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._serial.in_waiting:
                line = self._serial.readline().decode(...)
                self.buffer.write(line)
                self._last_activity = time.monotonic()
            time.sleep(0.01)  # 10ms poll, low CPU

    def update_activity(self) -> None:
        """Reset idle timer (called on write/read)."""
        self._last_activity = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity
```

**关键设计：**
- 后台 daemon 线程以 10ms 间隔轮询 `in_waiting`，CPU 占用极低
- `_last_activity` 跟踪最后一次操作时间，用于空闲超时自动关闭
- `write` 自动追加 `\n`（除非数据已包含），方便 agent 发送命令

### 4.3 SSHConnection (`ssh_conn.py`)

封装 `paramiko`，通过交互式 shell channel 读取输出。

```python
class SSHConnection:
    """Manages a single SSH connection."""

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
        self.buffer = LogBuffer()
        self._client: paramiko.SSHClient | None = None
        self._channel: paramiko.Channel | None = None
        self._read_thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._last_activity = time.monotonic()

    def open(self) -> dict:
        """Connect and open interactive shell channel."""

    def close(self) -> dict:
        """Close shell channel and SSH connection."""

    def exec(self, command: str) -> dict:
        """Execute a command via shell channel. Output goes to buffer."""

    def read(self, lines: int = 50, filter: str | None = None) -> dict:
        """Read latest lines from buffer."""

    def is_open(self) -> bool:

    def _read_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._channel.recv_ready():
                data = self._channel.recv(4096).decode(...)
                for line in data.splitlines(True):
                    self.buffer.write(line)
                self._last_activity = time.monotonic()
            time.sleep(0.01)

    def update_activity(self) -> None:
        self._last_activity = time.monotonic()

    @property
    def idle_seconds(self) -> float:
        return time.monotonic() - self._last_activity
```

**关键设计：**
- 使用 `invoke_shell()` 打开交互式 channel（不是 `exec_command`），保持长连接
- `exec()` 通过 channel `send()` 发送命令 + `\n`，输出自动进入 buffer
- 认证支持 password 和 key_file 两种方式

### 4.4 ConnectionPool (`connection_pool.py`)

全局连接池，管理所有串口和 SSH 连接。

```python
class ConnectionPool:
    """Global connection pool with auto-connect and idle timeout."""

    def __init__(self, idle_timeout: float = 300):  # 5 minutes
        self._connections: dict[str, SerialConnection | SSHConnection] = {}
        self._lock = threading.Lock()
        self._idle_timeout = idle_timeout
        self._cleanup_thread = self._start_cleanup_thread()

    def get_or_open_serial(
        self, port: str, auto_connect: bool = True, **kwargs
    ) -> SerialConnection:
        """Get existing or auto-open serial connection."""

    def get_or_open_ssh(
        self, host: str, auto_connect: bool = True, **kwargs
    ) -> SSHConnection:
        """Get existing or auto-open SSH connection."""

    def close(self, key: str) -> dict:
        """Close a specific connection."""

    def list_connections(self) -> list[dict]:
        """List all active connections with status."""

    def cleanup_idle(self) -> list[str]:
        """Close connections idle longer than timeout. Return closed keys."""

    def _make_key(self, conn_type: str, identifier: str) -> str:
        return f"{conn_type}:{identifier}"

    def _start_cleanup_thread(self) -> threading.Thread:
        """Daemon thread that periodically cleans up idle connections."""
```

**关键设计：**
- key 格式：`serial:/dev/ttyUSB0`、`ssh:192.168.1.100`
- auto_connect 参数控制是否首次使用时自动打开连接
- 后台 daemon 线程每 60 秒检查一次空闲连接，超时的自动关闭
- 关闭前自动 `read()` 一次 buffer，确保不丢最后一段日志

### 4.5 DeviceConfig (`device_config.py`)

可选的设备 profile 配置，支持用户预定义设备信息。

```python
@dataclass
class DeviceProfile:
    name: str
    type: Literal["serial", "ssh"]
    # serial fields
    port: str | None = None
    baudrate: int = 115200
    # ssh fields
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
        """Load device profiles from YAML file."""

    def get(self, name: str) -> DeviceProfile | None:
        """Get a device profile by name."""

    def list_all(self) -> list[DeviceProfile]:
        """List all configured device profiles."""
```

**配置文件格式 (`devices.yaml`)：**
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
  test_device:
    type: ssh
    host: 192.168.1.200
    username: admin
    password: admin123
```

### 4.6 Filters (`filters.py`)

日志关键词过滤器，支持服务端过滤。

```python
# 默认异常关键词
DEFAULT_PATTERNS = [
    r"panic",
    r"Oops",
    r"BUG:",
    r"WARNING",
    r"ERROR",
    r"error",
    r"fail",
    r"fault",
    r"traceback",
    r"exception",
    r"segfault",
    r"assert",
]

class LogFilter:
    """Regex-based log filter with pre-compiled patterns."""

    def __init__(self, patterns: list[str] | None = None):
        self._patterns = [
            re.compile(p, re.IGNORECASE)
            for p in (patterns or DEFAULT_PATTERNS)
        ]

    def matches(self, line: str) -> bool:
        return any(p.search(line) for p in self._patterns)

    def filter_lines(self, lines: list[str]) -> list[str]:
        return [l for l in lines if self.matches(l)]
```

## 5. MCP Tools API

### 5.1 串口工具

#### `serial_read`
```
读取串口日志。如果连接未打开且 auto_connect=true，自动打开。

Parameters:
  device: str | None          # 设备 profile 名 (devices.yaml)
  port: str | None            # 串口设备路径，如 /dev/ttyUSB0
  baudrate: int = 115200      # 波特率 (auto_connect 时使用)
  lines: int = 50             # 读取行数
  filter: str | None          # 正则过滤关键词，null=全部
  auto_connect: bool = true   # 未连接时是否自动打开
  since: float | None         # 只读取此时间戳之后的行

Returns:
  {status, lines: [...], total_available, connection: {port, baudrate, open}}
```

#### `serial_write`
```
向串口发送数据。如果连接未打开且 auto_connect=true，自动打开。

Parameters:
  device: str | None
  port: str | None
  baudrate: int = 115200
  data: str                   # 要发送的数据
  auto_connect: bool = true
  append_newline: bool = true # 是否自动追加 \n

Returns:
  {status, bytes_sent, connection: {...}}
```

#### `serial_open`
```
显式打开串口连接（高级用法，通常不需要）。

Parameters:
  device: str | None
  port: str
  baudrate: int = 115200
  ... (其他 pyserial 参数)

Returns:
  {status, connection: {port, baudrate, open}}
```

#### `serial_close`
```
显式关闭串口连接。

Parameters:
  port: str | None            # null=关闭所有串口

Returns:
  {status, closed: [...]}
```

#### `serial_list`
```
列出系统可用串口。

Returns:
  {status, ports: [{device, description, hwid}, ...]}
```

### 5.2 SSH 工具

#### `ssh_read`
```
读取 SSH shell 输出日志。

Parameters:
  device: str | None
  host: str | None
  port: int = 22
  username: str = "root"
  password: str | None
  key_file: str | None
  lines: int = 50
  filter: str | None
  auto_connect: bool = true
  since: float | None

Returns:
  {status, lines: [...], total_available, connection: {host, port, open}}
```

#### `ssh_exec`
```
通过 SSH 执行命令。命令输出自动进入 buffer，可通过 ssh_read 获取。

Parameters:
  device: str | None
  host: str | None
  ... (连接参数)
  command: str                # 要执行的命令
  auto_connect: bool = true
  wait: bool = true           # 是否等待命令完成再返回

Returns:
  {status, exit_code: int|None, connection: {...}}
```

#### `ssh_open` / `ssh_close`
```
显式打开/关闭 SSH 连接（同 serial_open/close 模式）。
```

#### `ssh_list`
```
列出当前活跃的 SSH 连接。
```

### 5.3 设备工具

#### `device_list`
```
列出 devices.yaml 中配置的所有设备 profile。

Returns:
  {status, devices: [{name, type, config}, ...]}
```

#### `device_status`
```
查看所有设备的连接状态。

Returns:
  {status, devices: [{name, type, connected, idle_seconds, buffer_lines}, ...]}
```

### 5.4 连接管理工具

#### `connection_list`
```
列出所有活跃连接（串口 + SSH）。

Returns:
  {status, connections: [{key, type, connected, idle_seconds, buffer_lines}, ...]}
```

#### `connection_close_all`
```
关闭所有连接并 flush 日志。

Returns:
  {status, closed: [...]}
```

## 6. MCP Resources

### 6.1 Resource URI 模板

| URI | 描述 | 参数 |
|-----|------|------|
| `serial://{port}/log` | 串口实时日志流 | `port`（URL-encoded） |
| `ssh://{host}/shell` | SSH shell 实时输出流 | `host` |
| `embed://devices` | 可用设备 profile 列表 | — |

### 6.2 Resource Subscription

当 MCP 客户端订阅某个 resource 时：
1. Server 注册一个 subscription callback 到对应的 `LogBuffer`
2. 每次有新行写入 buffer 时，调用所有 subscriber callback
3. 如果设置了 filter，只推送匹配的行
4. 客户端断开或取消订阅时，unsubscribe

**Resource 读取协议：**
```
read_resource("serial:///dev/ttyUSB0/log")
→ 返回当前 buffer 中最新的 100 行

subscribe_resource("serial:///dev/ttyUSB0/log")
→ 每次 buffer 有新行时，推送该新行给客户端
```

## 7. 用户使用流程

### 7.1 场景 1：快速查看串口 log（最常见）

```
用户: "帮我看下板子的串口 log"
Agent 调用:
  serial_read(port="/dev/ttyUSB0")  # auto_connect=true，自动打开
→ 返回最新 50 行 log
→ Agent 分析并回复用户
```

无需任何显式 open/close，一条工具调用即可。

### 7.2 场景 2：持续监控崩溃/异常

```
用户: "帮我盯着这块板子，有 panic 告诉我"
Agent 调用:
  serial_read(port="/dev/ttyUSB0", filter="panic|oops|BUG", lines=100)
→ 如果有匹配行，报告异常
→ 在 loop 中定期调用（或订阅 resource push）
```

服务端过滤只推送匹配行，token 消耗极低。

### 7.3 场景 3：交互式调试

```
用户: "发几条命令到板子上看下状态"
Agent 调用:
  serial_write(port="/dev/ttyUSB0", data="cat /proc/meminfo")
  serial_read(port="/dev/ttyUSB0", lines=30)
→ 分析输出
  serial_write(port="/dev/ttyUSB0", data="dmesg | tail -20")
  serial_read(port="/dev/ttyUSB0", lines=30)
→ 分析输出
```

### 7.4 场景 4：SSH 远程调试

```
用户: "SSH 到 192.168.1.100 执行 dmesg"
Agent 调用:
  ssh_exec(host="192.168.1.100", username="root", key_file="~/.ssh/id_rsa",
           command="dmesg | tail -50")
  ssh_read(host="192.168.1.100", lines=50)
→ 分析输出
```

### 7.5 场景 5：使用设备 profile

```
用户: "看下 my_board 的 log"  (假设 devices.yaml 已配置)
Agent 调用:
  serial_read(device="my_board")
→ 自动从配置读取 port/baudrate，auto_connect 打开连接
→ 返回 log
```

### 7.6 场景 6：空闲自动关闭

```
用户: "帮我看下板子启动 log"
Agent 调用:
  serial_read(port="/dev/ttyUSB0", lines=200)
→ 读取完毕后，用户不再交互
→ 5 分钟后 connection_pool 后台线程自动关闭串口
→ Agent 下次需要时 auto_connect 重新打开
```

## 8. 错误处理

所有工具返回统一格式：

```python
{
    "status": "ok" | "error",
    "message": str | None,       # 错误时的人类可读描述
    "data": ...,                 # 具体数据
}
```

常见错误场景及处理：

| 场景 | 处理 |
|------|------|
| 串口被占用 | `{"status": "error", "message": "Port /dev/ttyUSB0 is busy"}` |
| SSH 认证失败 | `{"status": "error", "message": "Authentication failed"}` |
| 设备未找到 | `{"status": "error", "message": "Device 'foo' not in devices.yaml"}` |
| 连接断开 | 下次 auto_connect 时自动重连 |
| buffer 为空 | 返回空列表，不报错 |

**不抛出 Python 异常中断 MCP 协议**——所有异常都在工具内部捕获并转化为 `status: "error"` 响应。

## 9. 依赖

```toml
[project]
dependencies = [
    "fastmcp>=0.1.0",
    "pyserial>=3.5",
    "paramiko>=3.4",
    "pyyaml>=6.0",
]
```

- `fastmcp`：Python MCP Server 框架，支持 tools + resources + subscriptions
- `pyserial`：串口通信，Linux/Windows/macOS 全平台
- `paramiko`：SSH 2.0 协议客户端库
- `pyyaml`：YAML 配置文件解析

## 10. 客户端配置示例

### Claude Code (`settings.json`)
```json
{
  "mcpServers": {
    "embed-debug": {
      "command": "uv",
      "args": ["--directory", "/path/to/MCP_for_SerialPort_ssh_debug", "run", "embed-debug-mcp"]
    }
  }
}
```

### Cursor (`.vscode/mcp.json`)
```json
{
  "servers": {
    "embed-debug": {
      "command": "uv",
      "args": ["--directory", "${workspaceFolder}/../MCP_for_SerialPort_ssh_debug", "run", "embed-debug-mcp"]
    }
  }
}
```

### Windsurf
同 Cursor 配置方式。

## 11. 启动命令

```bash
# 使用 uv 运行（推荐）
uv run embed-debug-mcp

# 或直接 Python 模块
python -m embed_debug_mcp

# 指定设备配置文件路径
python -m embed_debug_mcp --devices /path/to/devices.yaml

# 自定义空闲超时（秒）
python -m embed_debug_mcp --idle-timeout 600
```

## 12. 实现优先级

| 阶段 | 内容 | 优先级 |
|------|------|--------|
| Phase 1 | pyproject.toml, log_buffer.py, serial_conn.py, main.py 最小可用版本 | P0 |
| Phase 2 | ssh_conn.py, connection_pool.py, 全部 tools 注册 | P0 |
| Phase 3 | device_config.py, devices.yaml, device_* tools | P1 |
| Phase 4 | filters.py, resource subscription | P1 |
| Phase 5 | README.md, 测试, 错误处理完善 | P2 |
