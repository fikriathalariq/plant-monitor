import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import django
import subprocess
import time
import json
import urllib.request
import asyncio

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'plant_monitor.settings')
django.setup()

from django.contrib.auth.models import User
from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import HASH_SESSION_KEY

admin = User.objects.get(username='admin')
s = SessionStore()
s['_auth_user_id'] = str(admin.id)
s['_auth_user_backend'] = 'django.contrib.auth.backends.ModelBackend'
s[HASH_SESSION_KEY] = admin.get_session_auth_hash()
s.save()
session_key = s.session_key
print('Created valid Django session:', session_key)

# Launch Chrome with remote debugging
chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
port = 9222
proc = subprocess.Popen([
    chrome,
    '--headless=new',
    '--disable-gpu',
    f'--remote-debugging-port={port}',
    'about:blank'
])

try:
    time.sleep(2)
    # Get WebSocket URL
    req = urllib.request.urlopen(f'http://127.0.0.1:{port}/json')
    tabs = json.loads(req.read().decode())
    ws_url = tabs[0]['webSocketDebuggerUrl']
    print('WS URL:', ws_url)

    # Use simple asyncio websocket to control Chrome via CDP
    import sys
    # Try importing websockets or write a simple raw socket client
    import socket
    import base64

    # Connect to websocket
    host, port_str = ws_url.replace('ws://', '').split('/')[0].split(':')
    path = '/' + '/'.join(ws_url.replace('ws://', '').split('/')[1:])
    sock = socket.create_connection((host, int(port_str)), timeout=10)
    
    # Handshake
    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{port_str}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(handshake.encode())
    resp = sock.recv(4096)
    
    def send_cdp(method, params=None, msg_id=1):
        payload = json.dumps({"id": msg_id, "method": method, "params": params or {}})
        payload_bytes = payload.encode('utf-8')
        length = len(payload_bytes)
        frame = bytearray([0x81]) # text frame fin
        if length <= 125:
            frame.append(0x80 | length)
        elif length <= 65535:
            frame.append(0x80 | 126)
            frame.extend(length.to_bytes(2, 'big'))
        else:
            frame.append(0x80 | 127)
            frame.extend(length.to_bytes(8, 'big'))
        mask = os.urandom(4)
        frame.extend(mask)
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload_bytes))
        frame.extend(masked)
        sock.sendall(frame)

    # Set Cookie
    send_cdp("Network.enable", msg_id=1)
    send_cdp("Network.setCookie", {
        "name": "sessionid",
        "value": session_key,
        "domain": "127.0.0.1",
        "path": "/"
    }, msg_id=2)
    time.sleep(0.5)

    # Navigate to dashboard-1
    send_cdp("Page.navigate", {"url": "http://127.0.0.1:8000/dashboard-1"}, msg_id=3)
    print('Navigated to dashboard-1, waiting for load & animation...')
    time.sleep(5)

    # Screenshot via Chrome CLI on that active session or capture
    artifact_dir = r'C:\Users\HP\.gemini\antigravity\brain\b04a2a90-03d6-4297-ba59-6cf1c0ec979f'
    out_png = os.path.join(artifact_dir, 'dashboard_1_live.png')
    
    send_cdp("Page.captureScreenshot", {"format": "png"}, msg_id=4)
    # Read response
    chunks = []
    sock.settimeout(15)
    start_time = time.time()
    while time.time() - start_time < 10:
        data = sock.recv(65536)
        if not data:
            break
        chunks.append(data)
        if b'"id":4' in b''.join(chunks) or b'"data"' in b''.join(chunks):
            # Try to see if full frame received
            pass
    raw = b''.join(chunks)
    # Extract JSON with "data": "base64..."
    idx = raw.find(b'"data":"')
    if idx != -1:
        end_idx = raw.find(b'"', idx + 8)
        b64_str = raw[idx+8:end_idx].decode()
        with open(out_png, 'wb') as img_f:
            img_f.write(base64.b64decode(b64_str))
        print('Captured successfully to:', out_png, 'Size:', os.path.getsize(out_png))
    else:
        print('Could not find data in response, length:', len(raw))

finally:
    proc.terminate()
