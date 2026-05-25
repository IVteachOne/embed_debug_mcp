# Development Log — Embed Debug MCP Tool

## 2026-05-25

### 阶段 1: 项目初始化
- 创建 `pyproject.toml`，定义项目元数据和依赖
- 创建 `src/embed_debug_mcp/` 包结构
- 依赖：`fastmcp`, `pyserial`, `paramiko`, `pyyaml`

### 阶段 2: 核心模块

- `log_buffer.py` — 基于 deque 的线程安全环形缓冲区，支持过滤和订阅回调
- `serial_conn.py` — pyserial 封装，后台 daemon 线程 10ms 轮询读取，activity tracking
- `ssh_conn.py` — paramiko 封装，invoke_shell 交互式 channel，后台线程读取输出
- `connection_pool.py` — 全局连接池，auto-connect on first use，60s 周期 idle 清理
- `device_config.py` — YAML 设备 profile 加载，DeviceProfile dataclass
- `filters.py` — 默认异常关键词（panic/oops/BUG/error/fault 等）
- `main.py` — FastMCP Server，注册 14 个 tools + 2 个 resources

### 阶段 3: 测试验证

- `uv sync` — 依赖安装成功（77 packages）
- `embed-debug-mcp --help` — CLI 参数正常
- `embed-debug-mcp` — Server 启动成功，FastMCP 3.3.1 识别为 `embed-debug-mcp`
- 待测试：MCP 工具实际调用（需要真实串口/SSH 设备）

## 项目结构

```
MCP_for_SerialPort_ssh_debug/260525/code/
├── pyproject.toml
├── uv.lock
├── README.md
├── devices.yaml.example
├── embed_debug_tool_design.md
├── development_log.md
└── src/embed_debug_mcp/
    ├── __init__.py
    ├── __main__.py
    ├── main.py              # FastMCP Server (14 tools + 2 resources)
    ├── log_buffer.py         # 环形日志缓冲
    ├── serial_conn.py        # 串口连接
    ├── ssh_conn.py           # SSH 连接
    ├── connection_pool.py    # 连接池
    ├── device_config.py      # 设备配置
    └── filters.py            # 日志过滤
```

## 已注册的 MCP Tools (14)

| 分类 | Tools |
|------|-------|
| 串口 | serial_read, serial_write, serial_open, serial_close, serial_list |
| SSH | ssh_read, ssh_exec, ssh_open, ssh_close, ssh_list |
| 设备 | device_list, device_status |
| 连接管理 | connection_list, connection_close_all |

## 已注册的 MCP Resources (2)

| URI | 描述 |
|-----|------|
| serial://{port}/log | 串口实时日志 |
| ssh://{host}/shell | SSH shell 输出 |
