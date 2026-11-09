import struct
from datetime import datetime, timedelta
from unittest.mock import MagicMock
from django.test import SimpleTestCase
from django.utils import timezone

from monitoring.services.jumo_config import (
    regs_to_float_jumo,
    _parse_start_addr,
    sanitize_values,
    read_all_ai_safe,
    MAX_VALID_VALUE,
)
from monitoring.utils.signal_freshness import (
    is_signal_stale,
    get_machine_display_status,
    STATUS_NO_SIGNAL,
    STALE_THRESHOLD_SECONDS,
)
from monitoring.utils.cooling_active import (
    is_cooling_dyeing_machine,
    is_cooling_active_from_snapshot,
)
from monitoring.utils.steam_active import (
    is_steam_active_from_snapshot,
)
from monitoring.utils.file_parser import (
    FileFormatDetector,
    ParsedData,
)


class ModbusProtocolAndTelemetryTest(SimpleTestCase):
    """
    Unit test suite for JUMO Modbus/TCP decoding, signal freshness,
    cooling/steam detection from snapshots, and raw CSV/Excel file parsing.
    """

    def test_regs_to_float_jumo_ieee754(self):
        """Verify 16-bit Big-Endian register pair conversion to 32-bit float."""
        # 0.0 in float32 = 0x00000000
        self.assertEqual(regs_to_float_jumo(0x0000, 0x0000), 0.0)

        # 100.5 in float32:
        # struct.pack(">f", 100.5) -> b'\x42\xc9\x00\x00'
        # reg_x1 (high 16 bit): 0x42c9, reg_x (low 16 bit): 0x0000
        val = regs_to_float_jumo(0x0000, 0x42C9)
        self.assertAlmostEqual(val, 100.5, places=3)

        # -25.25 in float32:
        b = struct.pack(">f", -25.25)
        high = (b[0] << 8) | b[1]
        low = (b[2] << 8) | b[3]
        self.assertAlmostEqual(regs_to_float_jumo(low, high), -25.25, places=3)

    def test_parse_start_addr_hex_and_decimal(self):
        """Verify parsing of hex (0x1006) and decimal start addresses."""
        self.assertEqual(_parse_start_addr("0x1006"), 4102)
        self.assertEqual(_parse_start_addr("0x0000"), 0)
        self.assertEqual(_parse_start_addr("4102"), 4102)
        self.assertEqual(_parse_start_addr(" 0x1000 "), 4096)

        with self.assertRaises(ValueError):
            _parse_start_addr("invalid_hex")

    def test_sanitize_values_sensor_bounds(self):
        """Verify that sensor readings outside valid thermal range are sanitized to None."""
        raw_values = [25.5, 95.2, None, -1005.0, 999999.0, 100.0]
        sanitized = sanitize_values(raw_values, limit=MAX_VALID_VALUE)

        self.assertEqual(sanitized[0], 25.5)
        self.assertEqual(sanitized[1], 95.2)
        self.assertIsNone(sanitized[2])  # None preserved
        self.assertIsNone(sanitized[3])  # -1005.0 < -1000 -> None
        self.assertIsNone(sanitized[4])  # 999999.0 > limit -> None
        self.assertEqual(sanitized[5], 100.0)
        self.assertIsNone(sanitize_values(None))

    def test_read_all_ai_safe_error_handling(self):
        """Verify error handling in read_all_ai_safe when Modbus responds with error or short registers."""
        mock_client = MagicMock()
        dev = {"start_addr": 4102, "num_ai": 4, "device_id": 1}

        # Subtest 1: Exception thrown by client
        mock_client.read_holding_registers.side_effect = ConnectionResetError("Reset")
        values, err = read_all_ai_safe(mock_client, dev, "TestDev")
        self.assertIsNone(values)
        self.assertIn("Exception Modbus read", err)

        # Subtest 2: Modbus isError() response
        mock_resp = MagicMock()
        mock_resp.isError.return_value = True
        mock_client.read_holding_registers.side_effect = None
        mock_client.read_holding_registers.return_value = mock_resp
        values, err = read_all_ai_safe(mock_client, dev, "TestDev")
        self.assertIsNone(values)
        self.assertIn("Respon Modbus error", err)

        # Subtest 3: Registers list shorter than required (num_ai * 2 = 8)
        mock_resp.isError.return_value = False
        mock_resp.registers = [0x0000, 0x42C9]  # only 2 registers instead of 8
        values, err = read_all_ai_safe(mock_client, dev, "TestDev")
        self.assertIsNone(values)
        self.assertIn("Register kurang/kosong", err)

    def test_is_signal_stale_and_display_status(self):
        """Verify signal staleness calculation for AUTO machines vs MANUAL machines."""
        now = timezone.now()

        # Dummy mock machine AUTO
        mock_machine_auto = MagicMock()
        mock_machine_auto.operation_mode = "AUTO"
        mock_machine_auto.code = "JD_01"
        mock_machine_auto.last_valid_reading_at = now - timedelta(seconds=STALE_THRESHOLD_SECONDS + 15)
        mock_machine_auto.last_thermal_status = "HEAT"

        # Mock get_polled_machine_codes to include JD_01
        from unittest.mock import patch
        with patch("monitoring.utils.signal_freshness.get_polled_machine_codes", return_value={"JD_01"}):
            self.assertTrue(is_signal_stale(mock_machine_auto, now=now))
            status = get_machine_display_status(mock_machine_auto, now=now)
            self.assertEqual(status, STATUS_NO_SIGNAL)

            # When fresh
            mock_machine_auto.last_valid_reading_at = now - timedelta(seconds=10)
            self.assertFalse(is_signal_stale(mock_machine_auto, now=now))
            status = get_machine_display_status(mock_machine_auto, now=now)
            self.assertEqual(status, "HEAT")

        # MANUAL machine should not be affected by Modbus staleness
        mock_machine_manual = MagicMock()
        mock_machine_manual.operation_mode = "MANUAL"
        mock_machine_manual.manual_status = "Running"
        self.assertFalse(is_signal_stale(mock_machine_manual, now=now))
        self.assertEqual(get_machine_display_status(mock_machine_manual, now=now), "Running")

    def test_is_cooling_dyeing_machine_filtering(self):
        """Verify cooling machine prefix identification (JD_*, JR_*, ZET_*)."""
        self.assertTrue(is_cooling_dyeing_machine("JD_01"))
        self.assertTrue(is_cooling_dyeing_machine("jr_03"))
        self.assertTrue(is_cooling_dyeing_machine("ZET_02"))
        self.assertFalse(is_cooling_dyeing_machine("STENTER_01"))
        self.assertFalse(is_cooling_dyeing_machine("BOILER_01"))
        self.assertFalse(is_cooling_dyeing_machine(""))
        self.assertFalse(is_cooling_dyeing_machine(None))

    def test_is_cooling_active_from_snapshot(self):
        """Verify condition for cooling active: thermal_state == 'COOL', temp >= 40.0, grad <= 0.05."""
        # Valid active cooling
        valid_snap = {"thermal_state": "COOL", "temperature": 65.0, "gradient": -0.5}
        self.assertTrue(is_cooling_active_from_snapshot(valid_snap, "JD_01"))

        # Inactive due to low temperature (ambient idle)
        low_temp_snap = {"thermal_state": "COOL", "temperature": 35.0, "gradient": -0.2}
        self.assertFalse(is_cooling_active_from_snapshot(low_temp_snap, "JD_01"))

        # Inactive due to positive gradient (machine heating up)
        rising_snap = {"thermal_state": "COOL", "temperature": 65.0, "gradient": 0.8}
        self.assertFalse(is_cooling_active_from_snapshot(rising_snap, "JD_01"))

        # Inactive due to state being HEAT
        heat_snap = {"thermal_state": "HEAT", "temperature": 75.0, "gradient": 1.2}
        self.assertFalse(is_cooling_active_from_snapshot(heat_snap, "JD_01"))

        # Machine code not a dyeing machine
        self.assertFalse(is_cooling_active_from_snapshot(valid_snap, "MONFONG_01"))

    def test_is_steam_active_auto_vs_manual(self):
        """Verify active steam consumption condition from snapshot."""
        # AUTO machine in HEAT with gradient > -0.1
        heat_snap = {"mode": "AUTO", "detail": "HEAT", "gradient": 0.5, "temperature": 70.0}
        self.assertTrue(is_steam_active_from_snapshot(heat_snap))

        # AUTO machine in STEADY with temp >= 90.0 and gradient > -0.1
        steady_hot_snap = {"mode": "AUTO", "detail": "STEADY", "gradient": 0.0, "temperature": 98.0}
        self.assertTrue(is_steam_active_from_snapshot(steady_hot_snap))

        # AUTO machine in STEADY but low temp (< 90.0) -> false
        steady_low_snap = {"mode": "AUTO", "detail": "STEADY", "gradient": 0.0, "temperature": 85.0}
        self.assertFalse(is_steam_active_from_snapshot(steady_low_snap))

        # MANUAL machine
        manual_running = {"mode": "MANUAL", "status": "Running"}
        manual_stop = {"mode": "MANUAL", "status": "Stop"}
        self.assertTrue(is_steam_active_from_snapshot(manual_running))
        self.assertFalse(is_steam_active_from_snapshot(manual_stop))

    def test_file_format_detector_wide_vs_long(self):
        """Verify file format detector categorizing WIDE vs LONG tables."""
        # 3 columns with timestamp, temperature, machine -> LONG
        long_headers = ["Timestamp", "Temperature", "MachineCode"]
        self.assertEqual(FileFormatDetector.detect(long_headers), "LONG")

        long_headers_id = ["Tanggal Waktu", "Suhu", "Mesin"]
        self.assertEqual(FileFormatDetector.detect(long_headers_id), "LONG")

        # 4+ columns with date, time, and machine names -> WIDE
        wide_headers = ["Tanggal", "Waktu", "JD_01", "JD_02", "JD_03"]
        self.assertEqual(FileFormatDetector.detect(wide_headers), "WIDE")

        # Empty headers
        self.assertEqual(FileFormatDetector.detect([]), "UNKNOWN")

    def test_parsed_data_container(self):
        """Verify ParsedData container conversion to preview dictionary."""
        pd = ParsedData()
        pd.format_type = "WIDE"
        pd.headers = ["Tanggal", "Waktu", "JD_01"]
        pd.rows = [{"Tanggal": "2026-11-09", "Waktu": "08:00", "JD_01": "65.5"}]
        pd.machine_codes = ["JD_01"]
        pd.row_count = 1

        d = pd.to_dict()
        self.assertEqual(d["format_type"], "WIDE")
        self.assertEqual(d["total_rows"], 1)
        self.assertEqual(d["machine_codes"], ["JD_01"])
