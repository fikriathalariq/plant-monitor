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
import base64
import websockets

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
print('Django session key created:', session_key)

port = 9224
chrome = r'C:\Program Files\Google\Chrome\Application\chrome.exe'
user_dir = r'C:\Users\HP\AppData\Local\Temp\chrome_ws_profile'
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

async def capture():
    await asyncio.sleep(2)
    req = urllib.request.urlopen(f'http://127.0.0.1:{port}/json')
    tabs = json.loads(req.read().decode())
    ws_url = tabs[0]['webSocketDebuggerUrl']
    print('Connecting to CDP WS:', ws_url)

    async with websockets.connect(ws_url, max_size=25*1024*1024) as ws:
        # Enable network
        await ws.send(json.dumps({"id": 1, "method": "Network.enable"}))
        await ws.recv()

        # Set auth cookie
        await ws.send(json.dumps({
            "id": 2,
            "method": "Network.setCookie",
            "params": {
                "name": "sessionid",
                "value": session_key,
                "domain": "127.0.0.1",
                "path": "/"
            }
        }))
        await ws.recv()

        # Navigate to /history/report/4150075?machine=&batch=732
        await ws.send(json.dumps({
            "id": 3,
            "method": "Page.navigate",
            "params": {"url": "http://127.0.0.1:8000/history/report/4150075?machine=&batch=732"}
        }))
        print('Navigated to process report. Waiting 5 seconds...')
        await asyncio.sleep(5)

        # Capture screenshot
        await ws.send(json.dumps({
            "id": 4,
            "method": "Page.captureScreenshot",
            "params": {"format": "png"}
        }))

        while True:
            msg = await ws.recv()
            obj = json.loads(msg)
            if obj.get("id") == 4 and "result" in obj:
                img_data = base64.b64decode(obj["result"]["data"])
                out_path = r'C:\Users\HP\.gemini\antigravity\brain\b04a2a90-03d6-4297-ba59-6cf1c0ec979f\process_report_identity_live.png'
                with open(out_path, 'wb') as f:
                    f.write(img_data)
                print('Screenshot saved successfully to:', out_path, 'Size:', len(img_data))
                break

try:
    asyncio.run(capture())
finally:
    proc.terminate()
