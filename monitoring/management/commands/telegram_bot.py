"""
Long-polling listener untuk command bot Telegram (fase 1).
Hanya chat di TELEGRAM_CHAT_IDS yang dilayani.
"""

import time

from django.conf import settings
from django.core.management.base import BaseCommand

from monitoring.utils.telegram_commands import is_chat_allowed, parse_and_handle
from monitoring.utils.telegram_notifier import get_bot_updates, send_telegram_message


class Command(BaseCommand):
    help = "Listener command Telegram bot (long polling)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout",
            type=int,
            default=25,
            help="Long-poll timeout detik (default 25).",
        )

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
        if not token:
            self.stderr.write(self.style.ERROR("TELEGRAM_BOT_TOKEN kosong."))
            return
        if not getattr(settings, "TELEGRAM_ENABLED", False):
            self.stderr.write(self.style.ERROR("TELEGRAM_ENABLED=false."))
            return

        timeout = max(5, int(options["timeout"]))
        offset = None
        self.stdout.write(self.style.SUCCESS(
            f"Start telegram_bot (timeout={timeout}s, "
            f"allowlist={settings.TELEGRAM_CHAT_IDS}). CTRL+C untuk berhenti."
        ))

        # Buang update lama agar tidak memproses backlog saat start
        boot = get_bot_updates(limit=100, offset=offset, timeout=0)
        if boot.get("ok") and boot.get("result"):
            last = boot["result"][-1]["update_id"]
            offset = last + 1
            self.stdout.write(f"Skip {len(boot['result'])} update lama, offset={offset}")

        try:
            while True:
                data = get_bot_updates(limit=50, offset=offset, timeout=timeout)
                if not data.get("ok"):
                    err = data.get("error") or "unknown"
                    self.stdout.write(self.style.WARNING(f"getUpdates: {err}"))
                    time.sleep(3)
                    continue

                for upd in data.get("result") or []:
                    offset = upd["update_id"] + 1
                    msg = upd.get("message") or upd.get("edited_message")
                    if not msg:
                        continue
                    chat = msg.get("chat") or {}
                    chat_id = chat.get("id")
                    text = msg.get("text") or ""
                    if chat_id is None:
                        continue

                    if not is_chat_allowed(chat_id):
                        self.stdout.write(
                            f"Ignore chat {chat_id} (bukan allowlist)"
                        )
                        continue

                    self.stdout.write(
                        f"← {chat_id}: {text[:80]!r}"
                    )
                    try:
                        reply = parse_and_handle(text)
                    except Exception as exc:
                        self.stdout.write(self.style.ERROR(f"Handler error: {exc}"))
                        reply = "Terjadi error saat memproses perintah."

                    if not reply:
                        continue

                    result = send_telegram_message(
                        reply, chat_ids=[str(chat_id)]
                    )
                    if result["errors"]:
                        self.stdout.write(self.style.ERROR(
                            "; ".join(result["errors"])
                        ))
                    else:
                        self.stdout.write(f"→ balas OK ({result['sent']})")

        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Dihentikan user (CTRL+C)."))
