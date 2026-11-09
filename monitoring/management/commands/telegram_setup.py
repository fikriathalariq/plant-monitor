"""Setup / uji Telegram bot: temukan chat_id dan kirim pesan tes."""

from django.conf import settings
from django.core.management.base import BaseCommand

from monitoring.utils.telegram_notifier import (
    extract_chat_ids_from_updates,
    get_bot_updates,
    send_telegram_message,
)


class Command(BaseCommand):
    help = "Temukan TELEGRAM_CHAT_IDS dan uji kirim pesan."

    def add_arguments(self, parser):
        parser.add_argument(
            "--discover",
            action="store_true",
            help="Tampilkan chat_id dari getUpdates (kirim /start ke bot dulu).",
        )
        parser.add_argument(
            "--test",
            action="store_true",
            help="Kirim pesan tes ke TELEGRAM_CHAT_IDS di .env.",
        )
        parser.add_argument(
            "--chat-id",
            type=str,
            default="",
            help="Opsional: kirim tes ke chat_id ini saja.",
        )

    def handle(self, *args, **options):
        token = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
        if not token:
            self.stderr.write(self.style.ERROR(
                "TELEGRAM_BOT_TOKEN kosong di .env"
            ))
            return

        self.stdout.write(
            f"Token: ...{token[-8:]} | ENABLED={settings.TELEGRAM_ENABLED} | "
            f"CHAT_IDS={settings.TELEGRAM_CHAT_IDS or '(kosong)'}"
        )

        if options["discover"]:
            self._discover()
        if options["test"] or options["chat_id"]:
            self._test(options.get("chat_id") or "")
        if not options["discover"] and not options["test"] and not options["chat_id"]:
            self.stdout.write(
                "Gunakan --discover dan/atau --test\n"
                "1) Buka t.me/suritex_energi_bot, kirim /start (atau undang ke grup)\n"
                "2) python manage.py telegram_setup --discover\n"
                "3) Isi TELEGRAM_CHAT_IDS di .env\n"
                "4) python manage.py telegram_setup --test"
            )

    def _discover(self):
        self.stdout.write("Mengambil getUpdates...")
        data = get_bot_updates(limit=50)
        if not data.get("ok"):
            self.stderr.write(self.style.ERROR(
                f"Gagal: {data.get('error')}"
            ))
            return

        chats = extract_chat_ids_from_updates(data.get("result") or [])
        if not chats:
            self.stdout.write(self.style.WARNING(
                "Belum ada chat. Buka bot, kirim /start, lalu jalankan ulang --discover."
            ))
            return

        self.stdout.write(self.style.SUCCESS("Chat ditemukan:"))
        for c in chats:
            self.stdout.write(
                f"  chat_id={c['chat_id']}  type={c['type']}  name={c['title']}"
            )
        ids = ",".join(c["chat_id"] for c in chats)
        self.stdout.write(
            f"\nTambahkan ke .env:\nTELEGRAM_CHAT_IDS={ids}"
        )

    def _test(self, chat_id: str):
        targets = [chat_id] if chat_id else None
        text = (
            "✅ <b>Plant Monitor</b>\n"
            "Tes koneksi Telegram berhasil.\n"
            "Bot siap untuk alert No Signal."
        )
        result = send_telegram_message(text, chat_ids=targets)
        if result["sent"]:
            self.stdout.write(self.style.SUCCESS(
                f"Terkirim ke {result['sent']} chat."
            ))
        if result["errors"]:
            self.stderr.write(self.style.ERROR(
                "; ".join(result["errors"])
            ))
