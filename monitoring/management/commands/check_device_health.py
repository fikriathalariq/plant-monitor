"""
Cek mesin AUTO yang dipoll JUMO tanpa pembacaan valid,
buat/resolve Alert NO_SIGNAL, dan kirim Telegram pada transisi.
"""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from django.utils.html import escape

from monitoring.services.jumo_config import get_channel_meta
from monitoring.models import Alert, Machine
from monitoring.utils.signal_freshness import get_polled_machine_codes
from monitoring.utils.telegram_notifier import is_telegram_configured, send_telegram_message


def _channel_meta():
    """code -> {controller, ip, channel_index}"""
    return get_channel_meta()

def _format_lost(machine, age_min, threshold_min, meta):
    info = meta.get(machine.code) or {}
    ctrl = info.get("controller") or "-"
    ip = info.get("ip") or "-"
    ch = info.get("channel_index")
    ch_label = f"ch{ch}" if ch else "-"
    last = (
        timezone.localtime(machine.last_valid_reading_at).strftime("%H:%M:%S")
        if machine.last_valid_reading_at
        else "-"
    )
    return (
        f"⚠️ <b>No Signal — {escape(machine.code)}</b>\n"
        f"Mesin: {escape(machine.name or machine.code)}\n"
        f"Pembacaan valid terakhir: {escape(last)}\n"
        f"Umur: {age_min:.0f} menit (ambang {threshold_min:.0f} mnt)\n"
        f"Controller: {escape(ctrl)} ({escape(ip)}) {escape(ch_label)}"
    )


def _format_recovered(machine, meta):
    info = meta.get(machine.code) or {}
    ctrl = info.get("controller") or "-"
    temp = machine.temperature
    temp_s = f"{temp:.1f}" if temp is not None else "-"
    unit = machine.unit_symbol or "°C"
    return (
        f"✅ <b>Recovered — {escape(machine.code)}</b>\n"
        f"Mesin: {escape(machine.name or machine.code)}\n"
        f"Sinyal kembali. Suhu: {escape(temp_s)} {escape(unit)}\n"
        f"Controller: {escape(ctrl)}"
    )


class Command(BaseCommand):
    help = "Monitor No Signal (last_valid_reading_at) + kirim Telegram pada transisi."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Jalankan satu siklus lalu keluar (untuk Task Scheduler).",
        )
        parser.add_argument(
            "--interval",
            type=int,
            default=60,
            help="Interval detik antar siklus (default 60).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Deteksi saja, jangan tulis Alert / kirim Telegram.",
        )

    def handle(self, *args, **options):
        import time

        once = options["once"]
        interval = max(15, int(options["interval"]))
        dry_run = options["dry_run"]
        threshold_min = float(getattr(settings, "TELEGRAM_NO_SIGNAL_MINUTES", 3) or 3)
        threshold = timedelta(minutes=threshold_min)
        meta = _channel_meta()
        polled = get_polled_machine_codes()

        self.stdout.write(self.style.SUCCESS(
            f"Start check_device_health "
            f"(threshold={threshold_min}m, telegram="
            f"{'ON' if is_telegram_configured() else 'OFF'}, "
            f"dry_run={dry_run}). CTRL+C untuk berhenti."
        ))

        try:
            while True:
                self._run_cycle(polled, threshold, threshold_min, meta, dry_run)
                if once:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            self.stdout.write(self.style.WARNING("Dihentikan user (CTRL+C)."))

    def _run_cycle(self, polled, threshold, threshold_min, meta, dry_run):
        now = timezone.now()
        ts = timezone.localtime(now).strftime("%H:%M:%S")
        machines = list(
            Machine.objects.filter(
                is_active=True,
                operation_mode="AUTO",
                code__in=polled,
            )
        )

        stale_ids = set()
        created = 0
        resolved = 0

        for m in machines:
            reading_at = m.last_valid_reading_at
            if reading_at is None:
                continue
            age = now - reading_at
            if age <= threshold:
                continue

            stale_ids.add(m.id)
            age_min = age.total_seconds() / 60.0
            active = Alert.objects.filter(
                machine=m,
                alert_type=Alert.TYPE_NO_SIGNAL,
                is_active=True,
            ).exists()

            if active:
                continue

            self.stdout.write(
                f"[{ts}] NO_SIGNAL {m.code} age={age_min:.1f}m"
            )
            if dry_run:
                continue

            Alert.objects.create(
                severity=Alert.SEVERITY_WARNING,
                alert_type=Alert.TYPE_NO_SIGNAL,
                machine=m,
                title=f"No Signal — {m.code}",
                message=(
                    f"Tidak ada pembacaan valid selama {age_min:.0f} menit "
                    f"(ambang {threshold_min:.0f} menit)."
                ),
                current_value=round(age_min, 2),
                threshold_value=threshold_min,
                is_active=True,
            )
            created += 1
            if is_telegram_configured():
                result = send_telegram_message(
                    _format_lost(m, age_min, threshold_min, meta)
                )
                if result["errors"]:
                    self.stdout.write(self.style.ERROR(
                        f"  Telegram error: {'; '.join(result['errors'])}"
                    ))

        # Resolve alerts yang sudah pulih
        active_alerts = (
            Alert.objects.filter(
                alert_type=Alert.TYPE_NO_SIGNAL,
                is_active=True,
                machine_id__isnull=False,
            )
            .select_related("machine")
        )
        for alert in active_alerts:
            m = alert.machine
            if not m or m.id in stale_ids:
                continue
            # Pulih jika ada reading baru dalam threshold, atau mesin tidak lagi AUTO/polled
            reading_at = m.last_valid_reading_at
            recovered = (
                reading_at is not None
                and (now - reading_at) <= threshold
            )
            if not recovered:
                continue

            self.stdout.write(f"[{ts}] RECOVERED {m.code}")
            if dry_run:
                continue

            alert.is_active = False
            alert.save(update_fields=["is_active"])
            resolved += 1
            if is_telegram_configured():
                result = send_telegram_message(_format_recovered(m, meta))
                if result["errors"]:
                    self.stdout.write(self.style.ERROR(
                        f"  Telegram error: {'; '.join(result['errors'])}"
                    ))

        self.stdout.write(
            f"[{ts}] cycle done — stale={len(stale_ids)} "
            f"created={created} resolved={resolved}"
        )
