# VNC/SPICE WebSocket Console Support

## Feature Overview

**Date**: 2026-03-16
**Status**: Implemented
**Branch**: `feature/vnc-interface`
**Component**: Compute API, Controller API, BaseNode

### Summary

Add WebSocket-based console support for VNC and SPICE console types, enabling browser-based graphical console access to QEMU VMs and Docker containers without requiring standalone websockify processes.

---

## Architecture

### Design Principles

1. **Unified WebSocket Architecture**: All console types (Telnet, VNC, SPICE) use consistent WebSocket endpoints
2. **Authentication Integration**: Leverage existing GNS3 authentication mechanisms
3. **No External Dependencies**: Eliminate standalone websockify processes and additional port allocations
4. **Layered Design**: Controller → Compute → Node WebSocket forwarding

### Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                         Browser Client                          │
│  - noVNC for VNC                                                │
│  - spice-html5 for SPICE                                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ WebSocket Connection
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  GNS3 Controller API                                            │
│  - /v3/controller/projects/{id}/qemu/nodes/{id}/console/vnc     │
│  - /v3/controller/projects/{id}/qemu/nodes/{id}/console/spice   │
│  - HTTP Basic Auth + RBAC (Node.Console privilege)              │
└────────────────────────┬────────────────────────────────────────┘
                         │ WebSocket Forwarding
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  GNS3 Compute API                                               │
│  - /v3/compute/projects/{id}/qemu/nodes/{id}/console/vnc       │
│  - /v3/compute/projects/{id}/qemu/nodes/{id}/console/spice     │
│  - HTTP Basic Auth (compute credentials)                        │
└────────────────────────┬────────────────────────────────────────┘
                         │ WebSocket → TCP Bridge
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  BaseNode.start_vnc_websocket_console()                         │
│  BaseNode.start_spice_websocket_console()                       │
│  - Bidirectional binary data forwarding                         │
│  - WebSocket → TCP (VNC:5900+, SPICE:5900+)                     │
└────────────────────────┬────────────────────────────────────────┘
                         │ TCP Connection
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│  QEMU VM / Docker Container                                     │
│  - VNC Server (QXL display)                                     │
│  - SPICE Server (with optional spice-vdagent)                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### Compute Layer

#### VNC Console WebSocket

```
WS /v3/compute/projects/{project_id}/qemu/nodes/{node_id}/console/vnc
WS /v3/compute/projects/{project_id}/docker/nodes/{node_id}/console/vnc
```

**Authentication**: HTTP Basic Auth (compute credentials)

**Request Headers**:
```http
Upgrade: websocket
Connection: Upgrade
Authorization: Basic <base64(username:password)>
```

**Response**:
- Binary WebSocket connection for VNC protocol (RFB)

**Implementation**:
```python
# gns3server/api/routes/compute/qemu_nodes.py
@router.websocket("/{node_id}/console/vnc")
async def vnc_console_ws(
    websocket: WebSocket = Depends(ws_compute_authentication),
    node: QemuVM = Depends(dep_node)
):
    await node.start_vnc_websocket_console(websocket)
```

---

#### SPICE Console WebSocket

```
WS /v3/compute/projects/{project_id}/qemu/nodes/{node_id}/console/spice
WS /v3/compute/projects/{project_id}/docker/nodes/{node_id}/console/spice
```

**Authentication**: HTTP Basic Auth (compute credentials)

**Request Headers**:
```http
Upgrade: websocket
Connection: Upgrade
Authorization: Basic <base64(username:password)>
```

**Response**:
- Binary WebSocket connection for SPICE protocol

**Implementation**:
```python
# gns3server/api/routes/compute/qemu_nodes.py
@router.websocket("/{node_id}/console/spice")
async def spice_console_ws(
    websocket: WebSocket = Depends(ws_compute_authentication),
    node: QemuVM = Depends(dep_node)
):
    await node.start_spice_websocket_console(websocket)
```

