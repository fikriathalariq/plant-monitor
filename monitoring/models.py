from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
import math
import os


class MachineGroup(models.Model):
    code = models.CharField(
        max_length=10,
        unique=True,
        help_text="Kode group, misal: PRC, PRT"
    )
    name = models.CharField(
        max_length=50,
        help_text="Nama group, misal: Proses Continuous / Proses Printing"
    )
    description = models.TextField(
        blank=True,
        help_text="Keterangan tambahan (opsional)"
    )
    
    PROCESS_TYPE_CHOICES = [
        ("JET", "Mesin Jet"),
        ("CONTINUOUS", "Mesin Continous"),
        ("ENERGY_SOURCE", "Mesin Sumber Energi"),
    ]
    
    process_type = models.CharField(
        max_length=20,
        choices=PROCESS_TYPE_CHOICES,
        blank=True,
        null=True,
        help_text="Jenis proses mesin"
    )

    def __str__(self):
        return f"{self.code} - {self.name}"



PHYSICS_GROUP_CHOICES = [
    ('A_2800L', 'Group A (2800L)'),
    ('B_4000L', 'Group B (4000L)'),
    ('C_2000L', 'Group C (2000L)'),
    ('D_5000L', 'Group D (5000L)'),
    ('E_1500L', 'Group E (1500L)'),
    ('F_700L',  'Group F Mini (700L)'),
]

class Machine(models.Model):
    MODE_CHOICES = [
        ("AUTO", "Mode Otomatis"),
        ("MANUAL", "Mode Manual"),
    ]

    # Tipe status menentukan pilihan manual_status yang tersedia
    STATUS_TYPE_CHOICES = [
        (1, "Tipe 1: Stop / Running"),
        (2, "Tipe 2: Stop / Running / Standby"),
        (3, "Tipe 3: Stop / Standby / Preset & Final"),
    ]

    # Semua kemungkinan manual status dari ketiga tipe
    MANUAL_STATUS_CHOICES = [
        ("Stop",                    "Stop"),
        ("Running",                 "Running"),
        ("Standby",                 "Standby"),
        ("Preset Suhu Tinggi",      "Preset Suhu Tinggi"),
        ("Preset Suhu Rendah",      "Preset Suhu Rendah"),
        ("Final Resin Suhu Tinggi", "Final Resin Suhu Tinggi"),
        ("Final Resin Suhu Rendah", "Final Resin Suhu Rendah"),
        ("Final Kering",            "Final Kering"),
    ]

    # Mapping tipe → daftar status yang diizinkan
    STATUS_TYPE_MAP = {
        1: ["Stop", "Running"],
        2: ["Stop", "Running", "Standby"],
        3: [
            "Stop", "Standby",
            "Preset Suhu Tinggi", "Preset Suhu Rendah",
            "Final Resin Suhu Tinggi", "Final Resin Suhu Rendah",
            "Final Kering",
        ],
    }

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=50, unique=True)

    group = models.ForeignKey("MachineGroup", on_delete=models.CASCADE)

    category = models.CharField(
        max_length=20,
        choices=[
            ('FINISHING', 'Finishing (Stenter / Monfong / Ehwa)'),
            ('SCOURING', 'Scouring (SMCH)'),
            ('DYEING', 'Dyeing (JD / JR)'),
            ('ROLL_OFF', 'Persiapan / Roll Off'),
            ('CDR', 'Continuous Dyeing Range'),
        ],
        null=True,
        blank=True,
        verbose_name="Kategori Mesin",
        help_text="Opsional. Jika tidak diisi, tidak ada efek samping apa pun (semua fitur tetap berjalan normal)."
    )

    # NEW FIELD
    operation_mode = models.CharField(
        max_length=10,
        choices=MODE_CHOICES,
        default="AUTO"
    )

    valid_min = models.FloatField(
        default=-50.0,
        verbose_name="Batas Bawah Sensor Valid",
        help_text="Nilai di bawah ini dianggap Noise/Sensor Putus. JD=10.0, CDR Speed=-20.0, Steam_Pr=0.0"
    )
    
    valid_max = models.FloatField(
        default=1000.0,
        verbose_name="Batas Atas Sensor Valid",
        help_text="Nilai di atas ini dianggap Short Circuit / Sensor Rusak."
    )

    # NEW FIELD: Kapasitas mesin (kW) untuk referensi load factor / kalkulasi
    nominal_power = models.FloatField(
        null=True, 
        blank=True, 
        help_text="Daya Nominal (kW) untuk referensi analisis energi."
    )

    # NEW FIELD: Rata-rata penggunaan uap per jam (kg/h)
    average_steam_usage = models.FloatField(
        default=0,
        help_text="Rata-rata penggunaan uap per jam (kg/h)"
    )

    # NEW FIELD: Penggunaan steam (kg) untuk 1 batch Jet Dyeing
    batch_steam = models.FloatField(
        default=0,
        help_text="Penggunaan steam (kg) untuk 1 batch Jet Dyeing"
    )

    # NEW FIELD: Loss steam (kg) untuk setiap 1 jam
    losses_steam = models.FloatField(
        default=0,
        help_text="Loss steam (kg) untuk setiap 1 jam"
    )

    # NEW FIELD: Kapasitas Air Maksimal (Liter)
    max_water_capacity = models.FloatField(
        null=True,
        blank=True,
        help_text="Kapasitas Air Maksimal (Liter)"
    )

    # NEW FIELD: Kapasitas Kain Maksimal (kg)
    max_fabric_capacity = models.FloatField(
        null=True,
        blank=True,
        help_text="Kapasitas Kain Maksimal (kg)"
    )

    # NEW FIELD: Luas Permukaan (m^2)
    surface_area = models.FloatField(
        null=True,
        blank=True,
        help_text="Luas Permukaan (m^2)"
    )

    # NEW FIELD: U-Value / Nilai Insulasi (W/m².K)
    u_value = models.FloatField(
        null=True,
        blank=True,
        help_text="U-Value / Nilai Insulasi (W/m².K)"
    )

    # NEW FIELD: C_Mesin / Kapasitas Kalor Mesin Kosong (kJ/K)
    c_machine = models.FloatField(
        null=True,
        blank=True,
        help_text="C_Mesin / Kapasitas Kalor Mesin Kosong (kJ/K)"
    )
    
    # NEW FIELD: Kalori Rata-Rata HTO
    avg_hto_calories = models.FloatField(
        default=0,
        help_text="Kalori Rata-Rata HTO (energi yang diperlukan)"
    )

    # AUTO MODE FIELDS
    temperature = models.FloatField(null=True, blank=True)
    temperature_gradient = models.FloatField(null=True, blank=True)
    
    # Tipe status mesin (menentukan pilihan manual_status)
    status_type = models.IntegerField(
        choices=STATUS_TYPE_CHOICES,
        default=1,
        help_text="Tipe status menentukan pilihan yang tersedia saat kontrol manual"
    )

    # MANUAL MODE FIELDS
    manual_status = models.CharField(
        max_length=30,
        choices=MANUAL_STATUS_CHOICES,
        null=True,
        blank=True,
        default="Stop",
    )
    
    UNIT_BOOLEAN = "BOOL"
    UNIT_CELSIUS = "C"
    UNIT_VOLT = "V"
    UNIT_AMPERE = "A"
    UNIT_BAR = "BAR"
    UNIT_KW = "KW"
    UNIT_HZ = "HZ"

    UNIT_CHOICES = [
        (UNIT_CELSIUS, "Derajat Celcius (°C)"),
        (UNIT_VOLT,    "Volt (V)"),
        (UNIT_AMPERE,  "Ampere (A)"),
        (UNIT_BAR,     "Barg"),
        (UNIT_KW,      "kW"),
        (UNIT_BOOLEAN, "Boolean (ON/OFF)"),
        (UNIT_HZ,      "Hertz (Hz)"),
        
    ]

    unit = models.CharField(
        max_length=8,
        choices=UNIT_CHOICES,
        default=UNIT_CELSIUS,   # ✅ default-nya °C
    )

    @property
    def unit_symbol(self) -> str:
        """
        Simbol pendek untuk ditampilkan di UI.
        """
        mapping = {
            self.UNIT_CELSIUS: "°C",
            self.UNIT_VOLT: "V",
            self.UNIT_AMPERE: "A",
            self.UNIT_BAR: "barg",
            self.UNIT_KW: "kW",
            self.UNIT_BOOLEAN: "",   # boolean biasanya tidak pakai unit
            self.UNIT_HZ: "Hz",
        }
        return mapping.get(self.unit, "")
    
    @property
    def manual_status_options(self):
        """
        Return list pilihan manual_status yang valid sesuai status_type mesin ini.
        Digunakan oleh frontend (dropdown) dan validasi.
        """
        return self.STATUS_TYPE_MAP.get(self.status_type, ["Stop", "Running"])

    @property
    def is_manual_on(self):
        """
        True kalau mesin sedang aktif di mode manual (bukan Stop).
        """
        return self.operation_mode == "MANUAL" and self.manual_status not in ("Stop", None, "")

    def clean(self):
        """Validasi: manual_status harus sesuai dengan status_type."""
        if self.manual_status and self.manual_status not in self.manual_status_options:
            raise ValidationError({
                "manual_status": (
                    f"Status '{self.manual_status}' tidak valid untuk "
                    f"{self.get_status_type_display()}. "
                    f"Pilihan yang tersedia: {', '.join(self.manual_status_options)}."
                )
            })

    # STATUS (berlaku untuk kedua mode)
    last_status = models.CharField(
        max_length=20,
        choices=[
            ("Running", "Running"),
            ("Warning", "Warning"),
            ("Stop", "Stop"),
            ("Offline", "Offline"),
            ("No Signal", "No Signal"),
        ],
        default="Offline",
    )
    
    # THERMAL STATUS (from MachineMinuteLog)
    last_thermal_status = models.CharField(
        max_length=10,
        choices=[
            ("OFFLINE", "Offline/No Data"),
            ("OFF", "Off"),
            ("HEAT", "Heating"),
            ("STEADY", "Steady"),
            ("COOL", "Cooling"),
            ("FAULT", "Fault/Sensor Error"),
        ],
        default="OFFLINE",
        blank=True,
        help_text="Thermal state from latest MachineMinuteLog"
    )

    last_update = models.DateTimeField(null=True, blank=True)

    # Waktu pembacaan Modbus valid terakhir (HANYA diisi jumo_realtime).
    # Dipakai untuk deteksi No Signal; jangan di-refresh oleh log_minute_history.
    last_valid_reading_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp pembacaan sensor valid terakhir dari jumo_realtime",
    )

    # ── Status-change tracking (diisi otomatis oleh MachineMinuteLog.save) ───────
    # Menyimpan KAPAN status terakhir kali berubah dan apa status sebelumnya.
    # Ini menghindari kebutuhan query snapshot saat dashboard ditampilkan.
    status_changed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Waktu status terakhir berubah (auto-filled)"
    )
    previous_display_status = models.CharField(
        max_length=20, blank=True, default='',
        help_text="Status sebelum perubahan terakhir (auto-filled)"
    )

    is_active = models.BooleanField(default=True)
    physics_group = models.CharField(
        max_length=20, choices=PHYSICS_GROUP_CHOICES, null=True, blank=True,
        help_text="Grup termodinamika mesin (Group A, B, C, D, E). Dipakai sebagai Fallback PINN."
    )

    def __str__(self):
        return self.name

class MachineSensorProfile(Machine):
    """Proxy model khusus untuk merapikan UI Django Admin agar Mapping tidak bercampur dengan master Machine"""
    class Meta:
        proxy = True
        verbose_name = "Sensor Mapping Profile"
        verbose_name_plural = "Sensor Mapping Profiles"

class MachineSensorMapping(models.Model):
    ROLE_CHOICES = [
        ("TRIGGER_OP", "Trigger Operation (Penentu Availability)"),
        ("TRIGGER_ENERGY", "Trigger Energy (Penentu Konsumsi Energi)"),
        ("QUALITY", "Metric Quality (Parameter Mutu)"),
        ("UTILITY_RESOURCE", "Utility Resource (Sumber Energi Global)"),
    ]
    EVAL_METHOD_CHOICES = [
        ("STATIC_HYSTERESIS", "Evaluasi Angka Absolut (Contoh: Speed CDR)"),
        ("THERMAL_STATE_BASED", "Ikuti Thermal State Bawaan Mesin (Contoh: Suhu Batch)"),
    ]
    UTILITY_CHOICES = [
        ("STEAM", "Steam"), ("OIL", "Thermal Oil"), 
        ("AIR", "Compressed Air"), ("ELECTRIC", "Listrik")
    ]
    
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="sensor_mappings")
    sensor_machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="mapped_as_sensor_to")
    
    role = models.CharField(max_length=20, choices=ROLE_CHOICES)
    utility_type = models.CharField(max_length=20, choices=UTILITY_CHOICES, blank=True, null=True)
    eval_method = models.CharField(max_length=20, choices=EVAL_METHOD_CHOICES, default="STATIC_HYSTERESIS")
    
    threshold_on = models.FloatField(null=True, blank=True, help_text="Hanya untuk STATIC_HYSTERESIS")
    threshold_off = models.FloatField(null=True, blank=True, help_text="Hanya untuk STATIC_HYSTERESIS")

    class Meta:
        constraints = [
            # 1. Mutlak: Maksimal SATU TRIGGER_OP dan SATU TRIGGER_ENERGY per mesin
            models.UniqueConstraint(
                fields=['machine', 'role'],
                condition=models.Q(role__in=["TRIGGER_OP", "TRIGGER_ENERGY"]),
                name="unique_trigger_role_per_machine"
            ),
            # 2. Sisanya (QUALITY, UTILITY): Boleh banyak, asal sensornya beda
            models.UniqueConstraint(
                fields=['machine', 'sensor_machine', 'role'],
                name="unique_mapping_per_machine_sensor_role"
            )
        ]

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.role == "UTILITY_RESOURCE" and not self.utility_type:
            raise ValidationError({"utility_type": "Wajib diisi jika role UTILITY_RESOURCE."})
        if self.eval_method == "STATIC_HYSTERESIS" and (self.threshold_on is not None and self.threshold_off is not None):
            if self.threshold_off >= self.threshold_on:
                raise ValidationError({"threshold_off": "Threshold OFF harus lebih kecil dari Threshold ON."})
        
        # UI Validation
        if self.role in ["TRIGGER_OP", "TRIGGER_ENERGY"]:
            existing = MachineSensorMapping.objects.filter(machine=self.machine, role=self.role)
            if self.pk:
                existing = existing.exclude(pk=self.pk)
            if existing.exists():
                raise ValidationError({"role": f"Mesin ini sudah memiliki {self.role}. Hanya boleh ada 1 per mesin."})


    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)
        
    def __str__(self):
        return f"{self.machine.code} <- {self.role} <- {self.sensor_machine.code}"

