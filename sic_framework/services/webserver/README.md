# SIC Webserver Service

This folder contains a reusable SIC webserver component built on **Flask** + **Flask-SocketIO**. It’s intended to be used by many applications by providing a small, stable core (server lifecycle + common endpoints + Socket.IO transport) and allowing apps to provide their own web content (templates/static) and optional extensions (custom routes / socket handlers).

## Webserver basics (quick definitions)

### HTTP and “endpoints”

When you type a URL like `http://localhost:8080/healthz` in a browser, your browser makes an **HTTP request** to a specific *path* on a server.

- An **HTTP endpoint** is a combination of:
  - a **method** (like `GET` or `POST`), and
  - a **path** (like `/healthz` or `/api/buttonClick`)
- The server handles that request and returns an **HTTP response** (status code like `200` and usually some data like HTML or JSON).

Typical patterns you’ll see:
- **`GET /...`**: “fetch something” (HTML page, JSON state, an image)
- **`POST /...`**: “send something / trigger something” (a vote, a button click)

### Socket.IO (real-time events)

HTTP is *request/response*: the client asks, the server replies. For interactive UIs you often want the server to **push updates** to the page immediately (e.g., live transcripts, turn-taking signals) without the page polling every 500ms.

**Socket.IO** provides a persistent connection (over WebSocket when possible) so the client and server can exchange **events**:
- The client can emit an event like `sic/button_clicked`
- The server can emit events like `sic/transcript` or `sic/webinfo` as soon as new data arrives

This is why Socket.IO feels “real-time” compared to plain HTTP endpoints.

### CORS (who is allowed to talk to your server)

Browsers enforce a security rule called **Same-Origin Policy**. **CORS** (Cross-Origin Resource Sharing) is how a server tells the browser which *origins* are allowed.

- An **origin** is the scheme + host + port, e.g. `http://localhost:8080`
- If your frontend is loaded from one origin and tries to call APIs or connect sockets on a different origin, the browser may block it unless CORS allows it.

In this webserver, Socket.IO CORS is controlled by `WebserverConf(cors_allowed_origins=...)`. A restrictive default (e.g. localhost-only) is safer; widen it only when you need remote access.

### Tunneling (making a local server reachable remotely)

If your webserver runs on your laptop (e.g. `http://localhost:8080`), other devices on the internet can’t reach it directly. A **tunnel** tool (like `cloudflared` or `ngrok`) can create a temporary public URL that forwards traffic back to your local server.

This is useful for “audience phones connect to my demo” scenarios, but it also increases exposure:
- Anyone with the URL may be able to reach your endpoints and Socket.IO events
- You should be intentional about CORS and what actions your endpoints allow

## Core concepts

- **`WebserverComponent` (service)**: runs a Flask app + Socket.IO server in a background thread.
- **`Webserver` (connector)**: client used by applications to start/connect to the service and send/receive SIC messages.
- **Templates/static**: each application typically points `templates_dir` and `static_dir` at its own `webfiles/` directory.
- **Extensions**: optional, app-provided add-ons that can register HTTP routes and/or Socket.IO handlers without modifying the core service.

## Minimal usage (serving app webfiles)

In an application:

```python
import os
from sic_framework.services.webserver.webserver_service import WebserverConf, Webserver

current_dir = os.path.dirname(os.path.abspath(__file__))
webfiles_dir = os.path.join(current_dir, "webfiles")

conf = WebserverConf(
    host="0.0.0.0",
    port=8080,
    templates_dir=webfiles_dir,
    static_dir=webfiles_dir,
)
webserver = Webserver(conf=conf)
```

Your `webfiles/` should contain at least an `index.html` (served at `/`).

## Common HTTP endpoints

- **`GET /`**: renders `index.html` from the configured templates folder.
- **`GET /healthz`**: returns `{"status":"ok"}` (process is alive).
- **`GET /readyz`**: returns 200 when the port is reachable (otherwise 503).
- **`GET /api/webinfo/<label>`**: polling endpoint for the latest `WebInfoMessage` value for `label`.
- **`POST /api/buttonClick`**: sends a `ButtonClicked` SIC message to the application callback.
- **`GET /api/tunnel`**: reports tunnel status/url (if tunnel support is enabled).
- **`GET /api/qr?data=...`**: returns a QR PNG encoding the provided data string.

## Socket.IO contract (namespaced)

The server uses a small set of stable Socket.IO events:

- **`sic/state`** *(server → client)*: initial snapshot on connect
  - payload: `{ "transcript": string, "webinfo": { [label]: any }, "tunnel_url": string|null }`
- **`sic/transcript`** *(server → client)*:
  - payload: `{ "transcript": string }`
- **`sic/webinfo`** *(server → client)*:
  - payload: `{ "label": string, "message": any }`
- **`sic/turn`** *(server → client)*:
  - payload: `{ "user_turn": bool }`
- **`sic/html`** *(server → client)*:
  - payload: `{ "html": string }`
- **`sic/button_clicked`** *(client → server)*:
  - payload: any (string or object); forwarded to the app as a `ButtonClicked(button=<payload>)`.

## How to load the Socket.IO client

Use the Socket.IO client script served by the running SIC webserver:

```html
<script src="/socket.io/socket.io.js"></script>
<script>
  const socket = io();
  socket.on("connect", () => console.log("connected", socket.id));
  socket.on("connect_error", (err) => console.error(err.message));
</script>
```

### Important notes