---

### Controller Layer

#### VNC Console WebSocket

```
WS /v3/controller/projects/{project_id}/qemu/nodes/{node_id}/console/vnc
WS /v3/controller/projects/{project_id}/docker/nodes/{node_id}/console/vnc
```

**Authentication**: User JWT token + RBAC privilege check

**Required Privilege**: `Node.Console`

**Response**:
- Binary WebSocket connection (proxied to compute layer)

---

#### SPICE Console WebSocket

```
WS /v3/controller/projects/{project_id}/qemu/nodes/{node_id}/console/spice
WS /v3/controller/projects/{project_id}/docker/nodes/{node_id}/console/spice
```

**Authentication**: User JWT token + RBAC privilege check

**Required Privilege**: `Node.Console`

**Response**:
- Binary WebSocket connection (proxied to compute layer)

---

## Console Types

### Supported Console Types

| Console Type | Description | Node Support |
|-------------|-------------|-------------|
| `telnet` | Serial console via Telnet protocol | All nodes |
| `vnc` | Graphical console via VNC (RFB) protocol | QEMU, Docker |
| `spice` | Enhanced graphical console via SPICE protocol | QEMU only* |
| `spice+agent` | SPICE with spice-vdagent for features like clipboard sharing, folder sharing | QEMU only* |
| `none` | No console | All nodes |

*Docker supports the console type in schema but typically doesn't use SPICE (SPICE is designed for KVM/QEMU VMs).

### Console Type Configuration

**QEMU VM**:
```json
{
  "console_type": "spice+agent",
  "console": 5900
}
```

**Docker Container**:
```json
{
  "console_type": "vnc",
  "console": 5900
}
```

---

## Implementation Details

### BaseNode WebSocket Forwarding

**File**: `gns3server/compute/base_node.py`

#### VNC Console Implementation

```python
async def start_vnc_websocket_console(self, websocket):
    """
    Connect to VNC console using WebSocket.

    :param websocket: FastAPI WebSocket object
    """
    # 1. Validation
    if self.status != "started":
        await websocket.close(code=1000)
        raise NodeError(f"Node {self.name} is not started")
    if self._console_type != "vnc":
        await websocket.close(code=1000)
        raise NodeError(f"Node {self.name} console type is not vnc")

    # 2. Connect to VNC server
    vnc_reader, vnc_writer = await asyncio.open_connection(
        self._manager.port_manager.console_host,
        self.console  # VNC TCP port (e.g., 5900)
    )

    # 3. Bidirectional forwarding
    async def ws_forward(vnc_writer):
        # Browser → VNC
        while True:
            data = await websocket.receive_bytes()
            vnc_writer.write(data)
            await vnc_writer.drain()

    async def vnc_forward(vnc_reader):
        # VNC → Browser
        while not vnc_reader.at_eof():
            data = await vnc_reader.read(65536)  # Larger buffer for VNC frames
            await websocket.send_bytes(data)

    # 4. Run both directions concurrently
    aws = [
        asyncio.create_task(ws_forward(vnc_writer)),
        asyncio.create_task(vnc_forward(vnc_reader))
    ]
    done, pending = await asyncio.wait(aws, return_when=asyncio.FIRST_COMPLETED)

    # 5. Cleanup
    for task in pending:
        task.cancel()
    vnc_writer.close()
    await vnc_writer.wait_closed()
```

#### SPICE Console Implementation

SPICE implementation is identical to VNC, except for:
- Console type validation: `self._console_type in ("spice", "spice+agent")`
- Connection target: SPICE TCP port
- Log messages reference SPICE instead of VNC

---

### Controller Layer Proxy

**File**: `gns3server/api/routes/controller/nodes.py`