class Shift(models.Model):
    code = models.CharField(max_length=20, unique=True, help_text="Kode shift, misal: Shift-A")
    name = models.CharField(max_length=50, help_text="Nama shift, misal: Shift A")
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class PagePermission(models.Model):
    """Defines available pages in the system that can be controlled"""
    code = models.CharField(
        max_length=50, 
        unique=True, 
        help_text="Kode halaman, misal: dashboard"
    )
    name = models.CharField(
        max_length=100, 
        help_text="Nama halaman, misal: Dashboard"
    )
    url_name = models.CharField(
        max_length=100, 
        help_text="Nama URL dari urls.py"
    )
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    
    class Meta:
        ordering = ['name']
        verbose_name = "Page Permission"
        verbose_name_plural = "Page Permissions"
    
    def __str__(self):
        return self.name


class Position(models.Model):
    code = models.CharField(max_length=20, unique=True, help_text="Kode posisi, misal: SUPV")
    name = models.CharField(max_length=50, help_text="Nama posisi, misal: Supervisor Produksi")
    is_active = models.BooleanField(default=True)
    allowed_pages = models.ManyToManyField(
        PagePermission,
        blank=True,
        related_name="positions",
        help_text="Halaman yang bisa diakses oleh posisi ini"
    )

    def __str__(self):
        return self.name

class CompanyProfile(models.Model):
    name = models.CharField(max_length=200)
    logo = models.ImageField(upload_to="company_logo/", blank=True, null=True)

    def __str__(self):
        return self.name

class OperatorProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    display_name = models.CharField(max_length=100, help_text="Nama tampilan di dashboard")
    position = models.ForeignKey(
        Position,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Posisi operator"
    )
    shift = models.ForeignKey(
        Shift,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Shift aktif"
    )

    def __str__(self):
        return self.display_name or self.user.username

class MachineMinuteLog(models.Model):
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="minute_logs",
        db_index=False,
    )
    timestamp = models.DateTimeField(db_index=True)

    # Raw data from sensor (sebelum kalibrasi)
    raw_temperature = models.FloatField(
        null=True, blank=True,
        help_text="Nilai suhu asli dari sensor sebelum kalibrasi. Diisi otomatis saat save."
    )
    # Nilai suhu setelah kalibrasi (yang digunakan untuk semua proses downstream)
    temperature = models.FloatField(null=True, blank=True)
    last_status = models.CharField(max_length=20, blank=True)

    # === PROCESSED/FILTERED DATA ===
    filtered_temp = models.FloatField(
        null=True, blank=True,
        help_text="Suhu setelah filtering (Outlier + EWMA + Kalman)"
    )
    gradient = models.FloatField(
        null=True, blank=True,
        help_text="Gradien suhu (°C/min) setelah smoothing"
    )
    thermal_state = models.CharField(
        max_length=10,
        choices=[
            ("OFFLINE", "Offline/No Data"),
            ("OFF", "Off"),
            ("HEAT", "Heating"),
            ("STEADY", "Steady"),
            ("COOL", "Cooling"),
            ("FAULT", "Fault/Sensor Error"),
        ],
        blank=True,
        default="",
        help_text="State termal: OFFLINE/OFF/HEAT/STEADY/COOL/FAULT"
    )

    # === FILTER STATE (untuk kontinuitas antar record) ===
    ewma_temp = models.FloatField(null=True, blank=True, help_text="EWMA output")
    kalman_x = models.FloatField(null=True, blank=True, help_text="Kalman state estimate")
    kalman_p = models.FloatField(null=True, blank=True, help_text="Kalman error covariance")
    
    # Gradient filter state (NEW)
    ewma_gradient = models.FloatField(null=True, blank=True, help_text="EWMA gradient output")
    kalman_grad_x = models.FloatField(null=True, blank=True, help_text="Kalman gradient estimate")

    data_quality = models.CharField(
        max_length=10,
        default="NORMAL",
        choices=[
            ("NORMAL",   "Normal - Sensor membaca data valid"),
            ("SHADOWED", "Shadowed - Nilai dibekukan dari menit sebelumnya"),
            ("OFFLINE",  "Offline - Tidak ada data valid"),
        ]
    )

    class Meta:
        ordering = ['-timestamp']
        unique_together = [['machine', 'timestamp']]
        indexes = [
            models.Index(fields=['machine', '-timestamp'], name='idx_log_machine_ts_desc'),
            models.Index(fields=['machine', 'timestamp', 'data_quality'], name='idx_log_machine_ts_dq'),
        ]



    def __str__(self):
        return f"{self.machine.code} @ {self.timestamp:%Y-%m-%d %H:%M}"


    def save(self, *args, **kwargs):
        # === STEP 0: APPLY CALIBRATION ===
        # Simpan nilai raw sensor ke raw_temperature (hanya jika belum diisi)
        if self.raw_temperature is None:
            self.raw_temperature = self.temperature

        # Terapkan kalibrasi: temperature = hasil kalibrasi dari raw_temperature
        self.temperature = get_calibrated_temperature(self.machine_id, self.raw_temperature)

        # Clamping khusus untuk sensor dengan unit Hz (misal Speed Batu Bara)
        if self.temperature is not None and getattr(self, 'machine', None) and self.machine.unit == 'HZ':
            if isinstance(self.temperature, (int, float)) and self.temperature < 0.2:
                self.temperature = 0.0

        # Use centralized helpers for temperature validation
        from monitoring.utils.gradient_processor import (
            is_invalid_temperature, get_machine_status, get_filtered_temp_for_invalid
        )
        
        is_invalid_temp = is_invalid_temperature(self.temperature)
        
        if is_invalid_temp:
            # If temp is "-", filtered_temp should also be "-"
            self.filtered_temp = get_filtered_temp_for_invalid(self.temperature)
            self.gradient = None
            self.thermal_state = "OFFLINE"  # Changed from OFF to OFFLINE
            # Clear all filter states
            self.ewma_temp = None
            self.kalman_x = None
            self.kalman_p = None
            self.ewma_gradient = None
            self.kalman_grad_x = None

        # 2. Automatic Gradient Calculation if valid and missing
        elif (self.filtered_temp is None or self.gradient is None):
            
            from monitoring.utils.gradient_processor import GradientProcessor, FilterState, ProcessingConfig, build_filter_state_from_log
            
            # Fetch previous log for continuity (Filter State)
            # Use timestamp < current timestamp for this machine
            prev_log = MachineMinuteLog.objects.filter(
                machine=self.machine, 
                timestamp__lt=self.timestamp
            ).order_by('-timestamp').first()
            
            config = ProcessingConfig()
            processor = GradientProcessor(config)

            # Reconstruct FilterState
            if prev_log and prev_log.ewma_temp is not None:
                state = build_filter_state_from_log(prev_log, config)
                prev_timestamp = prev_log.timestamp
            else:
                state = FilterState()
                prev_timestamp = None
            
            # Calculate dt
            if prev_timestamp:
                dt_minutes = (self.timestamp - prev_timestamp).total_seconds() / 60.0
            else:
                dt_minutes = 1.0
            
            dt_minutes = max(0.5, min(dt_minutes, 10.0))
            
            # Process
            filtered, gradient, thermal_state, new_state = processor.process_single(
                raw_temp=self.temperature,
                state=state,
                dt_minutes=dt_minutes
            )
            
            # Apply results to self
            self.filtered_temp = filtered
            self.gradient = round(gradient, 4) if gradient is not None else None
            self.thermal_state = thermal_state
            
            # Store State
            self.ewma_temp = new_state.ewma_temp
            self.kalman_x = new_state.kalman_x
            self.kalman_p = new_state.kalman_p
            self.ewma_gradient = new_state.ewma_gradient
            self.kalman_grad_x = new_state.kalman_grad_x
            
        # POPULATE SELF.LAST_STATUS (derived from thermal_state)
        # Mapping: HEAT/COOL/STEADY→Running, OFF→Stop, OFFLINE→Offline, FAULT→Warning
        self.last_status = get_machine_status(self.thermal_state)

        # SYNC MACHINE STATUS (Only if this is the latest log)
        newer_exists = MachineMinuteLog.objects.filter(
            machine=self.machine, 
            timestamp__gt=self.timestamp
        ).exists()

        if not newer_exists:
            # Derive last_status from thermal_state using centralized mapping
            new_last_status = get_machine_status(self.thermal_state)
            new_thermal     = self.thermal_state

            # ─ Tentukan display_status (sama seperti logika di views.py dashboard) ─
            if self.machine.operation_mode == "MANUAL":
                new_display = self.machine.manual_status or "Stop"
            elif self.machine.code in ["Oil_Temp", "Steam_Pr"]:
                new_display = new_last_status
            else:
                new_display = new_thermal or "OFFLINE"

            # Ambil display_status lama sebelum di-update
            if self.machine.operation_mode == "MANUAL":
                old_display = self.machine.manual_status or "Stop"
            elif self.machine.code in ["Oil_Temp", "Steam_Pr"]:
                old_display = self.machine.last_status or "Offline"
            else:
                old_display = self.machine.last_thermal_status or "OFFLINE"

            update_fields = ['last_status', 'last_thermal_status', 'last_update', 'temperature_gradient']

            # Jika status berubah, catat waktu perubahan dan status sebelumnya
            if new_display != old_display:
                self.machine.previous_display_status = old_display
                self.machine.status_changed_at = self.timestamp
                update_fields += ['previous_display_status', 'status_changed_at']

            self.machine.last_status        = new_last_status
            self.machine.last_thermal_status = new_thermal
            self.machine.last_update        = self.timestamp
            self.machine.temperature_gradient = self.gradient
            self.machine.save(update_fields=update_fields)

        super().save(*args, **kwargs)



class MachinePhysicsProfile(models.Model):
    """
    DNA Termodinamika mesin — parameter fisika hasil kalibrasi PINN.
    Setiap mesin punya 1 profil aktif (is_active=True).
    Riwayat kalibrasi lama diarsip (is_active=False).
    """
    machine = models.ForeignKey(
        'Machine', on_delete=models.CASCADE,
        related_name='physics_profiles'
    )
    
    # ── Parameter ODE Fisika ──────────────────────────────────────
    meq = models.FloatField(help_text="Massa termal efektif (kJ/degC)")
    uloss = models.FloatField(help_text="Koefisien rugi radiasi (kW/degC)")
    p_set = models.FloatField(help_text="Batas tekanan optimal uap (Bar)")
    k_drop = models.FloatField(help_text="Penalti fraksi uap basah per Bar drop")
    n_exp = models.FloatField(help_text="Eksponen penalti tekanan drop")

    # ── Lokasi Bobot NN di Filesystem ────────────────────────────
    weights_path = models.CharField(
        max_length=500, blank=True,
        help_text="Path absolut ke file .npy bobot PINN"
    )

    # ── Metadata Kalibrasi ────────────────────────────────────────
    machine_group = models.CharField(
        max_length=20, blank=True,
        help_text="A_2800L | B_4000L | C_2000L | D_5000L | E_1500L"
    )
    is_best_of_group = models.BooleanField(
        default=False,
        help_text="True jika profil ini menjadi referensi terbaik untuk grupnya"
    )
    calibration_mae_pct = models.FloatField(
        null=True, blank=True,
        help_text="Mean Absolute Error (%) saat kalibrasi"
    )
    calibration_batches = models.JSONField(
        default=list,
        help_text="List batch_number yang dipakai saat kalibrasi"
    )
    calibrated_at = models.DateTimeField(auto_now_add=True)
    calibrated_by = models.CharField(max_length=100, blank=True)
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-calibrated_at']
        indexes = [
            models.Index(fields=['machine', 'is_active']),
            models.Index(fields=['machine_group', 'is_best_of_group']),
        ]
    
    def __str__(self):
        return f"{self.machine.code} Physics Profile ({self.calibrated_at.date()})"
    
    def get_weights(self):
        """Load bobot PINN dari filesystem. Return None jika belum ada."""
        import numpy as np
        if self.weights_path and os.path.exists(self.weights_path):
            return np.load(self.weights_path)
        return None
    
    def to_physics_dict(self) -> dict:
        """Return parameter fisika sebagai dict untuk PINNSteamPredictor."""
        return {
            'meq': self.meq, 'uloss': self.uloss,
            'p_set': self.p_set, 'k_drop': self.k_drop, 'n_exp': self.n_exp
        }


    @classmethod
    def get_best_for_machine(cls, machine):
        """Cari profil Best-of-Group yang kompatibel untuk mesin ini."""
        if not machine.physics_group:
            return None
        return cls.objects.filter(
            machine_group=machine.physics_group,
            is_best_of_group=True,
            is_active=True
        ).exclude(machine=machine).first()
    @classmethod
    def get_best_for_group(cls, machine_group: str):
        """Ambil profil referensi terbaik untuk kelompok mesin tertentu."""
        return cls.objects.filter(
            machine_group=machine_group,
            is_best_of_group=True,
            is_active=True
        ).first()

