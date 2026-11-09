"""Parse & handle perintah Telegram fase 1 (read-only)."""

from __future__ import annotations

import re
from typing import Optional

from django.utils import timezone
from django.utils.html import escape

from monitoring.services.jumo_config import get_channel_meta
from monitoring.models import Alert, Machine, MachineGroup
from monitoring.utils.signal_freshness import (
    STATUS_NO_SIGNAL,
    get_machine_display_status,
    get_polled_machine_codes,
    is_signal_stale,
)

MAX_MESSAGE_LEN = 3900

HELP_TEXT = (
    "<b>Plant Monitor Bot</b> (fase 1 - baca saja)\n\n"
    "/help - daftar perintah\n"
    "/status KODE - detail mesin (atau ketik saja KODE)\n"
    "/nosignal - mesin tanpa sinyal\n"
    "/alerts - alert aktif\n"
    "/heat - mesin HEAT / STEADY / Running\n"
    "/steam - tekanan uap &amp; suhu HTO\n"
    "/group [nama|kode] - ringkas per grup\n"
    "/summary - ringkasan plant\n\n"
    "Contoh: <code>/status JR_12</code> atau <code>JR_12</code>"
)


def _channel_meta():
    return get_channel_meta()


def _clip(text: str) -> str:
    if len(text) <= MAX_MESSAGE_LEN:
        return text
    return text[: MAX_MESSAGE_LEN - 20] + "\n… (dipotong)"


def _fmt_temp(machine: Machine) -> str:
    t = machine.temperature
    if t is None:
        return "-"
    unit = machine.unit_symbol or "°C"
    return f"{t:.1f} {unit}"


def _fmt_age(dt) -> str:
    if not dt:
        return "-"
    local = timezone.localtime(dt)
    age_sec = (timezone.now() - dt).total_seconds()
    if age_sec < 60:
        age = f"{age_sec:.0f} dtk"
    elif age_sec < 3600:
        age = f"{age_sec / 60:.0f} mnt"
    else:
        age = f"{age_sec / 3600:.1f} jam"
    return f"{local.strftime('%H:%M:%S')} ({age} lalu)"


def _normalize_code(raw: str) -> str:
    s = (raw or "").strip().upper().replace(" ", "_")
    s = re.sub(r"_+", "_", s)
    return s


def _find_machine(code_raw: str) -> Optional[Machine]:
    code = _normalize_code(code_raw)
    if not code:
        return None
    qs = Machine.objects.filter(is_active=True).select_related("group")
    m = qs.filter(code__iexact=code).first()
    if m:
        return m
    # JR12 → JR_12, JD4 → JD_04
    m = qs.filter(code__iexact=code.replace("_", "")).first()
    if m:
        return m
    compact = code.replace("_", "")
    for cand in qs:
        if cand.code.replace("_", "").upper() == compact:
            return cand
    # partial name
    m = qs.filter(name__icontains=code_raw.strip()).first()
    return m


def cmd_help(_args: str = "") -> str:
    return HELP_TEXT


def cmd_status(args: str) -> str:
    if not (args or "").strip():
        return "Pakai: <code>/status JR_12</code> atau ketik <code>JR_12</code>"
    m = _find_machine(args)
    if not m:
        return f"Mesin <code>{escape(_normalize_code(args))}</code> tidak ditemukan."

    status = get_machine_display_status(m)
    meta = _channel_meta().get(m.code) or {}
    lines = [
        f"<b>{escape(m.code)}</b> - {escape(m.name or m.code)}",
        f"Status: <b>{escape(status)}</b>",
        f"Mode: {escape(m.operation_mode or '-')}",
    ]
    if m.operation_mode == "MANUAL":
        lines.append(f"Manual: {escape(m.manual_status or 'Stop')}")
    else:
        lines.append(f"Thermal: {escape(m.last_thermal_status or 'OFFLINE')}")

    temp_label = "Suhu (terakhir)" if status == STATUS_NO_SIGNAL else "Suhu"
    lines.append(f"{temp_label}: {_fmt_temp(m)}")

    if m.temperature_gradient is not None:
        lines.append(f"Gradient: {m.temperature_gradient:.3f} °C/mnt")

    if m.group_id:
        g = m.group
        lines.append(f"Grup: {escape(g.name)} ({escape(g.code)})")

    if m.code in get_polled_machine_codes():
        lines.append(f"Valid terakhir: {_fmt_age(m.last_valid_reading_at)}")
        ctrl = meta.get("controller") or "-"
        ip = meta.get("ip") or "-"
        ch = meta.get("channel_index")
        ch_s = f"ch{ch}" if ch else "-"
        lines.append(f"Controller: {escape(ctrl)} ({escape(ip)}) {escape(ch_s)}")

    return _clip("\n".join(lines))