```python
@router.websocket("/{node_id}/console/spice")
async def spice_console(
    websocket: WebSocket,
    current_user: schemas.User = Depends(has_privilege_on_websocket("Node.Console")),
    node: Node = Depends(dep_node)
):
    """
    SPICE WebSocket console.

    Required privilege: Node.Console
    """
    # 1. Authentication & Authorization
    if current_user is None:
        return

    # 2. Build compute layer URL
    compute = node.compute
    spice_console_compute_url = (
        f"{websocket.url.scheme}://{compute.host}:{compute.port}"
        f"/v3/compute/projects/{node.project.id}/{node.node_type}/nodes/{node.id}/console/spice"
    )

    # 3. Forward to compute layer
    async def spice_receive(spice_console_compute):
        """Client → Compute"""
        while True:
            data = await websocket.receive_bytes()
            await spice_console_compute.send_bytes(data)

    async with HTTPClient.get_client().ws_connect(
        spice_console_compute_url,
        auth=aiohttp.BasicAuth(user, password),
        ssl_context=ssl_context
    ) as ws:
        asyncio.ensure_future(spice_receive(ws))
        async for msg in ws:
            if msg.type == aiohttp.WSMsgType.BINARY:
                await websocket.send_bytes(msg.data)  # Compute → Client
```

---

## Authentication Flow

### Compute Layer Authentication

**File**: `gns3server/api/routes/compute/dependencies/authentication.py`

```python
async def ws_compute_authentication(websocket: WebSocket) -> Union[None, WebSocket]:
    server_settings = Config.instance().settings.Server

    # Accept connection first
    await websocket.accept()

    # Skip auth if disabled
    if not server_settings.enable_http_auth:
        return websocket

    # Extract Authorization header
    authorization = websocket.headers.get("Authorization")
    scheme, param = get_authorization_scheme_param(authorization)

    # Validate Basic Auth
    if scheme.lower() != "basic":
        await websocket.close(code=1008)
        return websocket

    # Decode and verify credentials
    data = base64.b64decode(param).decode("ascii")
    username, separator, password = data.partition(":")

    username_valid = secrets.compare_digest(username, server_settings.compute_username)
    password_valid = secrets.compare_digest(password, server_settings.compute_password.get_secret_value())

    if not (username_valid and password_valid):
        await websocket.close(code=1008)
        return websocket

    return websocket
```

### Controller Layer Authentication

```python
# WebSocket dependency for privilege checking
async def has_privilege_on_websocket(privilege_id: str):
    async def _has_privilege(websocket: WebSocket):
        # 1. Extract and verify JWT token
        token = websocket.query_params.get("ticket")
        current_user = decode_jwt_token(token)

        # 2. Check privilege
        if not check_privilege(current_user, privilege_id):
            await websocket.close(code=1008)
            return None

        return current_user

    return _has_privilege
```

---

## Usage Examples

### JavaScript Client (noVNC)

```javascript
// Connect to VNC console
const host = "gns3-server.example.com";
const port = 3080;  // GNS3 controller port
const projectId = "uuid";
const nodeId = "uuid";
const token = "jwt_token";  // User authentication token

const vncUrl = `wss://${host}:${port}/v3/controller/projects/${projectId}/qemu/nodes/${nodeId}/console/vnc?ticket=${token}`;

const rfb = new RFB({
    target: document.getElementById('vnc-canvas'),
    url: vncUrl,
    credentials: { password: '' }  // VNC password (if configured)
});

rfb.addEventListener("connect", () => {
    console.log("Connected to VNC console");
});

rfb.addEventListener("disconnect", () => {
    console.log("Disconnected from VNC console");
});
```

### JavaScript Client (spice-html5)

```javascript
// Connect to SPICE console
const host = "gns3-server.example.com";
const port = 3080;
const projectId = "uuid";
const nodeId = "uuid";
const token = "jwt_token";

const spiceUrl = `wss://${host}:${port}/v3/controller/projects/${projectId}/qemu/nodes/${nodeId}/console/spice?ticket=${token}`;