class DyeingProcess(models.Model):
    """
    Tracks complete dyeing process cycles (HEAT → STEADY → COOL → OFF).
    Each record represents one batch/cycle.
    """
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="dyeing_processes",
    )
    batch_number = models.PositiveIntegerField(
        help_text="Auto-increment batch number per machine"
    )
    
    # Timestamps
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(null=True, blank=True)
    
    # Event Timestamps (untuk analisis detail)
    heating_start_time = models.DateTimeField(null=True, blank=True, help_text="Waktu mulai heating (first HEAT state)")
    steady_start_time = models.DateTimeField(null=True, blank=True, help_text="Waktu mulai steady")
    cooling_start_time = models.DateTimeField(null=True, blank=True, help_text="Waktu mulai cooling setelah peak")
    reached_70c_time = models.DateTimeField(null=True, blank=True, help_text="Waktu mencapai 70°C saat cooling")
    
    # === ENERGY CONSUMPTION ===
    machine_nominal_power = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Snapshot daya mesin (kW) dari Machine.nominal_power "
            "pada saat batch ini diproses. Disimpan agar histori "
            "tidak berubah jika data mesin diupdate di masa depan."
        )
    )
    power_consumption_kwh = models.FloatField(
        null=True, blank=True,
        help_text=(
            "Konsumsi daya (kWh) = (end_time - heating_start_time) "
            "dalam jam × machine_nominal_power. Jika heating_start_time "
            "kosong, fallback ke start_time."
        )
    )
    program_ideal_duration_mins = models.FloatField(
        null=True, blank=True,
        help_text="Snapshot durasi ideal (menit) dari ProgramMaster saat batch diproses."
    )
    ideal_power_consumption_kwh = models.FloatField(
        null=True, blank=True,
        help_text="Snapshot listrik ideal (kWh). Dihitung dari durasi ideal x nominal_power."
    )

    # Parameter Analitik Penagihan Listrik (WBP & LWBP)
    power_consumption_wbp_kwh = models.FloatField(null=True, blank=True, help_text="Konsumsi Listrik di jam WBP (kWh)")
    power_consumption_lwbp_kwh = models.FloatField(null=True, blank=True, help_text="Konsumsi Listrik di luar jam WBP (kWh)")
    power_cost_wbp = models.FloatField(null=True, blank=True, help_text="Biaya Listrik WBP (Rp)")
    power_cost_lwbp = models.FloatField(null=True, blank=True, help_text="Biaya Listrik LWBP (Rp)")
    power_cost_total = models.FloatField(null=True, blank=True, help_text="Total Biaya Listrik (Rp)")
    power_cost_ideal = models.FloatField(null=True, blank=True, help_text="Biaya Listrik Ideal (Rp) - Menggunakan tarif LWBP")
    power_cost_loss = models.FloatField(null=True, blank=True, help_text="Loss Biaya Listrik (Rp) = Total - Ideal")
    
    # Phase durations (minutes)
    heating_duration = models.FloatField(null=True, blank=True, help_text="Durasi heating (menit)")
    heating_avg_gradient = models.FloatField(null=True, blank=True, help_text="Gradien rata-rata heating (°C/min)")
    
    steady_duration = models.FloatField(null=True, blank=True, help_text="Durasi steady (menit)")
    
    cooling_duration = models.FloatField(null=True, blank=True, help_text="Durasi cooling (menit)")
    cooling_avg_gradient = models.FloatField(null=True, blank=True, help_text="Gradien rata-rata cooling (°C/min)")
    
    # Temperature Metrics
    start_temp = models.FloatField(null=True, blank=True, help_text="Suhu awal batch")
    end_temp = models.FloatField(null=True, blank=True, help_text="Suhu akhir batch")
    max_temp = models.FloatField(null=True, blank=True, help_text="Suhu maksimum tercapai (peak)")
    
    # Enhanced Efficiency Metrics
    avg_heating_efficiency = models.FloatField(null=True, blank=True, help_text="Efisiensi rata-rata heating (K)")
    real_heating_duration = models.FloatField(null=True, blank=True, help_text="Durasi real heating/Rise Time (menit)")
    duration_effective = models.FloatField(null=True, blank=True, help_text="Durasi efektif dari heat start sampai 70°C (menit)")
    heating_gradient_duration = models.FloatField(null=True, blank=True, help_text="Durasi dengan gradient > 0.1 (menit)")
    heating_span = models.FloatField(null=True, blank=True, help_text="Span dari first HEAT sampai last HEAT (menit)")
    
    # Physics-based Analysis (Newton's Law of Heating)
    ideal_heating_time = models.FloatField(null=True, blank=True, help_text="Waktu heating teoritis ideal menggunakan k=4.3e-4/sec (menit)")
    heating_lag_time = models.FloatField(null=True, blank=True, help_text="Selisih waktu heating: Real - Ideal (menit)")
    avg_steam_temp = models.FloatField(null=True, blank=True, help_text="Rata-rata suhu steam (Tsteam) selama heating (°C)")
    avg_steam_pressure = models.FloatField(null=True, blank=True, help_text="Rata-rata tekanan steam selama heating (Bar Gauge)")
    
    # Stats
    is_complete = models.BooleanField(default=False, help_text="Apakah proses sudah selesai (sudah OFF)")
    is_valid_process = models.BooleanField(default=True, verbose_name="Process?")
    

    # ── PINN Steam Prediction — 3-Layer System ───────────────────
    predicted_steam_kg = models.FloatField(
        null=True, blank=True,
        help_text="[Lapis 1] Prediksi PINN parameter DNA mesin ini sendiri (kg)"
    )
    predicted_steam_best_kg = models.FloatField(
        null=True, blank=True,
        help_text="[Lapis 2] Prediksi PINN parameter mesin terbaik sejenis (kg)"
    )
    predicted_steam_ideal_kg = models.FloatField(
        null=True, blank=True,
        help_text="[Lapis 3] Prediksi PINN best model + fraksi uap sempurna x=1.0 (kg)"
    )
    steam_computed_at = models.DateTimeField(
        null=True, blank=True,
        help_text="Waktu terakhir ketiga prediksi dihitung"
    )
    class Meta:
        ordering = ['-start_time']
        unique_together = ['machine', 'batch_number']
        indexes = [
            models.Index(fields=['machine', 'start_time']),
        ]
    
    def __str__(self):
        status = "Complete" if self.is_complete else "In Progress"
        return f"{self.machine.code} Batch #{self.batch_number} ({status})"
    
    @property
    def total_duration(self):
        """Total duration in minutes."""
        if self.end_time and self.start_time:
            return (self.end_time - self.start_time).total_seconds() / 60
        return None
    
    @property
    def heating_efficiency_percent(self):
        """Calculate heating efficiency percentage."""
        if not self.heating_duration:
            return None
        
        try:
            # Import here to avoid circular dependency
            from monitoring.utils.gradient_processor import ProcessingConfig
            
            # Get logs for this batch
            start_dt = self.start_time
            end_dt = self.end_time or timezone.now()
            
            logs = MachineMinuteLog.objects.filter(
                machine=self.machine,
                timestamp__range=(start_dt, end_dt),
                thermal_state="HEAT"
            ).order_by("timestamp")
            
            if not logs.exists():
                return None
            
            # Get start and end temperatures during heating
            start_temp = None
            end_temp = None
            
            for log in logs:
                if log.temperature is not None:
                    if start_temp is None:
                        start_temp = log.temperature
                    end_temp = log.temperature
            
            if not start_temp or not end_temp:
                return None
            
            # Get config
            try:
                cfg = ProcessingConfig()
            except:
                class DefaultConfig:
                    T_STEAM = 155.0
                    UA_mCp = 0.00385
                cfg = DefaultConfig()
            
            # Calculate ideal heating time
            if end_temp < cfg.T_STEAM:
                numerator = cfg.T_STEAM - end_temp
                denominator = cfg.T_STEAM - start_temp
                
                if numerator > 0 and denominator > 0:
                    val = numerator / denominator
                    t_ideal_sec = - (1.0 / cfg.UA_mCp) * math.log(val)
                    t_ideal_min = t_ideal_sec / 60.0
                    
                    # Calculate efficiency
                    if self.heating_duration > 0:
                        efficiency = (t_ideal_min / self.heating_duration) * 100
                        return round(efficiency, 1)
            
            return None
        except Exception:
            return None
    
    @property
    def time_efficiency_percent(self):
        """Calculate time efficiency: (Ideal / Real) × 100%"""
        if self.ideal_heating_time and self.real_heating_duration and self.real_heating_duration > 0:
            efficiency = (self.ideal_heating_time / self.real_heating_duration) * 100
            return round(efficiency, 1)
        return None


class UserFavoriteBatch(models.Model):
    """Per-user favorite dyeing batches for Daily Batch Overview pinning."""
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="favorite_batches")
    process = models.ForeignKey(
        DyeingProcess,
        on_delete=models.CASCADE,
        related_name="favorited_by",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [("user", "process")]
        indexes = [
            models.Index(fields=["user", "process"]),
        ]

    def __str__(self):
        return f"{self.user.username} ♥ {self.process}"


class ProgramMaster(models.Model):
    nama = models.CharField(max_length=200, unique=True, verbose_name="Nama Program")
    suhu_max = models.FloatField(verbose_name="Suhu Max Ideal (°C)", null=True, blank=True)
    durasi_ideal = models.FloatField(verbose_name="Total Durasi Ideal (Menit)", null=True, blank=True)
    durasi_heating_ideal = models.FloatField(verbose_name="Durasi Heating Ideal (Menit)", null=True, blank=True)
    durasi_keeping_ideal = models.FloatField(verbose_name="Durasi Keeping Ideal (Menit)", null=True, blank=True)
    durasi_cooling_ideal = models.FloatField(verbose_name="Durasi Cooling Ideal (Menit)", null=True, blank=True)
    
    class Meta:
        verbose_name = "Master Program"
        verbose_name_plural = "Master Programs"
        
    def __str__(self):
        return self.nama


class DyeingIdentity(models.Model):
    """
    Identitas produksi untuk setiap DyeingProcess yang terdeteksi.
    Diisi manual oleh operator setelah proses selesai.

    Struktur proteksi data:
    - OneToOneField ke DyeingProcess dengan SET_NULL:
      Jika DyeingProcess dihapus/recreated saat reprocess,
      DyeingIdentity TIDAK ikut terhapus — hanya field dyeing_process jadi NULL (orphan aman).
    - Anchor fields (machine + start_time_snapshot):
      Disimpan otomatis sebagai "jangkar". Digunakan untuk re-link
      ke DyeingProcess baru jika batch pernah jadi orphan.
    """

    JENIS_PROSES_CHOICES = [
        ("FRESH", "Fresh"),
        ("CREAPING", "Creaping"),
        ("CREAPING_WR", "Creaping WR"),
        ("PROSES_ULANG", "PU Creaping"),
        ("TOPPING",  "Topping"),
        ("TOP_LEVEL", "Top Level"),
        ("CUCI_MESIN", "Cuci Mesin"),
        ("CUCI_CUKA", "Cuci Cuka"),
        ("CUCI_KANJI", "Cuci Kanji"),
        ("CUCI_KOTOR", "Cuci Kotor"),
        ("CUCI_BELANG", "Cuci Belang"),
        ("CUCI_FLEKWARNA", "Cuci Flek Warna"),
        ("CUCI_RC", "Cuci RC"),
        ("CUCI_PANAS", "Cuci Panas"),
        ("CUCI", "Cuci"),
        ("WR_ULANG", "WR Ulang"),
        ("LEVELLING", "Levelling"),
        ("CUCI_SEBELUMCELUP", "Cuci Sebelum Celup"),
        ("MIGRASI", "Migrasi"),
    ]

    # ── Link utama ──────────────────────────────────────────────────────────────
    dyeing_process = models.OneToOneField(
        "DyeingProcess",
        on_delete=models.SET_NULL,   # SET_NULL: identity tidak ikut hilang saat reprocess
        null=True,
        blank=True,
        related_name="identity",
        help_text="Batch dyeing yang terhubung",
    )

    # ── Anchor fields (auto-filled, untuk proteksi reprocess) ──────────────────
    machine = models.ForeignKey(
        "Machine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="dyeing_identities",
        help_text="Mesin saat batch terjadi (auto-filled dari DyeingProcess)",
    )
    start_time_snapshot = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Waktu mulai batch saat identity dibuat (auto-filled)",
    )

    # ── Identitas produksi (diisi manual oleh operator) ─────────────────────────
    nomor_order      = models.CharField(max_length=100,  blank=True, verbose_name="Nomor Order")
    artikel_kain     = models.CharField(max_length=200,  blank=True, verbose_name="Artikel Kain")
    batch            = models.CharField(max_length=100,  blank=True, verbose_name="Batch")
    kode_buyer       = models.CharField(max_length=100,  blank=True, verbose_name="Kode Buyer")
    program          = models.ForeignKey(ProgramMaster, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Program")
    isi_per_tube     = models.CharField(max_length=100, null=True, blank=True, verbose_name="Isi per Tube")
    operator         = models.CharField(max_length=200, null=True, blank=True, verbose_name="Operator")
    cycle_60         = models.CharField(max_length=100, null=True, blank=True, verbose_name="Cycle 60", help_text="Waktu siklus kain pada suhu 60°C")
    cycle_puncak     = models.CharField(max_length=100, null=True, blank=True, verbose_name="Cycle Puncak", help_text="Waktu siklus kain pada suhu puncak")
    nozzle_main_pump = models.CharField(max_length=100, null=True, blank=True, verbose_name="Nozzle / Main Pump", help_text="Setting ukuran nozzle dan pompa utama")
    nomor_warna      = models.CharField(max_length=100,  blank=True, verbose_name="Nomor Warna")
    nomor_desain     = models.CharField(max_length=100,  blank=True, verbose_name="Nomor Desain")
    handling_quality = models.TextField(blank=True, verbose_name="Handling Quality")
    jenis_proses     = models.CharField(
        max_length=20,
        choices=JENIS_PROSES_CHOICES,
        blank=True,
        verbose_name="Jenis Proses",
    )
    masalah          = models.TextField(
        blank=True,
        verbose_name="Masalah",
        help_text="Detail isu/kendala (opsional)"
    )
    keterangan       = models.TextField(
        blank=True,
        verbose_name="Keterangan",
        help_text="Catatan bebas (opsional)",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name        = "Dyeing Identity"
        verbose_name_plural = "Dyeing Identities"
        indexes = [
            models.Index(fields=["machine", "start_time_snapshot"]),
        ]

    def __str__(self):
        if self.dyeing_process:
            return f"Identity – {self.dyeing_process}"
        machine_str = str(self.machine) if self.machine else "?"
        ts = self.start_time_snapshot.strftime("%Y-%m-%d %H:%M") if self.start_time_snapshot else "?"
        return f"Identity (orphan) – {machine_str} @ {ts}"


    @property
    def output_yard(self):
        """Kalkulasi output dalam satuan yard berdasarkan isi_per_tube."""
        if not self.isi_per_tube:
            return None
            
        import re
        val_clean = str(self.isi_per_tube).strip()
        
        # Helper function for recursive parsing
        def parse_val(v):
            v = v.strip()
            # 1. Roll check: e.g. '6 Roll' or '6 Roll ( 739 )'
            m_roll = re.match(r'^(\d+)\s*roll', v, re.I)
            if m_roll:
                return int(m_roll.group(1)) * 100
                
            # 2. Check 'X PCS ( YX )'
            m_pcs_x = re.search(r'(\d+)\s*pcs\s*\(\s*(\d+)\s*x\s*\)', v, re.I)
            if m_pcs_x:
                pcs = int(m_pcs_x.group(1))
                x = int(m_pcs_x.group(2))
                return pcs * x * 50
                
            # 3. Check 'X PCS'
            m_pcs = re.search(r'(\d+)\s*pcs', v, re.I)
            if m_pcs:
                pcs = int(m_pcs.group(1))
                return pcs * 50
                
            # 4. Meter '300 M'
            m_m = re.match(r'^(\d+)\s*m$', v, re.I)
            if m_m:
                return round(int(m_m.group(1)) * 1.09361)
                
            return None

        # Check for slash or multi-expression: e.g. '6 pcs ( 2x ) / 7 pcs ( 2x )' or '9 pcs / 8 pcs'
        if '/' in val_clean:
            parts = val_clean.split('/')
            sub_results = [parse_val(p) for p in parts]
            if all(r is not None for r in sub_results):
                return sum(sub_results)
                
        # If no slash, parse directly
        return parse_val(val_clean)

    def save(self, *args, **kwargs):
        """Auto-fill anchor fields dari DyeingProcess saat pertama kali disimpan."""
        if self.dyeing_process and (not self.machine or not self.start_time_snapshot):
            self.machine             = self.dyeing_process.machine
            self.start_time_snapshot = self.dyeing_process.start_time
        super().save(*args, **kwargs)

class DyeingAnalytics(DyeingIdentity):
    class Meta:
        proxy = True
        verbose_name = "Dyeing Analytics"
        verbose_name_plural = "📊 Dyeing Analytics"


class DyeingExecutiveSummary(DyeingIdentity):
    class Meta:
        proxy = True
        verbose_name = "Executive Summary"
        verbose_name_plural = "📊 Executive Summary"


class DailyBatchOverview(DyeingIdentity):
    class Meta:
        proxy = True
        verbose_name = "Daily Batch Overview"
        verbose_name_plural = "📈 Daily Batch Overview"


class RawDataFile(models.Model):

    """
    Model untuk menampung file upload data raw (CSV/Excel).
    Supports both WIDE format (Date|Time|Machine1|Machine2|...) 
    and LONG format (Timestamp|Temperature|MachineCode).
    """
    FORMAT_WIDE = "WIDE"
    FORMAT_LONG = "LONG"
    FORMAT_CHOICES = [
        (FORMAT_WIDE, "Wide Format (Multiple Machines per Row)"),
        (FORMAT_LONG, "Long Format (Single Machine per Row)"),
    ]
    
    file = models.FileField(upload_to="raw_data_uploads/")
    uploaded_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)
    log_message = models.TextField(blank=True, help_text="Log hasil processing")
    
    # Preview & Metadata
    preview_data = models.JSONField(
        default=dict, 
        blank=True,
        help_text="Parsed preview data for display (first 100 rows + metadata)"
    )
    file_format = models.CharField(
        max_length=10,
        choices=FORMAT_CHOICES,
        blank=True,
        help_text="Auto-detected file format"
    )
    row_count = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Total number of data rows"
    )
    machine_count = models.IntegerField(
        null=True, 
        blank=True,
        help_text="Number of machines detected in file"
    )
    date_range = models.CharField(
        max_length=100, 
        blank=True,
        help_text="Date range of data (e.g., '2025-12-01 to 2025-12-21')"
    )
    
    def __str__(self):
        return f"Raw Data: {self.file.name} ({'Processed' if self.processed else 'Pending'})"


