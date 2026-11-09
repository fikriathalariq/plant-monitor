from django.contrib import admin
from django.core.paginator import Paginator
from monitoring.models import (
    Machine,
    MachineGroup,
    MachineMinuteLog,
    DyeingProcess,
    DyeingIdentity,
    OperatorProfile,
    Position,
    PagePermission,
    RawDataFile,
    Shift,
    MachineStatusSnapshot,
    MachinePerformanceSummary,
    Alert,
    UserActivityLog,
    IPAccessControl,
    ProgramMaster,
    MachineCalibration,
    MachineSensorMapping,
    MachineSensorProfile,
    get_calibrated_temperature,
    DyeingAnalytics,
    DyeingExecutiveSummary,
    GlobalSettings,
    DataAnomaly,
    MasterAnyaman,
    MasterKain,
    BenangLusi,
    BenangPakan,
    RevisiKain,
    JumoDevice,
    JumoChannel,
)
from django.utils.html import format_html
from .models import CompanyProfile
from monitoring.utils.gradient_processor import GradientProcessor, ProcessingConfig
import math
from django.contrib import messages
from django.utils import timezone
from rangefilter.filters import DateRangeFilter


class LargeTablePaginator(Paginator):
    """
    Paginator khusus untuk tabel dengan jutaan baris (MachineMinuteLog).

    Dua optimasi utama:
    1. count      - mengembalikan angka dummy besar, menghindari SELECT COUNT(*) yang berat.
    2. page_range - hanya mengembalikan maks 3 nomor halaman (prev/current/next),
                    sehingga template pagination tidak merender ribuan link halaman.

    Halaman aktif di-inject oleh MachineMinuteLogAdmin.get_paginator() melalui
    atribut _current_page_number.
    """

    # Diisi oleh MachineMinuteLogAdmin.get_paginator() sebelum paginator dipakai
    _current_page_number = 1

    @property
    def count(self):
        # Angka besar agar Django tidak pernah menjalankan SELECT COUNT(*)
        return 999_999_999

    @property
    def num_pages(self):
        """
        Paksa Django percaya bahwa jumlah halaman hanya sampai halaman berikutnya.
        Ini menghilangkan tombol '... 9999999' di ujung pagination.
        """
        return self._current_page_number + 1

    @property
    def page_range(self):
        """
        Hanya kembalikan halaman: [current-1, current, current+1].
        """
        current = self._current_page_number
        start = max(1, current - 1)
        end = current + 2
        return range(start, end)

@admin.register(MachineGroup)
class MachineGroupAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "process_type")
    list_filter = ("process_type",)
    search_fields = ("code", "name")

@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("name",)

class SensorMappingInline(admin.TabularInline):
    model = MachineSensorMapping
    fk_name = "machine"
    extra = 1
    fields = ['sensor_machine', 'role', 'eval_method', 'threshold_on', 'threshold_off', 'utility_type']
    autocomplete_fields = ['sensor_machine']

@admin.register(MachineSensorProfile)
class MachineSensorProfileAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "group", "operation_mode")
    list_filter = ("group", "operation_mode")
    search_fields = ("code", "name")
    inlines = [SensorMappingInline]
    
    # Sembunyikan field-field master machine agar halaman admin ini bersih khusus untuk mapping
    fields = ("code", "name", "operation_mode")
    readonly_fields = ("code", "name", "operation_mode")
    
    def has_add_permission(self, request):
        return False # Tidak bisa tambah mesin dari sini, hanya edit mapping

class MachineCalibrationInline(admin.StackedInline):
    """
    Inline admin untuk MachineCalibration yang ditampilkan di dalam halaman detail Machine.
    Memudahkan admin membuat/mengedit kalibrasi sensor langsung dari halaman mesin.
    """
    model = MachineCalibration
    can_delete = True
    max_num = 1
    min_num = 0
    extra = 0
    verbose_name = "Kalibrasi Sensor"
    verbose_name_plural = "Konfigurasi Kalibrasi"
    fields = ('is_active', 'a_coeff', 'b_coeff', 'c_coeff', 'notes')
    
    help_texts = {
        'a_coeff': 'Koefisien Kuadratik (default 0). Contoh: 0.05 untuk kurva melengkung naik.',
        'b_coeff': 'Koefisien Linear (default 1.0). Contoh: 1.05 untuk naik 5% di seluruh range.',
        'c_coeff': 'Offset (default 0). Contoh: 2.5 untuk tambah 2.5°C.',
    }


@admin.register(Machine)
class MachineAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "group", "operation_mode", "get_process_type", "avg_hto_calories", "average_steam_usage", "batch_steam", "losses_steam", "max_water_capacity", "max_fabric_capacity", "surface_area", "u_value", "c_machine", "is_active", "unit", "temperature", "last_status", "last_update", "last_valid_reading_at")
    list_filter = ("group", "group__process_type", "operation_mode", "is_active", "unit", "last_status")
    search_fields = ("name", "code")
    list_editable = ("is_active",)
    inlines = [MachineCalibrationInline]
    
    def get_process_type(self, obj):
        """Display process type from MachineGroup (read-only)"""
        if obj.group and obj.group.process_type:
            return obj.group.get_process_type_display()
        return "-"
    get_process_type.short_description = "Process Type"
    get_process_type.admin_order_field = "group__process_type"
    
    @admin.action(description='Scan & Detect Batches (Last 30 Days)')
    def scan_for_batches(self, request, queryset):
        """
        Scan last 30 days of logs for selected machines and detect batches.
        Useful for manual refresh of DyeingProcess.
        """
        from datetime import timedelta
        
        count_machines = 0
        total_batches = 0
        
        # Helper to avoid massive duplication (re-defined here for safety within action scope)
        def _create_or_update_batch_local(machine, start_time, end_time, logs):
            # Look for batch for this machine that starts within small window
            batch = DyeingProcess.objects.filter(
                machine=machine,
                start_time__range=(start_time - timedelta(minutes=5), start_time + timedelta(minutes=5))
            ).first()
            
            if not batch:
                 # Create new
                 last_batch = DyeingProcess.objects.filter(machine=machine).order_by('-batch_number').first()
                 next_num = (last_batch.batch_number + 1) if last_batch else 1
                 
                 batch = DyeingProcess.objects.create(
                     machine=machine,
                     batch_number=next_num,
                     start_time=start_time,
                     end_time=end_time
                 )
                 
                 # ── Re-link orphaned DyeingIdentity (anchor-based matching) ──────
                 orphan_identity = DyeingIdentity.objects.filter(
                     machine=machine,
                     dyeing_process__isnull=True,
                     start_time_snapshot__range=(
                         start_time - timedelta(minutes=15),
                         start_time + timedelta(minutes=15),
                     )
                 ).first()
                 if orphan_identity:
                     orphan_identity.dyeing_process = batch
                     orphan_identity.save(update_fields=["dyeing_process"])
                 # ─────────────────────────────────────────────────────────────────
            else:
                batch.end_time = end_time
            
            if end_time:
                batch.is_complete = True
            else:
                batch.is_complete = False
                
            # Calc Stats (reuse similar logic)
            heating_duration = 0.0
            heating_grad_sum = 0.0
            heating_count = 0
            max_temp = 0.0
            steady_duration = 0.0
            cooling_duration = 0.0
            cooling_grad_sum = 0.0
            cooling_count = 0
            
            prev_ts = None
            
            for log in logs:
                if prev_ts:
                    dt = (log.timestamp - prev_ts).total_seconds() / 60.0
                else:
                    dt = 1.0 
                dt = max(0.5, min(dt, 10.0))
                
                temp = log.temperature or 0
                if temp > max_temp: max_temp = temp
                
                state = log.thermal_state
                grad = log.gradient or 0
                
                if state == "HEAT":
                    heating_duration += dt
                    if grad > 0:
                        heating_grad_sum += grad
                        heating_count += 1
                elif state == "STEADY":
                    steady_duration += dt
                elif state == "COOL":
                    cooling_duration += dt
                    if grad < 0:
                        cooling_grad_sum += grad
                        cooling_count += 1
                
                prev_ts = log.timestamp

            batch.max_temp = max_temp
            batch.heating_duration = heating_duration
            batch.steady_duration = steady_duration
            batch.cooling_duration = cooling_duration
            
            if heating_count > 0:
                batch.heating_avg_gradient = heating_grad_sum / heating_count
            else:
                batch.heating_avg_gradient = 0.0
            
            if cooling_count > 0:
                batch.cooling_avg_gradient = cooling_grad_sum / cooling_count
            else:
                batch.cooling_avg_gradient = 0.0
                
            batch.save()

        # CONFIG & PROCESSOR
        config = ProcessingConfig()
        
        for machine in queryset:
            # 1. Fetch Logs (Last 30 Days)
            start_scan = timezone.now() - timedelta(days=30)
            logs = MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp__gte=start_scan
            ).order_by('timestamp')
            
            if not logs.exists():
                continue
                
            # 2. Init Processor
            processor = GradientProcessor(config)
            from monitoring.utils.gradient_processor import FilterState
            state = FilterState()
            
            # Seed state?
            prev_log = MachineMinuteLog.objects.filter(
                machine=machine, 
                timestamp__lt=start_scan
            ).order_by('-timestamp').first()
            
            if prev_log and prev_log.ewma_temp is not None:
                state = FilterState(
                    last_valid_temp=prev_log.filtered_temp,
                    ewma_temp=prev_log.ewma_temp,
                    kalman_x=prev_log.kalman_x,
                    kalman_p=prev_log.kalman_p,
                    last_thermal_state=prev_log.thermal_state or "OFF"
                )
            
            prev_timestamp = prev_log.timestamp if prev_log else None
            
            current_batch_start = None
            current_batch_logs = []
            updates = []
            machine_batches = 0
            
            for log in logs:
                # Use centralized helper for validation
                from monitoring.utils.gradient_processor import is_invalid_temperature
                if is_invalid_temperature(log.temperature):
                     continue
                     
                # DT
                if prev_timestamp:
                    dt_minutes = (log.timestamp - prev_timestamp).total_seconds() / 60.0
                else:
                    dt_minutes = 1.0
                dt_minutes = max(0.5, min(dt_minutes, 10.0))
                
                # Capture Previous State
                prev_thermal_state = state.last_thermal_state
                
                # Process
                filtered, gradient, thermal_state, state = processor.process_single(
                    raw_temp=log.temperature,
                    state=state,
                    dt_minutes=dt_minutes
                )
                
                log.filtered_temp = filtered
                log.gradient = gradient
                log.thermal_state = thermal_state
                log.ewma_temp = state.ewma_temp
                log.kalman_x = state.kalman_x
                log.kalman_p = state.kalman_p
                
                updates.append(log)
                
                # BATCH DETECTION
                if current_batch_start is None:
                    if thermal_state in ["HEAT", "STEADY"] and prev_thermal_state == "OFF":
                        current_batch_start = log.timestamp
                        current_batch_logs = [log]
                elif current_batch_start is not None:
                    current_batch_logs.append(log)
                    if thermal_state == "OFF":
                        _create_or_update_batch_local(machine, current_batch_start, log.timestamp, current_batch_logs)
                        machine_batches += 1
                        current_batch_start = None
                        current_batch_logs = []

                prev_timestamp = log.timestamp
                
                if len(updates) > 1000:
                    MachineMinuteLog.objects.bulk_update(updates, ['filtered_temp', 'gradient', 'thermal_state', 'ewma_temp', 'kalman_x', 'kalman_p'])
                    updates = []
            
            if updates:
                MachineMinuteLog.objects.bulk_update(updates, ['filtered_temp', 'gradient', 'thermal_state', 'ewma_temp', 'kalman_x', 'kalman_p'])
                
            if current_batch_start:
                 _create_or_update_batch_local(machine, current_batch_start, None, current_batch_logs)
                 machine_batches += 1
            
            count_machines += 1
            total_batches += total
        
        self.message_user(request, f"Scanned {count_machines} machines, found/updated {total_batches} batches.")
    
    @admin.action(description='🔧 Turn to MANUAL Mode')
    def turn_to_manual_mode(self, request, queryset):
        """
        Bulk action to change selected machines to MANUAL mode.
        """
        updated_count = queryset.update(operation_mode='MANUAL')
        
        self.message_user(
            request, 
            f"Successfully changed {updated_count} machine(s) to MANUAL mode.",
            level='success'
        )
    
    @admin.action(description='⚙️ Turn to AUTO Mode')
    def turn_to_auto_mode(self, request, queryset):
        """
        Bulk action to change selected machines to AUTO mode.
        """
        updated_count = queryset.update(operation_mode='AUTO')
        
        self.message_user(
            request, 
            f"Successfully changed {updated_count} machine(s) to AUTO mode.",
            level='success'
        )
    
    # Register actions
    actions = ['scan_for_batches', 'turn_to_manual_mode', 'turn_to_auto_mode']

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")

@admin.register(PagePermission)
class PagePermissionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "url_name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code", "url_name")
    fieldsets = (
        ("Informasi Dasar", {
            "fields": ("code", "name", "url_name", "description", "is_active")
        }),
    )


@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ("name", "code", "allowed_pages_count", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "code")
    filter_horizontal = ("allowed_pages",)
    
    fieldsets = (
        ("Informasi Posisi", {
            "fields": ("code", "name", "is_active")
        }),
        ("Hak Akses Halaman", {
            "fields": ("allowed_pages",),
            "description": "Pilih halaman yang bisa diakses oleh posisi ini"
        }),
    )
    
    def allowed_pages_count(self, obj):
        count = obj.allowed_pages.filter(is_active=True).count()
        if count == 0:
            return "Tidak ada akses"
        return f"{count} halaman"
    allowed_pages_count.short_description = "Jumlah Akses"

@admin.register(OperatorProfile)
class OperatorProfileAdmin(admin.ModelAdmin):
    list_display = ("display_name", "user", "position", "shift")
    search_fields = ("display_name", "user__username")


