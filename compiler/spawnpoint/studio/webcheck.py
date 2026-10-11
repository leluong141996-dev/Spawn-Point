"""Load a web build in headless Chrome via the DevTools protocol: console errors + screenshot.

Standard library only (a minimal WebSocket client), so it runs anywhere Chrome is installed.
"""

from __future__ import annotations

import base64
import json
import os
import re
import shutil
import signal
import socket
import struct
import subprocess
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

CHROME_CANDIDATES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser")


def find_chrome() -> str | None:
    env = os.environ.get("CHROME_BIN")
    if env:
        return env
    for c in CHROME_CANDIDATES:
        if shutil.which(c):
            return shutil.which(c)
    return None


@dataclass
class WebCheck:
    console: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    screenshot: bytes | None = None
    canvas_size: tuple[int, int] | None = None
    value: object = None  # result of `expression`, if given


class _WebSocket:
    def __init__(self, url: str):
        m = re.match(r"ws://([^/:]+):(\d+)(/.*)", url)
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=30)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
                           f"Connection: Upgrade\r\nSec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n").encode())
        resp = b""
        while b"\r\n\r\n" not in resp:
            resp += self.sock.recv(4096)
        if b" 101 " not in resp.split(b"\r\n")[0]:
            raise ConnectionError(f"websocket handshake failed: {resp[:200]!r}")
        self._buf = resp.split(b"\r\n\r\n", 1)[1]

    def send(self, obj: dict) -> None:
        data = json.dumps(obj).encode()
        header = bytearray([0x81])
        n = len(data)
        if n < 126:
            header.append(0x80 | n)
        elif n < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", n)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", n)
        mask = os.urandom(4)
        header += mask
        self.sock.sendall(bytes(header) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def _read(self, n: int) -> bytes:
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("websocket closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def recv(self) -> dict:
        payload = b""
        while True:
            b1, b2 = self._read(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack(">H", self._read(2))[0]
            elif n == 127:
                n = struct.unpack(">Q", self._read(8))[0]
            payload += self._read(n)
            if b1 & 0x80:
                break
        return json.loads(payload)

    def close(self) -> None:
        self.sock.close()


def check(url: str, seconds: float = 12.0, size: tuple[int, int] = (960, 540), keys: list[str] | None = None,
          expression: str | None = None, clicks: list[tuple[float, float, str]] | None = None,
          script: str | None = None) -> WebCheck:
    """Open `url`, wait `seconds` (optionally pressing `keys`, clicking or running `script` midway), return
    console output and a PNG. `expression` is evaluated at the end and returned as `value`."""
    chrome = find_chrome()
    if chrome is None:
        raise RuntimeError("Chrome not found (set CHROME_BIN)")
    result = WebCheck()
    # Chrome's helper processes can outlive the main one for a moment and keep writing to the profile.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as profile:
        proc = subprocess.Popen(
            [chrome, "--headless=new", "--no-sandbox", f"--user-data-dir={profile}", "--remote-debugging-port=0",
             "--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--autoplay-policy=no-user-gesture-required",
             f"--window-size={size[0]},{size[1]}", "about:blank"],
            stderr=subprocess.PIPE, stdout=subprocess.DEVNULL, text=True, start_new_session=True)
        try:
            ws_url = _devtools_url(proc)
            port = re.match(r"ws://[^:]+:(\d+)", ws_url).group(1)
            targets = json.loads(urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=10).read())
            page = next(t for t in targets if t.get("type") == "page")
            ws = _WebSocket(page["webSocketDebuggerUrl"])
            msg_id = 0

            def call(method: str, **params) -> dict:
                nonlocal msg_id
                msg_id += 1
                ws.send({"id": msg_id, "method": method, "params": params})
                while True:
                    m = ws.recv()
                    _collect(m, result)
                    if m.get("id") == msg_id:
                        return m.get("result", {})

            call("Runtime.enable")
            call("Log.enable")
            call("Page.enable")
            call("Page.navigate", url=url)
            deadline = time.time() + seconds
            pressed = False
            ws.sock.settimeout(0.5)
            while time.time() < deadline:
                if (keys or clicks or script) and not pressed and time.time() > deadline - seconds / 2:
                    ws.sock.settimeout(30)
                    for k in keys or []:
                        _key(call, k)
                    for x, y, button in clicks or []:
                        for t in ("mousePressed", "mouseReleased"):
                            call("Input.dispatchMouseEvent", type=t, x=x, y=y, button=button, clickCount=1)
                    if script:
                        call("Runtime.evaluate", expression=script)
                    ws.sock.settimeout(0.5)
                    pressed = True
                try:
                    _collect(ws.recv(), result)
                except (socket.timeout, TimeoutError):
                    pass
            ws.sock.settimeout(30)
            shot = call("Page.captureScreenshot", format="png")
            result.screenshot = base64.b64decode(shot["data"]) if shot.get("data") else None
            dims = call("Runtime.evaluate", returnByValue=True, expression=(
                "(() => { const c = document.querySelector('canvas'); return c ? [c.width, c.height] : null })()"))
            value = dims.get("result", {}).get("value")
            result.canvas_size = tuple(value) if value else None
            if expression:
                ev = call("Runtime.evaluate", returnByValue=True, expression=expression)
                result.value = ev.get("result", {}).get("value")
            ws.close()
        finally:
            _stop(proc)
    return result


def _stop(proc: subprocess.Popen) -> None:
    """Stop Chrome and every helper process it started (they share its process group)."""
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            continue
        deadline = time.time() + 5  # the main process is gone; give the helpers a moment to follow
        while time.time() < deadline:
            try:
                os.killpg(proc.pid, 0)
            except ProcessLookupError:
                return
            time.sleep(0.05)


def _devtools_url(proc: subprocess.Popen) -> str:
    deadline = time.time() + 20
    while time.time() < deadline:
        line = proc.stderr.readline()
        m = re.search(r"DevTools listening on (ws://\S+)", line)
        if m:
            return m.group(1)
    raise RuntimeError("Chrome did not start its DevTools endpoint")


def _key(call, key: str) -> None:
    code = {"Space": 32, "ArrowRight": 39, "ArrowLeft": 37, "KeyX": 88}.get(key, 0)
    for t in ("keyDown", "keyUp"):
        call("Input.dispatchKeyEvent", type=t, code=key, key=" " if key == "Space" else key,
             windowsVirtualKeyCode=code)


def _collect(m: dict, result: WebCheck) -> None:
    method = m.get("method")
    if method == "Runtime.consoleAPICalled":
        p = m["params"]
        text = " ".join(str(a.get("value", a.get("description", ""))) for a in p.get("args", []))
        result.console.append(f"{p.get('type')}: {text}")
        if p.get("type") == "error":
            result.errors.append(text)
    elif method == "Runtime.exceptionThrown":
        d = m["params"]["exceptionDetails"]
        result.errors.append(d.get("exception", {}).get("description") or d.get("text", "exception"))
    elif method == "Log.entryAdded":
        e = m["params"]["entry"]
        if e.get("level") == "error" and "favicon" not in e.get("url", ""):
            result.errors.append(f"{e.get('source')}: {e.get('text')}")


def save_screenshot(res: WebCheck, path: Path) -> None:
    if res.screenshot:
        path.write_bytes(res.screenshot)
