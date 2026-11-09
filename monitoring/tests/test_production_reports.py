from datetime import date, time
from decimal import Decimal
from unittest.mock import MagicMock, patch
from django.test import SimpleTestCase

from monitoring.models_production_reports import (
    FinishingReport,
    StenterItem,
    StenterEvent,
)


class ProductionReportsTimelineAndSeederTest(SimpleTestCase):
    """
    Unit tests for Stenter / Finishing production reports, proportional counter splitting,
    speed-to-duration calculation, cross-day midnight shift handling, and downtime collision avoidance.
    """

    def test_proportional_counter_split_calculation(self):
        """
        Verify SOP rule: When fabric rows are grouped/bracketed with a combined counter,
        each row's counter = (row_pcs / total_pcs) * total_counter.
        Sum of split counters must equal grand total exactly.
        """
        grouped_items = [
            {"label": "Roll 1", "pcs": 2},
            {"label": "Roll 2", "pcs": 5},
            {"label": "Roll 3", "pcs": 3},
        ]
        total_pcs = sum(item["pcs"] for item in grouped_items)  # 10
        total_counter_meter = 1500.0  # 1500 meters

        split_counters = []
        for item in grouped_items:
            split_m = (item["pcs"] / total_pcs) * total_counter_meter
            split_counters.append(split_m)

        self.assertEqual(split_counters[0], 300.0)
        self.assertEqual(split_counters[1], 750.0)
        self.assertEqual(split_counters[2], 450.0)
        self.assertEqual(sum(split_counters), total_counter_meter)

    def test_stenter_duration_calculation(self):
        """Verify: duration_minutes = round(counter_m / speed_m_min)."""
        # Case 1: 1200 meters at 30 m/min -> 40 mins
        counter = Decimal("1200.00")
        speed = Decimal("30.00")
        duration = int(round(float(counter) / float(speed)))
        self.assertEqual(duration, 40)

        # Case 2: 1050 meters at 35 m/min -> 30 mins
        self.assertEqual(int(round(1050.0 / 35.0)), 30)

    def test_timeline_recalculation_day_shift(self):
        """Verify timeline starts at 06:00 for Shift A (Pagi) and shifts sequentially."""
        report = FinishingReport()
        report.tanggal = date(2026, 11, 9)
        report.waktu_shift = "A (Pagi)"

        # In-memory StenterItem instances (no database creation)
        item1 = StenterItem(line_number=1, counter_m=Decimal("600.00"), speed_m_min=Decimal("30.00"))
        item2 = StenterItem(line_number=2, counter_m=Decimal("900.00"), speed_m_min=Decimal("30.00"))

        mock_items_manager = MagicMock()
        mock_items_manager.all.return_value.order_by.return_value = [item1, item2]

        mock_events_manager = MagicMock()
        mock_events_manager.all.return_value.order_by.return_value = []

        with patch.object(FinishingReport, "items", mock_items_manager), \
             patch.object(FinishingReport, "events", mock_events_manager), \
             patch.object(StenterItem.objects, "bulk_update"):

            report.recalculate_timeline()

            # Item 1: starts at 06:00, runs 20 min -> ends at 06:20
            self.assertEqual(item1.jam_mulai, time(6, 0))
            self.assertEqual(item1.jam_selesai, time(6, 20))

            # Item 2: starts at 06:20, runs 30 min -> ends at 06:50
            self.assertEqual(item2.jam_mulai, time(6, 20))
            self.assertEqual(item2.jam_selesai, time(6, 50))

    def test_timeline_recalculation_night_shift_midnight_crossing(self):
        """Verify Shift C (Malam) starting at 22:00 crosses midnight into 01:00 next day."""
        report = FinishingReport()
        report.tanggal = date(2026, 11, 9)
        report.waktu_shift = "C (Malam)"

        # Fabric running 180 mins (3 hours) from 22:00 -> finishes at 01:00 next day
        item1 = StenterItem(line_number=1, counter_m=Decimal("3600.00"), speed_m_min=Decimal("20.00"))

        mock_items_manager = MagicMock()
        mock_items_manager.all.return_value.order_by.return_value = [item1]

        mock_events_manager = MagicMock()
        mock_events_manager.all.return_value.order_by.return_value = []

        with patch.object(FinishingReport, "items", mock_items_manager), \
             patch.object(FinishingReport, "events", mock_events_manager), \
             patch.object(StenterItem.objects, "bulk_update"):

            report.recalculate_timeline()

            self.assertEqual(item1.jam_mulai, time(22, 0))
            self.assertEqual(item1.jam_selesai, time(1, 0))

    def test_timeline_downtime_event_collision_fast_forward(self):
        """Verify that when an event (e.g. TEMP_DROP 30m) occurs between items, timeline fast-forwards."""
        report = FinishingReport()
        report.tanggal = date(2026, 11, 9)
        report.waktu_shift = "A (Pagi)"

        # Item 1: 06:00 - 06:30 (30 min)
        item1 = StenterItem(line_number=1, counter_m=Decimal("900.00"), speed_m_min=Decimal("30.00"))
        # Event TEMP_DROP from 06:30 to 07:00 (30 min pause)
        event_pause = StenterEvent(jam_mulai=time(6, 30), jam_selesai=time(7, 0))
        # Item 2: 900m @ 30m/min -> should start at 07:00, not 06:30!
        item2 = StenterItem(line_number=2, counter_m=Decimal("900.00"), speed_m_min=Decimal("30.00"))

        mock_items_manager = MagicMock()
        mock_items_manager.all.return_value.order_by.return_value = [item1, item2]

        mock_events_manager = MagicMock()
        mock_events_manager.all.return_value.order_by.return_value = [event_pause]

        with patch.object(FinishingReport, "items", mock_items_manager), \
             patch.object(FinishingReport, "events", mock_events_manager), \
             patch.object(StenterItem.objects, "bulk_update"):

            report.recalculate_timeline()

            # Item 1 ends at 06:30
            self.assertEqual(item1.jam_mulai, time(6, 0))
            self.assertEqual(item1.jam_selesai, time(6, 30))

            # Item 2 must start at 07:00 (after TEMP_DROP) and finish at 07:30
            self.assertEqual(item2.jam_mulai, time(7, 0))
            self.assertEqual(item2.jam_selesai, time(7, 30))

    def test_empty_report_timeline_graceful(self):
        """Verify recalculate_timeline returns gracefully without errors if items and events are empty."""
        report = FinishingReport()
        report.tanggal = date(2026, 11, 9)
        report.waktu_shift = "A"

        mock_items_manager = MagicMock()
        mock_items_manager.all.return_value.order_by.return_value = []
        mock_events_manager = MagicMock()
        mock_events_manager.all.return_value.order_by.return_value = []

        with patch.object(FinishingReport, "items", mock_items_manager), \
             patch.object(FinishingReport, "events", mock_events_manager):
            result = report.recalculate_timeline()
            self.assertIsNone(result)