- Prefer `"/socket.io/socket.io.js"` over manually bundled copies. It matches the server protocol version and avoids common Engine.IO mismatch errors.
- If your page shows `Socket.IO client failed to load`, first open this URL directly in your browser:
  - `http://localhost:<port>/socket.io/socket.io.js`
- If you configure `WebserverConf(static_dir=...)`, that only affects `/static/...` paths. It does **not** replace `/socket.io/socket.io.js`.
- If your app loads the client from `/static/js/socket.io.min.js`, make sure that file actually exists in the configured `static_dir`.

### Client example (sending a click)

```html
<script src="/socket.io/socket.io.js"></script>
<script>
  const socket = io();
  socket.emit("sic/button_clicked", { action: "dance" });
  socket.on("sic/transcript", (p) => console.log(p.transcript));
  socket.on("sic/webinfo", (p) => console.log(p.label, p.message));
  socket.on("sic/turn", (p) => console.log("user_turn:", p.user_turn));
  socket.on("sic/state", (p) => console.log("initial:", p));
</script>
```

## SIC messages (Python side)

Your application can:

- **Send** to the webserver:
  - `TranscriptMessage(transcript=...)` → updates clients via `sic/transcript`
  - `WebInfoMessage(label=..., message=...)` → updates clients via `sic/webinfo` and makes it available via `/api/webinfo/<label>`
  - `SetTurnMessage(user_turn=True/False)` → updates clients via `sic/turn`
  - `HtmlMessage(html="...")` → pushes raw HTML to clients via `sic/html` (client decides how/where to render it)

- **Receive** from the webserver:
  - `ButtonClicked(button=...)` when clients call `/api/buttonClick` or emit `sic/button_clicked`

## Extensions (optional)

You can add app-specific endpoints and socket handlers without modifying `WebserverComponent` by passing import specs in `WebserverConf.extensions`.

Supported extension forms:

- A Flask `Blueprint`
- An object/class with `register_routes(app)` and/or `register_socketio(socketio)`

Example:

```python
# my_app/web_ext.py
class MyWebExtension:
    def register_routes(self, app):
        @app.route("/api/ping")
        def ping():
            return {"pong": True}
```

```python
conf = WebserverConf(
    ...,
    extensions=["my_app.web_ext:MyWebExtension"],
)
```

## Configuration notes

- **CORS**: Socket.IO CORS defaults to allowing only localhost origins. Override with `cors_allowed_origins=...` if needed.
- **Template pages**: you may allowlist extra template routes via `pages={"/vote": "vote.html"}`.
- **Tunnel**: enable with `tunnel_enable=True` (requires `cloudflared` or `ngrok` installed). The public URL is surfaced via `/api/tunnel` and included in `sic/state`.

### Installing tunnel tools (`ngrok` / `cloudflared`)

You only need **one** tunneling tool. Both options are free for basic use.

#### Option A: `cloudflared` (Cloudflare Tunnel)

- **macOS (Homebrew)**
  - Install: `brew install cloudflared`
  - Verify: `cloudflared --version`
- **macOS (no Homebrew)**
  - Download the latest `cloudflared` binary for macOS from the Cloudflare downloads page (`https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/`).
  - Make it executable and move it somewhere on your `PATH`, for example:
    - `chmod +x ~/Downloads/cloudflared`
    - `sudo mv ~/Downloads/cloudflared /usr/local/bin/cloudflared`
  - Verify: `cloudflared --version`
- **Windows**
  - Download the Windows installer (`.msi`) from the same Cloudflare downloads page.
  - Run the installer and follow the prompts.
  - Open *Command Prompt* or *PowerShell* and verify: `cloudflared --version`
- **Linux (Debian/Ubuntu)**
  - `curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null`
  - `echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared $(lsb_release -cs) main" | sudo tee /etc/apt/sources.list.d/cloudflared.list`
  - `sudo apt update && sudo apt install -y cloudflared`
  - Verify: `cloudflared --version`
- **Linux (generic)**
  - Download the appropriate binary (or `.deb`/`.rpm`) from the Cloudflare downloads page.
  - Install via your package manager or mark the binary as executable and place it on your `PATH`.

Once installed, you usually do **not** need to start `cloudflared` manually; the SIC webserver will invoke it when `tunnel_enable=True` (see application demo configs for details).

#### Option B: `ngrok`

- **Create an ngrok account**
  - Go to `https://ngrok.com` and sign up (free tier is sufficient).
  - Copy your **authtoken** from the ngrok dashboard.
- **macOS**
  - With Homebrew: `brew install ngrok/ngrok/ngrok`
  - Or download the macOS archive from `https://ngrok.com/download` and place `ngrok` on your `PATH`.
  - Verify: `ngrok version`
- **Windows**
  - Download the Windows zip from `https://ngrok.com/download`.
  - Extract `ngrok.exe` and place it in a folder on your `PATH` (e.g. `C:\Users\<you>\AppData\Local\Programs\ngrok` or similar).
  - In *Command Prompt* or *PowerShell*: `ngrok version`
- **Linux**
  - Download the Linux archive from `https://ngrok.com/download`.
  - Extract the `ngrok` binary and move it to a directory on your `PATH`, e.g.:
    - `unzip ngrok-v3-*.zip`
    - `sudo mv ngrok /usr/local/bin/ngrok`
  - Verify: `ngrok version`
- **Configure your authtoken (all OSes)**
  - Run: `ngrok config add-authtoken <YOUR_AUTHTOKEN>`

As with `cloudflared`, the SIC webserver will handle starting `ngrok` when `tunnel_enable=True` and the ngrok binary is on your `PATH`.