class MachineStatusSnapshot(models.Model):
    """
    Stores status snapshot for all machines at a specific timestamp.
    Data stored as JSON for pivot table display.
    
    Example snapshot_data:
    {
        "JR_01": {"status": "Running", "detail": "Running", "mode": "MANUAL"},
        "ZET_05": {"status": "Running", "detail": "HEAT", "mode": "AUTO"}
    }
    """
    timestamp = models.DateTimeField(unique=True, db_index=True)
    snapshot_data = models.JSONField(
        default=dict,
        help_text="Dict of {machine_code: {status, detail, mode}}"
    )
    
    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Machine Status Snapshot"
        verbose_name_plural = "Machine Status Snapshots"
    
    def __str__(self):
        return f"Snapshot at {self.timestamp:%Y-%m-%d %H:%M}"


class MachinePerformanceSummary(Machine):
    """
    Proxy model untuk menampilkan summary performa mesin
    berdasarkan agregasi dari DyeingProcess.
    Tidak membuat tabel baru, hanya untuk admin display.
    """
    class Meta:
        proxy = True
        verbose_name = "Machine Performance Summary"
        verbose_name_plural = "Machine Performance Summaries"


class Alert(models.Model):
    """
    Alert system for critical infrastructure monitoring.
    Tracks critical conditions like low steam pressure or HTO temperature.
    """
    SEVERITY_CRITICAL = 'CRITICAL'
    SEVERITY_WARNING = 'WARNING'
    SEVERITY_INFO = 'INFO'
    
    SEVERITY_CHOICES = [
        (SEVERITY_CRITICAL, 'Critical'),
        (SEVERITY_WARNING, 'Warning'),
        (SEVERITY_INFO, 'Info'),
    ]
    
    TYPE_STEAM_PRESSURE = 'STEAM_PRESSURE'
    TYPE_HTO_TEMPERATURE = 'HTO_TEMPERATURE'
    TYPE_NO_SIGNAL = 'NO_SIGNAL'
    
    TYPE_CHOICES = [
        (TYPE_STEAM_PRESSURE, 'Steam Pressure Low'),
        (TYPE_HTO_TEMPERATURE, 'HTO Temperature Low'),
        (TYPE_NO_SIGNAL, 'Sensor No Signal'),
    ]
    
    severity = models.CharField(
        max_length=10, 
        choices=SEVERITY_CHOICES, 
        default=SEVERITY_CRITICAL,
        db_index=True
    )
    alert_type = models.CharField(
        max_length=20, 
        choices=TYPE_CHOICES,
        db_index=True
    )
    machine = models.ForeignKey(
        Machine, 
        on_delete=models.CASCADE, 
        related_name='alerts',
        null=True, 
        blank=True
    )
    
    title = models.CharField(max_length=200)
    message = models.TextField()
    current_value = models.FloatField(
        help_text="Current value when alert triggered"
    )
    threshold_value = models.FloatField(
        help_text="Threshold that was crossed"
    )
    
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    is_acknowledged = models.BooleanField(default=False)
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    acknowledged_by = models.ForeignKey(
        User, 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True,
        related_name='acknowledged_alerts'
    )
    
    # Auto-dismiss after certain time for non-critical alerts
    is_active = models.BooleanField(default=True, db_index=True)
    
    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['is_active', 'severity', '-created_at']),
            models.Index(fields=['machine', '-created_at']),
        ]
        verbose_name = "Alert"
        verbose_name_plural = "Alerts"
    
    def __str__(self):
        return f"[{self.severity}] {self.title} at {self.created_at:%Y-%m-%d %H:%M}"


class UserActivityLog(models.Model):
    """
    Model untuk tracking aktivitas user di sistem (admin & website).
    Mencatat semua aktivitas penting untuk audit trail dan analytics.
    """
    ACTION_CHOICES = [
        ('LOGIN', 'Login'),
        ('LOGOUT', 'Logout'),
        ('CREATE', 'Create'),
        ('UPDATE', 'Update'),
        ('DELETE', 'Delete'),
        ('VIEW', 'View Page'),
        ('SEARCH', 'Search'),
        ('FILTER', 'Apply Filter'),
        ('EXPORT', 'Export Data'),
        ('ACTION', 'Admin Action'),
    ]
    
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='activity_logs')
    username = models.CharField(max_length=150, help_text="Backup jika user di-delete")
    action = models.CharField(max_length=10, choices=ACTION_CHOICES, db_index=True)
    
    # For tracking model changes (admin)
    content_type = models.ForeignKey(
        'contenttypes.ContentType', 
        on_delete=models.SET_NULL, 
        null=True, 
        blank=True
    )
    object_id = models.PositiveIntegerField(null=True, blank=True)
    object_repr = models.CharField(max_length=200, blank=True)
    
    # For tracking page visits and interactions (website)
    request_path = models.CharField(max_length=255, blank=True)
    request_method = models.CharField(max_length=10, blank=True)
    query_params = models.JSONField(null=True, blank=True)
    
    description = models.TextField(blank=True)
    additional_data = models.JSONField(null=True, blank=True)
    
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    
    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
            models.Index(fields=['action', '-timestamp']),
            models.Index(fields=['content_type', 'object_id']),
            models.Index(fields=['request_path', '-timestamp']),
        ]
        verbose_name = "User Activity Log"
        verbose_name_plural = "User Activity Logs"
    
    def __str__(self):
        return f"{self.username} - {self.action} at {self.timestamp:%Y-%m-%d %H:%M}"


class IPAccessControl(models.Model):
    """
    Mencatat semua IP yang pernah mengakses website.
    Admin bisa memblokir/mengizinkan IP langsung dari Django Admin.
    Secara otomatis mencatat negara, ISP, akun yang login, dsb.
    """
    ip_address = models.GenericIPAddressField(
        unique=True,
        verbose_name="IP Address"
    )
    is_blocked = models.BooleanField(
        default=False,
        verbose_name="Blokir?",
        help_text="Centang untuk memblokir IP ini dari mengakses website"
    )
    country = models.CharField(
        max_length=80,
        blank=True,
        verbose_name="Negara",
        help_text="Nama negara asal IP (auto-detect)"
    )
    country_code = models.CharField(
        max_length=5,
        blank=True,
        verbose_name="Kode Negara"
    )
    isp = models.CharField(
        max_length=150,
        blank=True,
        verbose_name="ISP / Organisasi",
        help_text="Nama Internet Service Provider atau organisasi"
    )
    first_seen = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Pertama Terlihat"
    )
    last_seen = models.DateTimeField(
        auto_now=True,
        verbose_name="Terakhir Terlihat"
    )
    access_count = models.PositiveIntegerField(
        default=1,
        verbose_name="Jumlah Akses"
    )
    note = models.CharField(
        max_length=200,
        blank=True,
        verbose_name="Catatan",
        help_text="Catatan tambahan dari admin"
    )
    # Akun Django yang pernah login dari IP ini
    known_users = models.ManyToManyField(
        User,
        blank=True,
        related_name='ip_access_records',
        verbose_name="Akun yang Pernah Login",
        help_text="Akun Plant Monitor yang pernah login dari IP ini (kosong = tidak pernah login)"
    )

    class Meta:
        ordering = ['-last_seen']
        verbose_name = "IP Access Control"
        verbose_name_plural = "IP Access Control"
        indexes = [
            models.Index(fields=['is_blocked']),
            models.Index(fields=['country_code']),
        ]

    def __str__(self):
        status = "BLOCKED" if self.is_blocked else "ALLOWED"
        country = f" ({self.country_code})" if self.country_code else ""
        return f"{self.ip_address}{country} [{status}]"


# ─── MachineManualLog ─────────────────────────────────────────────────────────

class MachineManualLog(models.Model):
    """
    Audit trail for every manual status change.
    Records: who changed, when, from what status/temp to what status/temp.
    """
    machine = models.ForeignKey(
        Machine,
        on_delete=models.CASCADE,
        related_name="manual_logs",
    )
    changed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    changed_by_username = models.CharField(
        max_length=150,
        blank=True,
        help_text="Backup username jika user dihapus",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    old_status = models.CharField(max_length=50, blank=True)
    new_status = models.CharField(max_length=50, blank=True)

    old_target_temp = models.IntegerField(null=True, blank=True)
    new_target_temp = models.IntegerField(null=True, blank=True)

    source = models.CharField(
        max_length=30,
        blank=True,
        default="",
        help_text="Sumber perubahan: dashboard_toggle, mesin_aktif_api, sync_command, dll.",
    )

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["machine", "-timestamp"]),
        ]
        verbose_name = "Machine Manual Log"
        verbose_name_plural = "Machine Manual Logs"

    def __str__(self):
        return (
            f"{self.machine.code}: {self.old_status} → {self.new_status}"
            f" @ {self.timestamp:%Y-%m-%d %H:%M}"
        )


class PlantHourlySummary(models.Model):
    """
    Rollup/Aggregation tabel per jam untuk merangkum data Steam Usage & Pressure History.
    Menyimpan agregasi total dari seluruh mesin yang aktif pada jam tersebut.
    """
    timestamp = models.DateTimeField(unique=True, db_index=True, help_text="Waktu awal jam (misal 14:00:00)")
    total_steam_usage = models.FloatField(default=0.0, help_text="Total estimasi pemakaian uap (kg) dalam 1 jam")
    avg_steam_pressure = models.FloatField(default=0.0, help_text="Rata-rata tekanan uap (Bar) dalam 1 jam")
    machine_count = models.IntegerField(default=0, help_text="Jumlah rata-rata mesin aktif dalam 1 jam")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Plant Hourly Summary"
        verbose_name_plural = "Plant Hourly Summaries"

    def __str__(self):
        return f"Hourly Summary @ {self.timestamp:%Y-%m-%d %H:%M}"


