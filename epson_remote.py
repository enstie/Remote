"""
Epson Projector Local Remote (ESC/VP21)

Single-file Flask application with:
- Local auto-discovery on port 3629
- ESC/VP21 TCP command transport with handshake per command
- Mobile-first glassmorphism control UI
"""

from __future__ import annotations

import ipaddress
import socket
import threading
import time
from typing import Optional

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

# ESC/VP.net discovery / command handshake payload required by Epson protocol.
ESCVP_HANDSHAKE = b"ESC/VP.net\x10\x03\x00\x00\x00\x00\x0d"
PROJECTOR_PORT = 3629
WEB_PORT = 5000

# Shared state protected by a lock because discovery runs in a background thread.
state_lock = threading.Lock()
projector_ip: Optional[str] = None
last_error: Optional[str] = None

# Supported source and key mappings exposed by API/UI.
SOURCE_MAP = {
    "hdmi1": "30",
    "hdmi2": "A0",
    "computer": "11",
}

KEY_MAP = {
    "up": "UP",
    "down": "DOWN",
    "left": "LEFT",
    "right": "RIGHT",
    "enter": "ENTER",
    "menu": "MENU",
    "back": "ESC",
}


def get_local_ip() -> str:
    """Detect the primary local IPv4 used for outbound traffic."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # No internet is required; this does not send traffic successfully.
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def discover_by_udp_broadcast(timeout_seconds: float = 3.0) -> Optional[str]:
    """Broadcast handshake on UDP/3629 and return first responder IP."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.settimeout(0.5)
    try:
        deadline = time.time() + timeout_seconds
        while time.time() < deadline:
            sock.sendto(ESCVP_HANDSHAKE, ("255.255.255.255", PROJECTOR_PORT))
            try:
                data, addr = sock.recvfrom(1024)
                if addr and data is not None:
                    return addr[0]
            except socket.timeout:
                continue
    finally:
        sock.close()
    return None


def probe_projector_tcp(ip: str, timeout_seconds: float = 0.4) -> bool:
    """Quickly verify host speaks enough Epson protocol to be treated as projector."""
    try:
        with socket.create_connection((ip, PROJECTOR_PORT), timeout=timeout_seconds) as sock:
            sock.settimeout(timeout_seconds)
            sock.sendall(ESCVP_HANDSHAKE)
            try:
                sock.recv(128)
            except socket.timeout:
                # Some models do not reply immediately; open socket + handshake is enough to accept.
                pass
            return True
    except OSError:
        return False


def discover_by_subnet_scan(timeout_seconds: float = 12.0) -> Optional[str]:
    """Fallback /24 scan for hosts with open Epson port when UDP discovery fails."""
    local_ip = get_local_ip()
    try:
        network = ipaddress.ip_network(f"{local_ip}/24", strict=False)
    except ValueError:
        return None

    deadline = time.time() + timeout_seconds
    for host in network.hosts():
        if time.time() > deadline:
            break
        host_ip = str(host)
        if host_ip == local_ip:
            continue
        if probe_projector_tcp(host_ip):
            return host_ip
    return None


def discover_projector() -> Optional[str]:
    """Try UDP broadcast first, then subnet scan fallback."""
    found_ip = discover_by_udp_broadcast()
    if found_ip:
        return found_ip
    return discover_by_subnet_scan()


def set_state(ip: Optional[str] = None, error: Optional[str] = None) -> None:
    """Update shared projector state safely."""
    global projector_ip, last_error
    with state_lock:
        if ip is not None:
            projector_ip = ip
        if error is not None:
            last_error = error


def get_state() -> tuple[Optional[str], Optional[str]]:
    """Read shared projector state safely."""
    with state_lock:
        return projector_ip, last_error


def discovery_worker() -> None:
    """Background discovery that runs at launch."""
    found_ip = discover_projector()
    if found_ip:
        set_state(ip=found_ip, error=None)
    else:
        set_state(error="No Epson projector discovered on local network.")