const client = new SpiceHtml5.Client({
    uri: spiceUrl,
    screenId: 'spice-screen',
    password: '',  // SPICE password (if configured)
    tls: true  // Use TLS
});

client.addEventListener('connect', () => {
    console.log("Connected to SPICE console");
});

client.connect();
```

### Python Client (websockets)

```python
import asyncio
import websockets
import base64

async def connect_vnc_console(host, port, project_id, node_id, username, password):
    # Compute endpoint URL
    url = f"ws://{host}:{port}/v3/compute/projects/{project_id}/qemu/nodes/{node_id}/console/vnc"

    # HTTP Basic Auth
    credentials = base64.b64encode(f"{username}:{password}".encode()).decode()
    headers = {"Authorization": f"Basic {credentials}"}

    async with websockets.connect(url, extra_headers=headers) as ws:
        # Send/receive VNC binary data
        while True:
            data = await ws.recv()
            # Process VNC protocol data...

asyncio.run(connect_vnc_console("localhost", 3080, "...", "...", "admin", "password"))
```

### cURL (WebSocket Test)

```bash
# Test WebSocket connection (using websocat)
websocat \
  -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
  ws://localhost:3080/v3/compute/projects/{project_id}/qemu/nodes/{node_id}/console/vnc
```

---

## Comparison: Old vs New Architecture

### Old Architecture (websockify standalone)

```
Browser → websockify process 1 → VNC TCP (5900)
         → websockify process 2 → VNC TCP (5901)
         → websockify process N → VNC TCP (590N)

Issues:
- Each node requires separate websockify process
- Each node consumes additional WebSocket port
- No authentication on websockify port
- Complex process lifecycle management
- Resource intensive (many processes)
```

### New Architecture (GNS3 API WebSocket)

```
Browser → GNS3 Controller WebSocket (single port)
         → GNS3 Compute WebSocket
         → Internal TCP bridge to VNC/SPICE

Advantages:
- Single WebSocket endpoint
- Integrated authentication
- No external processes
- Consistent with telnet console
- Lower resource footprint
```

---

## Configuration

### Server Settings

**File**: `gns3server/config.py`

```yaml
Server:
  # Enable/disable compute authentication
  enable_http_auth: true

  # Compute credentials (for controller → compute auth)
  compute_username: "admin"
  compute_password: "password"

  # Console host configuration
  console_host: "0.0.0.0"  # or "::" for IPv6
```

### QEMU VM Console Configuration

```python
# Start QEMU VM with SPICE console
node = await qemu_manager.create_node(
    project_id=project_id,
    name="ubuntu-vm",
    console_type="spice+agent",  # SPICE with guest agent
    console=5900,  # SPICE port
    # ... other QEMU parameters
)
```

**Resulting QEMU Command**:
```bash
qemu-system-x86_64 \
  -spice addr=0.0.0.0,port=5900,disable-ticketing \
  -vga qxl \
  -device virtio-serial \
  -chardev spicevmc,id=vdagent,debug=0,name=vdagent \
  -device virtserialport,chardev=vdagent,name=com.redhat.spice.0 \
  # ... other QEMU options
```

### Docker Container Console Configuration

```python
# Start Docker container with VNC console
node = await docker_manager.create_node(
    project_id=project_id,
    name="ubuntu-container",
    image="ubuntu:latest",
    console_type="vnc",
    console=5900,
    console_resolution="1280x720",
    # ... other Docker parameters
)
```

**Result**:
- TigerVNC server starts in container
- VNC server listens on port 5900
- WebSocket endpoint available at `/console/vnc`

---

## Performance Considerations

### Buffer Sizes

- **VNC frames**: Up to 65536 bytes per read (larger for graphics)
- **SPICE data**: Up to 65536 bytes per read
- **WebSocket → TCP**: Unbuffered (immediate write)
- **TCP → WebSocket**: Buffered reads for efficiency

### Concurrent Connections

- **Multiple clients**: Supported (like telnet console)
- **Broadcast behavior**: Each WebSocket connection is independent
- **Resource usage**: Linear with number of concurrent connections

### Network Bandwidth

| Console Type | Typical Bandwidth | Notes |
|-------------|-------------------|-------|
| Telnet | < 1 KB/s | Text only |
| VNC | 1-10 MB/s | Depends on screen changes |
| SPICE | 1-20 MB/s | Variable compression, can be higher with video |

---

## Troubleshooting

### Common Issues

#### 1. Connection Refused

**Symptom**: `WebSocket connection to 'ws://...' failed: Error in connection establishment`

**Possible Causes**:
- Node not started
- Wrong console type configured
- Firewall blocking port

**Solution**:
```bash
# Check node status
curl -X GET http://localhost:3080/v3/controller/projects/{project_id}/qemu/nodes/{node_id}