class PlantDailySummary(models.Model):
    """
    Rollup/Aggregation tabel per hari untuk merangkum data Steam Usage & Pressure History.
    Diambil berdasarkan agregasi dari PlantHourlySummary.
    """
    timestamp = models.DateField(unique=True, db_index=True, help_text="Tanggal ringkasan")
    total_steam_usage = models.FloatField(default=0.0, help_text="Total estimasi pemakaian uap (kg) dalam 1 hari")
    avg_steam_pressure = models.FloatField(default=0.0, help_text="Rata-rata tekanan uap (Bar) dalam 1 hari")
    machine_count = models.IntegerField(default=0, help_text="Jumlah rata-rata mesin aktif dalam 1 hari")

    class Meta:
        ordering = ['-timestamp']
        verbose_name = "Plant Daily Summary"
        verbose_name_plural = "Plant Daily Summaries"

    def __str__(self):
        return f"Daily Summary @ {self.timestamp:%Y-%m-%d}"


def get_calibrated_temperature(machine_id, raw_value):
    """
    Fungsi helper terpusat untuk mengaplikasikan kalibrasi sensor.

    Menggunakan persamaan polinomial: y = (A * x^2) + (B * x) + C
      - A (a_coeff): Koefisien kuadratik untuk non-linearitas
      - B (b_coeff): Span multiplier (1.0 = tidak ada koreksi span)
      - C (c_coeff): Offset

    Jika tidak ada konfigurasi kalibrasi aktif, nilai raw dikembalikan langsung.
    Jika raw_value None atau invalid (bukan angka), dikembalikan apa adanya.

    Args:
        machine_id (int): Primary key dari Machine.
        raw_value: Nilai suhu mentah dari sensor.

    Returns:
        float|None: Nilai suhu yang sudah dikalibrasi, atau raw_value jika tidak ada kalibrasi.
    """
    if raw_value is None:
        return None

    try:
        raw_float = float(raw_value)
    except (TypeError, ValueError):
        # Nilai tidak bisa dikonversi ke float (misal "-" atau string lain)
        return raw_value

    try:
        cal = MachineCalibration.objects.get(machine_id=machine_id, is_active=True)
        calibrated = (cal.a_coeff * raw_float ** 2) + (cal.b_coeff * raw_float) + cal.c_coeff
        return round(calibrated, 4)
    except MachineCalibration.DoesNotExist:
        # Tidak ada kalibrasi → kembalikan nilai asli
        return raw_float


class MachineCalibration(models.Model):
    """
    Master kalibrasi sensor per mesin menggunakan persamaan polinomial kuadratik:
        Calibrated_Value = (A * Raw^2) + (B * Raw) + C

    Kasus penggunaan:
      - Hanya Offset        : A=0, B=1, C=<nilai_offset>
      - Hanya Span          : A=0, B=<faktor_span>, C=0
      - Span + Offset       : A=0, B=<faktor>, C=<offset>
      - Non-Linearitas Penuh: A=<koef>, B=<koef>, C=<offset>

    Nilai default (A=0, B=1, C=0) berarti tidak ada koreksi (pass-through).
    """
    machine = models.OneToOneField(
        Machine,
        on_delete=models.CASCADE,
        related_name="calibration",
        help_text="Mesin yang dikalibrasi"
    )
    a_coeff = models.FloatField(
        default=0.0,
        verbose_name="Koefisien A (Kuadratik x²)",
        help_text="Koefisien untuk suku kuadratik (non-linearitas). Default 0."
    )
    b_coeff = models.FloatField(
        default=1.0,
        verbose_name="Koefisien B (Span, x)",
        help_text="Faktor pengali span. Default 1.0 (tidak ada koreksi span)."
    )
    c_coeff = models.FloatField(
        default=0.0,
        verbose_name="Koefisien C (Offset)",
        help_text="Nilai offset yang ditambahkan. Default 0 (tidak ada offset)."
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Aktifkan/nonaktifkan kalibrasi untuk mesin ini"
    )
    notes = models.TextField(
        blank=True,
        help_text="Catatan kalibrasi (misal: tanggal kalibrasi, referensi, kondisi)"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Machine Calibration"
        verbose_name_plural = "Machine Calibrations"

    def __str__(self):
        status = "Active" if self.is_active else "Inactive"
        return f"Calibration [{status}] — {self.machine.code} | y = {self.a_coeff}x² + {self.b_coeff}x + {self.c_coeff}"

    def apply(self, raw_value):
        """Terapkan persamaan kalibrasi ke satu nilai."""
        if raw_value is None:
            return None
        try:
            x = float(raw_value)
            return round((self.a_coeff * x ** 2) + (self.b_coeff * x) + self.c_coeff, 4)
        except (TypeError, ValueError):
            return raw_value


class DailyPlantMetric(models.Model):
    """
    Stores daily aggregated metrics (06:00 to 06:00) to speed up dashboard queries.
    """
    date = models.DateField(unique=True, help_text="Tanggal pelaporan (mengacu pada hari mulainya, misal 06:00 tanggal 1 sampai 06:00 tanggal 2 -> date=tanggal 1)")
    total_steam_usage = models.FloatField(default=0.0, help_text="Total penggunaan uap (kg) dalam 24 jam")
    average_availability = models.FloatField(default=0.0, help_text="Rata-rata availability (%) mesin aktif")
    productivity_goal = models.FloatField(default=0.0, help_text="Rata-rata productivity goal (%)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Daily Plant Metric"
        verbose_name_plural = "Daily Plant Metrics"
        ordering = ['-date']

    def __str__(self):
        return f"{self.date} - Steam: {self.total_steam_usage}kg, Avail: {self.average_availability}%"


class BoilerDailyMetric(models.Model):
    """
    Ringkasan KPI boiler per hari (06:00–06:00), di-cache agar kalender bulanan
    dan laporan historis tidak perlu menghitung ulang dari raw log setiap kali dibuka.
    Diperbarui otomatis oleh log_minute_history (hari berjalan) dan management command.
    """
    date = models.DateField(
        unique=True,
        db_index=True,
        help_text="Tanggal hari operasional (06:00 tanggal ini s/d 06:00 besok)",
    )
    total_steam_usage_kg = models.FloatField(default=0.0)
    total_steam_ideal_usage_kg = models.FloatField(
        null=True, blank=True,
        help_text="Total ideal steam usage (kg), derived from actual for non-jet, and PINN ideal for Jet"
    )
    steam_efficiency_percent = models.FloatField(
        null=True, blank=True,
        help_text="Steam efficiency = (Ideal / Actual) * 100%"
    )
    avg_pressure = models.FloatField(null=True, blank=True)
    avg_oil_temp = models.FloatField(null=True, blank=True)
    total_fuel_kg = models.FloatField(null=True, blank=True)
    total_fuel_steam_kg = models.FloatField(null=True, blank=True)
    total_fuel_hto_kg = models.FloatField(null=True, blank=True)
    specific_fuel_consumption = models.FloatField(null=True, blank=True)
    pressure_ideal_percent = models.FloatField(null=True, blank=True)
    pressure_ideal_count = models.IntegerField(default=0)
    pressure_under_count = models.IntegerField(default=0)
    pressure_over_count = models.IntegerField(default=0)
    alert_count_critical = models.IntegerField(default=0)
    alert_count_warning = models.IntegerField(default=0)
    alert_count_total = models.IntegerField(default=0)
    has_data = models.BooleanField(
        default=False,
        help_text="True jika ada data sensor/tekanan valid pada hari ini",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Boiler Daily Metric"
        verbose_name_plural = "Boiler Daily Metrics"
        ordering = ['-date']

    def __str__(self):
        return f"Boiler {self.date} — steam {self.total_steam_usage_kg} kg, SFC {self.specific_fuel_consumption}"


class GlobalSettings(models.Model):
    # Parameter Air
    water_specific_heat = models.FloatField(
        default=4.18, 
        verbose_name="Kalor Jenis Air (kJ/kg.K)",
        help_text="Default: 4.18"
    )
    water_density = models.FloatField(
        default=1000.0, 
        verbose_name="Kerapatan Air (kg/m³)",
        help_text="Default: 1000"
    )
    
    # Parameter Kain
    fabric_specific_heat = models.FloatField(
        default=1.05, 
        verbose_name="Kalor Jenis Kain (kJ/kg.K)",
        help_text="Default: 1.05"
    )
    
    # Parameter Penagihan Listrik
    wbp_start_time = models.TimeField(
        default='17:00:00',
        verbose_name="Waktu Beban Puncak (WBP) Mulai",
        help_text="Default: 17:00"
    )
    wbp_end_time = models.TimeField(
        default='22:00:00',
        verbose_name="Waktu Beban Puncak (WBP) Selesai",
        help_text="Default: 22:00"
    )
    wbp_multiplier = models.FloatField(
        default=1.4,
        verbose_name="Faktor Pengali WBP (k)",
        help_text="Default: 1.4"
    )
    electricity_base_rate = models.FloatField(
        default=1035.8,
        verbose_name="Harga Listrik LWBP / Dasar (Rp/kWh)",
        help_text="Default: 1035.8"
    )

    # Parameter Penagihan Listrik
    wbp_start_time = models.TimeField(
        default='17:00:00',
        verbose_name="Waktu Beban Puncak (WBP) Mulai",
        help_text="Default: 17:00"
    )
    wbp_end_time = models.TimeField(
        default='22:00:00',
        verbose_name="Waktu Beban Puncak (WBP) Selesai",
        help_text="Default: 22:00"
    )
    wbp_multiplier = models.FloatField(
        default=1.4,
        verbose_name="Faktor Pengali WBP (k)",
        help_text="Default: 1.4"
    )
    electricity_base_rate = models.FloatField(
        default=1035.8,
        verbose_name="Harga Listrik LWBP / Dasar (Rp/kWh)",
        help_text="Default: 1035.8"
    )

    # Parameter Lingkungan
    standard_ambient_temp = models.FloatField(
        default=30.0, 
        verbose_name="Suhu Lingkungan Standar (°C)",
        help_text="Default: 30"
    )

    # Konversi Bahan Bakar Boiler (kalibrasi terhadap nilai Hz sensor feeder)
    fuel_factor_steam_boiler = models.FloatField(
        default=0.0,
        verbose_name="Faktor Konsumsi Batu Bara — Speed RB Steam (kg/jam per Hz)",
        help_text=(
            "Kalibrasi terhadap sensor Speed_RB_Steam (Hz). "
            "Rumus: konsumsi (kg/jam) = Speed RB (Hz) × faktor ini. "
            "Contoh: Speed RB = 30 Hz, faktor = 2 → 60 kg/jam. Isi 0 jika belum dikalibrasi."
        )
    )
    fuel_factor_hto_boiler = models.FloatField(
        default=0.0,
        verbose_name="Faktor Konsumsi Batu Bara — Speed RB HTO (kg/jam per Hz)",
        help_text=(
            "Kalibrasi terhadap sensor Speed_R_Bakar / Speed RB HTO (Hz). "
            "Rumus: konsumsi (kg/jam) = Speed RB HTO (Hz) × faktor ini. "
            "Contoh: Speed RB HTO = 25 Hz, faktor = 1.5 → 37.5 kg/jam. Isi 0 jika belum dikalibrasi."
        )
    )
    coal_calorific_value = models.FloatField(
        default=5500.0,
        verbose_name="Nilai Kalor Batu Bara (kcal/kg)",
        help_text="Dipakai untuk hitung efisiensi termal (energi output / energi input)."
    )
    
    sensor_shadow_max_minutes = models.IntegerField(
        default=15,
        verbose_name="Maks. Durasi Shadow Berturut-turut (menit)",
        help_text="Berapa menit berturut-turut sensor boleh di-shadow sebelum sistem memaksa OFFLINE. Default: 15. Nilai ini juga menentukan depth query rehydration saat restart."
    )
    
    sensor_rehydrate_buffer_minutes = models.IntegerField(
        default=5,
        verbose_name="Toleransi Jeda Restart (menit)",
        help_text="Jika jeda antara log terakhir dan waktu restart > nilai ini, shadow counter dianggap tidak relevan (fresh start). Default: 5 menit. Set lebih tinggi jika daemon sering lambat startup."
    )
    steam_healthy_threshold = models.FloatField(
        default=3.8,
        verbose_name="Batas Steam Sehat (barg)",
        help_text="Batas minimum tekanan steam rata-rata (barg) untuk dikategorikan sebagai steam sehat."
    )
    
    # === Threshold Regulasi Boiler ===
    boiler_regulation_pressure_min = models.FloatField(
        default=5.0,
        verbose_name="Regulasi Boiler: Min Steam Pressure (barg)",
        help_text="Batas bawah tekanan uap untuk deteksi regulasi"
    )
    boiler_regulation_hto_oil_temp_min = models.FloatField(
        default=244.0,
        verbose_name="Regulasi HTO: Min Oil Temp (°C)",
        help_text="Batas bawah suhu oli HTO saat regulasi dianggap aktif"
    )
    boiler_regulation_speed_max = models.FloatField(
        default=0.5,
        verbose_name="Regulasi Boiler: Max Coal Speed (Hz)",
        help_text="Batas atas speed batu bara saat regulasi"
    )
    boiler_regulation_pre_window_min = models.IntegerField(
        default=2,
        verbose_name="Regulasi Boiler: Pre-Window (menit)",
        help_text="Berapa menit ke belakang/depan untuk nge-cek peak pressure"
    )
    boiler_regulation_gap_tolerance_min = models.IntegerField(
        default=1,
        verbose_name="Regulasi Boiler: Gap Tolerance (menit)",
        help_text="Maksimal menit non-regulasi yang diabaikan (digabung ke kejadian yang sama)"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Master Global"
        verbose_name_plural = "Master Global"

    def __str__(self):
        return "Konfigurasi Global System"


    def save(self, *args, **kwargs):
        # Paksa ID selalu 1 agar hanya ada 1 baris setting global
        self.pk = 1
        super().save(*args, **kwargs)
        from django.core.cache import cache
        cache.delete('global_settings')

    @classmethod
    def load(cls):
        """Helper untuk memuat setting, otomatis buat dengan default jika kosong"""
        from django.core.cache import cache
        settings = cache.get('global_settings')
        if settings is None:
            settings, created = cls.objects.get_or_create(pk=1)
            # Cache for 10 minutes (600 seconds) - caching ringan
            cache.set('global_settings', settings, 600)
        return settings


# ═══════════════════════════════════════════════════════════════════════════════
# MASTER KAIN — Modul spesifikasi kain tenun
# ═══════════════════════════════════════════════════════════════════════════════

class MasterAnyaman(models.Model):
    """Daftar jenis anyaman kain (misal: Plain, Twill 2/1, Satin 8H, dst.)"""
    nama = models.CharField(
        max_length=100,
        verbose_name="Nama Anyaman",
        help_text="Contoh: Plain, Twill 2/1, Satin 8H"
    )
    kode = models.CharField(
        max_length=20,
        unique=True,
        verbose_name="Kode",
        help_text="Kode singkat unik, contoh: PLN, TWL21"
    )
    deskripsi = models.TextField(
        blank=True,
        verbose_name="Deskripsi",
        help_text="Keterangan tambahan (opsional)"
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="Aktif",
        help_text="Centang agar muncul di dropdown form Master Kain"
    )

    class Meta:
        verbose_name = "Master Anyaman"
        verbose_name_plural = "Master Anyaman"
        ordering = ["nama"]

    def __str__(self):
        return f"{self.kode} — {self.nama}"


class MasterKain(models.Model):
    """
    Data teknis master kain tenun.
    Satu record mewakili satu spesifikasi artikel kain.
    CFW dihitung otomatis menggunakan rumus tekstil:
        CFW = EPI / √(Ne_warp) + PPI / √(Ne_weft)
    """

    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("AKTIF", "Aktif"),
        ("TIDAK_BERLAKU", "Tidak Berlaku"),
    ]

    # ── Identitas ────────────────────────────────────────────────────────────
    nama_kain = models.CharField(
        max_length=200,
        verbose_name="Nama Kain",
    )
    tanggal_order = models.DateField(
        null=True, blank=True,
        verbose_name="Tanggal Order",
    )
    tanggal_greige = models.DateField(
        null=True, blank=True,
        verbose_name="Tanggal Greige",
    )
    tanggal_finish = models.DateField(
        null=True, blank=True,
        verbose_name="Tanggal Finish",
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="AKTIF",
        verbose_name="Status",
    )

    # ── Covering Factor ───────────────────────────────────────────────────────
    # CFW disimpan sebagai field terkomputasi (diisi otomatis di save())
    cfw = models.DecimalField(
        max_digits=10, decimal_places=4,
        null=True, blank=True,
        verbose_name="CFW (Covering Factor)",
        help_text="Dihitung otomatis: EPI/√Ne_warp + PPI/√Ne_weft"
    )
    epi = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="EPI (Ends per Inch)",
    )
    ne_warp = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Ne Warp",
    )
    ppi = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="PPI (Picks per Inch)",
    )
    ne_weft = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Ne Weft",
    )

    # ── Parameter Mesin ───────────────────────────────────────────────────────
    konst_mesin = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Konst di Mesin (inch)",
    )
    t_ends = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="T'Ends (HI)",
    )
    pick_mc = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Pick Mc (T)",
    )
    lebar_sisir_efektif = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Lebar Sisir Efektif (cm)",
    )
    lebar_greige = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Lebar Greige (cm)",
    )
    pick_greige = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Pick Greige (T)",
    )
    no_sisir = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="No Sisir",
    )
    cucukan = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Cucukan",
    )
    nama_anyaman = models.ForeignKey(
        MasterAnyaman,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Nama Anyaman",
        related_name="kain_set",
    )

    # ── Susut & Waste ─────────────────────────────────────────────────────────
    susut_anyaman = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="Susut Anyaman (%)",
    )
    waste_lusi = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="Waste Lusi (%)",
    )
    waste_pakan = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="Waste Pakan (%)",
    )

    # ── Produksi ─────────────────────────────────────────────────────────────
    pick_rolling = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Pick Rolling",
    )
    panjang_pakan_mc = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Panjang Pakan m/c (inch)",
    )
    pcs_length_yd = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Pcs/Length YD (YD)",
    )

    # ── Keterangan ────────────────────────────────────────────────────────────
    keterangan = models.TextField(
        blank=True,
        verbose_name="Keterangan",
        help_text="Catatan bebas (opsional)",
    )

    # ── Audit ─────────────────────────────────────────────────────────────────
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name="masterkain_dibuat",
        verbose_name="Dibuat oleh",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Dibuat pada")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Diperbarui pada")

    class Meta:
        verbose_name = "Master Kain"
        verbose_name_plural = "Master Kain"
        ordering = ["-created_at"]

    def __str__(self):
        return self.nama_kain

    def _compute_cfw(self):
        """Hitung Covering Factor: EPI/√Ne_warp + PPI/√Ne_weft."""
        try:
            result = 0.0
            if self.epi and self.ne_warp and float(self.ne_warp) > 0:
                result += float(self.epi) / math.sqrt(float(self.ne_warp))
            if self.ppi and self.ne_weft and float(self.ne_weft) > 0:
                result += float(self.ppi) / math.sqrt(float(self.ne_weft))
            return round(result, 4) if result else None
        except (TypeError, ValueError, ZeroDivisionError):
            return None

    @property
    def total_gross_gm(self):
        """Total Yarn Weight Gross (G/M) semua benang lusi + pakan."""
        lusi_sum = sum(
            float(b.yarn_weight_gross)
            for b in self.benang_lusi.all()
            if b.yarn_weight_gross is not None
        )
        pakan_sum = sum(
            float(b.yarn_weight_gross)
            for b in self.benang_pakan.all()
            if b.yarn_weight_gross is not None
        )
        return round(lusi_sum + pakan_sum, 4)

    @property
    def total_netto_gm(self):
        """Total Yarn Weight Netto (G/M) semua benang lusi + pakan."""
        lusi_sum = sum(
            float(b.yarn_weight_netto)
            for b in self.benang_lusi.all()
            if b.yarn_weight_netto is not None
        )
        pakan_sum = sum(
            float(b.yarn_weight_netto)
            for b in self.benang_pakan.all()
            if b.yarn_weight_netto is not None
        )
        return round(lusi_sum + pakan_sum, 4)


    def save(self, *args, **kwargs):
        # Hitung CFW otomatis sebelum simpan
        computed = self._compute_cfw()
        if computed is not None:
            from decimal import Decimal
            self.cfw = Decimal(str(computed))
        super().save(*args, **kwargs)