def cmd_nosignal(_args: str = "") -> str:
    now = timezone.now()
    polled = get_polled_machine_codes()
    machines = (
        Machine.objects.filter(is_active=True, operation_mode="AUTO", code__in=polled)
        .order_by("code")
    )
    rows = []
    for m in machines:
        if not is_signal_stale(m, now=now):
            continue
        age_min = (
            (now - m.last_valid_reading_at).total_seconds() / 60.0
            if m.last_valid_reading_at
            else 0
        )
        rows.append((age_min, m))
    rows.sort(key=lambda x: -x[0])

    if not rows:
        return "OK - Tidak ada mesin No Signal."

    lines = [f"<b>No Signal ({len(rows)})</b>:"]
    for age_min, m in rows[:40]:
        lines.append(
            f"- <code>{escape(m.code)}</code> - {age_min:.0f} mnt - {_fmt_temp(m)}"
        )
    if len(rows) > 40:
        lines.append(f"… +{len(rows) - 40} lagi")
    return _clip("\n".join(lines))


def cmd_alerts(_args: str = "") -> str:
    alert_list = list(
        Alert.objects.filter(is_active=True)
        .select_related("machine")
        .order_by("-created_at")[:40]
    )
    if not alert_list:
        return "OK - Tidak ada alert aktif."

    lines = [f"<b>Alert aktif ({len(alert_list)})</b>:"]
    for a in alert_list:
        code = a.machine.code if a.machine else "-"
        when = timezone.localtime(a.created_at).strftime("%d/%m %H:%M")
        lines.append(
            f"- [{escape(a.severity)}] {escape(a.alert_type)} "
            f"<code>{escape(code)}</code> - {escape(a.title)} ({when})"
        )
    return _clip("\n".join(lines))


def cmd_heat(_args: str = "") -> str:
    machines = Machine.objects.filter(is_active=True).select_related("group").order_by("code")
    rows = []
    for m in machines:
        if m.group and m.group.code == "MC_BOILER":
            continue
        status = get_machine_display_status(m)
        if status not in ("HEAT", "STEADY", "Running"):
            continue
        rows.append((status, m))

    if not rows:
        return "Tidak ada mesin HEAT / STEADY / Running."

    lines = [f"<b>Aktif produksi ({len(rows)})</b>:"]
    for status, m in rows[:50]:
        lines.append(
            f"- <code>{escape(m.code)}</code> {escape(status)} - {_fmt_temp(m)}"
        )
    if len(rows) > 50:
        lines.append(f"… +{len(rows) - 50} lagi")
    return _clip("\n".join(lines))


def cmd_steam(_args: str = "") -> str:
    steam = Machine.objects.filter(code="Steam_Pr", is_active=True).first()
    oil = Machine.objects.filter(code="Oil_Temp", is_active=True).first()
    lines = ["<b>Energi</b>:"]
    if steam:
        st = get_machine_display_status(steam)
        lines.append(
            f"Steam_Pr: {_fmt_temp(steam)} — {escape(st)}\n"
            f"  valid: {_fmt_age(steam.last_valid_reading_at)}"
        )
    else:
        lines.append("Steam_Pr: (tidak ada di DB)")
    if oil:
        st = get_machine_display_status(oil)
        lines.append(
            f"Oil_Temp: {_fmt_temp(oil)} — {escape(st)}\n"
            f"  valid: {_fmt_age(oil.last_valid_reading_at)}"
        )
    else:
        lines.append("Oil_Temp: (tidak ada di DB)")
    return "\n".join(lines)


