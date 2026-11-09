from django.utils.deprecation import MiddlewareMixin
from django.http import HttpResponse
from monitoring.models import UserActivityLog
from django.utils import timezone
from datetime import timedelta
import json
import re
import os
import logging
import threading
import time

# ============================================================
# Logger untuk aktivitas request (bot maupun manusia)
# File log: bot_requests.log di root project
# ============================================================
_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'logs', 'bot_requests.log')
_req_logger = logging.getLogger('bot_request_logger')
if not _req_logger.handlers:
    _handler = logging.FileHandler(_log_path, encoding='utf-8', delay=True)
    _handler.setFormatter(logging.Formatter('%(message)s'))
    _req_logger.addHandler(_handler)
    _req_logger.setLevel(logging.INFO)
    _req_logger.propagate = False


def _fetch_ip_geo(ip_address):
    """
    Background thread: ambil info negara + ISP dari ip-api.com,
    lalu update record IPAccessControl. Tidak memblokir request.
    """
    try:
        import requests as _req
        resp = _req.get(
            f'http://ip-api.com/json/{ip_address}?fields=country,countryCode,isp,org',
            timeout=4
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get('status') == 'success' or 'country' in data:
                from monitoring.models import IPAccessControl
                IPAccessControl.objects.filter(ip_address=ip_address).update(
                    country=data.get('country', ''),
                    country_code=data.get('countryCode', ''),
                    isp=(data.get('org') or data.get('isp') or '')[:150],
                )
    except Exception:
        pass


# ============================================================
# Cache sederhana in-memory untuk menghindari DB query berulang
# _ip_block_cache : {ip: (is_blocked: bool, timestamp: float)}
# _ip_upsert_cache: {ip: timestamp_last_upsert}
# ============================================================
_ip_block_cache = {}   # TTL: 60 detik
_ip_upsert_cache = {}  # TTL: 30 detik — throttle upsert ke DB
_ip_cache_lock = threading.Lock()

_BLOCK_CACHE_TTL = 60   # detik
_UPSERT_CACHE_TTL = 30  # detik


class BotBlockerMiddleware:
    """
    Middleware untuk memblokir bot scanner internet secara dini.
    Harus didaftarkan PERTAMA dalam MIDDLEWARE list agar koneksi
    bot langsung ditolak sebelum memakan resource Django/DB.

    Fitur tambahan:
    - Otomatis mencatat semua IP ke tabel IPAccessControl
    - Admin bisa blokir/izinkan IP dari Django Admin
    - Mencatat akun user yang pernah login dari setiap IP
    - Lookup negara/ISP di background (tidak mempengaruhi kecepatan)
    """

    # User-Agent yang dikenal sebagai bot scanner/vulnerability scanner
    BLOCKED_UA_PATTERNS = re.compile(
        r'(masscan|zgrab|nmap|nikto|sqlmap|dirbuster|gobuster|nuclei|'
        r'python-requests|go-http-client|curl/|wget/|libwww-perl|'
        r'java/|ruby|perl|scrapy|httpclient|okhttp|axios/'
        r'scanbot|censys|shodan|zoomeye|binaryedge|fofa)',
        re.IGNORECASE
    )

    # Path yang sering di-scan oleh bot (bukan path valid aplikasi ini)
    BLOCKED_PATH_PATTERNS = re.compile(
        r'(/wp-admin|/wp-login|/phpmyadmin|/phpinfo|/\.env|/\.git|'
        r'/admin\.php|/shell\.php|/config\.php|/setup\.php|'
        r'/actuator|/solr|/jmx|/manager/html|/console|'
        r'/cgi-bin|/xmlrpc\.php|/autodiscover|/owa|'
        r'\.jsp$|\.asp$|\.aspx$)',
        re.IGNORECASE
    )

    # Path API internal yang tidak perlu di-log (terlalu banyak noise)
    SKIP_LOG_PATHS = (
        '/api/kpi-realtime/', '/api/machines/', '/api/alerts/',
        '/api/v1/chat/', '/static/', '/media/',
    )

    def __init__(self, get_response):
        self.get_response = get_response

    def _get_ip(self, request):
        xff = request.META.get('HTTP_X_FORWARDED_FOR')
        return xff.split(',')[0].strip() if xff else request.META.get('REMOTE_ADDR', '-')

    def _log_request(self, request, status, note=''):
        """Catat request ke bot_requests.log (file)"""
        for skip in self.SKIP_LOG_PATHS:
            if request.path.startswith(skip):
                return
        try:
            ip = self._get_ip(request)
            ua = request.META.get('HTTP_USER_AGENT', '-')[:120]
            ts = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            line = (
                f"{ts} | {ip:<22} | {request.method:<6} | "
                f"{status:<10} | {note:<10} | "
                f"{request.path:<40} | {ua}"
            )
            _req_logger.info(line)
        except Exception:
            pass

    def _is_blocked_in_db(self, ip):
        """Cek apakah IP diblokir — dengan cache in-memory TTL 60 detik."""
        now = time.monotonic()
        with _ip_cache_lock:
            cached = _ip_block_cache.get(ip)
            if cached is not None:
                is_blocked, ts = cached
                if now - ts < _BLOCK_CACHE_TTL:
                    return is_blocked  # Gunakan cache, skip DB query
        # Cache miss atau expired — query DB
        try:
            from monitoring.models import IPAccessControl
            result = IPAccessControl.objects.filter(ip_address=ip, is_blocked=True).exists()
        except Exception:
            result = False
        with _ip_cache_lock:
            _ip_block_cache[ip] = (result, now)
        return result

    def _upsert_ip(self, ip, request, block_reason=''):
        """
        Buat atau update record IPAccessControl untuk IP ini.
        Di-throttle 30 detik per IP agar tidak query DB di setiap request.
        block_reason: NO_UA / BAD_UA / BAD_PATH / DB_BLOCK / '' (allowed)
        """
        now = time.monotonic()
        # Throttle: skip jika IP ini sudah di-upsert dalam 30 detik terakhir
        with _ip_cache_lock:
            last_upsert = _ip_upsert_cache.get(ip, 0)
            if now - last_upsert < _UPSERT_CACHE_TTL and not block_reason:
                # Sudah di-upsert baru-baru ini dan bukan request blokir — skip
                return
            _ip_upsert_cache[ip] = now

        # Snapshot user & auth status SEBELUM masuk thread (request object tidak aman diakses dari thread lain)
        current_user = getattr(request, 'user', None)
        user_to_link = current_user if (current_user and current_user.is_authenticated and not block_reason) else None

        # Jalankan DB update di background thread agar tidak memblokir response
        def _do_upsert():
            try:
                from monitoring.models import IPAccessControl
                from django.db.models import F

                record, created = IPAccessControl.objects.get_or_create(
                    ip_address=ip,
                    defaults={'access_count': 1, 'auto_block_count': 1 if block_reason else 0,
                              'last_block_reason': block_reason}
                )

                if not created:
                    update_fields = {'access_count': F('access_count') + 1,
                                     'last_block_reason': block_reason}
                    if block_reason:
                        update_fields['auto_block_count'] = F('auto_block_count') + 1
                    IPAccessControl.objects.filter(ip_address=ip).update(**update_fields)

                # Jika IP baru, fetch geo di background
                if created:
                    _fetch_ip_geo(ip)  # sudah dalam thread, panggil langsung

                # Link user yang sedang login ke known_users (hanya jika allowed)
                if user_to_link:
                    record.known_users.add(user_to_link)

            except Exception:
                pass
            finally:
                from django.db import connections
                connections.close_all()

        threading.Thread(target=_do_upsert, daemon=True).start()

    def __call__(self, request):
        user_agent = request.META.get('HTTP_USER_AGENT', '')
        path = request.path
        ip = self._get_ip(request)

        # ── Cek 1: Blokir IP yang sudah di-blacklist admin di DB ─────────
        if self._is_blocked_in_db(ip):
            self._upsert_ip(ip, request, block_reason='DB_BLOCK')
            self._log_request(request, 'BLOCKED', 'DB_BLOCK')
            return HttpResponse(
                '<h1>403 Forbidden</h1><p>Akses dari alamat IP Anda telah diblokir.</p>',
                status=403,
                content_type='text/html'
            )

        # ── Cek 2: Blokir jika tidak ada User-Agent sama sekali ──────────
        if not user_agent:
            self._upsert_ip(ip, request, block_reason='NO_UA')
            self._log_request(request, 'BLOCKED', 'NO_UA')
            return HttpResponse(status=400)

        # ── Cek 3: Blokir berdasarkan User-Agent scanner ─────────────────
        if self.BLOCKED_UA_PATTERNS.search(user_agent):
            self._upsert_ip(ip, request, block_reason='BAD_UA')
            self._log_request(request, 'BLOCKED', 'BAD_UA')
            return HttpResponse(status=403)

        # ── Cek 4: Blokir path illegal ───────────────────────────────────
        if self.BLOCKED_PATH_PATTERNS.search(path):
            self._upsert_ip(ip, request, block_reason='BAD_PATH')
            self._log_request(request, 'BLOCKED', 'BAD_PATH')
            return HttpResponse(status=404)

        # ── Request lolos — proses normal ────────────────────────────────
        response = self.get_response(request)

        # Upsert setelah request selesai agar request.user sudah diisi session
        self._upsert_ip(ip, request, block_reason='')
        self._log_request(request, 'ALLOWED', '')

        return response




class UserActivityMiddleware(MiddlewareMixin):
    """
    Middleware untuk mencatat aktivitas user secara otomatis (admin & website).
    Menggunakan session-based throttling untuk mengurangi spam logging.
    """
    
    # Pages yang akan di-log
    TRACKED_PATHS = [
        '/',  # Dashboard
        '/grafik/',  # Graph Menu
        '/history/',  # History List
        '/mesin-aktif/',  # Manual Machine Usage
        '/snapshot-history/',  # Snapshot History
        '/performance-summary/',  # Performance Summary
    ]
    
    # API endpoints yang tidak perlu di-log (untuk menghindari spam)
    EXCLUDED_PATHS = [
        '/api/machines/',
        '/api/kpi-realtime/',
        '/api/alerts/count/',
        '/api/steam-usage-history/',
        '/api/chart/',
        '/api/alerts/',
        '/static/',
        '/media/',
        '/admin/',  # Exclude admin pages from page view logging
    ]
    
    # Throttle duration in minutes
    THROTTLE_MINUTES = 5
    
    def process_request(self, request):
        # Simpan request untuk digunakan di signal handlers
        UserActivityLog._current_request = request
        if hasattr(request, 'user') and request.user.is_authenticated:
            try:
                from django.core.cache import cache
                cache.set(f"user_online_{request.user.id}", timezone.now().timestamp(), timeout=180)
            except Exception:
                pass
    
    def get_client_ip(self, request):
        """Helper untuk mendapatkan IP address client"""
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            ip = x_forwarded_for.split(',')[0]
        else:
            ip = request.META.get('REMOTE_ADDR')
        return ip
    
    def should_log_request(self, request):
        """Check apakah request perlu di-log"""
        path = request.path
        
        # Skip jika user tidak authenticated
        if not hasattr(request, 'user') or not request.user.is_authenticated:
            return False
        
        # Skip excluded paths
        for excluded in self.EXCLUDED_PATHS:
            if path.startswith(excluded):
                return False
        
        # Log tracked paths
        for tracked in self.TRACKED_PATHS:
            if path.startswith(tracked):
                return True
        
        # Log history detail pages
        if path.startswith('/history/') and path.count('/') >= 3:
            return True
        
        return False
    
    def should_throttle(self, request, action):
        """
        Check if we should throttle this log entry.
        Returns True if we should skip logging (throttled).
        Uses session to track last log time per page.
        """
        # Only throttle VIEW actions, not SEARCH or FILTER
        if action != 'VIEW':
            return False
        
        # Get session key for this path
        session_key = f'last_log_{request.path}'
        
        # Get last log time from session
        last_log_str = request.session.get(session_key)
        
        if last_log_str:
            try:
                last_log = timezone.datetime.fromisoformat(last_log_str)
                time_since_last = timezone.now() - last_log
                
                # If less than THROTTLE_MINUTES, skip logging
                if time_since_last < timedelta(minutes=self.THROTTLE_MINUTES):
                    return True  # Throttled
            except (ValueError, TypeError):
                # Invalid datetime, proceed with logging
                pass
        
        return False  # Not throttled
        
    def process_response(self, request, response):
        """Log page views dan interactions with throttling"""

        if response.status_code == 200 and self.should_log_request(request):
            try:
                query_params = dict(request.GET) if request.GET else None

                action = 'VIEW'
                description = f"Visited {request.path}"
                additional_data = {}

                if query_params:
                    if 'search' in query_params or 'q' in query_params:
                        action = 'SEARCH'
                        description = f"Searched in {request.path}"
                    elif any(key in query_params for key in ['machine', 'group', 'start', 'end', 'status']):
                        action = 'FILTER'
                        description = f"Applied filter in {request.path}"
                    additional_data['filters'] = {k: v[0] if len(v) == 1 else v for k, v in query_params.items()}

                if not self.should_throttle(request, action):
                    # Snapshot semua data yang dibutuhkan SEBELUM masuk thread
                    # (request object tidak aman diakses dari thread lain)
                    user      = request.user
                    path      = request.path
                    method    = request.method
                    ip        = self.get_client_ip(request)
                    ua        = request.META.get('HTTP_USER_AGENT', '')[:255]
                    _action   = action
                    _desc     = description
                    _extra    = additional_data if additional_data else None
                    _qparams  = query_params

                    def _write_log():
                        try:
                            UserActivityLog.objects.create(
                                user=user,
                                username=user.username,
                                action=_action,
                                request_path=path,
                                request_method=method,
                                query_params=_qparams,
                                description=_desc,
                                additional_data=_extra,
                                ip_address=ip,
                                user_agent=ua,
                            )
                        except Exception:
                            pass
                        finally:
                            from django.db import connections
                            connections.close_all()

                    threading.Thread(target=_write_log, daemon=True).start()

                    # Update session hanya untuk VIEW (setelah kita tahu tidak throttled)
                    if action == 'VIEW':
                        session_key = f'last_log_{request.path}'
                        request.session[session_key] = timezone.now().isoformat()

            except Exception:
                pass

        if hasattr(UserActivityLog, '_current_request'):
            delattr(UserActivityLog, '_current_request')

        return response


class ApiJsonUnauthorizedMiddleware(MiddlewareMixin):
    """
    Jika request menuju /api/* atau /api/v1/* menerima 302 redirect ke /login/
    (biasanya dari dekorator @login_required bawaan Django saat session habis),
    ubah menjadi response HTTP 401 Unauthorized (JSON) alih-alih redirect HTML.

    Ini mencegah Axios / RTK Query di frontend mem-follow redirect dan menerima
    HTML Login dengan status 200 OK yang menyebabkan infinite loading / spinner macet.
    """
    def process_response(self, request, response):
        if request.path.startswith('/api/') or request.path.startswith('/api/v1/'):
            if response.status_code == 302:
                location = response.get('Location', '')
                if '/login' in location:
                    from django.http import JsonResponse
                    return JsonResponse(
                        {
                            'detail': 'Sesi telah berakhir atau tidak sah. Silakan login kembali.',
                            'code': 'UNAUTHORIZED',
                            'login_url': location,
                        },
                        status=401
                    )
        return response