class BenangLusi(models.Model):
    """Detail benang lusi untuk satu Master Kain (multiple rows)."""

    master_kain = models.ForeignKey(
        MasterKain,
        on_delete=models.CASCADE,
        related_name="benang_lusi",
        verbose_name="Master Kain",
    )
    urutan = models.PositiveIntegerField(
        default=1,
        verbose_name="Urutan (Lusi ke-)",
        help_text="1 = Lusi 1, 2 = Lusi 2, dst.",
    )

    # ── Spesifikasi benang ────────────────────────────────────────────────────
    jenis_benang = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Jenis Benang",
    )
    denier = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Denier",
    )
    filamen = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Filamen",
    )
    no_lot = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="No LOT",
    )
    tpm = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="TPM (Twist per Meter)",
    )
    twist = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Twist (S/Z)",
    )
    repeat = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Repeat",
    )
    twist_shr = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Twist SHR",
    )

    # ── Vacuum Heat Setting ───────────────────────────────────────────────────
    vhs_suhu = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="VHS Suhu (°C)",
        help_text="Suhu Vacuum Heat Setting",
    )
    vhs_waktu = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="VHS Waktu (min)",
        help_text="Durasi Vacuum Heat Setting",
    )

    # ── Berat benang ──────────────────────────────────────────────────────────
    yarn_weight_gross = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Yarn Weight Gross (G/M)",
    )
    yarn_weight_netto = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Yarn Weight Netto (G/M)",
        help_text="Diisi manual",
    )

    class Meta:
        verbose_name = "Benang Lusi"
        verbose_name_plural = "Benang Lusi"
        ordering = ["urutan"]

    def __str__(self):
        return f"Lusi {self.urutan} — {self.jenis_benang or '-'}"


class BenangPakan(models.Model):
    """Detail benang pakan untuk satu Master Kain (multiple rows)."""

    master_kain = models.ForeignKey(
        MasterKain,
        on_delete=models.CASCADE,
        related_name="benang_pakan",
        verbose_name="Master Kain",
    )
    urutan = models.PositiveIntegerField(
        default=1,
        verbose_name="Urutan (Pakan ke-)",
        help_text="1 = Pakan 1, 2 = Pakan 2, dst.",
    )

    # ── Spesifikasi benang ────────────────────────────────────────────────────
    jenis_benang = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Jenis Benang",
    )
    denier = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Denier",
    )
    filamen = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Filamen",
    )
    no_lot = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="No LOT",
    )
    tpm = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="TPM (Twist per Meter)",
    )
    twist = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Twist (S/Z)",
    )
    repeat = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Repeat",
    )
    twist_shr = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Twist SHR",
    )

    # ── Vacuum Heat Setting ───────────────────────────────────────────────────
    vhs_suhu = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="VHS Suhu (°C)",
        help_text="Suhu Vacuum Heat Setting",
    )
    vhs_waktu = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="VHS Waktu (min)",
        help_text="Durasi Vacuum Heat Setting",
    )

    # ── Berat benang ──────────────────────────────────────────────────────────
    yarn_weight_gross = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Yarn Weight Gross (G/M)",
    )
    yarn_weight_netto = models.DecimalField(
        max_digits=10, decimal_places=2,
        null=True, blank=True,
        verbose_name="Yarn Weight Netto (G/M)",
        help_text="Diisi manual",
    )

    class Meta:
        verbose_name = "Benang Pakan"
        verbose_name_plural = "Benang Pakan"
        ordering = ["urutan"]

    def __str__(self):
        return f"Pakan {self.urutan} — {self.jenis_benang or '-'}"


class RevisiKain(models.Model):
    """
    Log otomatis setiap kali Master Kain diubah.
    Menyimpan snapshot data sebelum perubahan + info siapa yang edit.
    """
    master_kain = models.ForeignKey(
        MasterKain,
        on_delete=models.CASCADE,
        related_name="revisi",
        verbose_name="Master Kain",
    )
    diubah_oleh = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True, blank=True,
        verbose_name="Diubah oleh",
    )
    diubah_pada = models.DateTimeField(
        auto_now_add=True,
        verbose_name="Diubah pada",
    )
    catatan_perubahan = models.TextField(
        blank=True,
        verbose_name="Catatan Perubahan",
        help_text="Ringkasan field yang berubah (auto atau manual)",
    )
    snapshot_data = models.JSONField(
        default=dict,
        verbose_name="Snapshot Data",
        help_text="Salinan data MasterKain sebelum perubahan ini",
    )

    class Meta:
        verbose_name = "Revisi Kain"
        verbose_name_plural = "Revisi Kain"
        ordering = ["-diubah_pada"]

    def __str__(self):
        user_str = self.diubah_oleh.username if self.diubah_oleh else "system"
        ts = self.diubah_pada.strftime("%Y-%m-%d %H:%M") if self.diubah_pada else "?"
        return f"Revisi {self.master_kain} oleh {user_str} @ {ts}"


# ═══════════════════════════════════════════════════════════════════════════════


class DataAnomaly(models.Model):
    """
    Menyimpan deteksi keanehan data (salah linked, sensor spike, durasi aneh)
    sehingga tidak perlu dikalkulasi berat (real-time) di frontend.
    """
    SEVERITY_CHOICES = (
        ('CRITICAL', 'Kritis (3+ Flags)'),
        ('MEDIUM', 'Medium (2 Flags)'),
        ('LOW', 'Ringan (1 Flag)')
    )
    
    anomaly_type = models.CharField(max_length=50, help_text="Contoh: WRONG_LINK, SENSOR_SPIKE, PREMATURE_BATCH")
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    
    # Terkait ke record mana?
    identity_record = models.ForeignKey(
        'DyeingIdentity', on_delete=models.CASCADE, null=True, blank=True,
        related_name='anomalies'
    )
    process_record = models.ForeignKey(
        'DyeingProcess', on_delete=models.CASCADE, null=True, blank=True,
        related_name='anomalies'
    )
    
    # Detail berupa JSON (misal flag, selisih suhu, selisih waktu)
    details = models.JSONField(default=dict, help_text="Data spesifik anomali")
    
    # Resolusi
    is_resolved = models.BooleanField(default=False)
    resolved_action = models.CharField(max_length=50, null=True, blank=True, help_text="Aksi yang diambil (UNLINKED, dll)")
    resolution_notes = models.TextField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
        
    def __str__(self):
        return f"{self.severity} - {self.anomaly_type} (Resolved: {self.is_resolved})"


# ═══════════════════════════════════════════════════════════════════════════════
# ENGINEER WORKSPACE
# ═══════════════════════════════════════════════════════════════════════════════

class InspectionTemplate(models.Model):
    """Checklist template per grup mesin untuk inspeksi lapangan."""
    machine_group = models.ForeignKey(
        MachineGroup, on_delete=models.CASCADE, null=True, blank=True,
        related_name='inspection_templates',
        help_text="Kosongkan untuk template umum semua mesin"
    )
    name = models.CharField(max_length=100)
    items = models.JSONField(
        default=list,
        help_text='Daftar item checklist, misal: [{"id": "steam_leak", "label": "Kebocoran steam", "required": true}]'
    )
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class SparePart(models.Model):
    """Katalog spare part untuk mesin energi/proses."""
    name = models.CharField(max_length=200)
    part_number = models.CharField(max_length=100, blank=True)
    description = models.TextField(blank=True)
    machines = models.ManyToManyField(Machine, blank=True, related_name='spare_parts')
    location = models.CharField(max_length=100, blank=True, help_text="Lokasi di gudang")
    stock_quantity = models.IntegerField(default=0)
    min_stock = models.IntegerField(default=1, help_text="Stok minimum sebelum alert")
    unit = models.CharField(max_length=20, default='pcs')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.min_stock

    def __str__(self):
        return f"{self.name} ({self.part_number or 'no PN'})"


