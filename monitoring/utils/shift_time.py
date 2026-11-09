"""Utilitas waktu shift operasional (06:00–06:00)."""
from datetime import datetime, timedelta

from django.utils import timezone

TOTAL_BUCKETS = 24 * 60  # 1440 menit per shift


def current_shift_start(now=None):
    """Awal shift operasional (06:00) yang sedang berjalan."""
    now = timezone.localtime(now or timezone.now())
    base = now.replace(hour=6, minute=0, second=0, microsecond=0)
    if now.hour < 6:
        base -= timedelta(days=1)
    return base


def shift_bounds(shift_date):
    """
    Kembalikan (shift_start, full_end) aware datetime untuk tanggal awal shift.
    shift_date: datetime.date
    """
    shift_start = timezone.make_aware(
        datetime.combine(shift_date, datetime.min.time()).replace(
            hour=6, minute=0, second=0, microsecond=0
        )
    )
    full_end = shift_start + timedelta(days=1)
    return shift_start, full_end


def hour_axis_labels():
    """Label sumbu-X: 06, 07, …, 05, 06 (25 titik untuk 24 jam)."""
    labels = []
    for i in range(25):
        hour = (6 + i) % 24
        labels.append({
            "label": f"{hour:02d}",
            "pct": round(i / 24 * 100, 3),
        })
    return labels


def minutes_to_pct(minutes, total=TOTAL_BUCKETS):
    return round(minutes / total * 100, 4)


def pct_to_minutes(pct, total=TOTAL_BUCKETS):
    return round((pct / 100) * total)


def get_current_operational_shift(now=None):
    """
    Menghitung shift operasional pabrik yang sedang berjalan saat ini:
    - Shift 1 - Pagi : 06:00 - 14:00 (06:00:00 - 13:59:59)
    - Shift 2 - Siang: 14:00 - 22:00 (14:00:00 - 21:59:59)
    - Shift 3 - Malam: 22:00 - 06:00 (22:00:00 - 05:59:59)
    """
    local_dt = timezone.localtime(now or timezone.now())
    hour = local_dt.hour
    if 6 <= hour < 14:
        shift_num = 1
        shift_tag = "Pagi"
        shift_window = "06:00 - 14:00"
    elif 14 <= hour < 22:
        shift_num = 2
        shift_tag = "Siang"
        shift_window = "14:00 - 22:00"
    else:
        shift_num = 3
        shift_tag = "Malam"
        shift_window = "22:00 - 06:00"

    return {
        "num": shift_num,
        "tag": shift_tag,
        "name": f"Shift {shift_num} - {shift_tag}",
        "code": f"SHIFT_{shift_num}",
        "window": shift_window,
    }
