from datetime import datetime, date
from unittest.mock import MagicMock
from django.test import SimpleTestCase
from django.utils import timezone

from monitoring.utils.shift_time import (
    TOTAL_BUCKETS,
    current_shift_start,
    shift_bounds,
    hour_axis_labels,
    minutes_to_pct,
    pct_to_minutes,
    get_current_operational_shift,
)
from monitoring.utils.steam_calc import (
    compute_steam_timeline_from_plan_batches,
    compute_carryover_blocks,
    compute_carryover_steam_contribution,
    compute_steam_timeline_from_minute_buckets,
    is_steam_active_state,
)


class SteamAndShiftCalculationTest(SimpleTestCase):
    """
    Unit tests for plant operational shift boundaries (06:00 - 06:00),
    steam load computation across 1440-minute buckets, and multi-day carryover overflow.
    """

    def test_current_shift_start_before_and_after_0600(self):
        """Verify that 05:30 maps to previous calendar day shift start, and 06:00 maps to today."""
        # 10 Nov 2026 05:30 -> Shift started at 09 Nov 2026 06:00
        dt_early = timezone.make_aware(datetime(2026, 11, 10, 5, 30, 0))
        start_early = current_shift_start(dt_early)
        self.assertEqual(start_early.day, 9)
        self.assertEqual(start_early.hour, 6)
        self.assertEqual(start_early.minute, 0)

        # 10 Nov 2026 06:00 -> Shift starts at 10 Nov 2026 06:00
        dt_on_time = timezone.make_aware(datetime(2026, 11, 10, 6, 0, 0))
        start_on_time = current_shift_start(dt_on_time)
        self.assertEqual(start_on_time.day, 10)
        self.assertEqual(start_on_time.hour, 6)

    def test_shift_bounds(self):
        """Verify (shift_start, full_end) tuple spanning exactly 24 hours."""
        d = date(2026, 11, 10)
        start, end = shift_bounds(d)
        self.assertEqual(start.hour, 6)
        self.assertEqual(end.hour, 6)
        self.assertEqual((end - start).total_seconds(), 24 * 3600)

    def test_get_current_operational_shift_windows(self):
        """Verify standard 3 shifts: Pagi (06-14), Siang (14-22), Malam (22-06)."""
        dt_pagi = timezone.make_aware(datetime(2026, 11, 10, 9, 30, 0))
        s1 = get_current_operational_shift(dt_pagi)
        self.assertEqual(s1["num"], 1)
        self.assertEqual(s1["tag"], "Pagi")

        dt_siang = timezone.make_aware(datetime(2026, 11, 10, 16, 0, 0))
        s2 = get_current_operational_shift(dt_siang)
        self.assertEqual(s2["num"], 2)
        self.assertEqual(s2["tag"], "Siang")

        dt_malam = timezone.make_aware(datetime(2026, 11, 10, 23, 15, 0))
        s3 = get_current_operational_shift(dt_malam)
        self.assertEqual(s3["num"], 3)
        self.assertEqual(s3["tag"], "Malam")

    def test_minutes_to_pct_and_inverse(self):
        """Verify bi-directional conversion between shift minutes (0-1440) and percentage."""
        self.assertEqual(minutes_to_pct(0), 0.0)
        self.assertEqual(minutes_to_pct(720), 50.0)
        self.assertEqual(minutes_to_pct(1440), 100.0)

        self.assertEqual(pct_to_minutes(0.0), 0)
        self.assertEqual(pct_to_minutes(50.0), 720)
        self.assertEqual(pct_to_minutes(100.0), 1440)

    def test_hour_axis_labels_structure(self):
        """Verify 25 hour ticks starting at 06 and ending at 06 next morning."""
        labels = hour_axis_labels()
        self.assertEqual(len(labels), 25)
        self.assertEqual(labels[0]["label"], "06")
        self.assertEqual(labels[0]["pct"], 0.0)
        self.assertEqual(labels[-1]["label"], "06")
        self.assertEqual(labels[-1]["pct"], 100.0)

    def test_compute_steam_timeline_from_plan_batches(self):
        """Verify steam timeline calculation for AUTO and MANUAL batches."""
        # Create mock batch with 3 blocks: HEAT (30m), STEADY (60m), COOL (30m)
        mock_batch = MagicMock()
        mock_batch.machine_id = 1
        mock_batch.start_offset_minutes = 60
        mock_machine = MagicMock()
        mock_machine.operation_mode = "AUTO"
        mock_batch.machine = mock_machine

        b_heat = MagicMock(phase="HEAT", duration_minutes=30)
        b_steady = MagicMock(phase="STEADY", duration_minutes=60)
        b_cool = MagicMock(phase="COOL", duration_minutes=30)
        mock_batch.blocks.all.return_value = [b_heat, b_steady, b_cool]

        steam_usage_map = {1: 350.0}  # 350 kg/h average steam usage

        res = compute_steam_timeline_from_plan_batches([mock_batch], steam_usage_map)
        values = res["values"]

        self.assertEqual(len(values), TOTAL_BUCKETS)
        self.assertEqual(res["max_kg_h"], 350.0)

        # Before start (minute 0-59): 0 kg/h
        self.assertEqual(values[30], 0.0)
        # In HEAT phase (minute 60-89): 350 kg/h
        self.assertEqual(values[75], 350.0)
        # In STEADY phase (minute 90-149): 350 kg/h
        self.assertEqual(values[100], 350.0)
        # In COOL phase (minute 150-179): 0 kg/h (COOL does not consume steam)
        self.assertEqual(values[160], 0.0)

    def test_compute_carryover_blocks_overflow(self):
        """Verify that batches extending past minute 1440 generate tail blocks for next shift."""
        mock_batch = MagicMock()
        mock_batch.id = 101
        mock_batch.plan_id = 5
        mock_batch.label = "Batch Overflow"
        mock_batch.start_offset_minutes = 1350  # starts 90 min before shift end
        mock_machine = MagicMock(code="JD_01", operation_mode="AUTO")
        mock_batch.machine = mock_machine

        # Block 1: HEAT 60 min (ends at 1410 < 1440)
        # Block 2: STEADY 90 min (1410 to 1500 -> 60 min overflows into next day)
        b1 = MagicMock(phase="HEAT", duration_minutes=60)
        b2 = MagicMock(phase="STEADY", duration_minutes=90)
        mock_batch.blocks.all.return_value = [b1, b2]

        carryover = compute_carryover_blocks([mock_batch])
        self.assertIn("JD_01", carryover)
        entries = carryover["JD_01"]
        self.assertEqual(len(entries), 1)

        tail_blocks = entries[0]["tail_blocks"]
        self.assertEqual(len(tail_blocks), 1)
        self.assertEqual(tail_blocks[0]["phase"], "STEADY")
        self.assertEqual(tail_blocks[0]["duration_minutes"], 60)

    def test_compute_carryover_steam_contribution(self):
        """Verify carryover steam adds load at offset 0 of the current shift."""
        mock_machine = MagicMock(code="JD_01", operation_mode="AUTO", average_steam_usage=400.0)
        carryover_dict = {
            "JD_01": [
                {
                    "machine": mock_machine,
                    "tail_blocks": [{"phase": "STEADY", "duration_minutes": 45}],
                }
            ]
        }
        tail_values = compute_carryover_steam_contribution(carryover_dict)
        self.assertEqual(len(tail_values), TOTAL_BUCKETS)
        # Minute 0-44 should receive 400.0 kg/h
        self.assertEqual(tail_values[10], 400.0)
        # Minute 45+ should be 0.0
        self.assertEqual(tail_values[50], 0.0)

    def test_is_steam_active_state_helper(self):
        """Verify state helper for AUTO and MANUAL modes."""
        self.assertTrue(is_steam_active_state("HEAT", "AUTO"))
        self.assertTrue(is_steam_active_state("STEADY", "AUTO"))
        self.assertFalse(is_steam_active_state("COOL", "AUTO"))
        self.assertFalse(is_steam_active_state("OFF", "AUTO"))

        self.assertTrue(is_steam_active_state("RUNNING", "MANUAL"))
        self.assertFalse(is_steam_active_state("HEAT", "MANUAL"))
        self.assertFalse(is_steam_active_state("STOP", "MANUAL"))