# Verify console type
curl -X GET http://localhost:3080/v3/controller/projects/{project_id}/qemu/nodes/{node_id} | jq '.console_type'
```

---

#### 2. Authentication Failed

**Symptom**: WebSocket closes with code 1008

**Possible Causes**:
- Invalid credentials
- Missing Authorization header
- `enable_http_auth` enabled but no credentials provided

**Solution**:
```python
# Verify compute credentials
# In gns3_server configuration
Server.compute_username = "admin"
Server.compute_password = "password"

# Test with curl
curl -v \
  -H "Authorization: Basic $(echo -n 'admin:password' | base64)" \
  http://localhost:3080/v3/compute/projects/{project_id}/qemu/nodes/{node_id}
```

---

#### 3. Console Type Mismatch

**Symptom**: `Node console type is not vnc` or `Node console type is not SPICE`

**Possible Causes**:
- Node configured with different console type
- Wrong WebSocket endpoint used

**Solution**:
```bash
# Check actual console type
curl http://localhost:3080/v3/controller/projects/{project_id}/qemu/nodes/{node_id} | jq '.console_type'

# Use correct endpoint
# - If console_type == "vnc": /console/vnc
# - If console_type == "spice" or "spice+agent": /console/spice
```

---

#### 4. SPICE Not Working

**Symptom**: Cannot connect to SPICE console

**Possible Causes**:
- QEMU not built with SPICE support
- SPICE port already in use
- Node not started

**Solution**:
```bash
# Check QEMU SPICE support
qemu-system-x86_64 --help | grep spice

# Check if SPICE port is listening
netstat -tuln | grep 5900

# Check QEMU process
ps aux | grep qemu-system | grep spice
```

---

## Testing

### Unit Tests

**Test VNC WebSocket forwarding**:
```python
async def test_vnc_websocket_console():
    # Create QEMU node with VNC console
    node = QemuVM(
        name="test-vm",
        console_type="vnc",
        console=5900,
        # ...
    )

    # Start node
    await node.start()

    # Create mock WebSocket
    websocket = MockWebSocket()

    # Connect
    await node.start_vnc_websocket_console(websocket)

    # Verify data forwarding
    assert websocket.sent_data  # VNC data received
```

### Integration Tests

**Test end-to-end VNC console**:
```bash
# 1. Start GNS3 server
gns3server --local

# 2. Create project with QEMU VM
curl -X POST http://localhost:3080/v3/controller/projects \
  -H "Content-Type: application/json" \
  -d '{"name": "test-project"}'

# 3. Start QEMU VM with VNC
# (via API or GUI)

# 4. Connect WebSocket
websocat -H "Authorization: Basic ..." \
  ws://localhost:3080/v3/compute/projects/{id}/qemu/nodes/{id}/console/vnc