def send_escvp_command(raw_command: str) -> dict:
    """
    Open TCP connection, send protocol handshake, then send command + carriage return.
    Required command format examples: 'PWR ON', 'PWR OFF', 'SOURCE 30', 'KEY UP'
    """
    ip, _ = get_state()
    if not ip:
        return {"ok": False, "error": "Projector not discovered yet."}

    command_payload = f"{raw_command}\r".encode("ascii", errors="strict")
    try:
        with socket.create_connection((ip, PROJECTOR_PORT), timeout=2.0) as sock:
            sock.settimeout(2.0)
            sock.sendall(ESCVP_HANDSHAKE)
            # Read handshake response if any (non-fatal if absent).
            try:
                sock.recv(256)
            except socket.timeout:
                pass
            sock.sendall(command_payload)
            # Read command response if any.
            response = b""
            try:
                response = sock.recv(256)
            except socket.timeout:
                pass
        return {"ok": True, "command": raw_command, "response": response.decode(errors="ignore")}
    except OSError as exc:
        set_state(error=f"Command failed: {exc}")
        return {"ok": False, "error": str(exc), "command": raw_command}


HTML = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no" />
  <title>Epson Remote</title>
  <style>
    :root {
      --bg-a: #0f172a;
      --bg-b: #1e293b;
      --glass: rgba(255, 255, 255, 0.10);
      --glass-strong: rgba(255, 255, 255, 0.14);
      --text: #e2e8f0;
      --muted: #94a3b8;
      --ok: #22c55e;
      --danger: #ef4444;
      --accent: #38bdf8;
      --shadow: 0 20px 40px rgba(2, 6, 23, 0.5);
      --radius: 18px;
    }
    * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
    body {
      margin: 0;
      min-height: 100vh;
      font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
      background: radial-gradient(circle at top right, #1d4ed8 0%, transparent 35%),
                  radial-gradient(circle at bottom left, #0891b2 0%, transparent 30%),
                  linear-gradient(160deg, var(--bg-a), var(--bg-b));
      color: var(--text);
      display: grid;
      place-items: center;
      padding: 16px;
    }
    .app {
      width: min(420px, 100%);
      background: var(--glass);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 24px;
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      padding: 16px;
      box-shadow: var(--shadow);
    }
    .status {
      margin: 0 0 14px;
      padding: 10px 12px;
      border-radius: 12px;
      background: rgba(15,23,42,.35);
      font-size: .9rem;
      color: var(--muted);
      border: 1px solid rgba(255,255,255,.08);
    }
    .row { display: grid; gap: 10px; margin-bottom: 12px; }
    .power { grid-template-columns: 1fr 1fr; }
    .sources { grid-template-columns: repeat(3, 1fr); }
    .btn {
      border: 1px solid rgba(255,255,255,.16);
      background: var(--glass-strong);
      color: var(--text);
      border-radius: 14px;
      padding: 13px 10px;
      font-weight: 600;
      font-size: .95rem;
      box-shadow: 0 10px 24px rgba(15, 23, 42, .35);
      transition: transform .08s ease, filter .15s ease;
    }
    .btn:active { transform: scale(.97); filter: brightness(1.12); }
    .btn.on { background: rgba(34,197,94,.22); border-color: rgba(34,197,94,.55); }
    .btn.off { background: rgba(239,68,68,.22); border-color: rgba(239,68,68,.55); }
    .dpad-wrap {
      background: rgba(15,23,42,.32);
      border: 1px solid rgba(255,255,255,.09);
      border-radius: var(--radius);
      padding: 12px;
    }
    .dpad {
      width: 260px;
      max-width: 100%;
      aspect-ratio: 1/1;
      margin: 0 auto;
      display: grid;
      grid-template-columns: 1fr 1fr 1fr;
      grid-template-rows: 1fr 1fr 1fr;
      gap: 10px;
    }
    .dpad .btn { height: 100%; }
    .center { background: rgba(56,189,248,.20); border-color: rgba(56,189,248,.5); }
    .foot { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-top: 10px; }
    .tiny { font-size: .85rem; color: var(--muted); text-align: center; margin-top: 6px; }
  </style>
</head>
<body>
  <main class="app">
    <p id="status" class="status">Checking projector connection...</p>

    <section class="row power">
      <button class="btn on" onclick="send('/api/power/on')">Power On</button>
      <button class="btn off" onclick="send('/api/power/off')">Power Off</button>
    </section>

    <section class="dpad-wrap">
      <div class="dpad">
        <div></div>
        <button class="btn" onclick="send('/api/key/up')">▲</button>
        <div></div>

        <button class="btn" onclick="send('/api/key/left')">◀</button>
        <button class="btn center" onclick="send('/api/key/enter')">Enter</button>
        <button class="btn" onclick="send('/api/key/right')">▶</button>

        <div></div>
        <button class="btn" onclick="send('/api/key/down')">▼</button>
        <div></div>
      </div>

      <div class="foot">
        <button class="btn" onclick="send('/api/key/back')">Back</button>
        <button class="btn" onclick="send('/api/key/menu')">Menu</button>
      </div>
      <div class="tiny">Epson ESC/VP21 Remote</div>
    </section>

    <section class="row sources" style="margin-top: 12px;">
      <button class="btn" onclick="send('/api/source/hdmi1')">HDMI 1</button>
      <button class="btn" onclick="send('/api/source/hdmi2')">HDMI 2</button>
      <button class="btn" onclick="send('/api/source/computer')">Computer</button>
    </section>
  </main>

  <script>
    async function send(url) {
      try {
        const res = await fetch(url, { method: 'POST' });
        const data = await res.json();
        const info = data.ok ? `✅ ${data.command || 'Command sent'}` : `❌ ${data.error || 'Request failed'}`;
        setStatus(info);
      } catch (e) {
        setStatus(`❌ Network error: ${e.message}`);
      }
    }

    function setStatus(message) {
      document.getElementById('status').textContent = message;
    }

    async function refreshStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        if (data.connected) {
          setStatus(`Connected to projector at ${data.projector_ip}`);
        } else {
          setStatus(`Searching... ${data.error || 'No projector found yet'}`);
        }
      } catch {
        setStatus('Status unavailable.');
      }
    }

    refreshStatus();
    setInterval(refreshStatus, 5000);
  </script>