@admin.register(MachineMinuteLog)
class MachineMinuteLogAdmin(admin.ModelAdmin):
    show_facets = admin.ShowFacets.NEVER
    # ── Optimasi Performa Tabel Raksasa ───────────────────────────────────────
    # 1. LargeTablePaginator: tidak ada SELECT COUNT(*) pada jutaan baris
    # 2. show_full_result_count=False: sembunyikan angka total
    # 3. list_per_page=50: kurangi data yang di-fetch per halaman
    # 4. list_max_show_all=0: nonaktifkan tombol "Show All" (bisa mematikan server)
    # 5. date_hierarchy DIHAPUS: mencegah GROUP BY timestamp pada jutaan baris
    # 6. DateFieldListFilter DIHAPUS: filter tanggal juga menyebabkan query berat
    paginator = LargeTablePaginator
    show_full_result_count = False
    list_per_page = 50
    list_max_show_all = 0
    # ──────────────────────────────────────────────────────────────────────────

    list_display = (
        "machine",
        "timestamp",
        "temperature",
        "filtered_temp",
        "gradient",
        "thermal_state",
    )

    # CATATAN FILTER:
    # - machine__group & machine: ringan, query ke tabel Machine (kecil)
    # - thermal_state: SELECT DISTINCT pada kolom terindeks, sangat cepat
    # - DateRangeFilter: Menampilkan kalender Start Date & End Date di sidebar
    list_filter = (
        ('machine__group', admin.RelatedFieldListFilter),
        'machine',
        'thermal_state',
        ('timestamp', DateRangeFilter),
    )

    # date_hierarchy DIHAPUS - akan diganti dengan Date Range Filter di Sidebar
    # ordering = ("-timestamp",)
    ordering = ("-timestamp",)

    autocomplete_fields = ("machine",)

    readonly_fields = (
        "machine",
        "timestamp",
        "temperature",
        "raw_temperature",
        "last_status",
        "filtered_temp",
        "gradient",
        "thermal_state",
        "ewma_temp",
        "kalman_x",
        "kalman_p",
        "ewma_gradient",
        "kalman_grad_x",
    )

    fieldsets = (
        ("Data Sensor", {
            "fields": ("machine", "timestamp", "raw_temperature", "temperature"),
            "description": "raw_temperature = nilai asli sensor. temperature = setelah kalibrasi.",
        }),
        ("Data Terfilter", {
            "fields": ("filtered_temp", "gradient", "thermal_state"),
        }),
        ("Filter State (Temp)", {
            "fields": ("ewma_temp", "kalman_x", "kalman_p"),
            "classes": ("collapse",),
        }),
        ("Filter State (Gradient)", {
            "fields": ("ewma_gradient", "kalman_grad_x"),
            "classes": ("collapse",),
        }),
    )


    def get_paginator(self, request, queryset, per_page, orphans=0, allow_empty_first_page=True):
        """
        Override get_paginator untuk men-inject nomor halaman aktif ke LargeTablePaginator.
        Django Admin menggunakan query param 'p' (0-indexed):
        - Halaman 1 = ?p=0 (atau tidak ada param)
        - Halaman 2 = ?p=1
        Tanpa injeksi ini, page_range tidak tahu halaman mana yang aktif.
        """
        paginator = self.paginator(queryset, per_page, orphans, allow_empty_first_page)
        try:
            current = int(request.GET.get('p', 0)) + 1  # konversi dari 0-indexed ke 1-indexed
        except (ValueError, TypeError):
            current = 1
        paginator._current_page_number = max(1, current)
        return paginator

    def get_changelist(self, request, **kwargs):
        from django.contrib.admin.views.main import ChangeList
        class DummyCountChangeList(ChangeList):
            def get_results(self, request):
                super().get_results(request)
                # Sembunyikan angka 999_999_999 di tulisan "99999999 machine minute logs"
                self.result_count = "Banyak"
                self.full_result_count = "Banyak"
        return DummyCountChangeList

    @admin.action(description='Reprocess Logs & Detect Batches (Filtered)')
    def reprocess_logs(self, request, queryset):
        """
        Reprocess selected logs to update filtering and identify DyeingProcess batches.
        """
        # 1. Identify machines
        machines = queryset.values_list('machine', flat=True).distinct()
        
        count_logs = 0
        count_batches = 0
        
        config = ProcessingConfig()
        
        for machine_id in machines:
            machine = Machine.objects.get(id=machine_id)
            
            # Find time range of selected logs
            selected_logs = queryset.filter(machine=machine).order_by('timestamp')
            if not selected_logs.exists():
                continue
                
            start_time = selected_logs.first().timestamp
            
            # Fetch ALL logs from that start_time for this machine, to ensure correct sequence
            logs = MachineMinuteLog.objects.filter(
                machine=machine,
                timestamp__gte=start_time
            ).order_by('timestamp')
            
            # --- PROCESSING CHAIN ---
            processor = GradientProcessor(config)
            from monitoring.utils.gradient_processor import FilterState
            state = FilterState()
            
            # Seed state from previous log if exists
            prev_log = MachineMinuteLog.objects.filter(
                machine=machine, 
                timestamp__lt=start_time
            ).order_by('-timestamp').first()
            
            if prev_log and prev_log.ewma_temp is not None:
                state = FilterState(
                    last_valid_temp=prev_log.filtered_temp,
                    ewma_temp=prev_log.ewma_temp,
                    kalman_x=prev_log.kalman_x,
                    kalman_p=prev_log.kalman_p,
                    last_thermal_state=prev_log.thermal_state or "OFF"
                )
            
            prev_timestamp = prev_log.timestamp if prev_log else None
            
            # For Batch Detection
            current_batch_start = None
            current_batch_logs = []
            
            updates = []
            
            for log in logs:
                # Use centralized helper
                from monitoring.utils.gradient_processor import is_invalid_temperature
                if is_invalid_temperature(log.temperature):
                     continue

                # Calculate DT
                if prev_timestamp:
                    dt_minutes = (log.timestamp - prev_timestamp).total_seconds() / 60.0
                else:
                    dt_minutes = 1.0
                
                dt_minutes = max(0.5, min(dt_minutes, 10.0))
                
                # Capture Previous State for Transition Check
                prev_thermal_state = state.last_thermal_state
                
                # Run Processor
                filtered, gradient, thermal_state, state = processor.process_single(
                    raw_temp=log.temperature,
                    state=state,
                    dt_minutes=dt_minutes
                )
                
                # Update Log
                # ...
                
                # --- BATCH DETECTION LOGIC ---
                
                # 1. DETECT START: OFF -> (HEAT or STEADY)
                if current_batch_start is None:
                    if thermal_state in ["HEAT", "STEADY"] and prev_thermal_state == "OFF":
                        current_batch_start = log.timestamp
                        current_batch_logs = [log]
                
                # 2. DETECT END: (HEAT/STEADY/COOL) -> OFF
                elif current_batch_start is not None:
                    current_batch_logs.append(log)
                    
                    if thermal_state == "OFF":
                        # BATCH ENDED
                        self._create_or_update_batch(machine, current_batch_start, log.timestamp, current_batch_logs)
                        count_batches += 1
                        current_batch_start = None
                        current_batch_logs = []
                
                prev_timestamp = log.timestamp
                
                # Flush batch updates periodically
                if len(updates) > 1000:
                    MachineMinuteLog.objects.bulk_update(
                        updates,
                        ['filtered_temp', 'gradient', 'thermal_state', 'ewma_temp', 'kalman_x', 'kalman_p']
                    )
                    updates = []

            # Save remaining
            if updates:
                MachineMinuteLog.objects.bulk_update(
                    updates,
                    ['filtered_temp', 'gradient', 'thermal_state', 'ewma_temp', 'kalman_x', 'kalman_p']
                )
                
            # If still in batch at the end (Open Batch)
            if current_batch_start is not None:
                 self._create_or_update_batch(machine, current_batch_start, None, current_batch_logs)
                 count_batches += 1
            
            # --- SYNC MACHINE STATUS & GRADIENT ---
            # Fetch the LATEST log to ensure we update the machine with current state
            latest_log = MachineMinuteLog.objects.filter(machine=machine).order_by('-timestamp').first()
            if latest_log:
                # Use centralized helpers
                from monitoring.utils.gradient_processor import (
                    is_invalid_temperature, get_machine_status
                )
                new_status = get_machine_status(
                    latest_log.thermal_state, 
                    is_invalid_temperature(latest_log.temperature)
                )
                
                machine.last_status = new_status
                machine.last_update = latest_log.timestamp
                
                # Sync Smoothed Gradient if available
                if latest_log.gradient is not None:
                    machine.temperature_gradient = latest_log.gradient
                    
                machine.save(update_fields=['last_status', 'last_update', 'temperature_gradient'])
                 
        self.message_user(request, f"Processed {count_logs} logs. Detected/Updated {count_batches} batches. Machines updated.", messages.SUCCESS)

    def _create_or_update_batch(self, machine, start_time, end_time, logs):
        """Helper to sync DyeingProcess"""
        from datetime import timedelta
        # Look for batch for this machine that starts within small window
        batch = DyeingProcess.objects.filter(
            machine=machine,
            start_time__range=(start_time - timedelta(minutes=5), start_time + timedelta(minutes=5))
        ).first()
        
        if not batch:
             # Create new
             last_batch = DyeingProcess.objects.filter(machine=machine).order_by('-batch_number').first()
             next_num = (last_batch.batch_number + 1) if last_batch else 1
             
             batch = DyeingProcess.objects.create(
                 machine=machine,
                 batch_number=next_num,
                 start_time=start_time,
                 end_time=end_time
             )
             
             # ── Re-link orphaned DyeingIdentity (anchor-based matching) ──────
             orphan_identity = DyeingIdentity.objects.filter(
                 machine=machine,
                 dyeing_process__isnull=True,
                 start_time_snapshot__range=(
                     start_time - timedelta(minutes=15),
                     start_time + timedelta(minutes=15),
                 )
             ).first()
             if orphan_identity:
                 orphan_identity.dyeing_process = batch
                 orphan_identity.save(update_fields=["dyeing_process"])
             # ─────────────────────────────────────────────────────────────────
        else:
            # Update existing
            batch.end_time = end_time
            # Keep original start_time
        
        if end_time:
            batch.is_complete = True
        else:
            batch.is_complete = False
            
        # Calc Stats
        heating_duration = 0.0
        heating_grad_sum = 0.0
        heating_count = 0
        max_temp = 0.0
        steady_duration = 0.0
        cooling_duration = 0.0
        cooling_grad_sum = 0.0
        cooling_count = 0
        
        prev_ts = None
        
        for log in logs:
            if prev_ts:
                dt = (log.timestamp - prev_ts).total_seconds() / 60.0
            else:
                dt = 1.0 
            dt = max(0.5, min(dt, 10.0))
            
            temp = log.temperature or 0
            if temp > max_temp: max_temp = temp
            
            state = log.thermal_state
            grad = log.gradient or 0
            
            if state == "HEAT":
                heating_duration += dt
                if grad > 0:
                    heating_grad_sum += grad
                    heating_count += 1
            elif state == "STEADY":
                steady_duration += dt
            elif state == "COOL":
                cooling_duration += dt
                if grad < 0:
                    cooling_grad_sum += grad
                    cooling_count += 1
            
            prev_ts = log.timestamp

        batch.max_temp = max_temp
        batch.heating_duration = heating_duration
        batch.steady_duration = steady_duration
        batch.cooling_duration = cooling_duration
        
        if heating_count > 0:
            batch.heating_avg_gradient = heating_grad_sum / heating_count
        else:
            batch.heating_avg_gradient = 0.0
        
        if cooling_count > 0:
            batch.cooling_avg_gradient = cooling_grad_sum / cooling_count
        else:
            batch.cooling_avg_gradient = 0.0
            
        batch.save()
            
    actions = [reprocess_logs]


class ProcessStatusFilter(admin.SimpleListFilter):
    title = 'status'
    parameter_name = 'status'

    def lookups(self, request, model_admin):
        return (
            ('in_progress', 'IN PROGRESS'),
            ('complete', 'COMPLETE'),
        )

    def queryset(self, request, queryset):
        if self.value() == 'in_progress':
            return queryset.filter(is_complete=False)
        if self.value() == 'complete':
            return queryset.filter(is_complete=True)
        return queryset


class ProcessValidFilter(admin.SimpleListFilter):
    title = 'Process?'
    parameter_name = 'is_valid_process'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes'),
            ('0', 'No'),
            ('all', 'All'),
        )

    def choices(self, changelist):
        value = self.value()
        for lookup, title in self.lookup_choices:
            selected = False
            if value is None and str(lookup) == '1':
                selected = True
            elif value == str(lookup):
                selected = True
                
            if str(lookup) == '1':
                query_string = changelist.get_query_string({self.parameter_name: '1'}, [])
            elif str(lookup) == '0':
                query_string = changelist.get_query_string({self.parameter_name: '0'}, [])
            else:
                query_string = changelist.get_query_string({self.parameter_name: 'all'}, [])
                
            yield {
                'selected': selected,
                'query_string': query_string,
                'display': title,
            }

    def queryset(self, request, queryset):
        val = self.value()
        if val == '1' or val is None:
            return queryset.filter(is_valid_process=True)
        if val == '0':
            return queryset.filter(is_valid_process=False)
        return queryset

from django_admin_listfilter_dropdown.filters import RelatedDropdownFilter, DropdownFilter

class ChainedMachineDropdownFilter(RelatedDropdownFilter):
    def field_choices(self, field, request, model_admin):
        group_id = request.GET.get('machine__group__id__exact')
        if not group_id:
            group_id = request.GET.get('machine__group__exact')
            
        limit_kwargs = {}
        if group_id:
            limit_kwargs['group_id'] = group_id
            
        return field.get_choices(include_blank=False, limit_choices_to=limit_kwargs)


