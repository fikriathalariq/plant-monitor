import math
from datetime import datetime, timedelta
from unittest.mock import patch
from django.test import SimpleTestCase

from monitoring.utils.batch_analyzer import (
    BatchProcessingConfig,
    FilterState,
    BatchGradientProcessor,
    pressure_to_steam_temp,
    calculate_ideal_time,
    detect_multi_heating_cycles,
)


class BatchAnalyzerThermodynamicsAndSignalTest(SimpleTestCase):
    """
    Unit test for batch signal filtering, thermodynamic steam saturation conversion,
    and heat transfer calculation in monitoring/utils/batch_analyzer.py.
    """

    def setUp(self):
        self.config = BatchProcessingConfig()

    def test_pressure_to_steam_temp_normal_range(self):
        """Verify steam temperature conversion within industrial operating pressure (3 to 7 bar)."""
        temp_3bar = pressure_to_steam_temp(3.0, self.config)
        temp_5bar = pressure_to_steam_temp(5.0, self.config)
        temp_7bar = pressure_to_steam_temp(7.0, self.config)

        # At 3 bar gauge (~4 bar abs), saturation temp is ~143.6°C
        self.assertAlmostEqual(temp_3bar, 143.6, delta=2.5)
        # At 5 bar gauge (~6 bar abs), saturation temp is ~158.8°C
        self.assertAlmostEqual(temp_5bar, 158.8, delta=2.5)
        # At 7 bar gauge (~8 bar abs), saturation temp is ~170.4°C
        self.assertAlmostEqual(temp_7bar, 170.4, delta=2.5)
        # Monotonically increasing with pressure
        self.assertGreater(temp_5bar, temp_3bar)
        self.assertGreater(temp_7bar, temp_5bar)

    def test_pressure_to_steam_temp_fallback_formula(self):
        """Verify empirical fallback formula when HAS_IAPWS is False: 179.32 * (p_abs ** 0.2390)."""
        p_gauge = 4.5
        p_abs = p_gauge + 1.013
        expected_empirical = 179.32 * (p_abs ** 0.2390)

        with patch("monitoring.utils.batch_analyzer.HAS_IAPWS", False):
            actual_temp = pressure_to_steam_temp(p_gauge, self.config)
            self.assertAlmostEqual(actual_temp, expected_empirical, delta=0.01)

    def test_pressure_to_steam_temp_invalid_and_edge_inputs(self):
        """Ensure invalid or edge inputs return DEFAULT_STEAM_TEMP without crashing."""
        default_temp = self.config.DEFAULT_STEAM_TEMP
        self.assertEqual(pressure_to_steam_temp(None, self.config), default_temp)
        self.assertEqual(pressure_to_steam_temp(float("nan"), self.config), default_temp)
        self.assertEqual(pressure_to_steam_temp(0.0, self.config), default_temp)
        self.assertEqual(pressure_to_steam_temp(-2.5, self.config), default_temp)

    def test_calculate_ideal_time_valid_physics(self):
        """Verify exponential heat transfer time model under standard heating conditions."""
        start_temp = 30.0
        end_temp = 130.0
        steam_temp = 160.0  # Saturation temp above target
        ideal_mins = calculate_ideal_time(start_temp, end_temp, steam_temp, self.config)

        # Ideal time must be positive and within reasonable industrial envelope (10 - 90 mins)
        self.assertGreater(ideal_mins, 10.0)
        self.assertLess(ideal_mins, 90.0)

    def test_calculate_ideal_time_inversion_and_guards(self):
        """Verify safety guards when target temperature <= start temperature or steam temperature."""
        # Case 1: Start temp >= end temp (no heating required)
        self.assertEqual(calculate_ideal_time(80.0, 60.0, 160.0, self.config), 0.0)
        self.assertEqual(calculate_ideal_time(80.0, 80.0, 160.0, self.config), 0.0)

        # Case 2: Steam temp lower than target temp (thermodynamically unfeasible)
        # Model should guard against math domain error in log
        guard_time = calculate_ideal_time(30.0, 130.0, 120.0, self.config)
        self.assertIsInstance(guard_time, float)
        self.assertGreater(guard_time, 0.0)

    def test_batch_gradient_processor_filtering(self):
        """Verify that BatchGradientProcessor dampens single-point noise spikes via EWMA/Kalman."""
        processor = BatchGradientProcessor(self.config)
        state = FilterState()

        # Constant steady state at 60.0
        for _ in range(5):
            kx, gx, therm, state = processor.process_single(60.0, state)

        # Sudden single-point spike to 95.0 (e.g. electrical noise)
        spike_filtered, gx, therm, state = processor.process_single(95.0, state)

        # Filtered output must dampen the 35-degree jump
        self.assertLess(spike_filtered, 85.0)
        self.assertGreater(spike_filtered, 60.0)

    def test_detect_multi_heating_cycles(self):
        """Verify multi-cycle segmentation detects distinct temperature rise phases."""
        from django.utils import timezone
        base_time = timezone.make_aware(datetime(2026, 11, 9, 8, 0, 0))
        times = [base_time + timedelta(minutes=i) for i in range(60)]

        # Simulate heating cycles
        temps = []
        for i in range(20):
            temps.append(40.0 + i * 1.5)  # 40 -> 68.5
        for i in range(10):
            temps.append(70.0)           # 70 steady
        for i in range(10):
            temps.append(70.0 - i * 3.0) # 70 -> 43 cool
        for i in range(20):
            temps.append(40.0 + i * 2.5) # 40 -> 87.5 heat 2

        raw_logs = list(zip(times, temps))
        result = detect_multi_heating_cycles(raw_logs)
        self.assertIsInstance(result, dict)
        self.assertIn("is_multi_heating", result)
        self.assertIn("cycle_count", result)
