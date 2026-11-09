from ninja import Router, Schema
from ninja.errors import HttpError
from typing import List, Optional, Any, Dict
from django.contrib.auth.models import User
from django.db.models import Q, Count
from django.utils import timezone
from django.core.cache import cache
from django.shortcuts import get_object_or_404

from monitoring.models import DirectConversation, DirectMessage, Machine, MachineMinuteLog
from monitoring.utils.signal_freshness import get_machine_display_status

chat_router = Router(tags=["Chat"])

def _require_auth(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Silakan login terlebih dahulu")
    return request.user

# Schemas
class SendMessageSchema(Schema):
    content: str = ""
    message_type: str = "TEXT"  # TEXT, REPORT_SHARE, MACHINE_SNAPSHOT, CHART_BOOKMARK, ACTION_CHECK
    metadata: Dict[str, Any] = {}
    reply_to_id: Optional[int] = None

@chat_router.get("/contacts")
def list_contacts(request):
    """
    Daftar seluruh kontak aktif di jaringan lokal beserta info operator,
    status online (in-memory cache), ringkasan pesan terakhir, dan unread badge.
    """
    user = _require_auth(request)

    # Refresh online status pemanggil
    cache.set(f"user_online_{user.id}", timezone.now().timestamp(), timeout=180)

    # Ambil user aktif lain
    other_users = (
        User.objects.filter(is_active=True)
        .exclude(id=user.id)
        .select_related("operatorprofile__position", "operatorprofile__shift")
    )

    # Ambil conversation yang melibatkan current user
    conversations = DirectConversation.objects.filter(
        Q(user1=user) | Q(user2=user)
    ).select_related("user1", "user2")

    conv_map = {}
    for c in conversations:
        other_id = c.user2_id if c.user1_id == user.id else c.user1_id
        conv_map[other_id] = c

    # Hitung unread count per sender
    unread_counts = dict(
        DirectMessage.objects.filter(
            conversation__in=conversations,
            is_read=False
        ).exclude(sender=user)
        .values("sender_id")
        .annotate(cnt=Count("id"))
        .values_list("sender_id", "cnt")
    )

    now_ts = timezone.now().timestamp()
    contacts = []

    for u in other_users:
        profile = getattr(u, "operatorprofile", None)
        disp_name = (
            profile.display_name
            if profile and profile.display_name
            else (f"{u.first_name} {u.last_name}".strip() or u.username)
        )
        pos_name = (
            profile.position.name
            if profile and profile.position
            else ("Superuser" if u.is_superuser else ("Staff" if u.is_staff else "Operator"))
        )
        shift_name = profile.shift.name if profile and profile.shift else "-"

        # Online jika last ping < 150 detik (2.5 menit)
        last_seen = cache.get(f"user_online_{u.id}")
        is_online = bool(last_seen and (now_ts - float(last_seen) < 150))

        conv = conv_map.get(u.id)
        last_msg_at = conv.last_message_at.isoformat() if conv and conv.last_message_at else None
        last_msg_preview = conv.last_message_preview if conv else ""
        unread_cnt = unread_counts.get(u.id, 0)

        contacts.append({
            "id": u.id,
            "username": u.username,
            "display_name": disp_name,
            "position": pos_name,
            "shift": shift_name,
            "is_online": is_online,
            "unread_count": unread_cnt,
            "last_message_preview": last_msg_preview,
            "last_message_at": last_msg_at,
        })

    # Sort contacts: unread first, then by last_message_at DESC, then display_name ASC
    def sort_key(c):
        has_unread = 1 if c["unread_count"] > 0 else 0
        last_at = c["last_message_at"] or ""
        return (has_unread, last_at, c["display_name"])

    contacts.sort(key=sort_key, reverse=True)
    return {"contacts": contacts}


@chat_router.get("/unread-summary")
def get_unread_summary(request):
    """
    Endpoint super ringan untuk polling unread badge di Header/FAB.
    """
    user = _require_auth(request)
    cache.set(f"user_online_{user.id}", timezone.now().timestamp(), timeout=180)

    total_unread = DirectMessage.objects.filter(
        Q(conversation__user1=user) | Q(conversation__user2=user),
        is_read=False
    ).exclude(sender=user).count()

    return {"total_unread": total_unread}


def _serialize_message(m):
    reply_preview = None
    if m.reply_to:
        reply_preview = {
            "id": m.reply_to.id,
            "sender_name": getattr(getattr(m.reply_to.sender, 'operatorprofile', None), 'display_name', None) or m.reply_to.sender.username,
            "content": m.reply_to.content[:80],
            "message_type": m.reply_to.message_type,
        }

    sender_disp = getattr(getattr(m.sender, 'operatorprofile', None), 'display_name', None) or m.sender.username

    return {
        "id": m.id,
        "sender_id": m.sender_id,
        "sender_username": m.sender.username,
        "sender_name": sender_disp,
        "message_type": m.message_type,
        "content": m.content,
        "metadata": m.metadata or {},
        "reply_to": reply_preview,
        "is_read": m.is_read,
        "read_at": m.read_at.isoformat() if m.read_at else None,
        "created_at": m.created_at.isoformat(),
    }


@chat_router.get("/messages/{other_user_id}")
def get_messages(request, other_user_id: int, after_id: int = 0, limit: int = 50):
    """
    Mengambil pesan obrolan dengan other_user_id.
    Mendukung delta polling jika after_id > 0.
    Otomatis menandai pesan yang ditujukan ke pemanggil sebagai sudah dibaca (is_read=True).
    """
    user = _require_auth(request)
    cache.set(f"user_online_{user.id}", timezone.now().timestamp(), timeout=180)

    other_user = get_object_or_404(User, id=other_user_id, is_active=True)
    conv = DirectConversation.get_or_create_conversation(user, other_user)

    # Tandai pesan masuk sebagai terbaca
    unread_incoming = conv.messages.filter(sender=other_user, is_read=False)
    if unread_incoming.exists():
        unread_incoming.update(is_read=True, read_at=timezone.now())

    qs = conv.messages.select_related("sender__operatorprofile", "reply_to__sender__operatorprofile")

    if after_id > 0:
        msgs = qs.filter(id__gt=after_id).order_by("created_at")
    else:
        # Ambil N pesan terakhir, diurutkan ascending
        msgs = qs.order_by("-created_at")[:limit]
        msgs = list(reversed(msgs))

    return {
        "conversation_id": conv.id,
        "messages": [_serialize_message(m) for m in msgs]
    }


@chat_router.post("/messages/{other_user_id}")
def send_message(request, other_user_id: int, payload: SendMessageSchema):
    """
    Mengirim pesan baru (teks, kartu laporan, snapshot mesin, bookmark grafik, atau konfirmasi tugas).
    """
    user = _require_auth(request)
    cache.set(f"user_online_{user.id}", timezone.now().timestamp(), timeout=180)

    other_user = get_object_or_404(User, id=other_user_id, is_active=True)
    if other_user.id == user.id:
        raise HttpError(400, "Tidak dapat mengirim pesan ke diri sendiri")

    content_clean = payload.content.strip() if payload.content else ""
    if payload.message_type == "TEXT" and not content_clean:
        raise HttpError(400, "Isi pesan tidak boleh kosong")

    # Batasi panjang teks untuk menjaga space ringan
    if len(content_clean) > 2000:
        content_clean = content_clean[:2000]

    conv = DirectConversation.get_or_create_conversation(user, other_user)

    reply_msg = None
    if payload.reply_to_id:
        reply_msg = DirectMessage.objects.filter(conversation=conv, id=payload.reply_to_id).first()

    msg = DirectMessage.objects.create(
        conversation=conv,
        sender=user,
        message_type=payload.message_type,
        content=content_clean,
        metadata=payload.metadata or {},
        reply_to=reply_msg,
    )

    # Preview ringkas untuk kontak
    if payload.message_type == "TEXT":
        preview = content_clean[:80]
    elif payload.message_type == "REPORT_SHARE":
        rep_title = (payload.metadata or {}).get("title", "Laporan")
        preview = f"📊 [Laporan] {rep_title}"[:80]
    elif payload.message_type == "MACHINE_SNAPSHOT":
        m_name = (payload.metadata or {}).get("machine_name", "Mesin")
        preview = f"⚙️ [Kondisi Mesin] {m_name}"[:80]
    elif payload.message_type == "CHART_BOOKMARK":
        preview = f"📈 [Bookmark Grafik]"
    elif payload.message_type == "ACTION_CHECK":
        preview = f"📋 [Instruksi] {content_clean[:60]}"
    else:
        preview = content_clean[:80]

    conv.last_message_at = msg.created_at
    conv.last_message_preview = preview
    conv.save(update_fields=["last_message_at", "last_message_preview"])

    return _serialize_message(msg)


@chat_router.post("/messages/{message_id}/acknowledge")
def acknowledge_action(request, message_id: int):
    """
    Konfirmasi tiket tugas cepat (ACTION_CHECK).
    Hanya bisa dikonfirmasi oleh penerima pesan.
    """
    user = _require_auth(request)
    msg = get_object_or_404(DirectMessage, id=message_id)

    conv = msg.conversation
    if user.id not in (conv.user1_id, conv.user2_id):
        raise HttpError(403, "Akses ditolak")

    if msg.sender_id == user.id:
        raise HttpError(400, "Tidak dapat mengonfirmasi tugas buatan sendiri")

    meta = dict(msg.metadata or {})
    meta["acknowledged"] = True
    meta["acknowledged_at"] = timezone.now().strftime("%Y-%m-%d %H:%M:%S")
    profile = getattr(user, "operatorprofile", None)
    meta["acknowledged_by"] = profile.display_name if profile and profile.display_name else user.username

    msg.metadata = meta
    msg.save(update_fields=["metadata"])

    return {"success": True, "metadata": meta}


@chat_router.get("/machine-snapshot/{machine_code}")
def get_machine_snapshot(request, machine_code: str):
    """
    Mengambil data snapshot live mesin untuk dilampirkan ke obrolan dalam 1 klik.
    """
    _require_auth(request)
    m = get_object_or_404(Machine, code=machine_code, is_active=True)

    status = get_machine_display_status(m)
    latest_log = m.minute_logs.order_by("-timestamp").first()

    temp = None
    speed = None
    if latest_log:
        temp = getattr(latest_log, "suhu", getattr(latest_log, "temperature", None))
        speed = getattr(latest_log, "speed", None)

    return {
        "machine_code": m.code,
        "machine_name": m.name,
        "status": status,
        "temperature": round(temp, 1) if temp is not None else None,
        "speed": round(speed, 1) if speed is not None else None,
        "timestamp": latest_log.timestamp.strftime("%H:%M:%S") if latest_log and latest_log.timestamp else timezone.now().strftime("%H:%M:%S"),
    }


@chat_router.get("/machine-list")
def get_active_machines_list(request):
    """
    Daftar ringkas mesin aktif untuk dropdown lampiran kondisi mesin di chat.
    """
    _require_auth(request)
    machines = (
        Machine.objects.filter(is_active=True)
        .values("id", "code", "name")
        .order_by("code")
    )
    return {"machines": list(machines)}
