from django.urls import path
from . import views
from . import views_anomaly

urlpatterns = [
    # KALIBRASI ANOMALI CHARTS
    path("calibration-chart/<str:source_type>/<int:record_id>/", views_anomaly.calibration_chart_view, name="calibration_chart_view"),

    path("home/", views.home_korlap, name="home_korlap"),
    path("api/home-korlap/", views.home_korlap_api, name="home_korlap_api"),
    path("", views.dashboard, name="dashboard"),
    path("api/machines/", views.machine_status_api, name="machine_status_api"),
    path(
        "mesin-aktif/",
        views.manual_machine_usage,
        name="manual_machine_usage",
    ),
    path("api/chart/<str:code>/", views.machine_chart_api, name="machine_chart_api"),
    path("api/kpi-realtime/", views.kpi_realtime_api, name="kpi_realtime_api"),
    path("api/steam-usage-history/", views.steam_usage_history_api, name="steam_usage_history_api"),
    path("api/hto-usage-history/", views.hto_usage_history_api, name="hto_usage_history_api"),
    path("api/steam-usage-detail/", views.steam_usage_detail_api, name="steam_usage_detail_api"),
    path("grafik/", views.graph_menu, name="graph_menu"),
    path("grafik/data/", views.graph_data_api, name="graph_data_api"),
    path("grafik/multi/", views.graph_multi_api, name="graph_multi_api"),
    path("grafik/steam-hto-analytics/", views.steam_hto_analytics_api, name="steam_hto_analytics_api"),
    path("grafik/snapshot-detail/", views.snapshot_detail_api, name="snapshot_detail_api"),
    path("history/", views.history_list, name="history_list"),
    
    # NEW: Stable URL using natural key (machine_code + batch_number)
    path("history/<str:machine_code>/<int:batch_number>/", views.history_report, name="history_report"),
    
    # LEGACY: Old URL for backwards compatibility (redirects to new format)
    path("history/<int:batch_id>/", views.history_report_legacy, name="history_report_legacy"),

    # Dyeing Analytics Report (standalone, per-identity)
    path("dyeing-report/<int:identity_pk>/", views.dyeing_analytics_report, name="dyeing_analytics_report"),
    
    # Daily Batch Overview Dashboard
    path("daily-batch-overview/", views.daily_batch_overview, name="daily_batch_overview"),
    
    path("snapshot-history/", views.snapshot_history, name="snapshot_history"),
    path(
        "performance-summary/",
        views.machine_performance_summary,
        name="machine_performance_summary",
    ),
    
    # ALERT API ENDPOINTS
    path("api/alerts/active/", views.get_active_alerts, name="get_active_alerts"),
    path("api/alerts/<int:alert_id>/acknowledge/", views.acknowledge_alert, name="acknowledge_alert"),
    path("api/alerts/count/", views.get_alert_count, name="get_alert_count"),
    
    # APIDOG API ENDPOINT
    path("api/external/dyeing-process-lookup/", views.apidog_dyeing_process_lookup_api, name="apidog_dyeing_process_lookup_api"),
    
    # CETAK STANDARD FLOW
    path("standard-flow/<int:pk>/cetak/", views.cetak_standard_flow, name="cetak_standard_flow"),

    # MACHINE MONTHLY FULL REPORT (Siap Cetak HTML)
    path("machine-report/<int:machine_id>/<str:date_str>/", views.machine_monthly_full_report, name="machine_monthly_full_report"),
    path("machine-report/<int:machine_id>/", views.machine_monthly_full_report, name="machine_monthly_full_report_default"),
]