# 5. Send VNC handshake
# (requires RFB protocol client)
```

---

## Future Enhancements

### Potential Improvements

1. **WebSocket Compression**
   - Enable permessage-deflate compression
   - Reduce bandwidth for text-heavy consoles

2. **Session Recording**
   - Record VNC/SPICE sessions for playback
   - Useful for training and debugging

3. **Clipboard Integration**
   - SPICE vdagent already supports clipboard
   - Could expose via WebSocket extensions

4. **File Transfer**
   - SPICE supports folder sharing via webdav
   - Could integrate with GNS3 file management

5. **Audio Support**
   - SPICE supports audio streaming
   - Could add WebSocket audio forwarding

---

## Security Considerations

### Authentication

- ✅ **Controller Layer**: JWT token + RBAC privilege check
- ✅ **Compute Layer**: HTTP Basic Auth
- ✅ **No standalone websockify**: Single authentication point
- ❌ **Old websockify approach**: No authentication on websockify port

### Authorization

- **Privilege Required**: `Node.Console`
- **Project Isolation**: Users can only access consoles in projects they have access to
- **Node Access Control**: Checked via `dep_node` dependency

### Transport Security

- **WebSocket (ws://)**: Unencrypted, for development
- **WebSocket Secure (wss://)**: Encrypted, recommended for production
- **SSL/TLS**: Configured via GNS3 server SSL settings

### Console Protocol Security

- **VNC**: Uses RFB protocol, supports password authentication
- **SPICE**: Supports ticket-based authentication (`disable-ticketing` in current implementation)
- **Recommendation**: Enable VNC/SPICE passwords for production

---

## References

### Files Modified

| File | Description |
|------|-------------|
| `gns3server/compute/base_node.py` | Add `start_vnc_websocket_console()` and `start_spice_websocket_console()` methods |
| `gns3server/api/routes/compute/qemu_nodes.py` | Add `/{node_id}/console/vnc` and `/{node_id}/console/spice` endpoints |
| `gns3server/api/routes/compute/docker_nodes.py` | Add `/{node_id}/console/vnc` and `/{node_id}/console/spice` endpoints |
| `gns3server/api/routes/controller/nodes.py` | Add controller layer WebSocket proxy endpoints |

### Commits

- `ba92b405` - feat: add VNC WebSocket console support for Docker and QEMU nodes
- Current implementation extends this with SPICE support

### Related Documentation

- [Telnet Console Documentation](../bugs/telnet-server-connection-race-condition.md)
- [GNS3 API Documentation](./openapi.json)
- [noVNC Documentation](https://github.com/novnc/noVNC)
- [SPICE Protocol](https://www.spice-space.org/documentation.html)

### External Libraries

- **noVNC**: HTML5 VNC Client (https://github.com/novnc/noVNC)
- **spice-html5**: HTML5 SPICE Client (https://github.com/spice-html5/spice-html5)

---

## Migration Guide

### From Standalone websockify

**Old Approach** (not recommended):
```python
# Start websockify for each node
websockify 10001 localhost:5900  # Process 1
websockify 10002 localhost:5901  # Process 2
websockify 10003 localhost:5902  # Process 3
```

**New Approach** (recommended):
```python
# No websockify processes needed
# Just use GNS3 WebSocket API
WS /v3/controller/projects/{id}/qemu/nodes/{id}/console/vnc
WS /v3/controller/projects/{id}/qemu/nodes/{id}/console/spice
```

**Client Migration**:
```javascript
// Old: Connect directly to websockify
const url = `ws://server:${websockify_port}/`;

// New: Connect through GNS3 API
const url = `wss://server:3080/v3/controller/projects/${projectId}/qemu/nodes/${nodeId}/console/vnc?ticket=${token}`;
```

---

## Changelog

### Version 1.0 (2026-03-16)

**Added**:
- VNC WebSocket console support for QEMU and Docker nodes
- SPICE WebSocket console support for QEMU nodes
- Controller layer WebSocket proxy endpoints
- Compute layer WebSocket endpoints with authentication
- Bidirectional binary data forwarding in BaseNode

**Changed**:
- N/A (new feature)

**Deprecated**:
- Standalone websockify approach (still functional but not recommended)

**Fixed**:
- N/A (new feature)
