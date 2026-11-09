from ninja import Router
from ninja.errors import HttpError
from datetime import datetime
from django.utils import timezone
from django.db.models import Avg, Count, Q

from monitoring.models import Machine, DyeingProcess
from monitoring.decorators import user_can_access_page

performance_router = Router(tags=["Performance"])

PAGE_CODE = "performance_summary"


def _require_permission(request):
    if not request.user.is_authenticated:
        raise HttpError(401, "Not authenticated")
    if not user_can_access_page(request.user, PAGE_CODE):
        raise HttpError(403, "Anda tidak memiliki izin untuk mengakses halaman ini")

VALID_SORT_FIELDS = {
    "code", "-code", "total_batches", "-total_batches",
    "avg_heating_efficiency", "-avg_heating_efficiency",
    "avg_real_heating_duration", "-avg_real_heating_duration",
    "avg_ideal_heating_time", "-avg_ideal_heating_time",
    "avg_start_temp", "-avg_start_temp", "avg_max_temp", "-avg_max_temp",
    "avg_heating_duration", "-avg_heating_duration",
    "avg_steady_duration", "-avg_steady_duration",
    "avg_cooling_duration", "-avg_cooling_duration",
    "avg_avg_steam_temp", "-avg_avg_steam_temp",
    "avg_avg_steam_pressure", "-avg_avg_steam_pressure",
    "avg_end_temp", "-avg_end_temp",
    "avg_heating_avg_gradient", "-avg_heating_avg_gradient",
    "avg_cooling_avg_gradient", "-avg_cooling_avg_gradient",
    "avg_duration_effective", "-avg_duration_effective",
    "avg_heating_gradient_duration", "-avg_heating_gradient_duration",
    "avg_heating_span", "-avg_heating_span",
    "avg_heating_lag_time", "-avg_heating_lag_time",
}

FLAT_AGG_FIELDS = dict(
    total_batches=Count("id"),
    avg_heating_duration=Avg("real_heating_duration"),
    avg_heating_avg_gradient=Avg("heating_avg_gradient"),
    avg_steady_duration=Avg("steady_duration"),
    avg_cooling_duration=Avg("cooling_duration"),
    avg_cooling_avg_gradient=Avg("cooling_avg_gradient"),
    avg_start_temp=Avg("start_temp"),
    avg_end_temp=Avg("end_temp"),
    avg_max_temp=Avg("max_temp"),
    avg_heating_efficiency=Avg("avg_heating_efficiency"),
    avg_real_heating_duration=Avg("real_heating_duration"),
    avg_duration_effective=Avg("duration_effective"),
    avg_heating_gradient_duration=Avg("heating_gradient_duration"),
    avg_heating_span=Avg("heating_span"),
    avg_ideal_heating_time=Avg("ideal_heating_time"),
    avg_heating_lag_time=Avg("heating_lag_time"),
    avg_avg_steam_temp=Avg("avg_steam_temp"),
    avg_avg_steam_pressure=Avg("avg_steam_pressure"),
)