def cmd_group(args: str) -> str:
    arg = (args or "").strip()
    groups = list(MachineGroup.objects.all().order_by("code"))
    if not arg:
        lines = ["<b>Grup mesin</b> - pakai <code>/group KODE</code> atau nama:"]
        for g in groups:
            n = Machine.objects.filter(is_active=True, group=g).count()
            lines.append(f"- <code>{escape(g.code)}</code> {escape(g.name)} ({n})")
        return _clip("\n".join(lines))

    g = None
    key = arg.upper()
    for cand in groups:
        if cand.code.upper() == key or key in (cand.name or "").upper():
            g = cand
            break
    if not g:
        return f"Grup <code>{escape(arg)}</code> tidak ditemukan. Coba /group tanpa argumen."

    machines = list(
        Machine.objects.filter(is_active=True, group=g).order_by("code")
    )
    counts = {"HEAT": 0, "STEADY": 0, "Running": 0, "COOL": 0, "No Signal": 0, "OFF": 0}
    lines_m = []
    for m in machines:
        status = get_machine_display_status(m)
        if status == STATUS_NO_SIGNAL:
            counts["No Signal"] += 1
        elif status in counts:
            counts[status] += 1
        elif status in ("OFF", "OFFLINE", "Offline", "Stop"):
            counts["OFF"] += 1
        else:
            counts["OFF"] += 1
        lines_m.append(f"- <code>{escape(m.code)}</code> {escape(status)} {_fmt_temp(m)}")

    summary = (
        f"<b>{escape(g.code)}</b> - {escape(g.name)} ({len(machines)} mesin)\n"
        f"HEAT {counts['HEAT']} | KEEP {counts['STEADY']} | RUN {counts['Running']} | "
        f"COOL {counts['COOL']} | NOSIG {counts['No Signal']} | OFF {counts['OFF']}"
    )
    return _clip(summary + "\n" + "\n".join(lines_m[:45]))


def cmd_summary(_args: str = "") -> str:
    machines = list(
        Machine.objects.filter(is_active=True).select_related("group")
    )
    total = 0
    heat = steady = running = cool = nosig = manual_on = offline = 0
    for m in machines:
        if m.group and m.group.code == "MC_BOILER":
            # tetap hitung steam di bawah, skip dari total produksi
            pass
        total += 1
        status = get_machine_display_status(m)
        if status == STATUS_NO_SIGNAL:
            nosig += 1
        elif status == "HEAT":
            heat += 1
        elif status == "STEADY":
            steady += 1
        elif status == "Running":
            running += 1
        elif status == "COOL":
            cool += 1
        elif status in ("OFFLINE", "Offline", "OFF", "Stop"):
            offline += 1
        if m.operation_mode == "MANUAL" and m.manual_status == "Running":
            manual_on += 1

    steam = Machine.objects.filter(code="Steam_Pr", is_active=True).first()
    oil = Machine.objects.filter(code="Oil_Temp", is_active=True).first()
    alerts_n = Alert.objects.filter(is_active=True).count()
    now_s = timezone.localtime().strftime("%H:%M:%S")

    lines = [
        f"<b>Ringkasan Plant</b> ({now_s})",
        f"Mesin aktif DB: {total}",
        f"HEAT {heat} | KEEP {steady} | RUN {running} | COOL {cool}",
        f"No Signal {nosig} | Offline/Stop {offline} | Manual ON {manual_on}",
        f"Alert aktif: {alerts_n}",
    ]
    if steam:
        lines.append(f"Steam: {_fmt_temp(steam)} ({escape(get_machine_display_status(steam))})")
    if oil:
        lines.append(f"HTO: {_fmt_temp(oil)} ({escape(get_machine_display_status(oil))})")
    return "\n".join(lines)


COMMANDS = {
    "start": cmd_help,
    "help": cmd_help,
    "status": cmd_status,
    "nosignal": cmd_nosignal,
    "alerts": cmd_alerts,
    "heat": cmd_heat,
    "steam": cmd_steam,
    "group": cmd_group,
    "summary": cmd_summary,
}


def parse_and_handle(text: str) -> Optional[str]:
    """
    Parse pesan user → balasan HTML, atau None jika diabaikan.
    """
    if not text:
        return None
    raw = text.strip()
    if not raw:
        return None

    # /cmd@botname args
    if raw.startswith("/"):
        body = raw[1:]
        parts = body.split(maxsplit=1)
        cmd = parts[0].split("@", 1)[0].lower()
        args = parts[1] if len(parts) > 1 else ""
        handler = COMMANDS.get(cmd)
        if not handler:
            return (
                f"Perintah <code>/{escape(cmd)}</code> tidak dikenal.\n"
                "Ketik /help untuk daftar perintah."
            )
        return handler(args)

    # Alias: ketik kode mesin saja
    if re.match(r"^[A-Za-z0-9][A-Za-z0-9_\-\s]{1,40}$", raw):
        maybe = _find_machine(raw)
        if maybe:
            return cmd_status(raw)

    return (
        "Tidak mengerti. Ketik /help atau kode mesin, contoh <code>JR_12</code>."
    )


def is_chat_allowed(chat_id) -> bool:
    from monitoring.utils.telegram_notifier import get_chat_ids

    allowed = set(get_chat_ids())
    return str(chat_id) in allowed
