"""Phone mode: a phone (or a laptop) with Web Bluetooth reads the trainer and the Zwift Click and sends the data here.

* HTTPS on the LAN (default port 8766): the page for the phone, its data, and the gradient going back (Server-Sent Events).
  Every request needs ``?t=<token>`` because the port is reachable from the local network.
* Plain HTTP (default port 8767): only the certificate authority, to be installed once on the phone.
"""
from __future__ import annotations

import json
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from .certs import ensure_certs, load_token
from .ftms import on_bike_data, on_control_point
from .keys import KEYMAP
from .paths import WEB_DIR
from .state import current_notice, effective_grade, log, state

PHONE_PORT, CA_PORT = 8766, 8767

# the physical Zwift Click buttons the phone may report
RAW_BUTTONS = {"LEFT", "RIGHT", "UP", "DOWN", "A", "B", "Y", "Z", "PLUS", "MINUS"}


class PhoneHandler(BaseHTTPRequestHandler):
    token = ""
    protocol_version = "HTTP/1.1"      # keep-alive: one TLS handshake for many requests
    timeout = 60                       # an idle kept-alive connection ends its thread after a minute

    def log_message(self, *a):
        pass

    def _send(self, code, body, ctype="application/json"):
        body = body if isinstance(body, bytes) else body.encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _route(self):
        u = urlparse(self.path)
        if parse_qs(u.query).get("t", [""])[0] != self.token:
            self.close_connection = True          # a rejected POST leaves its body unread: do not reuse the connection
            self._send(403, '{"error":"bad token"}')
            return None
        return u.path

    def do_GET(self):
        path = self._route()
        if path is None:
            return
        if path == "/phone":
            log(f"phone page requested from {self.client_address[0]} ({self.headers.get('User-Agent', '?')[:80]})")
            try:
                self._send(200, (WEB_DIR / "phone.html").read_bytes(), "text/html; charset=utf-8")
            except OSError:
                self._send(404, "phone.html missing", "text/plain")
        elif path == "/phone/ping":
            self._send(200, '{"ok":true}')
        elif path == "/phone/events":
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            who = self.client_address[0]
            t0 = time.time()
            log(f"phone/laptop {who}: gradient stream opened")
            try:
                while True:
                    msg = {"grade": round(effective_grade(), 2), "difficulty": state["difficulty"],
                           "notice": current_notice()}
                    self.wfile.write(f"data: {json.dumps(msg)}\n\n".encode())
                    self.wfile.flush()
                    time.sleep(0.5)
            except OSError as e:
                log(f"phone/laptop {who}: gradient stream closed after {time.time() - t0:.0f} s ({type(e).__name__}: {e})")
        else:
            self._send(404, "{}")

    def do_POST(self):
        path = self._route()
        if path is None:
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
            if path == "/phone/data":
                on_bike_data(None, bytearray.fromhex(body["hex"]))
                state["connected"] = True
            elif path == "/phone/buttons":
                state["buttons"] = [b for b in body.get("pressed", []) if b in KEYMAP]
                state["raw"] = [b for b in body.get("raw", []) if b in RAW_BUTTONS]
                state["t_buttons"] = time.time()
            elif path == "/phone/status":
                kind = body.get("kind")
                if kind == "connected":
                    state.update(connected=True, trainer_name=str(body.get("name") or "trainer")[:60])
                    log(f"phone connected to {state['trainer_name']}")
                elif kind == "disconnected":
                    state["connected"] = False
                    log("phone: trainer disconnected")
                elif kind == "click":
                    state.update(click_connected=bool(body.get("connected")), click_name=str(body.get("name") or "Zwift Click")[:60])
                    if not state["click_connected"]:
                        state.update(raw=[], buttons=[])
                    log(f"phone: Zwift Click {'connected: ' + state['click_name'] if state['click_connected'] else 'disconnected'}")
                elif kind == "cp":
                    on_control_point(None, bytearray.fromhex(body["hex"]))
                elif kind == "log":
                    msg = str(body.get("msg"))[:200]
                    if msg.startswith("Click: 23 08"):      # button frames: counted, not listed (they bury everything else)
                        state["click_frames"] = state.get("click_frames", 0) + 1
                    else:
                        log("phone: " + msg)
            else:
                return self._send(404, "{}")
            self._send(200, "{}")
        except Exception as e:
            self._send(400, json.dumps({"error": str(e)}))


