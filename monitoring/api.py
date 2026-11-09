import os
import time
from django.db import connection
from django.core.cache import cache
from django.utils import timezone
from ninja import NinjaAPI
from ninja.errors import HttpError

api = NinjaAPI(
    title="Plant Monitor API",
    description="API untuk aplikasi React Plant Monitor",
    version="1.0.0",
)

@api.get("/status")
def status(request):
    return {"status": "ok", "message": "API Plant Monitor berjalan dengan baik!"}

@api.get("/health")
def health_check(request, flush_cache: int = 0):
    """
    Health check endpoint untuk Nginx / Load Balancer Blue-Green deployment.
    Memeriksa koneksi database, slot aktif, port, dan waktu server.
    Mendukung pembersihan cache memori jika ?flush_cache=1 (khusus pemanggilan dari localhost).
    """
    db_ok = False
    db_error = None
    start_time = time.time()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1;")
            row = cursor.fetchone()
            if row and row[0] == 1:
                db_ok = True
    except Exception as e:
        db_error = str(e)
    db_latency_ms = round((time.time() - start_time) * 1000, 2)

    cache_flushed = False
    client_ip = request.META.get('REMOTE_ADDR', '')
    is_local = client_ip in ('127.0.0.1', '::1', 'localhost')
    if flush_cache and is_local:
        try:
            cache.clear()
            cache_flushed = True
        except Exception:
            pass

    current_slot = os.environ.get("PLANT_MONITOR_SLOT", "default")
    current_port = os.environ.get("PLANT_MONITOR_PORT", "8080")

    payload = {
        "status": "healthy" if db_ok else "unhealthy",
        "database": "connected" if db_ok else f"error: {db_error}",
        "database_latency_ms": db_latency_ms,
        "slot": current_slot,
        "port": current_port,
        "cache_flushed": cache_flushed,
        "timestamp": timezone.now().isoformat(),
    }

    if not db_ok:
        raise HttpError(503, f"Database health check failed: {db_error}")

    return payload

from monitoring.api_auth import auth_router
from monitoring.api_history import history_router
from monitoring.api_dashboard import dashboard_router
from monitoring.api_report import report_router
from monitoring.api_anomaly import anomaly_router
from monitoring.api_batch_detail import batch_detail_router
from monitoring.api_identity import identity_router
from monitoring.api_machines import machines_router
from monitoring.api_analytics import analytics_router
from monitoring.api_snapshots import snapshots_router
from monitoring.api_performance import performance_router

from monitoring.api_engineer import engineer_router
from monitoring.api_jumo_live import jumo_live_router
from monitoring.api_planning import planning_router
from monitoring.api_branding import branding_router
from monitoring.api_boiler import boiler_router
from monitoring.api_chat import chat_router

api.add_router("/auth", auth_router)
api.add_router("/history", history_router)
api.add_router("/dashboard", dashboard_router)
api.add_router("/report", report_router)
api.add_router("/anomalies", anomaly_router)
api.add_router("/batch-detail", batch_detail_router)
api.add_router("/identities", identity_router)
api.add_router("/machines", machines_router)
api.add_router("/analytics", analytics_router)
api.add_router("/snapshots", snapshots_router)
api.add_router("/performance", performance_router)
api.add_router("/engineer", engineer_router)
api.add_router("/jumo-live", jumo_live_router)
api.add_router("/planning", planning_router)
api.add_router("/branding", branding_router)
api.add_router("/boiler", boiler_router)
api.add_router("/chat", chat_router)