class FieldInspection(models.Model):
  STATUS_CHOICES = [
      ('DRAFT', 'Draft'),
      ('SUBMITTED', 'Submitted'),
  ]
  SEVERITY_CHOICES = [
      ('CRITICAL', 'Critical'),
      ('HIGH', 'High'),
      ('NORMAL', 'Normal'),
      ('OK', 'OK'),
  ]

  machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='field_inspections')
  inspector = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='field_inspections')
  template = models.ForeignKey(InspectionTemplate, on_delete=models.SET_NULL, null=True, blank=True)
  checklist_results = models.JSONField(default=dict, help_text="Hasil per item checklist")
  severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default='NORMAL')
  notes = models.TextField(blank=True)
  recommendation = models.TextField(blank=True)
  photo = models.ImageField(upload_to='inspections/%Y/%m/', null=True, blank=True)
  status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
  created_at = models.DateTimeField(auto_now_add=True)
  submitted_at = models.DateTimeField(null=True, blank=True)

  class Meta:
      ordering = ['-created_at']

  def __str__(self):
      return f"Inspeksi {self.machine.code} @ {self.created_at:%Y-%m-%d}"


class EngineerIssue(models.Model):
    """Antrian masalah terpadu untuk engineer (anomali, inspeksi, spare part, manual)."""
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('IN_PROGRESS', 'In Progress'),
        ('WAITING_PARTS', 'Waiting Parts'),
        ('RESOLVED', 'Resolved'),
    ]
    PRIORITY_CHOICES = [
        ('CRITICAL', 'Critical'),
        ('HIGH', 'High'),
        ('NORMAL', 'Normal'),
    ]
    SOURCE_CHOICES = [
        ('ANOMALY', 'Data Anomaly'),
        ('INSPECTION', 'Field Inspection'),
        ('SPARE_PART', 'Spare Part'),
        ('MANUAL', 'Manual'),
        ('MEETING', 'Meeting Action'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    source_type = models.CharField(max_length=20, choices=SOURCE_CHOICES, default='MANUAL')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='OPEN')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='NORMAL')
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True, related_name='engineer_issues')
    data_anomaly = models.ForeignKey(DataAnomaly, on_delete=models.SET_NULL, null=True, blank=True, related_name='engineer_issues')
    field_inspection = models.ForeignKey(FieldInspection, on_delete=models.SET_NULL, null=True, blank=True, related_name='engineer_issues')
    spare_part = models.ForeignKey(SparePart, on_delete=models.SET_NULL, null=True, blank=True, related_name='engineer_issues')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_issues')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='created_issues')
    due_date = models.DateField(null=True, blank=True)
    resolution_notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.priority}] {self.title}"


class EngineerNote(models.Model):
    """Catatan engineer per mesin (tidak mengubah data produksi)."""
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='engineer_notes')
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Note {self.machine.code} by {self.author}"


class SparePartUsageLog(models.Model):
    spare_part = models.ForeignKey(SparePart, on_delete=models.CASCADE, related_name='usage_logs')
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True)
    quantity = models.IntegerField(default=1)
    notes = models.TextField(blank=True)
    used_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    used_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-used_at']

    def __str__(self):
        return f"{self.spare_part.name} x{self.quantity}"


class CalculationSession(models.Model):
    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('FINAL', 'Final'),
    ]

    title = models.CharField(max_length=200)
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name='calculation_sessions')
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    parameters = models.JSONField(default=dict, help_text="Parameter perhitungan (misal k_ideal, steam_temp)")
    results = models.JSONField(default=dict, help_text="Hasil perhitungan dan chart data")
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='DRAFT')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"{self.title} ({self.status})"


class MeetingNote(models.Model):
    title = models.CharField(max_length=200)
    meeting_date = models.DateField()
    participants = models.TextField(blank=True, help_text="Daftar peserta, dipisah koma")
    agenda = models.TextField(blank=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-meeting_date', '-created_at']

    def __str__(self):
        return f"{self.title} ({self.meeting_date})"


class ActionItem(models.Model):
    STATUS_CHOICES = [
        ('OPEN', 'Open'),
        ('DONE', 'Done'),
    ]

    meeting = models.ForeignKey(MeetingNote, on_delete=models.CASCADE, null=True, blank=True, related_name='action_items')
    description = models.TextField()
    assignee = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='action_items')
    due_date = models.DateField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='OPEN')
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True)
    engineer_issue = models.ForeignKey(EngineerIssue, on_delete=models.SET_NULL, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['status', 'due_date', '-created_at']

    def __str__(self):
        return self.description[:60]


# ── STANDARD FLOW PROCESS ───────────────────────────────────────────────────

class StandardFlowProcess(models.Model):
    master_kain = models.ForeignKey(MasterKain, on_delete=models.CASCADE, related_name="flow_processes")
    tanggal_pembuatan_form = models.DateField(null=True, blank=True, help_text="Tanggal form alur ini aslinya dibuat")
    tanggal_generate = models.DateTimeField(auto_now_add=True, help_text="Waktu form ini direkam ke sistem")
    versi = models.CharField(max_length=50, blank=True, null=True, help_text="Dibuat otomatis dari tanggal pembuatan")
    status = models.CharField(
        max_length=20,
        choices=[("DRAFT", "Draft"), ("AKTIF", "Aktif"), ("ARSIP", "Arsip")],
        default="AKTIF"
    )
    hasil_lebar = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hasil_pick = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hasil_gramasi = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hasil_susut = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hasil_persen_wr = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Standard Flow Process"
        verbose_name_plural = "Standard Flow Processes"
        ordering = ["-created_at"]


    def save(self, *args, **kwargs):
        import datetime
        if not self.tanggal_pembuatan_form:
            self.tanggal_pembuatan_form = datetime.date.today()
        
        # Auto generate versi berdasarkan tanggal pembuatan
        if not self.versi:
            self.versi = f"v{self.tanggal_pembuatan_form.strftime('%Y%m%d')}"
            
        super().save(*args, **kwargs)

    def __str__(self):
        v = f" ({self.versi})" if self.versi else ""
        return f"Flow Process {self.master_kain.nama_kain}{v} - {self.status}"

class BaseFlowProcess(models.Model):
    master_flow = models.ForeignKey(StandardFlowProcess, on_delete=models.CASCADE)
    urutan = models.PositiveIntegerField(default=1)
    mesin = models.CharField(max_length=255, blank=True, null=True)
    hasil_lebar = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hasil_pick = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hasil_gramasi = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    hasil_panjang_jadi = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta:
        abstract = True
        ordering = ["urutan"]

class FlowProcessGreige(BaseFlowProcess):
    panjang_std = models.DecimalField("Panjang (YD)", max_digits=10, decimal_places=2, null=True, blank=True)
    lebar = models.DecimalField("Lebar (CM)", max_digits=10, decimal_places=2, null=True, blank=True)
    pick_mesin = models.DecimalField("Pick Mesin (T)", max_digits=10, decimal_places=2, null=True, blank=True)
    pick_greige = models.DecimalField("Pick Greige (T)", max_digits=10, decimal_places=2, null=True, blank=True)
    berat_greige = models.DecimalField("Berat Greige (KG)", max_digits=10, decimal_places=2, null=True, blank=True)
    gramasi = models.DecimalField("Gramasi (GR/M2)", max_digits=10, decimal_places=2, null=True, blank=True)
    catatan_koreksi = models.TextField(blank=True, null=True)

    class Meta(BaseFlowProcess.Meta):
        verbose_name = "Greige"
        verbose_name_plural = "Greige"

class FlowProcessCreeping(BaseFlowProcess):
    temperatur = models.DecimalField("Temp Keep (°C)", max_digits=10, decimal_places=2, null=True, blank=True)
    waktu = models.DecimalField("Keep Time (min)", max_digits=10, decimal_places=2, null=True, blank=True)
    program = models.CharField(max_length=255, blank=True, null=True)
    tekanan_pompa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    volume_air = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    isi_per_tube = models.CharField(max_length=255, blank=True, null=True)
    isi_per_batch = models.CharField(max_length=255, blank=True, null=True)
    resep = models.TextField(blank=True, null=True)

    class Meta(BaseFlowProcess.Meta):
        verbose_name = "Creeping"
        verbose_name_plural = "Creeping"

class FlowProcessDryer(BaseFlowProcess):
    temperatur = models.DecimalField("Temperatur (C)", max_digits=10, decimal_places=2, null=True, blank=True)
    speed = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    silinder_dry = models.BooleanField(default=False)
    scutcher = models.BooleanField(default=False)

    class Meta(BaseFlowProcess.Meta):
        verbose_name = "Dryer"
        verbose_name_plural = "Dryer"

class FlowProcessPreset(BaseFlowProcess):
    temperatur = models.DecimalField("Temperatur (C)", max_digits=10, decimal_places=2, null=True, blank=True)
    speed = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    set_lebar = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    blower = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    over_feed = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta(BaseFlowProcess.Meta):
        verbose_name = "Preset"
        verbose_name_plural = "Preset"

class FlowProcessWR(BaseFlowProcess):
    coustic = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    speed = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    persen_wr = models.DecimalField("%WR", max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta(BaseFlowProcess.Meta):
        verbose_name = "WR"
        verbose_name_plural = "WR"

class FlowProcessCelup(BaseFlowProcess):
    program = models.CharField(max_length=255, blank=True, null=True)
    temperatur = models.DecimalField("Temp Keep (C)", max_digits=10, decimal_places=2, null=True, blank=True)
    waktu = models.DecimalField("Time Keep (min)", max_digits=10, decimal_places=2, null=True, blank=True)
    nozzle = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    tekanan_pompa = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    isi_per_tube = models.CharField(max_length=255, blank=True, null=True)
    isi_per_batch = models.CharField(max_length=255, blank=True, null=True)
    resep = models.TextField(blank=True, null=True)

    class Meta(BaseFlowProcess.Meta):
        verbose_name = "Celup"
        verbose_name_plural = "Celup"

class FlowProcessDryerFinal(BaseFlowProcess):
    silinder_dry = models.BooleanField(default=False)
    centrifugal = models.BooleanField(default=False)

    class Meta(BaseFlowProcess.Meta):
        verbose_name = "Dryer Final"
        verbose_name_plural = "Dryer Final"

class FlowProcessFinalSet(BaseFlowProcess):
    temperatur = models.DecimalField("Temperatur (C)", max_digits=10, decimal_places=2, null=True, blank=True)
    speed = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    set_lebar = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    blower = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    over_feed = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    class Meta(BaseFlowProcess.Meta):
        verbose_name = "Final Set"
        verbose_name_plural = "Final Set"

class ObatAntistatic(models.Model):
    dryer_final = models.ForeignKey(FlowProcessDryerFinal, on_delete=models.CASCADE, related_name="obat_antistatic")
    nama = models.CharField(max_length=255)
    persentase = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = "Obat Antistatic"
        verbose_name_plural = "Obat Antistatic"

class ObatSoftener(models.Model):
    dryer_final = models.ForeignKey(FlowProcessDryerFinal, on_delete=models.CASCADE, related_name="obat_softener")
    nama = models.CharField(max_length=255)
    persentase = models.CharField(max_length=50, blank=True, null=True)

    class Meta:
        verbose_name = "Obat Softener"
        verbose_name_plural = "Obat Softener"


class ProductionPlan(models.Model):
    """Header rencana produksi untuk satu shift (06:00–06:00)."""
    STATUS_CHOICES = [
        ("DRAFT", "Draft"),
        ("PUBLISHED", "Published"),
        ("ARCHIVED", "Archived"),
    ]
    shift_date = models.DateField(
        help_text="Tanggal awal shift (jam 06:00), sama makna dgn shift_date di snapshot-history"
    )
    name = models.CharField(
        max_length=150,
        blank=True,
        help_text="Nama rencana, misal: 'Rencana Shift A - 21 Agu'",
    )
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="DRAFT")
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        related_name="production_plans_created",
    )
    updated_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="production_plans_updated",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    version = models.PositiveIntegerField(
        default=1,
        help_text="Dinaikkan setiap update tersimpan; untuk optimistic locking sederhana",
    )

    class Meta:
        indexes = [models.Index(fields=["shift_date", "status"])]
        ordering = ["-shift_date", "-created_at"]
        verbose_name = "Production Plan"
        verbose_name_plural = "Production Plans"

    def __str__(self):
        return f"{self.name or 'Rencana'} — {self.shift_date} ({self.status})"


class ProductionPlanBatch(models.Model):
    """
    Satu 'proses' (siklus Heat→Hold→Cool atau Running manual) yang ditempatkan pada satu mesin.
    Unit atomik yang ditambah/dihapus lewat drag.
    """
    plan = models.ForeignKey(ProductionPlan, on_delete=models.CASCADE, related_name="batches")
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE, related_name="plan_batches")
    program = models.ForeignKey(
        "ProgramMaster",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="plan_batches",
        help_text=(
            "Program target yang dipilih saat batch dibuat/diedit (opsional, hanya untuk mesin AUTO). "
            "Disimpan untuk histori/pelaporan — durasi aktual tetap di ProductionPlanBlock, "
            "TIDAK auto-sync kalau ProgramMaster diubah admin di kemudian hari."
        ),
    )
    label = models.CharField(
        max_length=100,
        blank=True,
        help_text="Label bebas, misal: 'Batch 12 - PO-2231'",
    )
    order = models.PositiveIntegerField(
        default=0,
        help_text="Urutan tampil bila >1 batch pada mesin yang sama",
    )
    start_offset_minutes = models.PositiveIntegerField(
        help_text="Menit sejak shift_start (0–1439)"
    )

    class Meta:
        ordering = ["machine_id", "start_offset_minutes"]
        indexes = [models.Index(fields=["plan", "machine"])]
        verbose_name = "Production Plan Batch"
        verbose_name_plural = "Production Plan Batches"

    def __str__(self):
        return f"{self.machine.code} @ +{self.start_offset_minutes}m ({self.label or 'Batch'})"

    @property
    def total_duration_minutes(self):
        # Prefetch batches__blocks di endpoint agar tidak N+1.
        return sum(b.duration_minutes for b in self.blocks.all())