class TlsServer(ThreadingHTTPServer):
    """HTTPS server: the handshake runs in the request's own thread and its failures are logged."""
    ctx: ssl.SSLContext
    request_queue_size = 64

    def get_request(self):
        sock, addr = self.socket.accept()
        return self.ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr

    def finish_request(self, request, client_address):
        request.settimeout(10)
        request.do_handshake()
        request.settimeout(60)
        super().finish_request(request, client_address)

    def handle_error(self, request, client_address):
        e = sys.exc_info()[1]
        if isinstance(e, (OSError, EOFError)):
            log(f"TLS/connection failed from {client_address[0]}: {e}")


CA_PAGE = """<!doctype html><meta charset=utf-8><meta name=viewport content="width=device-width">
<body style="font:20px/1.5 -apple-system,sans-serif;padding:20px;max-width:640px;margin:auto">
<h2>Pedalator</h2>
<p><a href="/ca.crt"><b>1. Download the certificate / Pobierz certyfikat</b></a></p>
<p>2. Settings &rarr; <i>Profile Downloaded</i> &rarr; Install.<br><small>Ustawienia &rarr; Pobrano profil &rarr; Zainstaluj.</small></p>
<p>3. Settings &rarr; General &rarr; About &rarr; <i>Certificate Trust Settings</i> &rarr; switch on <b>Pedalator local CA</b>.
<br><small>Ustawienia &rarr; Og&oacute;lne &rarr; Informacje &rarr; Zaufanie certyfikat&oacute;w &rarr; w&#322;&#261;cz.</small></p>
<p>4. Open the address printed by Pedalator on the PC, in <b>Bluefy</b> (iPhone) or Chrome.
<br><small>Otw&oacute;rz adres z konsoli Pedalatora w Bluefy (iPhone) lub w Chrome.</small></p>
"""


class CaHandler(BaseHTTPRequestHandler):
    """Plain HTTP, serves only the CA certificate."""
    cert_dir: Path

    def log_message(self, *a):
        pass

    def do_GET(self):
        log(f"http {self.path} from {self.client_address[0]} ({self.headers.get('User-Agent', '?')[:80]})")
        if self.path == "/ca.crt":
            body, ctype = (self.cert_dir / "ca.crt").read_bytes(), "application/x-x509-ca-cert"
        else:
            body, ctype = CA_PAGE.encode(), "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def start_phone_servers(ip: str, cert_dir: Path, phone_port: int = PHONE_PORT, ca_port: int = CA_PORT,
                        host: str = "0.0.0.0") -> tuple[str, list[ThreadingHTTPServer]]:
    """Start the HTTPS and CA servers. Returns the phone token and the servers (so tests can shut them down)."""
    crt, key = ensure_certs(cert_dir, ip)
    token = load_token(cert_dir)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(crt, key)

    tls = type("BoundTlsServer", (TlsServer,), {"ctx": ctx})
    phone = type("BoundPhoneHandler", (PhoneHandler,), {"token": token})
    ca = type("BoundCaHandler", (CaHandler,), {"cert_dir": cert_dir})

    servers: list[ThreadingHTTPServer] = []
    for server_cls, handler, port in ((tls, phone, phone_port), (ThreadingHTTPServer, ca, ca_port)):
        try:
            srv = server_cls((host, port), handler)
        except OSError as e:
            log(f"phone server NOT started (port {port}: {e})")
            continue
        srv.daemon_threads = True
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        servers.append(srv)
    log("PHONE MODE. On the phone:")
    log(f"  1) browser (once): http://{ip}:{ca_port}/  -> install and trust the certificate")
    log(f"  2) Bluefy (iPhone) or Chrome: https://{ip}:{phone_port}/phone?t={token}")
    return token, servers