</body>
</html>
"""


@app.get("/")
def index():
    return render_template_string(HTML)


@app.get("/api/status")
def status():
    ip, error = get_state()
    return jsonify({"connected": bool(ip), "projector_ip": ip, "error": error})


@app.post("/api/power/on")
def power_on():
    return jsonify(send_escvp_command("PWR ON"))


@app.post("/api/power/off")
def power_off():
    return jsonify(send_escvp_command("PWR OFF"))


@app.post("/api/source/<source_id>")
def source(source_id: str):
    source_code = SOURCE_MAP.get(source_id.lower())
    if not source_code:
        return jsonify({"ok": False, "error": f"Invalid source '{source_id}'."}), 400
    return jsonify(send_escvp_command(f"SOURCE {source_code}"))


@app.post("/api/key/<keycode>")
def key(keycode: str):
    key_cmd = KEY_MAP.get(keycode.lower())
    if not key_cmd:
        return jsonify({"ok": False, "error": f"Invalid key '{keycode}'."}), 400
    return jsonify(send_escvp_command(f"KEY {key_cmd}"))


if __name__ == "__main__":
    # Start discovery at launch so the user never has to enter an IP manually.
    threading.Thread(target=discovery_worker, daemon=True).start()
    print(f"Starting Epson Remote at http://0.0.0.0:{WEB_PORT}")
    app.run(host="0.0.0.0", port=WEB_PORT, debug=False)