@admin.register(DyeingProcess)
class DyeingProcessAdmin(admin.ModelAdmin):
    show_facets = admin.ShowFacets.NEVER
    list_display = (
        "machine", 
        "batch_number",
        "is_valid_process",
        "identity_status",
        "action_isi_identitas",
        "view_report_button",
        "status_display",
        "start_time_display",
        "real_heating_start_display",
        "steady_start_display",
        "cooling_start_display",
        "reached_70c_display",
        "end_time_display",
        "peak_temp",
        "avg_steam_temp_display",
        "avg_steam_pressure_display",
        "efficiency_display",
        "rise_time_display",
        "ideal_heating_time_display",
        "heating_lag_display",
        "time_efficiency_display",
        "steady_duration_display",
        "cooling_70_display",
        "duration_effective_display",
        "heating_gradient_dur_display",
        "heating_span_display",
        "nominal_power_display",
        "power_consumption_display",
        "total_duration_display"
    )
    

    list_filter = (
        ("machine__group", RelatedDropdownFilter),
        ("machine", ChainedMachineDropdownFilter),
        ProcessStatusFilter,
        ProcessValidFilter,
        ("start_time", admin.DateFieldListFilter),
    )
    

    
    @admin.action(description="❌ Tandai sebagai BUKAN Process (False)")
    def mark_bukan_process(self, request, queryset):
        updated = queryset.update(is_valid_process=False)
        self.message_user(request, f"{updated} data berhasil ditandai sebagai BUKAN Process.", messages.WARNING)

    @admin.action(description="✅ Tandai sebagai IS Process (True)")
    def mark_is_process(self, request, queryset):
        updated = queryset.update(is_valid_process=True)
        self.message_user(request, f"{updated} data berhasil ditandai sebagai IS Process.")

    search_fields = ("machine__code", "batch_number")
    date_hierarchy = "start_time"
    ordering = ("-start_time",)
    

    
    def action_isi_identitas(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        import urllib.parse
        
        try:
            from django.core.exceptions import ObjectDoesNotExist
            identity = getattr(obj, "identity", None)
            if identity:
                url = reverse('admin:monitoring_dyeingidentity_change', args=[identity.pk])
                return format_html('<a class="button" href="{}" style="background-color:#417690;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;">Edit ID</a>', url)
        except Exception:
            pass
            
        url = reverse('admin:monitoring_dyeingidentity_add')
        params = urllib.parse.urlencode({
            'dyeing_process': obj.id,
            'machine': obj.machine_id,
            'start_time_snapshot': obj.start_time.isoformat() if obj.start_time else "",
        })
        return format_html('<a class="button" href="{}?{}" style="background-color:#79aec8;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;">+ ID</a>', url, params)
    action_isi_identitas.short_description = "Form ID"

    def view_report_button(self, obj):
        from django.utils.html import format_html
        return format_html(
            '<a class="button" href="/history/report/{}?machine={}&batch={}" target="_blank" title="Lihat Grafik SCADA" style="background-color:#28a745;color:white;padding:4px 8px;border-radius:4px;font-size:16px;line-height:1;display:inline-block;">👁️</a>',
            obj.id, obj.machine.code, obj.batch_number
        )
    view_report_button.short_description = "Grafik"

    def identity_status(self, obj):
        """Shows ✅ if DyeingIdentity exists and has at least nomor_order filled."""
        try:
            identity = obj.identity
            if identity and identity.nomor_order:
                return format_html(
                    '<span style="color:green;font-size:16px" title="Identitas sudah diisi">✅</span>'
                )
            return format_html(
                '<span style="color:orange;font-size:16px" title="Identitas dibuat tapi belum lengkap">⚠️</span>'
            )
        except DyeingIdentity.DoesNotExist:
            return format_html(
                '<span style="color:red;font-size:16px" title="Belum ada identitas">❌</span>'
            )
    identity_status.short_description = "Identitas"
    
    def status_display(self, obj):
        if obj.is_complete:
            return format_html('<span style="color: green; font-weight: bold;">COMPLETE</span>')
        return format_html('<span style="color: orange; font-weight: bold;">IN PROGRESS</span>')
    status_display.short_description = "Status"
    
    def power_consumption_display(self, obj):
        if obj.power_consumption_kwh is not None:
            return f"{obj.power_consumption_kwh:.1f} kWh"
        return "-"
    power_consumption_display.short_description = "Konsumsi Daya"
    power_consumption_display.admin_order_field = "power_consumption_kwh"

    def nominal_power_display(self, obj):
        if obj.machine_nominal_power is not None:
            return f"{obj.machine_nominal_power:.1f} kW"
        return "-"
    nominal_power_display.short_description = "Daya Mesin"
    nominal_power_display.admin_order_field = "machine_nominal_power"

    def total_duration_display(self, obj):
        if obj.total_duration:
            hours = int(obj.total_duration // 60)
            mins = int(obj.total_duration % 60)
            return f"{hours}h {mins}m"
        return "-"
    total_duration_display.short_description = "Duration"
    
    def heating_stats(self, obj):
        if obj.heating_duration:
            return f"{obj.heating_duration:.0f}m ({obj.heating_avg_gradient:.2f}°C/m)"
        return "-"
    heating_stats.short_description = "Heating (Time/Grad)"

    def cooling_stats(self, obj):
        if obj.cooling_duration:
            return f"{obj.cooling_duration:.0f}m ({obj.cooling_avg_gradient:.2f}°C/m)"
        return "-"
    cooling_stats.short_description = "Cooling (Time/Grad)"
    
    def peak_temp(self, obj):
        if obj.max_temp:
            return f"{obj.max_temp:.1f}°C"
        return "-"
    peak_temp.short_description = "Peak"
    
    def avg_steam_temp_display(self, obj):
        if obj.avg_steam_temp:
            return f"{obj.avg_steam_temp:.1f}°C"
        return "-"
    avg_steam_temp_display.short_description = "Avg Tsteam"
    avg_steam_temp_display.admin_order_field = "avg_steam_temp"
    
    def avg_steam_pressure_display(self, obj):
        if obj.avg_steam_pressure:
            return f"{obj.avg_steam_pressure:.2f} Bar"
        return "-"
    avg_steam_pressure_display.short_description = "Avg Pressure"
    avg_steam_pressure_display.admin_order_field = "avg_steam_pressure"
    
    def efficiency_display(self, obj):
        if obj.avg_heating_efficiency:
            return f"{obj.avg_heating_efficiency:.5f}"
        return "-"
    efficiency_display.short_description = "Efficiency (K)"
    
    def rise_time_display(self, obj):
        if obj.real_heating_duration:
            return f"{obj.real_heating_duration:.1f}m"
        return "-"
    rise_time_display.short_description = "Rise Time"
    
    def ideal_heating_time_display(self, obj):
        if obj.ideal_heating_time:
            return f"{obj.ideal_heating_time:.1f}m"
        return "-"
    ideal_heating_time_display.short_description = "Ideal Time"
    ideal_heating_time_display.admin_order_field = "ideal_heating_time"
    
    def heating_lag_display(self, obj):
        if obj.heating_lag_time is not None:
            # Color code: positive lag (slower than ideal) = red, negative = green
            if obj.heating_lag_time > 0:
                return f"+{obj.heating_lag_time:.1f}m"
            else:
                return f"{obj.heating_lag_time:.1f}m"
        return "-"
    heating_lag_display.short_description = "Lag"
    heating_lag_display.admin_order_field = "heating_lag_time"
    
    def time_efficiency_display(self, obj):
        if obj.ideal_heating_time and obj.real_heating_duration and obj.ideal_heating_time > 0:
            # Efficiency = (Ideal / Real) * 100
            eff = (obj.ideal_heating_time / obj.real_heating_duration) * 100
            return f"{eff:.1f}%"
        return "-"
    time_efficiency_display.short_description = "Time Eff %"
    
    def start_time_display(self, obj):
        if obj.start_time:
            return timezone.localtime(obj.start_time).strftime("%Y-%m-%d %H:%M")
        return "-"
    start_time_display.short_description = "Start Time"
    start_time_display.admin_order_field = "start_time"
    
    def real_heating_start_display(self, obj):
        if obj.heating_start_time:
            return timezone.localtime(obj.heating_start_time).strftime("%Y-%m-%d %H:%M")
        return "-"
    real_heating_start_display.short_description = "Heat Start"
    real_heating_start_display.admin_order_field = "heating_start_time"
    
    def steady_start_display(self, obj):
        if obj.steady_start_time:
            return timezone.localtime(obj.steady_start_time).strftime("%Y-%m-%d %H:%M")
        return "-"
    steady_start_display.short_description = "Steady Start"
    steady_start_display.admin_order_field = "steady_start_time"
    
    def cooling_start_display(self, obj):
        if obj.cooling_start_time:
            return timezone.localtime(obj.cooling_start_time).strftime("%Y-%m-%d %H:%M")
        return "-"
    cooling_start_display.short_description = "Cool Start"
    cooling_start_display.admin_order_field = "cooling_start_time"
    
    def reached_70c_display(self, obj):
        if obj.reached_70c_time:
            return timezone.localtime(obj.reached_70c_time).strftime("%Y-%m-%d %H:%M")
        return "-"
    reached_70c_display.short_description = "Reached 70°C"
    reached_70c_display.admin_order_field = "reached_70c_time"
    
    def end_time_display(self, obj):
        if obj.end_time:
            return timezone.localtime(obj.end_time).strftime("%Y-%m-%d %H:%M")
        return "-"
    end_time_display.short_description = "End Time"
    end_time_display.admin_order_field = "end_time"
    
    def steady_duration_display(self, obj):
        if obj.steady_duration:
            return f"{obj.steady_duration}m"
        return "-"
    steady_duration_display.short_description = "Steady (min)"
    
    def cooling_70_display(self, obj):
        if obj.cooling_duration:
            return f"{obj.cooling_duration:.1f}m"
        return "-"
    cooling_70_display.short_description = "Cool to 70°C"
    
    def duration_effective_display(self, obj):
        if obj.duration_effective:
            return f"{obj.duration_effective:.1f}m"
        return "-"
    duration_effective_display.short_description = "Dur. Effective"
    
    def heating_gradient_dur_display(self, obj):
        if obj.heating_gradient_duration:
            return f"{obj.heating_gradient_duration}m"
        return "-"
    heating_gradient_dur_display.short_description = "Heat Grad>0.1"
    
    def heating_span_display(self, obj):
        if obj.heating_span:
            return f"{obj.heating_span:.1f}m"
        return "-"
    heating_span_display.short_description = "Heat Span"
    
    # Detailed fieldsets for batch view
    fieldsets = (
        ("Basic Information", {
            "fields": ("machine", "batch_number", "is_complete")
        }),
        ("Timing Events", {
            "fields": (
                "start_time", "end_time",
                "heating_start_time", "steady_start_time", 
                "cooling_start_time", "reached_70c_time"
            )
        }),
        ("Temperature Metrics", {
            "fields": ("start_temp", "max_temp", "end_temp")
        }),
        ("Phase Durations", {
            "fields": (
                "heating_duration", "heating_avg_gradient",
                "steady_duration",
                "cooling_duration", "cooling_avg_gradient"
            )
        }),
        ("Efficiency Metrics", {
            "fields": (
                "avg_heating_efficiency",
                "real_heating_duration",
                "duration_effective",
                "heating_gradient_duration",
                "heating_span"
            ),
            "description": "Advanced efficiency and performance metrics"
        }),
        ("Energy Consumption", {
            "fields": (
                "machine_nominal_power",
                "power_consumption_kwh",
            ),
            "description": (
                "Konsumsi daya (kWh) = durasi dari heating_start → end_time × daya mesin (kW). "
                "Nilai machine_nominal_power adalah snapshot pada saat batch diproses."
            )
        }),
        ("Summary (Calculated)", {
            "fields": ("total_duration_calc",),
            "description": "Auto-calculated fields for quick reference"
        }),
    )
    
    # Add calculated field for total duration
    def total_duration_calc(self, obj):
        if obj.total_duration:
            return f"{obj.total_duration:.1f} minutes ({obj.total_duration/60:.2f} hours)"
        return "-"
    total_duration_calc.short_description = "Total Duration"
    
    
    readonly_fields = (
        "machine", "batch_number", "start_time", "end_time",
        "heating_start_time", "steady_start_time", "cooling_start_time", "reached_70c_time",
        "start_temp", "max_temp", "end_temp",
        "heating_duration", "heating_avg_gradient", "steady_duration",
        "cooling_duration", "cooling_avg_gradient",
        "avg_heating_efficiency", "real_heating_duration", "duration_effective",
        "heating_gradient_duration", "heating_span", "is_complete",
        "machine_nominal_power",
        "power_consumption_kwh",
        "total_duration_calc"  # Add calculated field
    )

    def save_formset(self, request, form, formset, change):
        """
        Override to auto-populate anchor fields on DyeingIdentity when saved via inline.
        """
        instances = formset.save(commit=False)
        for instance in instances:
            if isinstance(instance, DyeingIdentity):
                # Auto-populate anchor fields from the parent DyeingProcess
                dp = instance.dyeing_process or form.instance
                if dp and dp.pk:
                    instance.dyeing_process = dp
                    instance.machine = dp.machine
                    instance.start_time_snapshot = dp.start_time
                instance.save()
        formset.save_m2m()

    @admin.action(description='Recalculate Thermal Analysis')
    def recalculate_analysis(self, request, queryset):
        """
        Recalculate gradient, thermal_state, and batch statistics 
        for selected DyeingProcess records.
        """
        count = 0
        config = ProcessingConfig()
        
        for process in queryset:
            try:
                # 1. Get logs for this process (Time window)
                start_dt = process.start_time
                end_dt = process.end_time or timezone.now()
                
                logs = MachineMinuteLog.objects.filter(
                    machine=process.machine,
                    timestamp__range=(start_dt, end_dt)
                ).order_by('timestamp')
                
                if not logs.exists():
                    continue
                
                # 2. Initialize fresh processor state
                # We do not carry over state from previous batches here for safety,
                # assuming the batch starts from a relatively clean state or 
                # acceptable convergence period.
                processor = GradientProcessor(config)
                # Initialize state with first log values if possible
                from monitoring.utils.gradient_processor import FilterState
                state = FilterState()
                
                # 3. Reprocess every log
                prev_timestamp = None
                
                # Stats accumulators (for DyeingProcess model update)
                heating_duration = 0.0
                heating_grad_sum = 0.0
                heating_count = 0
                max_temp = 0.0
                
                cooling_duration = 0.0
                cooling_grad_sum = 0.0
                cooling_count = 0
                
                steady_duration = 0.0
                
                updates = []
                
                for log in logs:
                    # Calculate dt
                    if prev_timestamp:
                        dt_minutes = (log.timestamp - prev_timestamp).total_seconds() / 60.0
                    else:
                        dt_minutes = 1.0 # default
                    
                    dt_minutes = max(0.5, min(dt_minutes, 10.0))
                    
                    # Process
                    filtered, gradient, thermal_state, state = processor.process_single(
                        raw_temp=log.temperature,
                        state=state,
                        dt_minutes=dt_minutes
                    )
                    
                    # Update Log Object (in memory)
                    log.filtered_temp = filtered
                    log.gradient = gradient
                    log.thermal_state = thermal_state
                    
                    # Save filter states so future debug is possible
                    log.ewma_temp = state.ewma_temp
                    log.kalman_x = state.kalman_x
                    log.kalman_p = state.kalman_p
                    
                    updates.append(log)
                    prev_timestamp = log.timestamp
                    
                    # --- Aggregate Stats for Process ---
                    if log.temperature and log.temperature > max_temp:
                        max_temp = log.temperature
                    
                    if thermal_state == "HEAT":
                        heating_duration += dt_minutes
                        if gradient > 0:
                            heating_grad_sum += gradient
                            heating_count += 1
                    elif thermal_state == "COOL":
                        cooling_duration += dt_minutes
                        if gradient < 0:
                            cooling_grad_sum += gradient
                            cooling_count += 1
                    elif thermal_state == "STEADY":
                        steady_duration += dt_minutes

                # 4. Bulk Update Logs
                MachineMinuteLog.objects.bulk_update(
                    updates, 
                    ['filtered_temp', 'gradient', 'thermal_state', 'ewma_temp', 'kalman_x', 'kalman_p']
                )
                
                # 5. Update Process Record
                process.max_temp = max_temp
                process.heating_duration = heating_duration
                process.steady_duration = steady_duration
                process.cooling_duration = cooling_duration
                
                if heating_count > 0:
                    process.heating_avg_gradient = heating_grad_sum / heating_count
                else:
                    process.heating_avg_gradient = 0.0
                    
                if cooling_count > 0:
                    process.cooling_avg_gradient = cooling_grad_sum / cooling_count
                else:
                    process.cooling_avg_gradient = 0.0
                
                process.save()
                count += 1
                
            except Exception as e:
                self.message_user(
                    request, 
                    f"Error processing batch {process.batch_number}: {str(e)}", 
                    level=messages.ERROR
                )
        
        self.message_user(
            request, 
            f"Successfully recalculated analysis for {count} processes.", 
            level=messages.SUCCESS
        )

    actions = [recalculate_analysis, "mark_bukan_process", "mark_is_process"]


@admin.register(RawDataFile)
class RawDataFileAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "file", 
        "uploaded_at", 
        "processed"
    )
    list_filter = ("processed", "file_format", "uploaded_at")
    readonly_fields = (
        "uploaded_at", 
        "preview_data", 
        "file_format", 
        "row_count", 
        "machine_count", 
        "date_range",
        "log_message"
    )
    
    fieldsets = (
        ("File Information", {
            "fields": ("file", "uploaded_at", "file_format")
        }),
        ("Preview Metadata", {
            "fields": ("row_count", "machine_count", "date_range"),
            "classes": ("collapse",)
        }),
        ("Processing Status", {
            "fields": ("processed", "log_message")
        }),
    )
    
    def file_name_display(self, obj):
        """Display file name"""
        import os
        return os.path.basename(obj.file.name)
    file_name_display.short_description = "File"
    
    def processed_status(self, obj):
        """Display processed status"""
        return "PROCESSED" if obj.processed else "PENDING"
    processed_status.short_description = "Status"
    
    def get_urls(self):
        """Add custom URL for preview page"""
        from django.urls import path
        urls = super().get_urls()
        custom_urls = [
            path(
                '<int:file_id>/preview/',
                self.admin_site.admin_view(self.preview_view),
                name='monitoring_rawdatafile_preview'
            ),
            path(
                '<int:file_id>/confirm-import/',
                self.admin_site.admin_view(self.confirm_import_view),
                name='monitoring_rawdatafile_confirm_import'
            ),
        ]
        # Return custom URLs + default URLs (order matters!)
        return custom_urls + urls
    
    def preview_view(self, request, file_id):
        """Display preview of file data"""
        from django.shortcuts import render, get_object_or_404
        from monitoring.utils.file_parser import FileParser
        
        raw_file = get_object_or_404(RawDataFile, pk=file_id)
        
        # Check if preview already exists
        if raw_file.preview_data and raw_file.preview_data.get('rows'):
            parsed = raw_file.preview_data
        else:
            # Parse file
            raw_file.file.open('rb')
            parsed_obj = FileParser.parse_file(raw_file.file, raw_file.file.name)
            raw_file.file.close()
            
            parsed = parsed_obj.to_dict()
            
            # Save preview data
            raw_file.preview_data = parsed
            raw_file.file_format = parsed['format_type']
            raw_file.row_count = parsed['row_count']
            raw_file.machine_count = len(parsed['machine_codes'])
            
            if parsed['date_range'][0] and parsed['date_range'][1]:
                from datetime import datetime
                start = datetime.fromisoformat(parsed['date_range'][0])
                end = datetime.fromisoformat(parsed['date_range'][1])
                raw_file.date_range = f"{start.strftime('%d/%m/%Y')} to {end.strftime('%d/%m/%Y')}"
            
            raw_file.save(update_fields=['preview_data', 'file_format', 'row_count', 'machine_count', 'date_range'])
        
        # Pagination
        page_size = 50
        page_number = int(request.GET.get('page', 1))
        total_rows = len(parsed.get('rows', []))
        total_pages = (total_rows + page_size - 1) // page_size if total_rows > 0 else 1
        
        # Clamp page number
        page_number = max(1, min(page_number, total_pages))
        
        start_idx = (page_number - 1) * page_size
        end_idx = min(start_idx + page_size, total_rows)
        
        preview_rows = parsed.get('rows', [])[start_idx:end_idx]
        
        context = {
            'file_id': file_id,
            'file_name': raw_file.file.name,
            'format_type': parsed.get('format_type', 'UNKNOWN'),
            'total_rows': parsed.get('row_count', 0),
            'machine_count': len(parsed.get('machine_codes', [])),
            'machine_codes': parsed.get('machine_codes', []),
            'date_range': raw_file.date_range,
            'warnings': parsed.get('warnings', []),
            'errors': parsed.get('errors', []),
            'preview_rows': preview_rows,
            'page_number': page_number,
            'total_pages': total_pages,
            'page_start': start_idx + 1,
            'page_end': end_idx,
        }
        
        return render(request, 'admin/raw_data_preview.html', context)
    
    def confirm_import_view(self, request, file_id):
        """Import the previewed data"""
        from django.shortcuts import redirect, get_object_or_404
        from django.contrib import messages as admin_messages
        from monitoring.models import Machine, MachineMinuteLog
        from monitoring.utils.file_parser import FileParser
        from django.utils import timezone
        from datetime import datetime
        
        raw_file = get_object_or_404(RawDataFile, pk=file_id)
        
        if raw_file.processed:
            admin_messages.warning(request, "This file has already been processed.")
            return redirect('admin:monitoring_rawdatafile_changelist')
        
        # IMPORTANT: Re-parse file to get ALL data (not limited to 100 preview rows)
        try:
            raw_file.file.open('rb')
            parsed_obj = FileParser.parse_file(raw_file.file, raw_file.file.name)
            raw_file.file.close()
        except Exception as e:
            admin_messages.error(request, f"Failed to read file: {str(e)}")
            return redirect('admin:monitoring_rawdatafile_changelist')
        
        # Check for errors
        if parsed_obj.errors:
            admin_messages.error(
                request, 
                f"Cannot import file with errors. Please fix the file and re-upload. Errors: {', '.join(parsed_obj.errors[:5])}"
            )
            return redirect('admin:monitoring_rawdatafile_changelist')
        
        # Process data
        log_output = []
        inserted_count = 0
        updated_count = 0
        skipped_count = 0
        error_count = 0
        
        force_overwrite = request.POST.get('force_overwrite') == '1'
        
        try:
            format_type = parsed_obj.format_type
            rows = parsed_obj.rows  # ALL rows, not limited
            
            # OPTIMIZATION: Collect all records to import first, then do bulk operations
            records_to_create = []
            records_to_update = []
            
            if format_type == "WIDE":
                # Process wide format
                machine_codes = parsed_obj.machine_codes
                
                # Fetch machines ONCE
                machines_dict = {}
                for code in machine_codes:
                    try:
                        machines_dict[code] = Machine.objects.get(code=code)
                    except Machine.DoesNotExist:
                        log_output.append(f"Machine '{code}' not found in database - skipped")
                
                # Collect all timestamp-machine combinations
                all_combinations = []
                for row in rows:
                    try:
                        timestamp_str = row.get('timestamp')
                        timestamp = datetime.fromisoformat(timestamp_str)
                        timestamp = timezone.make_aware(timestamp) if timezone.is_naive(timestamp) else timestamp
                        
                        machines_data = row.get('machines', {})
                        
                        for machine_code, temp_value in machines_data.items():
                            if machine_code not in machines_dict:
                                continue
                            
                            machine = machines_dict[machine_code]
                            all_combinations.append({
                                'machine': machine,
                                'machine_id': machine.id,
                                'timestamp': timestamp,
                                'temperature': temp_value,
                                'row_number': row.get('row_number')
                            })
                    except Exception as e:
                        error_count += 1
                        log_output.append(f"Row {row.get('row_number', '?')}: {str(e)}")
                
                # BULK collision detection: Query all existing records at once
                timestamps_to_check = list(set(c['timestamp'] for c in all_combinations))
                machine_ids_to_check = list(set(c['machine_id'] for c in all_combinations))
                
                existing_logs = MachineMinuteLog.objects.filter(
                    timestamp__in=timestamps_to_check,
                    machine_id__in=machine_ids_to_check
                ).select_related('machine')
                
                # Create lookup dict for fast collision detection
                existing_lookup = {
                    (log.machine_id, log.timestamp): log
                    for log in existing_logs
                }
                
                # Categorize: create vs update vs skip
                for combo in all_combinations:
                    key = (combo['machine_id'], combo['timestamp'])
                    existing = existing_lookup.get(key)
                    
                    if existing:
                        # Check if existing is valid
                        is_valid = (existing.temperature is not None and existing.temperature > 0)
                        
                        if is_valid and not force_overwrite:
                            skipped_count += 1
                        else:
                            # Mark for update
                            existing.temperature = combo['temperature']
                            records_to_update.append(existing)
                            updated_count += 1
                    else:
                        # Mark for creation; terapkan kalibrasi sebelum bulk_create
                        raw_temp = combo['temperature']
                        cal_temp = get_calibrated_temperature(combo['machine_id'], raw_temp)
                        records_to_create.append(MachineMinuteLog(
                            machine_id=combo['machine_id'],
                            timestamp=combo['timestamp'],
                            raw_temperature=raw_temp,
                            temperature=cal_temp,
                        ))
                        inserted_count += 1
            
            elif format_type == "LONG":
                # Process long format (similar optimization)
                all_records = []
                for row in rows:
                    try:
                        timestamp_str = row.get('timestamp')
                        timestamp = datetime.fromisoformat(timestamp_str)
                        timestamp = timezone.make_aware(timestamp) if timezone.is_naive(timestamp) else timestamp
                        
                        temp_value = row.get('temperature')
                        machine_code = row.get('machine_code')
                        
                        try:
                            machine = Machine.objects.get(code=machine_code)
                            all_records.append({
                                'machine': machine,
                                'machine_id': machine.id,
                                'timestamp': timestamp,
                                'temperature': temp_value,
                                'row_number': row.get('row_number')
                            })
                        except Machine.DoesNotExist:
                            skipped_count += 1
                    except Exception as e:
                        error_count += 1
                        log_output.append(f"Row {row.get('row_number', '?')}: {str(e)}")
                
                # Bulk collision detection
                timestamps_to_check = list(set(r['timestamp'] for r in all_records))
                machine_ids_to_check = list(set(r['machine_id'] for r in all_records))
                
                existing_logs = MachineMinuteLog.objects.filter(
                    timestamp__in=timestamps_to_check,
                    machine_id__in=machine_ids_to_check
                ).select_related('machine')
                
                existing_lookup = {
                    (log.machine_id, log.timestamp): log
                    for log in existing_logs
                }
                
                for record in all_records:
                    key = (record['machine_id'], record['timestamp'])
                    existing = existing_lookup.get(key)
                    
                    if existing:
                        is_valid = (existing.temperature is not None and existing.temperature > 0)
                        
                        if is_valid and not force_overwrite:
                            skipped_count += 1
                        else:
                            existing.temperature = record['temperature']
                            records_to_update.append(existing)
                            updated_count += 1
                    else:
                        # Terapkan kalibrasi sebelum bulk_create (Long Format)
                        raw_temp = record['temperature']
                        cal_temp = get_calibrated_temperature(record['machine_id'], raw_temp)
                        records_to_create.append(MachineMinuteLog(
                            machine_id=record['machine_id'],
                            timestamp=record['timestamp'],
                            raw_temperature=raw_temp,
                            temperature=cal_temp,
                        ))
                        inserted_count += 1
            
            # BULK OPERATIONS: Insert/Update in batches
            batch_size = 1000
            
            # Bulk create new records
            if records_to_create:
                for i in range(0, len(records_to_create), batch_size):
                    batch = records_to_create[i:i+batch_size]
                    MachineMinuteLog.objects.bulk_create(batch, ignore_conflicts=True)
            
            # Bulk update existing records
            if records_to_update:
                for i in range(0, len(records_to_update), batch_size):
                    batch = records_to_update[i:i+batch_size]
                    MachineMinuteLog.objects.bulk_update(batch, ['temperature'])
            
            # Mark as processed
            raw_file.processed = True
            raw_file.log_message = (
                f"Import completed successfully.\n"
                f"Inserted: {inserted_count}\n"
                f"Updated: {updated_count}\n"
                f"Skipped (valid data exists): {skipped_count}\n"
                f"Errors: {error_count}\n\n"
                f"Error Details:\n" + "\n".join(log_output[:50])
            )
            raw_file.save(update_fields=['processed', 'log_message'])
            
            admin_messages.success(
                request,
                f"Import completed! Inserted: {inserted_count}, Updated: {updated_count}, Skipped: {skipped_count}, Errors: {error_count}"
            )
            
        except Exception as e:
            raw_file.log_message = f"FATAL ERROR: {str(e)}"
            raw_file.save(update_fields=['log_message'])
            admin_messages.error(request, f"Import failed: {str(e)}")
        
        return redirect('admin:monitoring_rawdatafile_changelist')
    
    @admin.action(description='🔄 Mark as Unprocessed (Allow Re-import)')
    def mark_as_unprocessed(self, request, queryset):
        """Mark selected files as unprocessed to allow re-import"""
        count = queryset.filter(processed=True).update(processed=False)
        
        if count > 0:
            self.message_user(
                request, 
                f"Marked {count} file(s) as unprocessed. You can now preview and re-import them.",
                messages.SUCCESS
            )
        else:
            self.message_user(
                request,
                "No processed files were selected.",
                messages.WARNING
            )
    
    @admin.action(description='📋 Preview File Data')
    def preview_file_action(self, request, queryset):
        """Action to preview selected file"""
        if queryset.count() != 1:
            self.message_user(request, "Please select exactly one file to preview.", messages.WARNING)
            return
        
        raw_file = queryset.first()
        from django.shortcuts import redirect
        return redirect('admin:monitoring_rawdatafile_preview', file_id=raw_file.pk)
    
    actions = ['mark_as_unprocessed', 'preview_file_action']



@admin.register(MachineStatusSnapshot)
class MachineStatusSnapshotAdmin(admin.ModelAdmin):
    show_facets = admin.ShowFacets.NEVER
    """Custom admin for status snapshot with pivot table view."""
    change_list_template = "admin/machine_status_snapshot_changelist.html"
    
    list_display = ('timestamp', 'machine_count')
    date_hierarchy = 'timestamp'
    ordering = ('-timestamp',)
    
    def machine_count(self, obj):
        return len(obj.snapshot_data)
    machine_count.short_description = "Machines"
    
    # admin.py

    def changelist_view(self, request, extra_context=None):
        from datetime import timedelta
        from django.utils import timezone
        
        # 1. Parse Parameters (from original request)
        # Ambil semua mesin aktif
        all_machines = Machine.objects.filter(is_active=True).order_by('code')
        all_machine_codes = [m.code for m in all_machines]
        
        filter_applied = request.GET.get('filter_applied')
        selected_codes = request.GET.getlist('machines')
        hours_param = request.GET.get('hours', '24')
        
        # 2. Logic Filter
        if filter_applied:
            # Gunakan selection user (meskipun kosong)
            pass 
        else:
            # Default awal: Select All
            selected_codes = all_machine_codes

        # 3. Query Data
        try:
            hours = int(hours_param)
        except ValueError:
            hours = 24
            
        since = timezone.now() - timedelta(hours=hours)
        
        snapshots = self.get_queryset(request).filter(
            timestamp__gte=since
        )[:1000]
        
        # Pre-fetch Machine objects for calculations
        machines_dict = {m.code: m for m in Machine.objects.filter(code__in=selected_codes)}
        
        # Initialize grand totals
        grand_steam_total = 0.0
        grand_hto_total = 0.0
        
        # Initialize per-machine totals (how many times each machine was active)
        machine_totals = {code: 0 for code in selected_codes}
        
        # 4. Pivot Logic with Steam and HTO calculations
        pivot_rows = []
        for snap in snapshots:
            row = {'timestamp': snap.timestamp, 'cells': []}
            row_steam_total = 0.0
            row_hto_total = 0.0
            
            for idx, code in enumerate(selected_codes):
                data = snap.snapshot_data.get(code, {})
                cell = {
                    'status': data.get('status', '-'),
                    'detail': data.get('detail', '-'),
                    'mode': data.get('mode', '-')
                }
                row['cells'].append(cell)
                
                # Calculate steam and HTO usage
                if code in machines_dict:
                    machine = machines_dict[code]
                    
                    # Check if machine is actively consuming resources
                    is_active = False
                    if machine.operation_mode == "MANUAL":
                        is_active = (cell['status'] == 'Running')
                    else:  # AUTO
                        is_active = (cell['detail'] == 'HEAT')
                    
                    if is_active:
                        # Increment machine count
                        machine_totals[code] += 1
                        
                        # Calculate per minute (assuming snapshot is 1 minute)
                        steam_per_min = machine.average_steam_usage
                        hto_per_min = machine.avg_hto_calories
                        
                        row_steam_total += steam_per_min
                        row_hto_total += hto_per_min
            
            row['steam_total'] = row_steam_total
            row['hto_total'] = row_hto_total
            
            grand_steam_total += row_steam_total
            grand_hto_total += row_hto_total
            
            pivot_rows.append(row)
            
        # 5. PREVENT DJANGO REDIRECT / GLITCH
        # Django admin change_list akan memvalidasi request.GET.
        # Jika ada parameter yang tidak dikenal (seperti 'machines', 'hours', 'filter_applied'),
        # Django akan menganggapnya salah dan me-redirect ke halaman bersih (reset).
        # Solusinya: Kita copot parameter custom ini dari request.GET sebelum memanggil super().
        
        # Kita copy request.GET agar bisa dimodifikasi
        request.GET = request.GET.copy()
        
        # Hapus parameter custom kita agar super() tidak bingung
        if 'machines' in request.GET: del request.GET['machines']
        if 'filter_applied' in request.GET: del request.GET['filter_applied']
        if 'hours' in request.GET: del request.GET['hours']
        
        # Calculate colspan for footer (each machine has 2 cols + 1 timestamp col)
        total_colspan = len(selected_codes) * 2 + 1
        
        # Create list of (code, count) tuples for template iteration
        machine_data = [(code, machine_totals.get(code, 0)) for code in selected_codes]
        
        extra_context = extra_context or {}
        extra_context.update({
            'all_machines': all_machines,
            'selected_machines': selected_codes, # List kode mesin yang terpilih
            'pivot_rows': pivot_rows,
            'hours': hours,
            'grand_steam_total': grand_steam_total,
            'grand_hto_total': grand_hto_total,
            'total_colspan': total_colspan,
            'machine_data': machine_data,  # List of (code, count) tuples
        })
        
        return super().changelist_view(request, extra_context)
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


class PerformanceDateFilter(admin.SimpleListFilter):
    """Custom filter untuk menampilkan pilihan bulan berdasarkan data DyeingProcess"""
    title = 'Date'
    parameter_name = 'month'
    
    def lookups(self, request, model_admin):
        from django.db.models.functions import TruncMonth
        from django.db.models import Min, Max
        
        # Get all unique months from DyeingProcess
        months = DyeingProcess.objects.annotate(
            month=TruncMonth('start_time')
        ).values('month').distinct().order_by('-month')
        
        choices = [('all', 'All dates')]
        
        for item in months:
            if item['month']:
                month_date = item['month']
                # Format: "November 2025", "December 2025"
                month_str = month_date.strftime('%B %Y')
                # Value: "2025-11" for filtering
                month_value = month_date.strftime('%Y-%m')
                choices.append((month_value, month_str))
        
        return choices
    
    def queryset(self, request, queryset):
        from datetime import datetime
        from django.utils import timezone
        
        if self.value() == 'all' or self.value() is None:
            return queryset
        
        try:
            # Parse "2025-11" format
            year, month = self.value().split('-')
            year = int(year)
            month = int(month)
            
            # Get first day of selected month
            start_date = timezone.make_aware(datetime(year, month, 1))
            
            # Get first day of next month
            if month == 12:
                end_date = timezone.make_aware(datetime(year + 1, 1, 1))
            else:
                end_date = timezone.make_aware(datetime(year, month + 1, 1))
            
            if queryset.model.__name__ in ('MachinePerformanceSummary', 'Machine'):
                # Filter machines that have dyeing_processes in this month
                machine_ids = DyeingProcess.objects.filter(
                    start_time__gte=start_date,
                    start_time__lt=end_date
                ).values_list('machine_id', flat=True).distinct()
                return queryset.filter(id__in=machine_ids)
            elif queryset.model.__name__ in ('DyeingExecutiveSummary', 'DyeingAnalytics', 'DyeingIdentity'):
                return queryset.filter(dyeing_process__start_time__gte=start_date, dyeing_process__start_time__lt=end_date)
            return queryset
        except (ValueError, AttributeError):
            return queryset


@admin.register(MachinePerformanceSummary)
class MachinePerformanceSummaryAdmin(admin.ModelAdmin):
    """
    Admin untuk menampilkan summary performa mesin dari DyeingProcess.
    Setiap baris = 1 mesin dengan average dari semua field DyeingProcess.
    """
    list_display = (
        'machine_code',
        'machine_name',
        'total_batches',
        'avg_heating_duration',
        'avg_heating_avg_gradient',
        'avg_steady_duration',
        'avg_cooling_duration',
        'avg_cooling_avg_gradient',
        'avg_start_temp',
        'avg_end_temp',
        'avg_max_temp',
        'avg_heating_efficiency',
        'avg_real_heating_duration',
        'avg_duration_effective',
        'avg_heating_gradient_duration',
        'avg_heating_span',
        'avg_ideal_heating_time',
        'avg_heating_lag_time',
        'avg_avg_steam_temp',
        'avg_avg_steam_pressure',
    )
    
    list_filter = ('group', 'is_active', PerformanceDateFilter)
    search_fields = ('code', 'name')
    ordering = ('code',)
    
    def get_queryset(self, request):
        """
        Override queryset untuk annotate dengan aggregated values agar bisa di-sort.
        """
        from django.db.models import Avg, Count, Q
        from datetime import datetime
        from django.utils import timezone
        
        qs = super().get_queryset(request)
        
        # Determine date filter (month parameter)
        month_param = request.GET.get('month', 'all')
        
        # Parse month filter
        if month_param and month_param != 'all':
            try:
                # Parse "2025-11" format
                year, month = month_param.split('-')
                year = int(year)
                month = int(month)
                
                # Get first day of selected month
                start_date = timezone.make_aware(datetime(year, month, 1))
                
                # Get first day of next month
                if month == 12:
                    end_date = timezone.make_aware(datetime(year + 1, 1, 1))
                else:
                    end_date = timezone.make_aware(datetime(year, month + 1, 1))
                
                dyeing_filter = Q(
                    dyeing_processes__start_time__gte=start_date,
                    dyeing_processes__start_time__lt=end_date
                )
            except (ValueError, AttributeError):
                # If parsing fails, show all
                dyeing_filter = Q(dyeing_processes__isnull=False)
        else:
            # All dates
            dyeing_filter = Q(dyeing_processes__isnull=False)
        
        # Annotate dengan semua aggregated values
        qs = qs.filter(dyeing_filter).annotate(
            total_batch_count=Count('dyeing_processes', distinct=True),
            annotated_heating_duration=Avg('dyeing_processes__heating_duration'),
            annotated_heating_avg_gradient=Avg('dyeing_processes__heating_avg_gradient'),
            annotated_steady_duration=Avg('dyeing_processes__steady_duration'),
            annotated_cooling_duration=Avg('dyeing_processes__cooling_duration'),
            annotated_cooling_avg_gradient=Avg('dyeing_processes__cooling_avg_gradient'),
            annotated_start_temp=Avg('dyeing_processes__start_temp'),
            annotated_end_temp=Avg('dyeing_processes__end_temp'),
            annotated_max_temp=Avg('dyeing_processes__max_temp'),
            annotated_avg_heating_efficiency=Avg('dyeing_processes__avg_heating_efficiency'),
            annotated_real_heating_duration=Avg('dyeing_processes__real_heating_duration'),
            annotated_duration_effective=Avg('dyeing_processes__duration_effective'),
            annotated_heating_gradient_duration=Avg('dyeing_processes__heating_gradient_duration'),
            annotated_heating_span=Avg('dyeing_processes__heating_span'),
            annotated_ideal_heating_time=Avg('dyeing_processes__ideal_heating_time'),
            annotated_heating_lag_time=Avg('dyeing_processes__heating_lag_time'),
            annotated_avg_steam_temp=Avg('dyeing_processes__avg_steam_temp'),
            annotated_avg_steam_pressure=Avg('dyeing_processes__avg_steam_pressure'),
        ).distinct()
        
        return qs
    
    # Display methods with admin_order_field for sorting
    def machine_code(self, obj):
        return obj.code
    machine_code.short_description = 'Machine Code'
    machine_code.admin_order_field = 'code'
    
    def machine_name(self, obj):
        return obj.name
    machine_name.short_description = 'Machine Name'
    machine_name.admin_order_field = 'name'
    
    def total_batches(self, obj):
        """Total batch dari mesin ini"""
        return obj.total_batch_count if hasattr(obj, 'total_batch_count') else obj.dyeing_processes.count()
    total_batches.short_description = 'Total Batches'
    total_batches.admin_order_field = 'total_batch_count'
    
    def avg_heating_duration(self, obj):
        """Average heating duration"""
        avg = obj.annotated_heating_duration if hasattr(obj, 'annotated_heating_duration') else None
        return f"{avg:.1f} min" if avg else "-"
    avg_heating_duration.short_description = 'Avg Heating Duration'
    avg_heating_duration.admin_order_field = 'annotated_heating_duration'
    
    def avg_heating_avg_gradient(self, obj):
        """Average heating gradient"""
        avg = obj.annotated_heating_avg_gradient if hasattr(obj, 'annotated_heating_avg_gradient') else None
        return f"{avg:.3f} °C/min" if avg else "-"
    avg_heating_avg_gradient.short_description = 'Avg Heating Gradient'
    avg_heating_avg_gradient.admin_order_field = 'annotated_heating_avg_gradient'
    
    def avg_steady_duration(self, obj):
        """Average steady duration"""
        avg = obj.annotated_steady_duration if hasattr(obj, 'annotated_steady_duration') else None
        return f"{avg:.1f} min" if avg else "-"
    avg_steady_duration.short_description = 'Avg Steady Duration'
    avg_steady_duration.admin_order_field = 'annotated_steady_duration'
    
    def avg_cooling_duration(self, obj):
        """Average cooling duration"""
        avg = obj.annotated_cooling_duration if hasattr(obj, 'annotated_cooling_duration') else None
        return f"{avg:.1f} min" if avg else "-"
    avg_cooling_duration.short_description = 'Avg Cooling Duration'
    avg_cooling_duration.admin_order_field = 'annotated_cooling_duration'
    
    def avg_cooling_avg_gradient(self, obj):
        """Average cooling gradient"""
        avg = obj.annotated_cooling_avg_gradient if hasattr(obj, 'annotated_cooling_avg_gradient') else None
        return f"{avg:.3f} °C/min" if avg else "-"
    avg_cooling_avg_gradient.short_description = 'Avg Cooling Gradient'
    avg_cooling_avg_gradient.admin_order_field = 'annotated_cooling_avg_gradient'
    
    def avg_start_temp(self, obj):
        """Average start temperature"""
        avg = obj.annotated_start_temp if hasattr(obj, 'annotated_start_temp') else None
        return f"{avg:.1f} °C" if avg else "-"
    avg_start_temp.short_description = 'Avg Start Temp'
    avg_start_temp.admin_order_field = 'annotated_start_temp'
    
    def avg_end_temp(self, obj):
        """Average end temperature"""
        avg = obj.annotated_end_temp if hasattr(obj, 'annotated_end_temp') else None
        return f"{avg:.1f} °C" if avg else "-"
    avg_end_temp.short_description = 'Avg End Temp'
    avg_end_temp.admin_order_field = 'annotated_end_temp'
    
    def avg_max_temp(self, obj):
        """Average max temperature"""
        avg = obj.annotated_max_temp if hasattr(obj, 'annotated_max_temp') else None
        return f"{avg:.1f} °C" if avg else "-"
    avg_max_temp.short_description = 'Avg Max Temp'
    avg_max_temp.admin_order_field = 'annotated_max_temp'
    
    def avg_heating_efficiency(self, obj):
        """Average heating efficiency"""
        avg = obj.annotated_avg_heating_efficiency if hasattr(obj, 'annotated_avg_heating_efficiency') else None
        return f"{avg:.5f}" if avg else "-"
    avg_heating_efficiency.short_description = 'Avg Heating Efficiency (K)'
    avg_heating_efficiency.admin_order_field = 'annotated_avg_heating_efficiency'
    
    def avg_real_heating_duration(self, obj):
        """Average real heating duration (rise time)"""
        avg = obj.annotated_real_heating_duration if hasattr(obj, 'annotated_real_heating_duration') else None
        return f"{avg:.1f} min" if avg else "-"
    avg_real_heating_duration.short_description = 'Avg Rise Time'
    avg_real_heating_duration.admin_order_field = 'annotated_real_heating_duration'
    
    def avg_duration_effective(self, obj):
        """Average duration effective"""
        avg = obj.annotated_duration_effective if hasattr(obj, 'annotated_duration_effective') else None
        return f"{avg:.1f} min" if avg else "-"
    avg_duration_effective.short_description = 'Avg Duration Effective'
    avg_duration_effective.admin_order_field = 'annotated_duration_effective'
    
    def avg_heating_gradient_duration(self, obj):
        """Average heating gradient duration"""
        avg = obj.annotated_heating_gradient_duration if hasattr(obj, 'annotated_heating_gradient_duration') else None
        return f"{avg:.1f} min" if avg else "-"
    avg_heating_gradient_duration.short_description = 'Avg Heating Grad Duration'
    avg_heating_gradient_duration.admin_order_field = 'annotated_heating_gradient_duration'
    
    def avg_heating_span(self, obj):
        """Average heating span"""
        avg = obj.annotated_heating_span if hasattr(obj, 'annotated_heating_span') else None
        return f"{avg:.1f} min" if avg else "-"
    avg_heating_span.short_description = 'Avg Heating Span'
    avg_heating_span.admin_order_field = 'annotated_heating_span'
    
    def avg_ideal_heating_time(self, obj):
        """Average ideal heating time"""
        avg = obj.annotated_ideal_heating_time if hasattr(obj, 'annotated_ideal_heating_time') else None
        return f"{avg:.1f} min" if avg else "-"
    avg_ideal_heating_time.short_description = 'Avg Ideal Heating Time'
    avg_ideal_heating_time.admin_order_field = 'annotated_ideal_heating_time'
    
    def avg_heating_lag_time(self, obj):
        """Average heating lag time"""
        avg = obj.annotated_heating_lag_time if hasattr(obj, 'annotated_heating_lag_time') else None
        if avg is not None:
            prefix = "+" if avg > 0 else ""
            return f"{prefix}{avg:.1f} min"
        return "-"
    avg_heating_lag_time.short_description = 'Avg Heating Lag'
    avg_heating_lag_time.admin_order_field = 'annotated_heating_lag_time'
    
    def avg_avg_steam_temp(self, obj):
        """Average steam temperature"""
        avg = obj.annotated_avg_steam_temp if hasattr(obj, 'annotated_avg_steam_temp') else None
        return f"{avg:.1f} °C" if avg else "-"
    avg_avg_steam_temp.short_description = 'Avg Steam Temp'
    avg_avg_steam_temp.admin_order_field = 'annotated_avg_steam_temp'
    
    def avg_avg_steam_pressure(self, obj):
        """Average steam pressure"""
        avg = obj.annotated_avg_steam_pressure if hasattr(obj, 'annotated_avg_steam_pressure') else None
        return f"{avg:.2f} Bar" if avg else "-"
    avg_avg_steam_pressure.short_description = 'Avg Steam Pressure'
    avg_avg_steam_pressure.admin_order_field = 'annotated_avg_steam_pressure'
    
    # Permissions
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False


@admin.register(UserActivityLog)
class UserActivityLogAdmin(admin.ModelAdmin):
    show_facets = admin.ShowFacets.NEVER
    list_display = (
        'timestamp', 'username', 'action', 'request_path_display',
        'content_type', 'object_repr', 'ip_address', 'short_description'
    )
    list_filter = (
        'action',
        ('timestamp', admin.DateFieldListFilter),
        'user',
        'content_type',
        'request_method',
    )
    search_fields = ('username', 'object_repr', 'description', 'ip_address', 'request_path')
    date_hierarchy = 'timestamp'
    readonly_fields = (
        'user', 'username', 'action', 'content_type', 
        'object_id', 'object_repr', 'request_path', 'request_method',
        'query_params', 'description', 'additional_data',
        'ip_address', 'user_agent', 'timestamp'
    )
    
    fieldsets = (
        ('User Information', {
            'fields': ('user', 'username', 'timestamp', 'ip_address', 'user_agent')
        }),
        ('Action Details', {
            'fields': ('action', 'description')
        }),
        ('Admin Changes', {
            'fields': ('content_type', 'object_id', 'object_repr'),
            'classes': ('collapse',),
        }),
        ('Website Activity', {
            'fields': ('request_path', 'request_method', 'query_params', 'additional_data'),
            'classes': ('collapse',),
        }),
    )
    
    def has_add_permission(self, request):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def request_path_display(self, obj):
        return obj.request_path or '-'
    request_path_display.short_description = 'Page'
    
    def short_description(self, obj):
        if len(obj.description) > 50:
            return obj.description[:50] + '...'
        return obj.description
    short_description.short_description = 'Description'


@admin.register(IPAccessControl)
class IPAccessControlAdmin(admin.ModelAdmin):
    """
    Panel admin untuk memantau dan memblokir/mengizinkan IP yang mengakses website.
    """
    list_display = (
        'ip_address',
        'status_badge',
        'country_display',
        'isp_short',
        'known_users_display',
        'access_count',
        'first_seen',
        'last_seen',
        'note',
    )
    list_display_links = ('ip_address',)
    list_filter = ('is_blocked', 'country_code')
    search_fields = ('ip_address', 'isp', 'country', 'known_users__username')
    ordering = ('-last_seen',)
    readonly_fields = ('ip_address', 'country', 'country_code', 'isp', 'first_seen', 'last_seen', 'access_count')
    filter_horizontal = ('known_users',)

    fieldsets = (
        ('Informasi IP', {
            'fields': ('ip_address', 'country', 'country_code', 'isp'),
        }),
        ('Kontrol Akses', {
            'fields': ('is_blocked', 'note'),
            'description': 'Centang "Blokir" untuk menolak seluruh akses dari IP ini.',
        }),
        ('Akun yang Pernah Login', {
            'fields': ('known_users',),
            'description': 'Daftar akun Plant Monitor yang pernah login dari IP ini. Kosong = tidak pernah login.',
        }),
        ('Statistik', {
            'fields': ('access_count', 'first_seen', 'last_seen'),
            'classes': ('collapse',),
        }),
    )

    actions = ['action_block_selected', 'action_allow_selected']

    # ── Custom column: status badge ────────────────────────────────────
    def status_badge(self, obj):
        if obj.is_blocked:
            return format_html(
                '<span style="background:#dc3545;color:#fff;padding:2px 10px;'
                'border-radius:4px;font-size:11px;font-weight:bold;">🚫 BLOKIR</span>'
            )
        return format_html(
            '<span style="background:#28a745;color:#fff;padding:2px 10px;'
            'border-radius:4px;font-size:11px;font-weight:bold;">✅ IZIN</span>'
        )
    status_badge.short_description = 'Status'
    status_badge.admin_order_field = 'is_blocked'

    # ── Custom column: country dengan flag unicode ─────────────────────
    def country_display(self, obj):
        if obj.country_code:
            return f"{obj.country} ({obj.country_code})"
        return obj.country or '-'
    country_display.short_description = 'Negara'
    country_display.admin_order_field = 'country'

    # ── Custom column: ISP dipotong agar tidak terlalu panjang ─────────
    def isp_short(self, obj):
        isp = obj.isp or '-'
        if len(isp) > 35:
            return isp[:35] + '…'
        return isp
    isp_short.short_description = 'ISP / Org'

    # ── Custom column: akun yang pernah login ──────────────────────────
    def known_users_display(self, obj):
        users = obj.known_users.all()
        if not users.exists():
            return format_html('<span style="color:#aaa;font-style:italic;">-</span>')
        names = ', '.join(u.username for u in users[:5])
        if users.count() > 5:
            names += f' (+{users.count() - 5} lagi)'
        return format_html(
            '<span style="color:#007bff;font-weight:bold;">{}</span>', names
        )
    known_users_display.short_description = 'Akun Login'

    # ── Bulk action: blokir ────────────────────────────────────────────
    @admin.action(description='🚫 Blokir IP yang dipilih')
    def action_block_selected(self, request, queryset):
        n = queryset.update(is_blocked=True)
        self.message_user(request, f'{n} IP berhasil diblokir.', messages.WARNING)

    # ── Bulk action: izinkan ───────────────────────────────────────────
    @admin.action(description='✅ Izinkan IP yang dipilih')
    def action_allow_selected(self, request, queryset):
        n = queryset.update(is_blocked=False)
        self.message_user(request, f'{n} IP berhasil diizinkan.', messages.SUCCESS)

    # Jangan tampilkan tombol "Add" — IP ditambah otomatis oleh middleware
    def has_add_permission(self, request):
        return False

@admin.register(ProgramMaster)
class ProgramMasterAdmin(admin.ModelAdmin):
    list_display = ('nama', 'suhu_max', 'durasi_ideal', 'durasi_heating_ideal', 'durasi_keeping_ideal', 'durasi_cooling_ideal')
    search_fields = ('nama',)
    ordering = ('nama',)


class OrphanStatusFilter(admin.SimpleListFilter):
    title = 'Orphan Status'
    parameter_name = 'is_orphan'

    def lookups(self, request, model_admin):
        return (
            ('1', 'Yes (Orphan)'),
            ('0', 'No (Linked)'),
        )

    def queryset(self, request, queryset):
        if self.value() == '1':
            return queryset.filter(dyeing_process__isnull=True)
        if self.value() == '0':
            return queryset.filter(dyeing_process__isnull=False)
        return queryset

@admin.register(DyeingIdentity)
class DyeingIdentityAdmin(admin.ModelAdmin):
    list_display = (
        'machine', 'process_start', 'waktu_input_awal', 'is_orphan', 'nomor_desain', 'nomor_warna', 'jenis_proses',
        'nomor_order', 'artikel_kain', 'batch', 
        'program', 'isi_per_tube', 'operator',
        'cycle_60', 'cycle_puncak', 'nozzle_main_pump',
        'handling_quality', 
        'masalah', 'keterangan','kode_buyer'
    )
    list_filter = (
        ("machine__group", RelatedDropdownFilter),
        ("machine", ChainedMachineDropdownFilter),
        ("program", RelatedDropdownFilter),
        ("jenis_proses", DropdownFilter),
        "created_at",
        OrphanStatusFilter,
    )
    
    actions = ['force_relink_orphans', 'force_unlink_batch']
    search_fields = ('nomor_order', 'batch', 'artikel_kain', 'keterangan', 'operator', 'cycle_60', 'cycle_puncak', 'nozzle_main_pump')
    list_per_page = 50
    
    # Sembunyikan relasi asli agar tidak dimanipulasi manual
    exclude = ('dyeing_process',)
    readonly_fields = ('created_at', 'updated_at')
    autocomplete_fields = ['program']
    
    fieldsets = (
        ("📝 Identitas Order", {
            "fields": (
                "nomor_order", "artikel_kain", "batch",
                "kode_buyer", "nomor_warna", "nomor_desain",
            ),
        }),
        ("🔢 Detail Produksi", {
            "fields": (
                "program", "isi_per_tube", "operator",
                "cycle_60", "cycle_puncak", "nozzle_main_pump",
                "handling_quality", "jenis_proses",
                "masalah", "keterangan",
            ),
        }),
        ("⚓ Anchors (Terisi Otomatis, Jangan Diubah)", {
            "fields": ("machine", "start_time_snapshot", "created_at", "updated_at"),
            "classes": ("collapse",),
            "description": "Jangkar mesin dan jam mulai digunakan agar data ini selalu menempel di batch yang tepat walau saat proses re-kalkulasi."
        }),
    )
    
    def waktu_input_awal(self, obj):
        if obj.created_at:
            from django.utils import timezone
            local = timezone.localtime(obj.created_at)
            return local.strftime("%d %b %Y, %H:%M")
        return "-"
    waktu_input_awal.short_description = "Awal Input"
    waktu_input_awal.admin_order_field = 'created_at'

    def process_start(self, obj):
        if obj.start_time_snapshot:
            from django.utils import timezone
            local = timezone.localtime(obj.start_time_snapshot)
            return local.strftime("%d %b %Y, %H:%M")
        return "-"
    process_start.short_description = "Start Time"

    def is_orphan(self, obj):
        return obj.dyeing_process_id is None
    is_orphan.boolean = True
    is_orphan.short_description = "Orphan?"

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if 'dyeing_process' in request.GET:
            try:
                from monitoring.models import DyeingProcess
                proc = DyeingProcess.objects.filter(id=request.GET['dyeing_process']).select_related('machine').first()
                if proc:
                    if proc.machine_id:
                        initial['machine'] = proc.machine_id
                    if proc.start_time:
                        initial['start_time_snapshot'] = proc.start_time
            except Exception:
                pass
        if 'machine' in request.GET:
            initial['machine'] = request.GET['machine']
        if 'start_time_snapshot' in request.GET:
            try:
                from datetime import datetime
                initial['start_time_snapshot'] = datetime.fromisoformat(request.GET['start_time_snapshot'])
            except Exception:
                pass
        return initial

    def save_model(self, request, obj, form, change):
        # Jika user mengubah mesin atau jam secara manual di form, lepaskan dari batch lama
        if change and ('start_time_snapshot' in form.changed_data or 'machine' in form.changed_data):
            obj.dyeing_process = None
            
        # Jika ada parameter dyeing_process dari URL, langsung tautkan
        dp_id = request.GET.get('dyeing_process')
        if not obj.dyeing_process and dp_id:
            try:
                from monitoring.models import DyeingProcess
                proc = DyeingProcess.objects.filter(id=dp_id).first()
                if proc:
                    obj.dyeing_process = proc
                    if not obj.machine_id:
                        obj.machine = proc.machine
                    if not obj.start_time_snapshot:
                        obj.start_time_snapshot = proc.start_time
            except Exception:
                pass

        super().save_model(request, obj, form, change)
        
        # Logika Re-link Kustom
        if not obj.dyeing_process and obj.machine and obj.start_time_snapshot:
            from monitoring.models import DyeingProcess
            from datetime import timedelta
            
            # Find the best match
            match = DyeingProcess.objects.filter(
                machine=obj.machine,
                start_time__range=(
                    obj.start_time_snapshot - timedelta(minutes=15),
                    obj.start_time_snapshot + timedelta(minutes=15)
                )
            ).annotate(
                 # (Optional: If Django version supports it)
            ).first()
            
            if match:
                # Cek apakah DyeingProcess tersebut belum memiliki identity
                try:
                    from monitoring.models import DyeingIdentity
                    has_identity = hasattr(match, 'identity') and match.identity is not None
                except DyeingIdentity.DoesNotExist:
                    has_identity = False
                
                if not has_identity:
                    obj.dyeing_process = match
                    obj.save(update_fields=['dyeing_process'])

    @admin.action(description="🔗 Force Re-link Orphans")
    def force_relink_orphans(self, request, queryset):
        from monitoring.models import DyeingProcess
        from datetime import timedelta
        
        success_count = 0
        skip_count = 0
        
        for obj in queryset:
            if not obj.dyeing_process and obj.machine and obj.start_time_snapshot:
                match = DyeingProcess.objects.filter(
                    machine=obj.machine,
                    start_time__range=(
                        obj.start_time_snapshot - timedelta(minutes=15),
                        obj.start_time_snapshot + timedelta(minutes=15)
                    )
                ).first()
                
                if match:
                    # Check if OneToOne is already taken!
                    try:
                        has_identity = match.identity is not None
                    except DyeingIdentity.DoesNotExist:
                        has_identity = False
                        
                    if not has_identity:
                        obj.dyeing_process = match
                        obj.save(update_fields=['dyeing_process'])
                        success_count += 1
                    else:
                        skip_count += 1
        
        if success_count > 0:
            self.message_user(request, f"BERHASIL mere-link {success_count} data orphan kembali ke Dyeing Process-nya.")
        if skip_count > 0:
            from django.contrib import messages
            self.message_user(request, f"GAGAL mere-link {skip_count} data karena Dyeing Process-nya sudah diisi oleh Identity yang lain (Duplikat).", level=messages.WARNING)

    @admin.action(description="Force Unlink dari Batch")
    def force_unlink_batch(self, request, queryset):
        success_count = 0
        for obj in queryset:
            if obj.dyeing_process:
                obj.dyeing_process = None
                obj.save(update_fields=['dyeing_process'])
                success_count += 1
                
        if success_count > 0:
            self.message_user(request, f"BERHASIL melepaskan {success_count} Identity dari Batch-nya menjadi orphan.")



@admin.register(MachineCalibration)
class MachineCalibrationAdmin(admin.ModelAdmin):
    """
    Admin terpisah untuk Master Kalibrasi Sensor.
    Memungkinkan melihat semua kalibrasi aktif lintas mesin sekaligus.
    """
    list_display = (
        'machine_code',
        'machine_name',
        'a_coeff',
        'b_coeff',
        'c_coeff',
        'is_active',
        'formula_display',
        'updated_at',
    )
    list_filter = ('is_active', 'machine__group')
    search_fields = ('machine__code', 'machine__name', 'notes')
    readonly_fields = ('created_at', 'updated_at', 'formula_display')
    list_editable = ('is_active', 'a_coeff', 'b_coeff', 'c_coeff')
    ordering = ('machine__code',)

    fieldsets = (
        ('Mesin', {
            'fields': ('machine', 'is_active'),
        }),
        ('Parameter Kalibrasi  [y = Ax^2 + Bx + C]', {
            'fields': ('a_coeff', 'b_coeff', 'c_coeff', 'formula_display'),
            'description': (
                'Gunakan persamaan polinomial untuk mengkoreksi data sensor. '
                'Hanya Offset: A=0, B=1, C=nilai. '
                'Hanya Span: A=0, B=faktor, C=0. '
                'Tidak ada koreksi (pass-through): A=0, B=1, C=0.'
            ),
        }),
        ('Catatan & Histori', {
            'fields': ('notes', 'created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    def machine_code(self, obj):
        return obj.machine.code
    machine_code.short_description = 'Kode Mesin'
    machine_code.admin_order_field = 'machine__code'

    def machine_name(self, obj):
        return obj.machine.name
    machine_name.short_description = 'Nama Mesin'
    machine_name.admin_order_field = 'machine__name'

    def formula_display(self, obj):
        """Tampilkan formula kalibrasi secara visual di admin."""
        parts = []
        if obj.a_coeff != 0:
            parts.append(f"{obj.a_coeff}x^2")
        if obj.b_coeff != 1.0 or not parts:
            parts.append(f"{obj.b_coeff}x")
        else:
            parts.append("x")
        if obj.c_coeff != 0:
            sign = "+" if obj.c_coeff > 0 else ""
            parts.append(f"{sign}{obj.c_coeff}")
        formula = " + ".join(parts).replace("+ -", "- ")
        return format_html("<code>y = {}</code>", formula)
    formula_display.short_description = 'Formula'


@admin.register(DyeingAnalytics)
class DyeingAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        'machine',
        'report_link',
        'start_time_display',
        'nomor_order',
        'artikel_kain',
        'batch',
        'kode_buyer',
        'operator',
        'nomor_warna',
        'nomor_desain',
        'jenis_proses',
        'program_display',
        'isi_per_tube',
        'output_yard_display',
        'durasi_ideal_display',
        'durasi_efektif_display',
        'loss_time_display',
        'delay_heat_display',
        'delay_cool_display',
        'efficiency_display',
        'steam_usage_display',
        'steam_usage_best_display',
        'steam_usage_ideal_display',
        'steam_efficiency_display',
        'power_consumption_display',
        'ideal_power_consumption_display',
        'power_efficiency_display',
        'power_consumption_wbp_display',
        'power_consumption_lwbp_display',
        'power_cost_wbp_display',
        'power_cost_lwbp_display',
        'power_cost_total_display',
        'power_cost_ideal_display',
        'power_cost_loss_display',
        'max_temp_display',
        'heating_duration_display',
        'steady_duration_display',
        'cooling_duration_display',
        'masalah',
        'keterangan',
    )

    list_filter = (
        ('machine__group', RelatedDropdownFilter),
        ('machine', ChainedMachineDropdownFilter),
        ('program', RelatedDropdownFilter),
        ('jenis_proses', DropdownFilter),
        ('dyeing_process__start_time', admin.DateFieldListFilter),
    )

    search_fields = ('nomor_order', 'artikel_kain', 'batch', 'kode_buyer')
    list_per_page = 50
    ordering = ('-dyeing_process__start_time',)

    def output_yard_display(self, obj):
        val = obj.output_yard
        if val is None:
            return "-"
        return f"{val:,}"
    output_yard_display.short_description = "Output (yd)"
    output_yard_display.admin_order_field = None

    def get_queryset(self, request):
        return (
            super().get_queryset(request)
            .select_related('machine', 'machine__group', 'program', 'dyeing_process')
            .filter(dyeing_process__isnull=False)
            .filter(program__isnull=False)
            .filter(dyeing_process__is_valid_process=True)
        )

    def report_link(self, obj):
        from django.urls import reverse
        url = reverse('dyeing_analytics_report', args=[obj.pk])
        return format_html(
            '<a href="{}" target="_blank" '
            'style="font-size:11px; padding:3px 8px; background:#1e293b; color:#fff; '
            'border-radius:4px; text-decoration:none; white-space:nowrap;">📄 Report</a>',
            url
        )
    report_link.short_description = "Report"

    def start_time_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.start_time:
            from django.utils import timezone
            return timezone.localtime(obj.dyeing_process.start_time).strftime("%Y-%m-%d %H:%M")
        return "-"
    start_time_display.short_description = "Start Time"
    start_time_display.admin_order_field = 'dyeing_process__start_time'

    def program_display(self, obj):
        return obj.program.nama if obj.program else "-"
    program_display.short_description = "Program"
    program_display.admin_order_field = 'program__nama'

    def durasi_ideal_display(self, obj):
        if obj.program and obj.program.durasi_ideal is not None:
            return f"{obj.program.durasi_ideal:.1f}m"
        return "-"
    durasi_ideal_display.short_description = "Durasi Ideal"
    durasi_ideal_display.admin_order_field = 'program__durasi_ideal'

    def durasi_efektif_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.duration_effective is not None:
            return f"{obj.dyeing_process.duration_effective:.1f}m"
        return "-"
    durasi_efektif_display.short_description = "Dur. Efektif"
    durasi_efektif_display.admin_order_field = 'dyeing_process__duration_effective'

    def max_temp_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.max_temp is not None:
            return f"{obj.dyeing_process.max_temp:.1f}°C"
        return "-"
    max_temp_display.short_description = "Max Temp"
    max_temp_display.admin_order_field = 'dyeing_process__max_temp'

    def heating_duration_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.heating_duration is not None:
            return f"{obj.dyeing_process.heating_duration:.1f}m"
        return "-"
    heating_duration_display.short_description = "Heating Dur."
    heating_duration_display.admin_order_field = 'dyeing_process__heating_duration'

    def steady_duration_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.steady_duration is not None:
            return f"{obj.dyeing_process.steady_duration:.1f}m"
        return "-"
    steady_duration_display.short_description = "Steady Dur."
    steady_duration_display.admin_order_field = 'dyeing_process__steady_duration'

    def cooling_duration_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.cooling_duration is not None:
            return f"{obj.dyeing_process.cooling_duration:.1f}m"
        return "-"
    cooling_duration_display.short_description = "Cooling Dur."
    cooling_duration_display.admin_order_field = 'dyeing_process__cooling_duration'

    def delay_heat_display(self, obj):
        if obj.program and obj.dyeing_process:
            heat = obj.dyeing_process.real_heating_duration or 0
            steady = obj.dyeing_process.steady_duration or 0
            ideal_heat = obj.program.durasi_heating_ideal or 0
            ideal_keep = obj.program.durasi_keeping_ideal or 0
            
            if ideal_heat > 0 or ideal_keep > 0:
                delay = (heat + steady) - (ideal_heat + ideal_keep)
                color = "red" if delay > 0 else "green"
                formatted_delay = f"{delay:.1f}"
                return format_html('<span style="color:{}; font-weight:bold;">{}m</span>', color, formatted_delay)
        return "-"
    delay_heat_display.short_description = "Delay Heat"

    def delay_cool_display(self, obj):
        if obj.program and obj.dyeing_process:
            cool = obj.dyeing_process.cooling_duration or 0
            ideal_cool = obj.program.durasi_cooling_ideal or 0
            
            if ideal_cool > 0:
                delay = cool - ideal_cool
                color = "red" if delay > 0 else "green"
                formatted_delay = f"{delay:.1f}"
                return format_html('<span style="color:{}; font-weight:bold;">{}m</span>', color, formatted_delay)
        return "-"
    delay_cool_display.short_description = "Delay Cool"

    def loss_time_display(self, obj):
        if obj.program and obj.program.durasi_ideal is not None and \
           obj.dyeing_process and obj.dyeing_process.duration_effective is not None:
            loss_time = obj.dyeing_process.duration_effective - obj.program.durasi_ideal
            color = "red" if loss_time > 0 else "green"
            
            # Format angka menjadi string dengan 1 desimal terlebih dahulu
            formatted_loss_time = f"{loss_time:.1f}"
            
            # Masukkan ke format_html tanpa format :.1f
            return format_html('<span style="color:{}; font-weight:bold;">{}m</span>', color, formatted_loss_time)
        return "-"

    def efficiency_display(self, obj):
        if obj.program and obj.program.durasi_ideal is not None and \
        obj.dyeing_process and obj.dyeing_process.duration_effective is not None:
            # ✅ Cek duration_effective > 0, bukan durasi_ideal
            if obj.dyeing_process.duration_effective > 0:
                eff = (obj.program.durasi_ideal / obj.dyeing_process.duration_effective) * 100
                if eff >= 90:
                    color = "green"
                elif eff >= 70:
                    color = "orange"
                else:
                    color = "red"
                return format_html(
                    '<span style="color:{}; font-weight:bold;">{}%</span>',
                    color,
                    f"{eff:.1f}"
                )
        return "-"
    
    def steam_usage_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.predicted_steam_kg is not None:
            return f"{obj.dyeing_process.predicted_steam_kg:.1f} kg"
        return "-"
    steam_usage_display.short_description = "Steam Usage"
    steam_usage_display.admin_order_field = 'dyeing_process__predicted_steam_kg'

    def steam_usage_best_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.predicted_steam_best_kg is not None:
            return f"{obj.dyeing_process.predicted_steam_best_kg:.1f} kg"
        return "-"
    steam_usage_best_display.short_description = "Steam Best (Machine)"
    steam_usage_best_display.admin_order_field = 'dyeing_process__predicted_steam_best_kg'

    def steam_usage_ideal_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.predicted_steam_ideal_kg is not None:
            return f"{obj.dyeing_process.predicted_steam_ideal_kg:.1f} kg"
        return "-"
    steam_usage_ideal_display.short_description = "Steam Best of Best"
    steam_usage_ideal_display.admin_order_field = 'dyeing_process__predicted_steam_ideal_kg'

    def power_consumption_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.power_consumption_kwh is not None:
            return f"{obj.dyeing_process.power_consumption_kwh:.1f} kWh"
        return "-"
    power_consumption_display.short_description = "Listrik Aktual"
    power_consumption_display.admin_order_field = 'dyeing_process__power_consumption_kwh'

    def ideal_power_consumption_display(self, obj):
        if obj.dyeing_process and obj.dyeing_process.ideal_power_consumption_kwh is not None:
            return f"{obj.dyeing_process.ideal_power_consumption_kwh:.1f} kWh"
        return "-"
    ideal_power_consumption_display.short_description = "Listrik Ideal"
    ideal_power_consumption_display.admin_order_field = 'dyeing_process__ideal_power_consumption_kwh'

    def steam_efficiency_display(self, obj):
        if obj.dyeing_process and \
           obj.dyeing_process.predicted_steam_ideal_kg is not None and \
           obj.dyeing_process.predicted_steam_kg is not None:
            actual = obj.dyeing_process.predicted_steam_kg
            ideal = obj.dyeing_process.predicted_steam_ideal_kg
            if actual > 0:
                eff = (ideal / actual) * 100
                if eff >= 90: color = "green"
                elif eff >= 70: color = "orange"
                else: color = "red"
                return format_html('<span style="color:{}; font-weight:bold;">{}%</span>', color, f"{eff:.1f}")
        return "-"
    steam_efficiency_display.short_description = "Steam Eff."

    def power_efficiency_display(self, obj):
        if obj.dyeing_process and \
           obj.dyeing_process.ideal_power_consumption_kwh is not None and \
           obj.dyeing_process.power_consumption_kwh is not None:
            actual = obj.dyeing_process.power_consumption_kwh
            ideal = obj.dyeing_process.ideal_power_consumption_kwh
            if actual > 0:
                eff = (ideal / actual) * 100
                if eff >= 90: color = "green"
                elif eff >= 70: color = "orange"
                else: color = "red"
                return format_html('<span style="color:{}; font-weight:bold;">{}%</span>', color, f"{eff:.1f}")
        return "-"
    power_efficiency_display.short_description = "Listrik Eff."
    def power_consumption_wbp_display(self, obj):
        val = obj.dyeing_process.power_consumption_wbp_kwh if obj.dyeing_process else None
        return f"{val:.1f} kWh" if val is not None else "-"
    power_consumption_wbp_display.short_description = "Aktual WBP"
    power_consumption_wbp_display.admin_order_field = 'dyeing_process__power_consumption_wbp_kwh'

    def power_consumption_lwbp_display(self, obj):
        val = obj.dyeing_process.power_consumption_lwbp_kwh if obj.dyeing_process else None
        return f"{val:.1f} kWh" if val is not None else "-"
    power_consumption_lwbp_display.short_description = "Aktual LWBP"
    power_consumption_lwbp_display.admin_order_field = 'dyeing_process__power_consumption_lwbp_kwh'

    def power_cost_wbp_display(self, obj):
        val = obj.dyeing_process.power_cost_wbp if obj.dyeing_process else None
        return f"Rp {val:,.0f}".replace(",", ".") if val is not None else "-"
    power_cost_wbp_display.short_description = "Harga Listrik WBP"
    power_cost_wbp_display.admin_order_field = 'dyeing_process__power_cost_wbp'

    def power_cost_lwbp_display(self, obj):
        val = obj.dyeing_process.power_cost_lwbp if obj.dyeing_process else None
        return f"Rp {val:,.0f}".replace(",", ".") if val is not None else "-"
    power_cost_lwbp_display.short_description = "Harga Listrik LWBP"
    power_cost_lwbp_display.admin_order_field = 'dyeing_process__power_cost_lwbp'

    def power_cost_total_display(self, obj):
        val = obj.dyeing_process.power_cost_total if obj.dyeing_process else None
        return f"Rp {val:,.0f}".replace(",", ".") if val is not None else "-"
    power_cost_total_display.short_description = "Harga Listrik Total"
    power_cost_total_display.admin_order_field = 'dyeing_process__power_cost_total'
    
    def power_cost_ideal_display(self, obj):
        val = obj.dyeing_process.power_cost_ideal if obj.dyeing_process else None
        return f"Rp {val:,.0f}".replace(",", ".") if val is not None else "-"
    power_cost_ideal_display.short_description = "Harga Listrik Ideal"
    power_cost_ideal_display.admin_order_field = 'dyeing_process__power_cost_ideal'

    def power_cost_loss_display(self, obj):
        val = obj.dyeing_process.power_cost_loss if obj.dyeing_process else None
        if val is not None:
            formatted = f"Rp {val:,.0f}".replace(",", ".")
            color = "red" if val > 0 else "green"
            return format_html('<span style="color:{}; font-weight:bold;">{}</span>', color, formatted)
        return "-"
    power_cost_loss_display.short_description = "Loss Harga Listrik"
    power_cost_loss_display.admin_order_field = 'dyeing_process__power_cost_loss'


    # Make fields readonly as this is just an analytics proxy
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_module_permission(self, request):
        return request.user.is_active and (
            request.user.has_perm('monitoring.view_dyeinganalytics') or
            request.user.has_perm('monitoring.change_dyeinganalytics')
        )

    def has_view_permission(self, request, obj=None):
        return request.user.is_active and (
            request.user.has_perm('monitoring.view_dyeinganalytics') or
            request.user.has_perm('monitoring.change_dyeinganalytics')
        )

@admin.register(DyeingExecutiveSummary)
class DyeingExecutiveSummaryAdmin(admin.ModelAdmin):
    change_list_template = "admin/monitoring/dyeingexecutivesummary/change_list.html"
    list_filter = (
        PerformanceDateFilter,
        ('program', RelatedDropdownFilter),
    )
    
    def get_queryset(self, request):
        return super().get_queryset(request).filter(
            dyeing_process__isnull=False,
            program__isnull=False,
            dyeing_process__is_valid_process=True,
        ).select_related('machine', 'program', 'dyeing_process')
    
    def changelist_view(self, request, extra_context=None):
        from django.db.models import Avg, Count, Sum, F, FloatField, ExpressionWrapper, Q, Value, Case, When, IntegerField
        
        try:
            cl = self.get_changelist_instance(request)
            base_qs = cl.get_queryset(request)
        except Exception:
            base_qs = self.get_queryset(request)
        
        month_param = request.GET.get('month', 'all')
        

        total_agg = base_qs.aggregate(
            total_batch=Count('pk'),
            sum_ideal=Sum('program__durasi_ideal'),
            sum_effective=Sum('dyeing_process__duration_effective'),
            sum_loss=Sum(
                ExpressionWrapper(
                    F('dyeing_process__duration_effective') - F('program__durasi_ideal'),
                    output_field=FloatField()
                )
            ),
            avg_loss=Avg(
                ExpressionWrapper(
                    F('dyeing_process__duration_effective') - F('program__durasi_ideal'),
                    output_field=FloatField()
                )
            ),
            avg_delay_heat=Avg(
                ExpressionWrapper(
                    (F('dyeing_process__real_heating_duration') + F('dyeing_process__steady_duration'))
                    - (F('program__durasi_heating_ideal') + F('program__durasi_keeping_ideal')),
                    output_field=FloatField()
                )
            ),
            avg_delay_cool=Avg(
                ExpressionWrapper(
                    F('dyeing_process__cooling_duration') - F('program__durasi_cooling_ideal'),
                    output_field=FloatField()
                )
            ),
            avg_max_temp=Avg('dyeing_process__max_temp'),
        )
        
        on_time_qs = base_qs.annotate(
            is_on_time=Case(
                When(
                    dyeing_process__duration_effective__gt=0,
                    then=Case(
                        When(
                            program__durasi_ideal__gte=ExpressionWrapper(
                                0.85 * F('dyeing_process__duration_effective'),
                                output_field=FloatField()
                            ),
                            then=Value(1)
                        ),
                        default=Value(0),
                        output_field=IntegerField()
                    )
                ),
                default=Value(0),
                output_field=IntegerField()
            )
        )
        
        total_on_time_count = on_time_qs.aggregate(on_time_sum=Sum('is_on_time'))['on_time_sum'] or 0
        
        if total_agg['sum_effective'] and total_agg['sum_effective'] > 0:
            total_agg_eff = (total_agg['sum_ideal'] / total_agg['sum_effective']) * 100
        else:
            total_agg_eff = None
            
        total_on_time_rate = (total_on_time_count / total_agg['total_batch'] * 100) if total_agg['total_batch'] else 0
        
        total_status = "critical"
        if total_agg_eff is not None:
            if total_agg_eff >= 85:
                total_status = "good"
            elif total_agg_eff >= 70:
                total_status = "warning"
                
        # Prepare drill-down URL parameters
        from django.urls import reverse
        import urllib.parse
        from datetime import datetime
        from django.utils import timezone
        
        base_analytics_url = reverse('admin:monitoring_dyeinganalytics_changelist')
        
        url_params = {}
        program_id = request.GET.get('program__id__exact')
        if program_id:
            url_params['program__id__exact'] = program_id
            
        if month_param and month_param != 'all':
            try:
                year, month = month_param.split('-')
                year = int(year)
                month = int(month)
                start_date = timezone.make_aware(datetime(year, month, 1))
                if month == 12:
                    end_date = timezone.make_aware(datetime(year + 1, 1, 1))
                else:
                    end_date = timezone.make_aware(datetime(year, month + 1, 1))
                url_params['dyeing_process__start_time__gte'] = start_date.strftime('%Y-%m-%d')
                url_params['dyeing_process__start_time__lt'] = end_date.strftime('%Y-%m-%d')
            except (ValueError, AttributeError):
                pass

        total_query_string = urllib.parse.urlencode(url_params)
        total_drilldown_url = f"{base_analytics_url}?{total_query_string}"

        total_row = {
            'machine_code': 'TOTAL',
            'machine_name': 'Kinerja Keseluruhan',
            'total_batch': total_agg['total_batch'],
            'agg_efficiency': total_agg_eff,
            'on_time_rate': total_on_time_rate,
            'sum_loss': total_agg['sum_loss'] or 0,
            'avg_loss': total_agg['avg_loss'] or 0,
            'avg_delay_heat': total_agg['avg_delay_heat'] or 0,
            'avg_delay_cool': total_agg['avg_delay_cool'] or 0,
            'avg_max_temp': total_agg['avg_max_temp'] or 0,
            'status': total_status,
            'drilldown_url': total_drilldown_url
        }
        
        per_machine_agg = base_qs.values('machine__id', 'machine__code', 'machine__name').annotate(
            total_batch=Count('pk'),
            sum_ideal=Sum('program__durasi_ideal'),
            sum_effective=Sum('dyeing_process__duration_effective'),
            sum_loss=Sum(
                ExpressionWrapper(
                    F('dyeing_process__duration_effective') - F('program__durasi_ideal'),
                    output_field=FloatField()
                )
            ),
            avg_loss=Avg(
                ExpressionWrapper(
                    F('dyeing_process__duration_effective') - F('program__durasi_ideal'),
                    output_field=FloatField()
                )
            ),
            avg_delay_heat=Avg(
                ExpressionWrapper(
                    (F('dyeing_process__real_heating_duration') + F('dyeing_process__steady_duration'))
                    - (F('program__durasi_heating_ideal') + F('program__durasi_keeping_ideal')),
                    output_field=FloatField()
                )
            ),
            avg_delay_cool=Avg(
                ExpressionWrapper(
                    F('dyeing_process__cooling_duration') - F('program__durasi_cooling_ideal'),
                    output_field=FloatField()
                )
            ),
            avg_max_temp=Avg('dyeing_process__max_temp'),
        ).order_by('machine__code')
        
        machine_on_time = on_time_qs.values('machine__code').annotate(on_time_sum=Sum('is_on_time'))
        on_time_map = {item['machine__code']: item['on_time_sum'] for item in machine_on_time}
        
        machine_rows = []
        for m in per_machine_agg:
            code = m['machine__code']
            sum_eff = m['sum_effective']
            eff = (m['sum_ideal'] / sum_eff * 100) if sum_eff and sum_eff > 0 else None
            
            on_time_count = on_time_map.get(code, 0)
            on_time_rate = (on_time_count / m['total_batch'] * 100) if m['total_batch'] else 0
            
            status = "critical"
            if eff is not None:
                if eff >= 85:
                    status = "good"
                elif eff >= 70:
                    status = "warning"
            
            row_params = url_params.copy()
            row_params['machine__id__exact'] = m['machine__id']
            row_query_string = urllib.parse.urlencode(row_params)
            drilldown_url = f"{base_analytics_url}?{row_query_string}"
                    
            machine_rows.append({
                'machine_code': code,
                'machine_name': m['machine__name'],
                'total_batch': m['total_batch'],
                'agg_efficiency': eff,
                'on_time_rate': on_time_rate,
                'sum_loss': m['sum_loss'] or 0,
                'avg_loss': m['avg_loss'] or 0,
                'avg_delay_heat': m['avg_delay_heat'] or 0,
                'avg_delay_cool': m['avg_delay_cool'] or 0,
                'avg_max_temp': m['avg_max_temp'] or 0,
                'status': status,
                'drilldown_url': drilldown_url
            })
            
        extra_context = extra_context or {}
        extra_context.update({
            'total_row': total_row,
            'machine_rows': machine_rows,
            'month_param': month_param,
        })
        
        return super().changelist_view(request, extra_context)

    def has_add_permission(self, request): return False
    def has_change_permission(self, request, obj=None): return False
    def has_delete_permission(self, request, obj=None): return False
    
    def has_module_permission(self, request):
        return request.user.is_active and (
            request.user.has_perm('monitoring.view_dyeingexecutivesummary') or
            request.user.has_perm('monitoring.change_dyeingexecutivesummary')
        )
        
    def has_view_permission(self, request, obj=None):
        return request.user.is_active and (
            request.user.has_perm('monitoring.view_dyeingexecutivesummary') or
            request.user.has_perm('monitoring.change_dyeingexecutivesummary')
        )

from .models import DailyBatchOverview, DataAnomaly, GlobalSettings

@admin.register(DailyBatchOverview)
class DailyBatchOverviewAdmin(admin.ModelAdmin):
    """
    Admin override for DailyBatchOverview proxy model.
    Redirects changelist view to our custom daily_batch_overview view.
    """
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
        
    def has_change_permission(self, request, obj=None):
        return False

    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        return redirect('daily_batch_overview')


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "__str__", "water_specific_heat", "water_density", "fabric_specific_heat",
        "standard_ambient_temp", "fuel_factor_steam_boiler", "fuel_factor_hto_boiler",
        "coal_calorific_value", "sensor_shadow_max_minutes", "sensor_rehydrate_buffer_minutes", "updated_at",
    )
    fieldsets = (
        ("Data Quality Shield", {
            "fields": ("sensor_shadow_max_minutes", "sensor_rehydrate_buffer_minutes"),
            "description": "Konfigurasi sistem anti-drop dan shadow data untuk sensor.",
        }),
        ("Parameter Air", {
            "fields": ("water_specific_heat", "water_density"),
        }),
        ("Parameter Kain", {
            "fields": ("fabric_specific_heat",),
        }),
        ("Parameter Lingkungan", {
            "fields": ("standard_ambient_temp",),
        }),
        ("Konversi Bahan Bakar Boiler", {
            "fields": ("fuel_factor_steam_boiler", "fuel_factor_hto_boiler", "coal_calorific_value"),
            "description": (
                "Kalibrasi konsumsi batu bara berdasarkan nilai Hz sensor feeder. "
                "Speed RB Steam → sensor Speed_RB_Steam. Speed RB HTO → sensor Speed_R_Bakar. "
                "Rumus: kg/jam = Hz × faktor. Isi 0 jika belum dikalibrasi."
            ),
        }),
    )
    
    def changelist_view(self, request, extra_context=None):
        from django.shortcuts import redirect
        # Auto-create/ensure it exists and redirect directly to the change page
        obj = GlobalSettings.load()
        return redirect('admin:monitoring_globalsettings_change', obj.pk)
    
    def has_add_permission(self, request):
        # Prevent adding more if one already exists
        return not GlobalSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        # Prevent deletion of the singleton instance
        return False

from .models import DailyPlantMetric, BoilerDailyMetric

@admin.register(DailyPlantMetric)
class DailyPlantMetricAdmin(admin.ModelAdmin):
    list_display = ("date", "total_steam_usage", "average_availability", "productivity_goal", "updated_at")
    list_filter = ("date",)
    ordering = ("-date",)


@admin.register(BoilerDailyMetric)
class BoilerDailyMetricAdmin(admin.ModelAdmin):
    list_display = (
        "date", "total_steam_usage_kg", "avg_pressure", "total_fuel_kg",
        "specific_fuel_consumption", "pressure_ideal_percent",
        "alert_count_total", "has_data", "updated_at",
    )
    list_filter = ("has_data", "date")
    ordering = ("-date",)
    readonly_fields = ("created_at", "updated_at")

@admin.register(DataAnomaly)
class DataAnomalyAdmin(admin.ModelAdmin):
    list_display = ('id', 'identity_record', 'process_record', 'anomaly_type', 'severity', 'is_resolved', 'resolved_action', 'created_at')
    list_filter = ('anomaly_type', 'severity', 'is_resolved', 'resolved_action')
    search_fields = ('identity_record__nomor_order', 'identity_record__artikel_kain', 'process_record__machine__code', 'resolution_notes')
    readonly_fields = ('created_at', 'resolved_at')
    fieldsets = (
        ('Basic Information', {
            'fields': ('identity_record', 'process_record', 'anomaly_type', 'severity')
        }),
        ('Details', {
            'fields': ('details',)
        }),
        ('Resolution Status', {
            'fields': ('is_resolved', 'resolved_action', 'resolution_notes', 'resolved_at')
        }),
        ('Timestamps', {
            'fields': ('created_at',),
            'classes': ('collapse',)
        }),
    )


# ═══════════════════════════════════════════════════════════════════════════════
# 🧵 MASTER KAIN — Django Admin
# ═══════════════════════════════════════════════════════════════════════════════

@admin.register(MasterAnyaman)
class MasterAnyamanAdmin(admin.ModelAdmin):
    list_display = ("kode", "nama", "is_active", "jumlah_kain")
    list_filter = ("is_active",)
    search_fields = ("kode", "nama")
    list_editable = ("is_active",)

    def jumlah_kain(self, obj):
        n = obj.kain_set.count()
        return f"{n} kain"
    jumlah_kain.short_description = "Digunakan"


# ── Auto-numbering formsets ──────────────────────────────────────────────────

from django.forms.models import BaseInlineFormSet

class BenangLusiFormSet(BaseInlineFormSet):
    """Automatically assigns urutan (1, 2, 3…) – users never see/touch it."""
    def save_new(self, form, commit=True):
        if not hasattr(self, '_current_urutan'):
            self._current_urutan = self.instance.benang_lusi.count()
        self._current_urutan += 1
        
        obj = super().save_new(form, commit)
        obj.urutan = self._current_urutan
        if commit:
            obj.save(update_fields=['urutan'])
        return obj


class BenangPakanFormSet(BaseInlineFormSet):
    """Automatically assigns urutan (1, 2, 3…) – users never see/touch it."""
    def save_new(self, form, commit=True):
        if not hasattr(self, '_current_urutan'):
            self._current_urutan = self.instance.benang_pakan.count()
        self._current_urutan += 1
        
        obj = super().save_new(form, commit)
        obj.urutan = self._current_urutan
        if commit:
            obj.save(update_fields=['urutan'])
        return obj


# ── Inline: Benang Lusi ──────────────────────────────────────────────────────

class BenangLusiInline(admin.StackedInline):
    model = BenangLusi
    formset = BenangLusiFormSet
    extra = 1
    min_num = 0
    can_delete = True
    verbose_name = "Benang Lusi"
    verbose_name_plural = "Benang Lusi"
    exclude = ("urutan",)   # auto-assigned; no need to show in form
    fields = (
        ("jenis_benang", "denier", "filamen"),
        ("no_lot", "tpm", "twist"),
        ("repeat", "twist_shr"),
        ("vhs_suhu", "vhs_waktu"),
        ("yarn_weight_gross", "yarn_weight_netto"),
    )

    # ── Delegasikan permission ke MasterKain ────────────────────────────────
    # Inline muncul jika user punya akses view/change MasterKain,
    # tanpa perlu assign permission BenangLusi secara terpisah.
    def _has_masterkain_access(self, request):
        return (
            request.user.has_perm("monitoring.view_masterkain") or
            request.user.has_perm("monitoring.change_masterkain")
        )

    def has_view_permission(self, request, obj=None):
        return self._has_masterkain_access(request)

    def has_add_permission(self, request, obj=None):
        return request.user.has_perm("monitoring.change_masterkain")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("monitoring.change_masterkain")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("monitoring.change_masterkain")


# ── Inline: Benang Pakan ─────────────────────────────────────────────────────

class BenangPakanInline(admin.StackedInline):
    model = BenangPakan
    formset = BenangPakanFormSet
    extra = 1
    min_num = 0
    can_delete = True
    verbose_name = "Benang Pakan"
    verbose_name_plural = "Benang Pakan"
    exclude = ("urutan",)   # auto-assigned; no need to show in form
    fields = (
        ("jenis_benang", "denier", "filamen"),
        ("no_lot", "tpm", "twist"),
        ("repeat", "twist_shr"),
        ("vhs_suhu", "vhs_waktu"),
        ("yarn_weight_gross", "yarn_weight_netto"),
    )

    # ── Delegasikan permission ke MasterKain ────────────────────────────────
    def _has_masterkain_access(self, request):
        return (
            request.user.has_perm("monitoring.view_masterkain") or
            request.user.has_perm("monitoring.change_masterkain")
        )

    def has_view_permission(self, request, obj=None):
        return self._has_masterkain_access(request)

    def has_add_permission(self, request, obj=None):
        return request.user.has_perm("monitoring.change_masterkain")

    def has_change_permission(self, request, obj=None):
        return request.user.has_perm("monitoring.change_masterkain")

    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm("monitoring.change_masterkain")


# ── Inline: Revisi Kain (read-only history) ──────────────────────────────────

class RevisiKainInline(admin.TabularInline):
    model = RevisiKain
    extra = 0
    can_delete = False
    show_change_link = False
    verbose_name = "Revisi"
    verbose_name_plural = "📋 Riwayat Revisi"
    fields = ("diubah_pada", "diubah_oleh", "catatan_perubahan")
    readonly_fields = ("diubah_pada", "diubah_oleh", "catatan_perubahan")
    ordering = ("-diubah_pada",)
    max_num = 0  # Tidak bisa tambah manual, hanya tampil

    # ── Delegasikan permission ke MasterKain ────────────────────────────────
    # Revisi hanya read-only; cukup punya akses view/change MasterKain.
    def has_view_permission(self, request, obj=None):
        return (
            request.user.has_perm("monitoring.view_masterkain") or
            request.user.has_perm("monitoring.change_masterkain")
        )

    def has_add_permission(self, request, obj=None):
        return False   # selalu read-only

    def has_change_permission(self, request, obj=None):
        return False   # selalu read-only

    def has_delete_permission(self, request, obj=None):
        return False   # selalu read-only


# ── Main Admin: Master Kain ──────────────────────────────────────────────────

@admin.register(MasterKain)
class MasterKainAdmin(admin.ModelAdmin):
    list_display = (
        "nama_kain",
        "status_badge",
        "tanggal_order",
        "tanggal_greige",
        "tanggal_finish",
        "cfw_display",
        "nama_anyaman",
        "total_gross_display",
        "total_netto_display",
        "created_by",
        "updated_at",
    )
    list_filter = ("status", "nama_anyaman")
    search_fields = ("nama_kain",)
    date_hierarchy = "tanggal_order"
    ordering = ("-created_at",)
    readonly_fields = (
        "cfw",
        "total_gross_display",
        "total_netto_display",
        "created_by",
        "created_at",
        "updated_at",
    )
    inlines = [BenangLusiInline, BenangPakanInline, RevisiKainInline]
    actions = ["duplikasi_kain", "tandai_aktif", "tandai_tidak_berlaku"]

    class Media:
        js = ("monitoring/js/masterkain_nav.js",)

    fieldsets = (
        ("🏷️ Identitas Kain", {
            "fields": (
                "nama_kain",
                ("tanggal_order", "tanggal_greige", "tanggal_finish"),
                "status",
            ),
        }),
        ("📐 Covering Factor", {
            "description": "CFW dihitung otomatis: EPI / √Ne_warp + PPI / √Ne_weft",
            "fields": (
                "cfw",
                ("epi", "ne_warp"),
                ("ppi", "ne_weft"),
            ),
        }),
        ("⚙️ Parameter Mesin", {
            "fields": (
                ("konst_mesin", "t_ends", "pick_mc"),
                ("lebar_sisir_efektif", "lebar_greige", "pick_greige"),
                ("no_sisir", "cucukan", "nama_anyaman"),
            ),
        }),
        ("📉 Susut & Waste", {
            "fields": (
                ("susut_anyaman", "waste_lusi", "waste_pakan"),
            ),
        }),
        ("🔩 Produksi", {
            "fields": (
                ("pick_rolling", "panjang_pakan_mc", "pcs_length_yd"),
            ),
        }),
        ("⚖️ Total Yarn Weight", {
            "description": "Dihitung otomatis dari semua baris benang lusi dan pakan di bawah.",
            "fields": (
                ("total_gross_display", "total_netto_display"),
            ),
        }),
        ("📝 Keterangan", {
            "fields": ("keterangan",),
        }),
        ("🕒 Audit", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    # ── Computed columns ─────────────────────────────────────────────────────

    def status_badge(self, obj):
        colors = {
            "DRAFT": ("#92400e", "#fef3c7"),        # amber
            "AKTIF": ("#065f46", "#d1fae5"),         # green
            "TIDAK_BERLAKU": ("#6b7280", "#f3f4f6"), # gray
        }
        fg, bg = colors.get(obj.status, ("#111", "#fff"))
        label = obj.get_status_display()
        return format_html(
            '<span style="background:{};color:{};padding:2px 8px;border-radius:9px;'
            'font-size:11px;font-weight:600;">{}</span>',
            bg, fg, label,
        )
    status_badge.short_description = "Status"
    status_badge.admin_order_field = "status"

    def cfw_display(self, obj):
        if obj.cfw is not None:
            return format_html("<b>{}</b>", float(obj.cfw))
        return "—"
    cfw_display.short_description = "CFW"

    def total_gross_display(self, obj):
        total = obj.total_gross_gm
        if total:
            return format_html('<b style="color:#1d4ed8">{} G/M</b>', total)
        return "—"
    total_gross_display.short_description = "Total Gross G/M"

    def total_netto_display(self, obj):
        total = obj.total_netto_gm
        if total:
            return format_html('<b style="color:#047857">{} G/M</b>', total)
        return "—"
    total_netto_display.short_description = "Total Netto G/M"

    # ── Save: auto-fill created_by + catat revisi ─────────────────────────────

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        else:
            try:
                old = MasterKain.objects.get(pk=obj.pk)
                changed_fields = []
                snapshot = {}
                for field in form.changed_data:
                    try:
                        old_val = getattr(old, field)
                        new_val = form.cleaned_data.get(field)
                        changed_fields.append(
                            f"{field}: '{old_val}' → '{new_val}'"
                        )
                        snapshot[field] = str(old_val)
                    except AttributeError:
                        pass

                if changed_fields:
                    RevisiKain.objects.create(
                        master_kain=old,
                        diubah_oleh=request.user,
                        catatan_perubahan="\n".join(changed_fields),
                        snapshot_data=snapshot,
                    )
            except MasterKain.DoesNotExist:
                pass

        super().save_model(request, obj, form, change)

    def save_formset(self, request, form, formset, change):
        """After saving inline forms, renumber urutan sequentially (1, 2, 3…)."""
        super().save_formset(request, form, formset, change)
        master = form.instance
        if formset.model == BenangLusi:
            for idx, b in enumerate(
                master.benang_lusi.order_by("urutan", "id"), start=1
            ):
                if b.urutan != idx:
                    BenangLusi.objects.filter(pk=b.pk).update(urutan=idx)
        elif formset.model == BenangPakan:
            for idx, b in enumerate(
                master.benang_pakan.order_by("urutan", "id"), start=1
            ):
                if b.urutan != idx:
                    BenangPakan.objects.filter(pk=b.pk).update(urutan=idx)

    # ── Action: Duplikasi Kain ────────────────────────────────────────────────

    @admin.action(description="📋 Duplikasi kain terpilih (Clone)")
    def duplikasi_kain(self, request, queryset):
        total_created = 0
        for kain in queryset:
            # Simpan benang sebelum duplicate
            lusi_list = list(kain.benang_lusi.all())
            pakan_list = list(kain.benang_pakan.all())

            # Clone header
            kain.pk = None
            kain.nama_kain = f"[COPY] {kain.nama_kain}"
            kain.status = "DRAFT"
            kain.created_by = request.user
            kain.save()

            # Clone benang lusi
            for b in lusi_list:
                b.pk = None
                b.master_kain = kain
                b.save()

            # Clone benang pakan
            for b in pakan_list:
                b.pk = None
                b.master_kain = kain
                b.save()

            total_created += 1

        self.message_user(request, f"{total_created} kain berhasil diduplikasi.")

    @admin.action(description="✅ Tandai sebagai AKTIF")
    def tandai_aktif(self, request, queryset):
        queryset.update(status="AKTIF")
        self.message_user(request, "Status kain berhasil diubah menjadi AKTIF.")

    @admin.action(description="❌ Tandai sebagai TIDAK BERLAKU")
    def tandai_tidak_berlaku(self, request, queryset):
        queryset.update(status="TIDAK BERLAKU")
        self.message_user(request, "Status kain berhasil diubah menjadi TIDAK BERLAKU.")

from nested_admin import NestedModelAdmin, NestedStackedInline, NestedTabularInline
from .models import (
    StandardFlowProcess, FlowProcessGreige, FlowProcessCreeping,
    FlowProcessDryer, FlowProcessPreset, FlowProcessWR, FlowProcessCelup,
    FlowProcessDryerFinal, FlowProcessFinalSet, ObatAntistatic, ObatSoftener
)

# ── Flow Process ──────────────────────────────────────────────────────────────

class BaseFlowProcessInline(NestedStackedInline):
    extra = 0
    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('monitoring.view_standardflowprocess') or super().has_view_permission(request, obj)
    def has_add_permission(self, request, obj=None):
        return request.user.has_perm('monitoring.change_standardflowprocess') or super().has_add_permission(request, obj)
    def has_change_permission(self, request, obj=None):
        return request.user.has_perm('monitoring.change_standardflowprocess') or super().has_change_permission(request, obj)
    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm('monitoring.change_standardflowprocess') or super().has_delete_permission(request, obj)

class BaseObatInline(NestedTabularInline):
    extra = 0
    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('monitoring.view_standardflowprocess') or super().has_view_permission(request, obj)
    def has_add_permission(self, request, obj=None):
        return request.user.has_perm('monitoring.change_standardflowprocess') or super().has_add_permission(request, obj)
    def has_change_permission(self, request, obj=None):
        return request.user.has_perm('monitoring.change_standardflowprocess') or super().has_change_permission(request, obj)
    def has_delete_permission(self, request, obj=None):
        return request.user.has_perm('monitoring.change_standardflowprocess') or super().has_delete_permission(request, obj)

class FlowProcessGreigeInline(BaseFlowProcessInline):
    model = FlowProcessGreige
    fields = ['urutan', 'mesin', 'panjang_std', 'lebar', 'pick_mesin', 'pick_greige', 'berat_greige', 'gramasi', 'catatan_koreksi']

class FlowProcessCreepingInline(BaseFlowProcessInline):
    model = FlowProcessCreeping
    fields = ['urutan', 'mesin', 'temperatur', 'waktu', 'program', 'tekanan_pompa', 'volume_air', 'isi_per_tube', 'isi_per_batch', 'resep', 'hasil_lebar', 'hasil_pick', 'hasil_gramasi', 'hasil_panjang_jadi']

class FlowProcessDryerInline(BaseFlowProcessInline):
    model = FlowProcessDryer
    fields = ['urutan', 'mesin', 'temperatur', 'speed', 'silinder_dry', 'scutcher', 'hasil_lebar', 'hasil_pick', 'hasil_gramasi', 'hasil_panjang_jadi']

class FlowProcessPresetInline(BaseFlowProcessInline):
    model = FlowProcessPreset
    fields = ['urutan', 'mesin', 'temperatur', 'speed', 'set_lebar', 'blower', 'over_feed', 'hasil_lebar', 'hasil_pick', 'hasil_gramasi', 'hasil_panjang_jadi']

class FlowProcessWRInline(BaseFlowProcessInline):
    model = FlowProcessWR
    fields = ['urutan', 'mesin', 'coustic', 'speed', 'persen_wr', 'hasil_lebar', 'hasil_pick', 'hasil_gramasi', 'hasil_panjang_jadi']

class FlowProcessCelupInline(BaseFlowProcessInline):
    model = FlowProcessCelup
    fields = ['urutan', 'mesin', 'program', 'temperatur', 'waktu', 'nozzle', 'tekanan_pompa', 'isi_per_tube', 'isi_per_batch', 'resep', 'hasil_lebar', 'hasil_pick', 'hasil_gramasi', 'hasil_panjang_jadi']

class FlowProcessFinalSetInline(BaseFlowProcessInline):
    model = FlowProcessFinalSet
    fields = ['urutan', 'mesin', 'temperatur', 'speed', 'set_lebar', 'blower', 'over_feed', 'hasil_lebar', 'hasil_pick', 'hasil_gramasi', 'hasil_panjang_jadi']

class ObatAntistaticInline(BaseObatInline):
    model = ObatAntistatic

class ObatSoftenerInline(BaseObatInline):
    model = ObatSoftener

class FlowProcessDryerFinalInline(BaseFlowProcessInline):
    model = FlowProcessDryerFinal
    fields = ['urutan', 'mesin', 'silinder_dry', 'centrifugal', 'hasil_lebar', 'hasil_pick', 'hasil_gramasi', 'hasil_panjang_jadi']
    inlines = [ObatAntistaticInline, ObatSoftenerInline]

@admin.register(StandardFlowProcess)
class StandardFlowProcessAdmin(NestedModelAdmin):
    list_display = ("master_kain", "versi", "status", "tanggal_pembuatan_form", "tanggal_generate", "cetak_button")
    list_filter = ("status", "tanggal_pembuatan_form")
    search_fields = ("master_kain__nama_kain", "versi")
    autocomplete_fields = ["master_kain"]
    readonly_fields = ("versi", "tanggal_generate")
    inlines = [
        FlowProcessGreigeInline,
        FlowProcessCreepingInline,
        FlowProcessDryerInline,
        FlowProcessPresetInline,
        FlowProcessWRInline,
        FlowProcessCelupInline,
        FlowProcessDryerFinalInline,
        FlowProcessFinalSetInline
    ]
    
    def cetak_button(self, obj):
        from django.urls import reverse
        from django.utils.html import format_html
        url = reverse("cetak_standard_flow", args=[obj.pk])
        return format_html('<a class="button" href="{}" target="_blank" style="background-color:#417690;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;">Cetak PDF</a>', url)
    cetak_button.short_description = "Print"
    
    fieldsets = (
        ("Header", {
            "fields": (
                ("master_kain", "status"),
                ("tanggal_pembuatan_form", "tanggal_generate", "versi"),
            )
        }),
        ("Target Hasil Akhir Keseluruhan", {
            "fields": (
                ("hasil_lebar", "hasil_pick"),
                ("hasil_gramasi", "hasil_susut", "hasil_persen_wr"),
            )
        }),
    )

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
            
        if obj.status == "AKTIF":
            StandardFlowProcess.objects.filter(master_kain=obj.master_kain).exclude(pk=obj.pk).update(status="ARSIP")
            
        super().save_model(request, obj, form, change)


# ── Engineer Workspace ────────────────────────────────────────────────────────
from monitoring.models import (
    InspectionTemplate, FieldInspection, SparePart,
    EngineerIssue, CalculationSession, MeetingNote, ActionItem,
)

@admin.register(InspectionTemplate)
class InspectionTemplateAdmin(admin.ModelAdmin):
    list_display = ('name', 'machine_group', 'is_active')

@admin.register(FieldInspection)
class FieldInspectionAdmin(admin.ModelAdmin):
    list_display = ('machine', 'inspector', 'severity', 'status', 'created_at')
    list_filter = ('severity', 'status')

@admin.register(SparePart)
class SparePartAdmin(admin.ModelAdmin):
    list_display = ('name', 'part_number', 'stock_quantity', 'min_stock', 'location')
    filter_horizontal = ('machines',)

@admin.register(EngineerIssue)
class EngineerIssueAdmin(admin.ModelAdmin):
    list_display = ('title', 'priority', 'status', 'machine', 'assigned_to', 'due_date')
    list_filter = ('priority', 'status', 'source_type')

@admin.register(CalculationSession)
class CalculationSessionAdmin(admin.ModelAdmin):
    list_display = ('title', 'machine', 'status', 'created_by', 'updated_at')

@admin.register(MeetingNote)
class MeetingNoteAdmin(admin.ModelAdmin):
    list_display = ('title', 'meeting_date', 'created_by')

@admin.register(ActionItem)
class ActionItemAdmin(admin.ModelAdmin):
    list_display = ('description', 'status', 'assignee', 'due_date', 'meeting')


# ── Production Planning ───────────────────────────────────────────────────────
from monitoring.models import ProductionPlan, ProductionPlanBatch, ProductionPlanBlock


class ProductionPlanBlockInline(admin.TabularInline):
    model = ProductionPlanBlock
    extra = 0
    readonly_fields = ("phase", "sequence", "duration_minutes")
    can_delete = False


class ProductionPlanBatchInline(admin.StackedInline):
    model = ProductionPlanBatch
    extra = 0
    show_change_link = True
    readonly_fields = ("machine", "program", "label", "order", "start_offset_minutes")
    can_delete = False


@admin.register(ProductionPlan)
class ProductionPlanAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "shift_date", "status", "version", "updated_at", "created_by")
    list_filter = ("status", "shift_date")
    search_fields = ("name", "notes")
    readonly_fields = ("version", "created_at", "updated_at", "created_by", "updated_by")
    inlines = [ProductionPlanBatchInline]


@admin.register(ProductionPlanBatch)
class ProductionPlanBatchAdmin(admin.ModelAdmin):
    list_display = ("id", "plan", "machine", "program", "start_offset_minutes", "label")
    list_filter = ("machine",)
    inlines = [ProductionPlanBlockInline]
    readonly_fields = ("plan", "machine", "program", "label", "order", "start_offset_minutes")


# ─── Jumo Device Admin ────────────────────────────────────────────────────────

class JumoChannelInline(admin.TabularInline):
    """
    Tampilkan dan edit semua channel dari satu device secara inline.
    extra=0 untuk tidak menampilkan form kosong secara default.
    """
    model = JumoChannel
    extra = 0
    min_num = 0
    max_num = 16  # lebih dari cukup untuk semua tipe device
    fields = ("channel_index", "machine")
    autocomplete_fields = ("machine",)  # gunakan search box untuk Machine
    ordering = ("channel_index",)
    verbose_name = "Mapping Channel"
    verbose_name_plural = "Mapping Channel"


@admin.register(JumoDevice)
class JumoDeviceAdmin(admin.ModelAdmin):
    list_display = (
        "name", "ip_address", "port", "start_addr",
        "device_id", "num_ai", "is_active", "channel_count"
    )
    list_filter = ("is_active",)
    search_fields = ("name", "ip_address")
    list_editable = ("is_active",)
    inlines = [JumoChannelInline]

    def channel_count(self, obj):
        """Tampilkan jumlah channel yang sudah di-mapping."""
        count = obj.channels.filter(machine__isnull=False).count()
        total = obj.channels.count()
        return f"{count}/{obj.num_ai} mapped"
    channel_count.short_description = "Channels"

# ═══════════════════════════════════════════════════════════════════════════════
# ANOMALY DETECTION V2 ADMIN
# ═══════════════════════════════════════════════════════════════════════════════
from django.utils.safestring import mark_safe
from django import forms
from monitoring.models import AnomalyThresholdMaster, AnomalyThresholdProposal, AnomalyRuleConfig, AnomalySeverityLevel

MASTER_GUIDE = """
<div style="padding: 10px; background: #e1f5fe; border-left: 5px solid #0288d1; margin-bottom: 15px;">
    <strong>Panduan Master Threshold:</strong><br>
    Tabel ini adalah referensi UTAMA yang digunakan sistem setiap pagi (06:00) untuk mendeteksi anomali.<br>
    <ul>
        <li><strong>Update Mode (AUTO):</strong> Batas angka di bawah ini akan otomatis tertiban saat Anda meng-Approve proposal mingguan.</li>
        <li><strong>Update Mode (MANUAL):</strong> Kalibrasi mingguan akan melewati Mesin & Program ini (Batas terkunci).</li>
    </ul>
    <em>Tip: Perhatikan teks kecil di bawah setiap kolom input untuk memahami fungsinya!</em>
</div>
"""

master_help_texts = {
    'suhu_mean': 'Rata-rata deviasi suhu dari target program (berdasarkan data historis).',
    'suhu_stddev': 'Standar Deviasi (penyimpangan baku). Angka yang besar berarti suhu mesin untuk program ini sering tidak stabil.',
    'suhu_count': 'Jumlah data populasi (batch) yang membentuk statistik ini.',
    'suhu_m2': 'Variabel matematika Welford (Sum of Squares) untuk mengupdate kalibrasi secara efisien.',
    'suhu_lower_bound': 'BATAS BAWAH (Threshold). Jika deviasi aktual lebih KECIL (lebih minus) dari angka ini, anomali tercatat.',
    'suhu_upper_bound': 'BATAS ATAS (Threshold). Jika deviasi aktual lebih BESAR dari angka ini, anomali tercatat.',
    
    'heat_mean': 'Rata-rata deviasi durasi Heating.',
    'heat_stddev': 'Standar Deviasi durasi Heating.',
    'heat_lower_bound': 'BATAS BAWAH durasi Heating. (Terlalu cepat).',
    'heat_upper_bound': 'BATAS ATAS durasi Heating. (Terlalu lama).',
    
    'keep_mean': 'Rata-rata deviasi durasi Keeping.',
    'keep_stddev': 'Standar Deviasi durasi Keeping.',
    'keep_lower_bound': 'BATAS BAWAH durasi Keeping. (Terlalu cepat).',
    'keep_upper_bound': 'BATAS ATAS durasi Keeping. (Terlalu lama).',
    
    'cool_mean': 'Rata-rata deviasi durasi Cooling.',
    'cool_stddev': 'Standar Deviasi durasi Cooling.',
    'cool_lower_bound': 'BATAS BAWAH durasi Cooling. (Terlalu cepat).',
    'cool_upper_bound': 'BATAS ATAS durasi Cooling. (Terlalu lama).',
}

class AnomalyThresholdMasterForm(forms.ModelForm):
    class Meta:
        model = AnomalyThresholdMaster
        fields = '__all__'
        help_texts = master_help_texts

@admin.register(AnomalyThresholdMaster)
class AnomalyThresholdMasterAdmin(admin.ModelAdmin):
    form = AnomalyThresholdMasterForm
    list_display = ('machine', 'program', 'update_mode', 'last_calibrated_at', 'view_chart')

    def view_chart(self, obj):
        from django.utils.safestring import mark_safe
        return mark_safe(f'<a href="/calibration-chart/master/{obj.id}/" target="_blank" class="button" style="background-color: #2196F3; color: white; font-weight: bold; padding: 5px 10px; border-radius: 4px;">Lihat Grafik</a>')
    view_chart.short_description = 'Visualisasi'

    list_filter = ('update_mode', 'machine')
    search_fields = ('machine__code', 'program__nama')
    
    fieldsets = (
        (None, {
            'description': mark_safe(MASTER_GUIDE),
            'fields': ('machine', 'program', 'update_mode')
        }),
        ('Data Statistik Suhu', {
            'fields': ('suhu_mean', 'suhu_stddev', 'suhu_count', 'suhu_m2', 'suhu_lower_bound', 'suhu_upper_bound')
        }),
        ('Data Statistik Heat', {
            'fields': ('heat_mean', 'heat_stddev', 'heat_count', 'heat_m2', 'heat_lower_bound', 'heat_upper_bound')
        }),
        ('Data Statistik Keep', {
            'fields': ('keep_mean', 'keep_stddev', 'keep_count', 'keep_m2', 'keep_lower_bound', 'keep_upper_bound')
        }),
        ('Data Statistik Cool', {
            'fields': ('cool_mean', 'cool_stddev', 'cool_count', 'cool_m2', 'cool_lower_bound', 'cool_upper_bound')
        }),
    )

PROPOSAL_GUIDE = """
<div style="padding: 10px; background: #fff3e0; border-left: 5px solid #ff9800; margin-bottom: 15px;">
    <strong>Panduan Proposal Kalibrasi (Dry-Run):</strong><br>
    Ini adalah usulan angka baru dari sistem (berdasarkan kalibrasi).<br>
    <ul>
        <li>Pilih proposal dan gunakan fitur <em>Action</em> untuk <strong>APPROVE</strong> jika diperlukan.</li>
        <li>Perhatikan <strong>Warning Message</strong>: peringatan <em>Self-locking</em> berarti batas usulan ini mungkin membuang lebih dari 30% data asli.</li>
    </ul>
</div>
"""

proposal_help_texts = {
    'new_data_count': 'Jumlah data normal baru minggu ini yang berhasil memperbarui statistik.',
    'outlier_rejected_count': 'Jumlah data minggu ini yang DITOLAK (dibuang) karena melampaui batas ekstrim.',
    'is_warning': 'Menandakan jika ada resiko batas ini salah kalibrasi (terlalu sempit).',
    'status': 'Ubah ke APPROVED untuk menerapkan angka-angka ini ke Master.',
}

class AnomalyThresholdProposalForm(forms.ModelForm):
    class Meta:
        model = AnomalyThresholdProposal
        fields = '__all__'
        help_texts = proposal_help_texts

@admin.register(AnomalyThresholdProposal)
class AnomalyThresholdProposalAdmin(admin.ModelAdmin):
    form = AnomalyThresholdProposalForm
    list_display = ('master', 'week_start_date', 'week_end_date', 'status', 'is_warning', 'created_at', 'view_chart')

    def view_chart(self, obj):
        from django.utils.safestring import mark_safe
        return mark_safe(f'<a href="/calibration-chart/proposal/{obj.id}/" target="_blank" class="button" style="background-color: #ff9800; color: white; font-weight: bold; padding: 5px 10px; border-radius: 4px;">Lihat Grafik</a>')
    view_chart.short_description = 'Visualisasi Usulan'

    list_filter = ('status', 'is_warning')
    search_fields = ('master__machine__code', 'master__program__nama')
    readonly_fields = ('processed_at', 'created_at')
    
    fieldsets = (
        (None, {
            'description': mark_safe(PROPOSAL_GUIDE),
            'fields': ('master', 'week_start_date', 'week_end_date', 'status', 'is_warning', 'warning_message', 'new_data_count', 'outlier_rejected_count')
        }),
        ('Usulan Batas Suhu', {
            'fields': ('suhu_mean_new', 'suhu_stddev_new', 'suhu_lower_bound_new', 'suhu_upper_bound_new')
        }),
        ('Usulan Batas Heat', {
            'fields': ('heat_mean_new', 'heat_stddev_new', 'heat_lower_bound_new', 'heat_upper_bound_new')
        }),
        ('Usulan Batas Keep', {
            'fields': ('keep_mean_new', 'keep_stddev_new', 'keep_lower_bound_new', 'keep_upper_bound_new')
        }),
        ('Usulan Batas Cool', {
            'fields': ('cool_mean_new', 'cool_stddev_new', 'cool_lower_bound_new', 'cool_upper_bound_new')
        }),
        ('Meta', {
            'fields': ('created_at', 'processed_at')
        })
    )

RULE_GUIDE = """
<div style="padding: 10px; background: #e8f5e9; border-left: 5px solid #4caf50; margin-bottom: 15px;">
    <strong>Panduan Konfigurasi Hard-Limit (Rules):</strong><br>
    Aturan ekstrem paksa yang berlaku untuk semua mesin.
</div>
"""

@admin.register(AnomalyRuleConfig)
class AnomalyRuleConfigAdmin(admin.ModelAdmin):
    list_display = ('rule_code', 'rule_type', 'adds_flag', 'forces_severity', 'is_active')
    list_filter = ('rule_type', 'forces_severity', 'is_active')
    search_fields = ('rule_code', 'adds_flag')
    
    fieldsets = (
        (None, {
            'description': mark_safe(RULE_GUIDE),
            'fields': ('rule_code', 'rule_type', 'parameter_json', 'adds_flag', 'forces_severity', 'is_active')
        }),
    )

SEVERITY_GUIDE = """
<div style="padding: 10px; background: #fce4ec; border-left: 5px solid #e91e63; margin-bottom: 15px;">
    <strong>Panduan Level Keparahan:</strong><br>
    Syarat jumlah flag untuk masuk ke keparahan tertentu.
</div>
"""

@admin.register(AnomalySeverityLevel)
class AnomalySeverityLevelAdmin(admin.ModelAdmin):
    list_display = ('severity_name', 'min_flags_required')
    ordering = ('-min_flags_required',)
    
    fieldsets = (
        (None, {
            'description': mark_safe(SEVERITY_GUIDE),
            'fields': ('severity_name', 'min_flags_required')
        }),
    )


# --------------------------------------------------------------------------
# PRODUCTION PHYSICAL REPORTS ADMIN (ROLL OFF, SMCH, STENTER EHWA)
# --------------------------------------------------------------------------
from .admin_production_reports import *