class ProductionPlanBlock(models.Model):
    """Satu fase (Heat / Hold / Cool / Running) di dalam sebuah ProductionPlanBatch."""
    PHASE_CHOICES = [
        ("HEAT", "Heating"),
        ("STEADY", "Hold / Keeping"),
        ("COOL", "Cooling"),
        ("RUNNING", "Running (Manual On)"),
    ]
    batch = models.ForeignKey(ProductionPlanBatch, on_delete=models.CASCADE, related_name="blocks")
    phase = models.CharField(max_length=10, choices=PHASE_CHOICES)
    sequence = models.PositiveSmallIntegerField(
        help_text="0=Heat, 1=Hold, 2=Cool (AUTO) atau 0=Running (MANUAL)"
    )
    duration_minutes = models.IntegerField(validators=[MinValueValidator(0)])

    class Meta:
        ordering = ["batch_id", "sequence"]
        unique_together = [("batch", "sequence")]
        verbose_name = "Production Plan Block"
        verbose_name_plural = "Production Plan Blocks"

    def __str__(self):
        return f"{self.batch} · {self.phase} · {self.duration_minutes}m"



# ─── JUMO Device Configuration Models ────────────────────────────────────────

class JumoDevice(models.Model):
    """
    Menyimpan konfigurasi satu JUMO Modbus controller.
    Pengganti hardcoded DEVICES list di jumo_realtime.py.
    """
    name = models.CharField(
        max_length=100,
        unique=True,
        help_text="Nama device, misal: JUMO_A_601"
    )
    ip_address = models.GenericIPAddressField(
        help_text="IP Address Modbus TCP, misal: 192.168.4.10"
    )
    port = models.IntegerField(
        default=502,
        help_text="Port Modbus TCP (default 502)"
    )
    start_addr = models.CharField(
        max_length=10,
        help_text="Start Address register — decimal (4102) atau hex (0x1006)"
    )
    device_id = models.IntegerField(
        default=1,
        help_text="Device/Unit ID Modbus (255 untuk broadcast, 1 untuk individual)"
    )
    num_ai = models.IntegerField(
        default=6,
        help_text="Jumlah Analog Input yang dibaca dari device ini"
    )
    is_active = models.BooleanField(
        default=True,
        help_text="Nonaktifkan untuk menghentikan polling tanpa menghapus data"
    )

    class Meta:
        verbose_name = "Jumo Device"
        verbose_name_plural = "Jumo Devices"
        ordering = ["name"]

    def clean(self):
        """
        Validasi format start_addr saat disimpan melalui Admin.
        Error ditampilkan di form Admin, BUKAN saat runtime script.
        """
        super().clean()
        if self.start_addr:
            raw = self.start_addr.strip()
            try:
                if raw.lower().startswith("0x"):
                    int(raw, 16)
                else:
                    int(raw)
            except ValueError:
                raise ValidationError({
                    "start_addr": (
                        f"Format tidak valid: '{raw}'. "
                        "Gunakan decimal (misal 4102) atau hexadecimal (misal 0x1006)."
                    )
                })

    def __str__(self):
        return f"{self.name} ({self.ip_address})"


class JumoChannel(models.Model):
    """
    Mapping antara satu slot Analog Input (index) di sebuah JumoDevice
    dengan satu Machine di database.
    """
    device = models.ForeignKey(
        JumoDevice,
        on_delete=models.CASCADE,
        related_name="channels",
        help_text="Device JUMO tempat channel ini berada"
    )
    channel_index = models.IntegerField(
        help_text="Index channel (mulai 0). Harus < num_ai device terkait."
    )
    machine = models.ForeignKey(
        "Machine",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="jumo_channels",
        help_text="Machine yang menerima data dari channel ini. Kosongkan jika tidak digunakan."
    )

    class Meta:
        verbose_name = "Jumo Channel"
        verbose_name_plural = "Jumo Channels"
        unique_together = [["device", "channel_index"]]
        ordering = ["device", "channel_index"]

    def clean(self):
        """
        Validasi channel_index tidak melebihi num_ai device.
        Mencegah operator salah mengisi index di Admin.

        Catatan implementasi: saat admin membuat JumoDevice baru dan langsung
        mengisi channel di inline form yang sama (satu kali submit), Django
        memvalidasi inline SEBELUM device di-commit ke DB. Pada kondisi ini,
        self.device_id akan ada (diisi dari form), tapi pemanggilan self.device
        (FK lookup ke DB) akan raise RelatedObjectDoesNotExist atau return object
        yang belum tersimpan. Guard di bawah ini menangani kedua kasus tersebut.
        """
        super().clean()
        # Guard 1: channel_index harus diisi sebelum divalidasi
        if self.channel_index is None:
            return
        # Guard 2: device harus sudah terasosiasi
        if not self.device_id:
            return
        # Guard 3: coba ambil device — bisa gagal jika device baru belum di-commit
        try:
            device = self.device
            # Guard 4: device mungkin sudah ada di Python memory tapi belum punya PK
            if device.pk is None:
                return
        except Exception:
            return
        if self.channel_index < 0 or self.channel_index >= device.num_ai:
            raise ValidationError({
                "channel_index": (
                    f"Index {self.channel_index} tidak valid. "
                    f"Device '{device.name}' hanya punya {device.num_ai} channel "
                    f"(index 0 s/d {device.num_ai - 1})."
                )
            })

    def __str__(self):
        machine_name = self.machine.code if self.machine else "(tidak dipakai)"
        return f"{self.device.name} · Ch {self.channel_index} → {machine_name}"


# ═══════════════════════════════════════════════════════════════════════════════
# ANOMALY DETECTION V2 (Master Threshold & Z-Score Calibration)
# ═══════════════════════════════════════════════════════════════════════════════

class AnomalyThresholdMaster(models.Model):
    machine = models.ForeignKey(Machine, on_delete=models.CASCADE)
    program = models.ForeignKey('ProgramMaster', on_delete=models.CASCADE)
    
    UPDATE_MODE_CHOICES = [
        ('AUTO', 'Auto (Ikut kalibrasi mingguan)'),
        ('MANUAL', 'Manual (Terkunci, abaikan usulan)')
    ]
    update_mode = models.CharField(max_length=10, choices=UPDATE_MODE_CHOICES, default='AUTO')
    
    # SUHU
    suhu_mean = models.FloatField(default=0.0)
    suhu_stddev = models.FloatField(default=0.0)
    suhu_count = models.IntegerField(default=0)
    suhu_m2 = models.FloatField(default=0.0)
    suhu_lower_bound = models.FloatField(null=True, blank=True)
    suhu_upper_bound = models.FloatField(null=True, blank=True)

    # HEAT
    heat_mean = models.FloatField(default=0.0)
    heat_stddev = models.FloatField(default=0.0)
    heat_count = models.IntegerField(default=0)
    heat_m2 = models.FloatField(default=0.0)
    heat_lower_bound = models.FloatField(null=True, blank=True)
    heat_upper_bound = models.FloatField(null=True, blank=True)

    # KEEP
    keep_mean = models.FloatField(default=0.0)
    keep_stddev = models.FloatField(default=0.0)
    keep_count = models.IntegerField(default=0)
    keep_m2 = models.FloatField(default=0.0)
    keep_lower_bound = models.FloatField(null=True, blank=True)
    keep_upper_bound = models.FloatField(null=True, blank=True)

    # COOL
    cool_mean = models.FloatField(default=0.0)
    cool_stddev = models.FloatField(default=0.0)
    cool_count = models.IntegerField(default=0)
    cool_m2 = models.FloatField(default=0.0)
    cool_lower_bound = models.FloatField(null=True, blank=True)
    cool_upper_bound = models.FloatField(null=True, blank=True)

    last_calibrated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ['machine', 'program']
        ordering = ['machine', 'program']

    def __str__(self):
        return f"Master Threshold: {self.machine.code} - {self.program.nama}"

class AnomalyThresholdProposal(models.Model):
    master = models.ForeignKey(AnomalyThresholdMaster, on_delete=models.CASCADE, related_name='proposals')
    week_start_date = models.DateField()
    week_end_date = models.DateField()
    
    # NEW SUHU
    suhu_mean_new = models.FloatField(null=True, blank=True)
    suhu_stddev_new = models.FloatField(null=True, blank=True)
    suhu_lower_bound_new = models.FloatField(null=True, blank=True)
    suhu_upper_bound_new = models.FloatField(null=True, blank=True)

    # NEW HEAT
    heat_mean_new = models.FloatField(null=True, blank=True)
    heat_stddev_new = models.FloatField(null=True, blank=True)
    heat_lower_bound_new = models.FloatField(null=True, blank=True)
    heat_upper_bound_new = models.FloatField(null=True, blank=True)

    # NEW KEEP
    keep_mean_new = models.FloatField(null=True, blank=True)
    keep_stddev_new = models.FloatField(null=True, blank=True)
    keep_lower_bound_new = models.FloatField(null=True, blank=True)
    keep_upper_bound_new = models.FloatField(null=True, blank=True)

    # NEW COOL
    cool_mean_new = models.FloatField(null=True, blank=True)
    cool_stddev_new = models.FloatField(null=True, blank=True)
    cool_lower_bound_new = models.FloatField(null=True, blank=True)
    cool_upper_bound_new = models.FloatField(null=True, blank=True)

    new_data_count = models.IntegerField(default=0)
    outlier_rejected_count = models.IntegerField(default=0)
    
    is_warning = models.BooleanField(default=False)
    warning_message = models.TextField(blank=True, null=True)

    STATUS_CHOICES = [
        ('DRAFT', 'Draft'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('AUTO_SKIPPED', 'Auto Skipped (Master Manual)'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='DRAFT')
    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']

class AnomalyRuleConfig(models.Model):
    rule_code = models.CharField(max_length=100, unique=True, help_text="Contoh: HARD_TEMP_LIMIT")
    
    RULE_TYPE_CHOICES = [
        ('THRESHOLD_DIFF', 'Threshold Difference (Absolut)'),
        ('BOOLEAN_CHECK', 'Boolean Check'),
    ]
    rule_type = models.CharField(max_length=20, choices=RULE_TYPE_CHOICES, default='THRESHOLD_DIFF')
    
    parameter_json = models.JSONField(default=dict, help_text='Contoh: {"max_absolute_diff": 25}')
    adds_flag = models.CharField(max_length=50, help_text="Contoh: SUHU_HARD")
    display_label = models.CharField(max_length=50, null=True, blank=True, help_text="Label tampilan UI (misal: 'Suhu', 'Pressure')")
    
    FORCES_SEVERITY_CHOICES = [
        ('NONE', 'None (Ikut hitungan flag biasa)'),
        ('CRITICAL', 'CRITICAL'),
        ('MEDIUM', 'MEDIUM'),
        ('LOW', 'LOW')
    ]
    forces_severity = models.CharField(max_length=15, choices=FORCES_SEVERITY_CHOICES, default='NONE', help_text="Override ke severity ini jika rule terpenuhi")
    
    is_active = models.BooleanField(default=True)
    
    def __str__(self):
        return f"{self.rule_code} -> {self.adds_flag}"

class AnomalySeverityLevel(models.Model):
    severity_name = models.CharField(max_length=20, unique=True, help_text="CRITICAL, MEDIUM, LOW")
    min_flags_required = models.IntegerField(default=1)
    
    class Meta:
        ordering = ['-min_flags_required']
        
    def __str__(self):
        return f"{self.severity_name} (>= {self.min_flags_required} flags)"


# --------------------------------------------------------------------------
# PRODUCTION PHYSICAL REPORT MODELS (ROLL OFF, SMCH, STENTER EHWA)
# --------------------------------------------------------------------------
from .models_production_reports import (
    clean_canonical_order,
    clean_canonical_batch,
    RollOffReport,
    RollOffItem,
    RollOffEvent,
    SmchReport,
    SmchItem,
    SmchEvent,
    FinishingReport,
    StenterItem,
    StenterEvent,
)


# --------------------------------------------------------------------------
# LOCAL CHAT & REPORT SHARING MODELS (1-ON-1)
# --------------------------------------------------------------------------
class DirectConversation(models.Model):
    user1 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direct_conversations_user1')
    user2 = models.ForeignKey(User, on_delete=models.CASCADE, related_name='direct_conversations_user2')
    last_message_at = models.DateTimeField(db_index=True, null=True, blank=True)
    last_message_preview = models.CharField(max_length=255, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = [['user1', 'user2']]
        ordering = ['-last_message_at', '-created_at']

    @classmethod
    def get_or_create_conversation(cls, u1, u2):
        if u1.id > u2.id:
            u1, u2 = u2, u1
        conv, _ = cls.objects.get_or_create(user1=u1, user2=u2)
        return conv

    def __str__(self):
        return f"Chat: {self.user1.username} <-> {self.user2.username}"


class DirectMessage(models.Model):
    MESSAGE_TYPES = [
        ('TEXT', 'Pesan Teks'),
        ('REPORT_SHARE', 'Berbagi Laporan'),
        ('MACHINE_SNAPSHOT', 'Kondisi Mesin'),
        ('CHART_BOOKMARK', 'Bookmark Grafik'),
        ('ACTION_CHECK', 'Tiket Konfirmasi Cepat'),
    ]

    conversation = models.ForeignKey(DirectConversation, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_direct_messages')
    message_type = models.CharField(max_length=30, choices=MESSAGE_TYPES, default='TEXT')
    content = models.TextField(blank=True, default='')
    metadata = models.JSONField(default=dict, blank=True)
    reply_to = models.ForeignKey('self', null=True, blank=True, on_delete=models.SET_NULL, related_name='replies')
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.message_type}] {self.sender.username}: {self.content[:30]}"