@performance_router.get("/summary")
def get_performance_summary(request, year: int = None, month: int = None, sort: str = "-total_batches"):
    """
    Mengambil data performa per batch, di-group berdasarkan Mesin -> Program -> Steam Category.
    Menggunakan steam_healthy_threshold dari GlobalSettings.
    """
    _require_permission(request)

    today = timezone.now()
    year = year or today.year
    month = month or today.month

    start_date = datetime(year, month, 1)
    end_date = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    start_date = timezone.make_aware(start_date)
    end_date = timezone.make_aware(end_date)
    
    from monitoring.models import GlobalSettings
    from django.db.models import Case, When, Value, CharField
    
    settings = GlobalSettings.load()
    threshold = getattr(settings, 'steam_healthy_threshold', 3.8)

    # Hanya ambil batch yang memiliki identity dan program
    base_qs = DyeingProcess.objects.filter(
        start_time__gte=start_date, 
        start_time__lt=end_date,
        identity__isnull=False,
        identity__program__isnull=False
    )

    from django.db.models import Sum, Count, Q
    
    # Global Stats Custom Calculation
    unidentified_qs = DyeingProcess.objects.filter(
        start_time__gte=start_date, 
        start_time__lt=end_date
    ).filter(Q(identity__isnull=True) | Q(identity__program__isnull=True))
    total_unidentified = unidentified_qs.count()

    global_eff_data = base_qs.aggregate(
        total_ideal=Sum('identity__program__durasi_ideal'),
        total_effective=Sum('duration_effective'),
        total_sehat=Count('id', filter=Q(avg_steam_pressure__gte=threshold)),
        total_batches=Count('id')
    )

    total_identified = global_eff_data['total_batches'] or 0
    total_sehat = global_eff_data['total_sehat'] or 0
    health_percent = (total_sehat / total_identified * 100) if total_identified > 0 else 0
    
    total_ideal = global_eff_data['total_ideal'] or 0
    total_effective = global_eff_data['total_effective'] or 0
    avg_eff = (total_ideal / total_effective * 100) if total_effective > 0 else 0

    global_stats = {
        "avg_efficiency": avg_eff,
        "health_percent": health_percent,
        "total_identified": total_identified,
        "total_unidentified": total_unidentified
    }

    # Kategori Steam dan Group By
    grouped_qs = base_qs.annotate(
        steam_category=Case(
            When(avg_steam_pressure__isnull=True, then=Value('tidak_lengkap')),
            When(avg_steam_pressure__gte=threshold, then=Value('sehat')),
            When(avg_steam_pressure__lt=threshold, then=Value('kurang_bagus')),
            default=Value('tidak_lengkap'),
            output_field=CharField()
        )
    ).values(
        'machine__code', 
        'machine__name',
        'identity__program_id', 
        'identity__program__nama',
        'identity__program__durasi_ideal',
        'identity__program__durasi_heating_ideal',
        'identity__program__durasi_keeping_ideal',
        'identity__program__durasi_cooling_ideal',
        'steam_category'
    ).annotate(**FLAT_AGG_FIELDS)
    
    # Sort the resulting dictionaries if we want, or we can sort in frontend.
    # We will send a list of dictionaries to the frontend.
    flat_data = list(grouped_qs)
    
    # Frontend handles the sorting naturally if we pass it as is, but we can do a preliminary sort.
    # Note: flat_data is a list of dicts. We sort by total_batches desc by default.
    

    from django.db.models import F
    raw_qs = base_qs.select_related('machine', 'identity', 'identity__program').annotate(
        steam_category=Case(
            When(avg_steam_pressure__isnull=True, then=Value('tidak_lengkap')),
            When(avg_steam_pressure__gte=threshold, then=Value('sehat')),
            When(avg_steam_pressure__lt=threshold, then=Value('kurang_bagus')),
            default=Value('tidak_lengkap'),
            output_field=CharField()
        ),
        avg_heating_duration=F('real_heating_duration'),
        avg_steady_duration=F('steady_duration'),
        avg_cooling_duration=F('cooling_duration'),
        avg_duration_effective=F('duration_effective'),
        avg_max_temp=F('max_temp'),
        avg_avg_steam_pressure=F('avg_steam_pressure')
    ).values(
        'id',
        'identity__id',
        'start_time',
        'identity__batch',
        'machine__code',
        'machine__name',
        'identity__program_id',
        'identity__program__nama',
        'identity__program__durasi_ideal',
        'identity__program__durasi_heating_ideal',
        'identity__program__durasi_keeping_ideal',
        'identity__program__durasi_cooling_ideal',
        'avg_heating_duration',
        'avg_steady_duration',
        'avg_cooling_duration',
        'avg_duration_effective',
        'avg_max_temp',
        'avg_avg_steam_pressure',
        'steam_category'
    ).order_by('-start_time')

    first_batch = DyeingProcess.objects.order_by("start_time").first()
    start_year = first_batch.start_time.year if first_batch else today.year
    years = list(range(start_year, today.year + 2))

    return {
        "data": flat_data,
        "raw_data": list(raw_qs),
        "unidentified_raw_data": list(unidentified_qs.values('start_time', 'machine__code')),
        "global_stats": global_stats,
        "years": years,
        "selected_year": year,
        "selected_month": month,
        "current_sort": sort,
    }
