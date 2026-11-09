from django.test import SimpleTestCase, TestCase
from monitoring.services.batch_cost_calculator import BatchCostCalculator, ProcessDiagnosticService
from monitoring.services.boiler_analytics_service import BoilerAnalyticsService
from monitoring import api_report


class ServicesRefactorParityTest(SimpleTestCase):
    """
    Unit test to verify 100% parity between extracted Service Classes
    and backward-compatibility re-export aliases in api_report.py.
    """

    def test_reexport_aliases_point_to_service_methods(self):
        """Verify that api_report aliases point to the exact same callables."""
        self.assertEqual(api_report.sort_machines_custom, ProcessDiagnosticService.sort_machines_custom)
        self.assertEqual(api_report.classify_process_problems, ProcessDiagnosticService.classify_process_problems)
        self.assertEqual(api_report._compute_downtime_ranking, ProcessDiagnosticService.compute_downtime_ranking)
        self.assertEqual(api_report._compute_batch_electricity_metrics, BatchCostCalculator.compute_electricity)
        self.assertEqual(api_report._compute_changeover_stats, ProcessDiagnosticService.compute_changeover_stats)

        self.assertEqual(api_report._compute_boiler_chart_data, BoilerAnalyticsService.compute_chart_data)
        self.assertEqual(api_report._compute_boiler_kpi_summary, BoilerAnalyticsService.compute_kpi_summary)
        self.assertEqual(api_report._bucket_boiler_month_data, BoilerAnalyticsService.bucket_boiler_month_data)
        self.assertEqual(api_report._get_boiler_alert_history, BoilerAnalyticsService.get_alert_history)
        self.assertEqual(api_report._get_logical_boiler_today, BoilerAnalyticsService.get_logical_today)
        self.assertEqual(api_report.upsert_boiler_daily_metric, BoilerAnalyticsService.upsert_daily_metric)
        self.assertEqual(api_report._boiler_daily_metric_to_day_dict, BoilerAnalyticsService.daily_metric_to_day_dict)
        self.assertEqual(api_report._detect_boiler_regulations, BoilerAnalyticsService.detect_regulations)
        self.assertEqual(api_report._regulation_events_to_alerts, BoilerAnalyticsService.regulation_events_to_alerts)

    def test_boiler_constants_consistency(self):
        """Verify boiler constants in api_report match BoilerAnalyticsService constants."""
        self.assertEqual(api_report.BOILER_MACHINES, BoilerAnalyticsService.MACHINES)
        self.assertEqual(api_report.BOILER_INTERVAL_MINUTES, BoilerAnalyticsService.INTERVAL_MINUTES)
        self.assertEqual(api_report.BOILER_TARGET_POINTS, BoilerAnalyticsService.TARGET_POINTS)
        self.assertEqual(len(BoilerAnalyticsService.MACHINES), 6)

    def test_sort_machines_custom_behavior(self):
        """Verify sorting behavior for machine lists."""
        machines = [
            {"name": "ZET 1"},
            {"name": "JR 01"},
            {"name": "JD 02"},
            {"name": "Other 99"},
        ]
        BoilerAnalyticsService_machines = list(machines)
        api_report.sort_machines_custom(machines)
        ProcessDiagnosticService.sort_machines_custom(BoilerAnalyticsService_machines)
        self.assertEqual(machines, BoilerAnalyticsService_machines)
        # JR comes first, then JD, then ZET, then Other
        self.assertTrue(machines[0]["name"].startswith("JR"))
        self.assertTrue(machines[1]["name"].startswith("JD"))
        self.assertTrue(machines[2]["name"].startswith("ZET"))

    def test_regulation_events_to_alerts(self):
        """Verify regulation event alert conversion."""
        events = [
            {
                "channel": "STEAM",
                "start_time": "10:30",
                "duration_minutes": 15,
                "peak_value": 6.2,
            },
            {
                "channel": "HTO",
                "start_time": "14:00",
                "duration_minutes": 20,
                "peak_value": 260.5,
            },
        ]
        alerts = BoilerAnalyticsService.regulation_events_to_alerts(events, "2026-11-09")
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["severity"], "WARNING")
        self.assertEqual(alerts[0]["machine_code"], "Speed_RB_Steam")
        self.assertIn("6.2 bar", alerts[0]["message"])
        self.assertEqual(alerts[1]["machine_code"], "Speed_R_Bakar")
        self.assertIn("260.5 °C", alerts[1]["message"])

    def test_get_machine_process_history_signature(self):
        """Verify that get_machine_process_history handles start_date/end_date without NameError."""
        import inspect
        sig = inspect.signature(api_report.get_machine_process_history)
        params = list(sig.parameters.keys())
        self.assertEqual(params, ["request", "machine_id", "start_date", "end_date"])
