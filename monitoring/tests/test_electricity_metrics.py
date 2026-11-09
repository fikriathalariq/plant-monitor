from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from django.test import SimpleTestCase
from monitoring.api_report import _compute_batch_electricity_metrics


class BatchElectricityMetricsTests(SimpleTestCase):
    def test_fabric_allowance_capped_at_45_minutes(self):
        """Duration from <70C to machine stop must be capped at 45.0 mins."""
        t_70c = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.utc)
        # Machine stopped 90 minutes after cooling (exceeding 45 mins)
        t_end = t_70c + timedelta(minutes=90)

        dummy_process = SimpleNamespace(
            reached_70c_time=t_70c,
            end_time=t_end,
            program_ideal_duration_mins=120.0,
            machine_nominal_power=30.0,
            power_consumption_kwh=95.0,
            power_consumption_lwbp_kwh=95.0,
            power_consumption_wbp_kwh=0.0,
            power_cost_lwbp=None,
            power_cost_wbp=None,
            power_cost_total=None,
            ideal_power_consumption_kwh=None,
        )
        dummy_program = SimpleNamespace(durasi_ideal=120.0)

        res = _compute_batch_electricity_metrics(dummy_process, program=dummy_program, lwbp_rate=1000.0)

        self.assertEqual(res["late_stop_mins"], 90.0)
        self.assertEqual(res["fabric_allowance_mins"], 45.0)
        # 120 mins recipe + 45 mins fabric allowance = 165.0 mins (2.75 hrs)
        self.assertEqual(res["elec_ideal_duration_mins"], 165.0)
        # 2.75 hrs * 30 kW nominal power = 82.5 kWh
        self.assertEqual(res["ideal_kwh"], 82.5)
        # Loss: 95.0 actual - 82.5 ideal = 12.5 kWh
        self.assertEqual(res["pos_loss_kwh"], 12.5)

    def test_lwbp_and_wbp_tariff_defaults_and_efficiency(self):
        """WBP rate defaults to 1.4x of LWBP rate."""
        dummy_process = SimpleNamespace(
            reached_70c_time=None,
            end_time=None,
            program_ideal_duration_mins=60.0,
            machine_nominal_power=20.0,
            power_consumption_kwh=20.0,
            power_consumption_lwbp_kwh=10.0,
            power_consumption_wbp_kwh=10.0,
            power_cost_lwbp=None,
            power_cost_wbp=None,
            power_cost_total=None,
            ideal_power_consumption_kwh=None,
        )

        res = _compute_batch_electricity_metrics(dummy_process, program=None, lwbp_rate=1000.0)

        # 10 kWh * 1000 = 10000 LWBP
        self.assertEqual(res["cost_lwbp_rp"], 10000.0)
        # 10 kWh * 1400 (1000 * 1.4) = 14000 WBP
        self.assertEqual(res["cost_wbp_rp"], 14000.0)
        # Total actual cost = 24000
        self.assertEqual(res["cost_actual_rp"], 24000.0)
        # Efficiency = 100% when actual == ideal
        self.assertEqual(res["power_eff"], 100.0)

    def test_null_power_handling_without_crash(self):
        """Gracefully handle processes with None values."""
        dummy_process = SimpleNamespace(
            reached_70c_time=None,
            end_time=None,
            program_ideal_duration_mins=None,
            machine_nominal_power=None,
            machine=None,
            power_consumption_kwh=None,
            power_consumption_lwbp_kwh=None,
            power_consumption_wbp_kwh=None,
            power_cost_lwbp=None,
            power_cost_wbp=None,
            power_cost_total=None,
            ideal_power_consumption_kwh=None,
        )

        res = _compute_batch_electricity_metrics(dummy_process)
        self.assertIsNone(res["actual_kwh"])
        self.assertIsNone(res["ideal_kwh"])
        self.assertEqual(res["cost_loss_rp"], 0.0)
