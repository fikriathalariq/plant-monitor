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
import socket
import base64

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
print('Session ready:', session_key)

port = 9223
chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
user_dir = r'C:\Users\HP\AppData\Local\Temp\chrome_cdp_profile'
os.makedirs(user_dir, exist_ok=True)

proc = subprocess.Popen([
    chrome,
    '--headless=new',
    '--disable-gpu',
    f'--remote-debugging-port={port}',
    f'--user-data-dir={user_dir}',
    '--window-size=1680,1200',
    'about:blank'
])

try:
    time.sleep(2)
    req = urllib.request.urlopen(f'http://127.0.0.1:{port}/json')
    tabs = json.loads(req.read().decode())
    ws_url = tabs[0]['webSocketDebuggerUrl']
    
    host, p_str = ws_url.replace('ws://', '').split('/')[0].split(':')
    path = '/' + '/'.join(ws_url.replace('ws://', '').split('/')[1:])
    sock = socket.create_connection((host, int(p_str)), timeout=15)
    
    key = base64.b64encode(os.urandom(16)).decode()
    handshake = (
        f"GET {path} HTTP/1.1\r\n"
        f"Host: {host}:{p_str}\r\n"
        f"Upgrade: websocket\r\n"
        f"Connection: Upgrade\r\n"
        f"Sec-WebSocket-Key: {key}\r\n"
        f"Sec-WebSocket-Version: 13\r\n\r\n"
    )
    sock.sendall(handshake.encode())
    sock.recv(4096)
    
    def send_cdp(method, params=None, msg_id=1):
        payload = json.dumps({"id": msg_id, "method": method, "params": params or {}}).encode('utf-8')
        length = len(payload)
        frame = bytearray([0x81])
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
        frame.extend(bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))
        sock.sendall(frame)

    # 1. Enable network & set cookie
    send_cdp("Network.enable", msg_id=1)
    send_cdp("Network.setCookie", {
        "name": "sessionid",
        "value": session_key,
        "domain": "127.0.0.1",
        "path": "/"
    }, msg_id=2)
    time.sleep(0.5)

    # 2. Navigate
    send_cdp("Page.navigate", {"url": "http://127.0.0.1:8000/dashboard-1"}, msg_id=3)
    print('Navigated, waiting 6 seconds for React & Recharts animation...')
    time.sleep(6)

    # 3. Capture Screenshot
    send_cdp("Page.captureScreenshot", {"format": "png"}, msg_id=4)

    def recv_exact(n):
        buf = bytearray()
        while len(buf) < n:
            chunk = sock.recv(n - len(buf))
            if not chunk:
                raise EOFError()
            buf.extend(chunk)
        return buf

    # Loop reading frames until we get msg_id 4
    full_json = ""
    while True:
        head = recv_exact(2)
        fin = bool(head[0] & 0x80)
        opcode = head[0] & 0x0f
        masked = bool(head[1] & 0x80)
        plen = head[1] & 0x7f
        if plen == 126:
            plen = int.from_bytes(recv_exact(2), 'big')
        elif plen == 127:
            plen = int.from_bytes(recv_exact(8), 'big')
        mask = recv_exact(4) if masked else None
        pdata = recv_exact(plen)
        if masked:
            pdata = bytearray(b ^ mask[i % 4] for i, b in enumerate(pdata))
        
        text = pdata.decode('utf-8', errors='ignore')
        if '"id":4' in text or '"data"' in text:
            full_json += text
            if '}' in text:
                try:
                    obj = json.loads(full_json)
                    if obj.get("id") == 4 and "result" in obj:
                        img_bytes = base64.b64decode(obj["result"]["data"])
                        out_png = r'C:\Users\HP\.gemini\antigravity\brain\b04a2a90-03d6-4297-ba59-6cf1c0ec979f\dashboard_1_live.png'
                        with open(out_png, 'wb') as f:
                            f.write(img_bytes)
                        print("Saved live screenshot successfully! Size:", len(img_bytes))
                        break
                except Exception:
                    pass

finally:
    proc.terminate()
