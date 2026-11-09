"""Kirim pesan ke Telegram Bot API (stdlib urllib — tanpa requests)."""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request
from typing import Iterable, List, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
REQUEST_TIMEOUT_SEC = 10


def is_telegram_configured() -> bool:
    return bool(
        getattr(settings, "TELEGRAM_ENABLED", False)
        and getattr(settings, "TELEGRAM_BOT_TOKEN", "")
        and getattr(settings, "TELEGRAM_CHAT_IDS", None)
    )


def get_chat_ids() -> List[str]:
    return list(getattr(settings, "TELEGRAM_CHAT_IDS", []) or [])


def _ssl_context():
    if getattr(settings, "TELEGRAM_SSL_VERIFY", True):
        return ssl.create_default_context()
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


def _http_json(method: str, url: str, payload: Optional[dict] = None) -> dict:
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(
            req, timeout=REQUEST_TIMEOUT_SEC, context=_ssl_context()
        ) as resp:
            body = resp.read().decode("utf-8")
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(err_body) if err_body else {"ok": False, "description": str(exc)}
        except json.JSONDecodeError:
            return {"ok": False, "description": err_body or str(exc)}
    except urllib.error.URLError as exc:
        return {"ok": False, "description": str(exc.reason if hasattr(exc, "reason") else exc)}


def send_telegram_message(
    text: str,
    chat_ids: Optional[Iterable[str]] = None,
    *,
    parse_mode: Optional[str] = "HTML",
    disable_notification: bool = False,
) -> dict:
    """
    Kirim pesan ke satu/lebih chat.
    Return: {"ok": bool, "sent": int, "errors": [str]}
    """
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    if not getattr(settings, "TELEGRAM_ENABLED", False):
        return {"ok": False, "sent": 0, "errors": ["TELEGRAM_ENABLED=false"]}
    if not token:
        return {"ok": False, "sent": 0, "errors": ["TELEGRAM_BOT_TOKEN kosong"]}

    targets = list(chat_ids) if chat_ids is not None else get_chat_ids()
    if not targets:
        return {"ok": False, "sent": 0, "errors": ["TELEGRAM_CHAT_IDS kosong"]}

    url = f"{TELEGRAM_API}/bot{token}/sendMessage"
    sent = 0
    errors: List[str] = []

    for chat_id in targets:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_notification": disable_notification,
        }
        if parse_mode:
            payload["parse_mode"] = parse_mode
        data = _http_json("POST", url, payload)
        if data.get("ok"):
            sent += 1
        else:
            desc = data.get("description") or "unknown error"
            errors.append(f"chat {chat_id}: {desc}")
            logger.warning("Telegram send failed chat=%s: %s", chat_id, desc)

    return {"ok": sent > 0 and not errors, "sent": sent, "errors": errors}


def get_bot_updates(limit: int = 20, offset: Optional[int] = None, timeout: int = 0) -> dict:
    """
    Ambil update terbaru.
    timeout>0 = long polling (detik). offset = update_id berikutnya.
    """
    token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
    if not token:
        return {"ok": False, "result": [], "error": "TELEGRAM_BOT_TOKEN kosong"}
    params = {"limit": limit, "timeout": max(0, int(timeout))}
    if offset is not None:
        params["offset"] = int(offset)
    qs = urllib.parse.urlencode(params)
    url = f"{TELEGRAM_API}/bot{token}/getUpdates?{qs}"
    # Long poll butuh timeout HTTP > timeout Telegram
    http_timeout = REQUEST_TIMEOUT_SEC + int(params["timeout"]) + 5
    data = None
    headers = {}
    req = urllib.request.Request(url, data=None, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(
            req, timeout=http_timeout, context=_ssl_context()
        ) as resp:
            body = resp.read().decode("utf-8")
            data = json.loads(body) if body else {}
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        try:
            data = json.loads(err_body) if err_body else {"ok": False, "description": str(exc)}
        except json.JSONDecodeError:
            data = {"ok": False, "description": err_body or str(exc)}
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "result": [],
            "error": str(exc.reason if hasattr(exc, "reason") else exc),
        }

    if data.get("ok"):
        return {"ok": True, "result": data.get("result") or []}
    return {
        "ok": False,
        "result": [],
        "error": data.get("description") or "getUpdates failed",
    }


def extract_chat_ids_from_updates(updates: list) -> List[dict]:
    """Dari getUpdates → daftar unik {chat_id, type, title/username}."""
    seen = {}
    for upd in updates or []:
        msg = upd.get("message") or upd.get("my_chat_member") or upd.get("channel_post")
        if not msg:
            continue
        chat = msg.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            continue
        seen[str(chat_id)] = {
            "chat_id": str(chat_id),
            "type": chat.get("type"),
            "title": chat.get("title") or chat.get("username") or chat.get("first_name") or "",
        }
    return list(seen.values())
