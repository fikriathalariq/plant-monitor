"""
Kirim Telegram setiap kali mesin berubah status
(sumber sama dengan dashboard: status_changed_at + previous_display_status).
"""

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.html import escape

from monitoring.models import Machine
from monitoring.utils.signal_freshness import get_machine_display_status, STATUS_NO_SIGNAL
from monitoring.utils.telegram_notifier import is_telegram_configured, send_telegram_message

# Status "hilang sinyal / offline" dianggap setara — jangan spam Telegram
_LOST_SIGNAL_STATUSES = {
    "Offline",
    "OFFLINE",
    "No Signal",
    STATUS_NO_SIGNAL,
    "OFF",
}


def _is_noise_transition(old_display: str, new_display: str) -> bool:
    """True jika hanya flip antar label lost-signal (Offline <-> No Signal, dll)."""
    o = (old_display or "").strip()
    n = (new_display or "").strip()
    if o == n:
        return True
    return o in _LOST_SIGNAL_STATUSES and n in _LOST_SIGNAL_STATUSES


def _change_type(old_display: str, new_display: str) -> str:
    old = old_display or ""
    new = new_display or ""
    if new == "Running" and old != "Running":
        return "good"
    if new in ("HEAT", "STEADY") and old in (
        "Stop", "OFF", "OFFLINE", "Offline", "No Signal", "Warning", "COOL",
    ):
        return "good"
    if new in ("Stop", "Offline", "Warning", "OFFLINE", "OFF", "No Signal", "COOL") and old in (
        "Running", "HEAT", "STEADY",
    ):
        return "bad"
    if new == "Warning":
        return "warning"
    return "neutral"


def _emoji(change_type: str) -> str:
    return {
        "good": "✅",
        "bad": "🔴",
        "warning": "⚠️",
        "neutral": "🔄",
    }.get(change_type, "🔄")


def _format_change(machine, old_display, new_display, changed_at) -> str:
    local = timezone.localtime(changed_at)
    ctype = _change_type(old_display, new_display)
    group = machine.group.name if getattr(machine, "group_id", None) and machine.group else "-"
    mode = machine.operation_mode or "-"
    temp = machine.temperature
    unit = machine.unit_symbol or "°C"
    temp_s = f"{temp:.1f} {unit}" if temp is not None else "-"

    return (
        f"{_emoji(ctype)} <b>Status — {escape(machine.code)}</b>\n"
        f"Mesin: {escape(machine.name or machine.code)}\n"
        f"Group: {escape(group)} | Mode: {escape(mode)}\n"
        f"<b>{escape(old_display or '?')}</b> → <b>{escape(new_display or '?')}</b>\n"
        f"Waktu: {escape(local.strftime('%d/%m %H:%M:%S'))}\n"
        f"Suhu: {escape(temp_s)}"
    )


class Command(BaseCommand):
    help = (
        "Pantau perubahan status mesin (status_changed_at) "
        "dan kirim notifikasi Telegram — mirip dashboard."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Satu siklus lalu keluar.",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=30,
            help="Interval detik antar cek (default 30).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Deteksi saja, jangan kirim Telegram.",
        )

    def handle(self, *args, **options):
        import time

        once = options["once"]
        interval = max(10, int(options["interval"]))
        dry_run = options["dry_run"]
        enabled = getattr(settings, "TELEGRAM_STATUS_CHANGES", True)

        self.stdout.write(self.style.SUCCESS(
            f"Start notify_status_changes "
            f"(interval={interval}s, telegram="
            f"{'ON' if is_telegram_configured() and enabled else 'OFF'}, "
            f"dry_run={dry_run}). CTRL+C untuk berhenti."
        ))

        # Seed: jangan flood notifikasi lama saat proses baru start
        last_seen = {}
        for m in Machine.objects.filter(
            is_active=True, status_changed_at__isnull=False
        ).only("id", "status_changed_at"):
            last_seen[m.id] = m.status_changed_at

        self.stdout.write(
            f"  Seeded {len(last_seen)} mesin (hanya perubahan BARU yang dikirim)."
        )

        try:
            while True:
                self._run_cycle(last_seen, enabled, dry_run)
                if once:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Dihentikan user (CTRL+C)."))

    def _run_cycle(self, last_seen, enabled, dry_run):
        now = timezone.now()
        ts = timezone.localtime(now).strftime("%H:%M:%S")

        machines = (
            Machine.objects.filter(
                is_active=True,
                status_changed_at__isnull=False,
            )
            .select_related("group")
            .order_by("status_changed_at")
        )

        sent = 0
        skipped = 0

        for m in machines:
            changed_at = m.status_changed_at
            prev_ts = last_seen.get(m.id)
            if prev_ts is not None and changed_at <= prev_ts:
                continue

            # Update fingerprint dulu agar restart/mid-cycle tidak double-send
            last_seen[m.id] = changed_at

            old_display = m.previous_display_status or "?"
            new_display = get_machine_display_status(m, now=now)

            if _is_noise_transition(old_display, new_display):
                skipped += 1
                continue

            self.stdout.write(
                f"[{ts}] {m.code}: {old_display} → {new_display}"
            )

            if dry_run or not enabled:
                continue
            if not is_telegram_configured():
                continue

            result = send_telegram_message(
                _format_change(m, old_display, new_display, changed_at)
            )
            if result.get("ok"):
                sent += 1
            elif result.get("errors"):
                self.stdout.write(self.style.ERROR(
                    f"  Telegram error: {'; '.join(result['errors'])}"
                ))

        self.stdout.write(
            f"[{ts}] cycle done — notified={sent} skipped_same={skipped}"
        )
