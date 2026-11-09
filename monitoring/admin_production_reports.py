from django.contrib import admin
from .models_production_reports import (
    RollOffReport, RollOffItem, RollOffEvent,
    SmchReport, SmchItem, SmchEvent,
    FinishingReport, StenterItem, StenterEvent,
)

# --------------------------------------------------------------------------
# 1. ROLL OFF
# --------------------------------------------------------------------------
class RollOffItemInline(admin.TabularInline):
    model = RollOffItem
    extra = 1

class RollOffEventInline(admin.TabularInline):
    model = RollOffEvent
    extra = 1

@admin.register(RollOffReport)
class RollOffReportAdmin(admin.ModelAdmin):
    list_display = ('production_date', 'shift', 'operator_name')
    list_filter = ('production_date', 'shift')
    inlines = [RollOffItemInline, RollOffEventInline]


# --------------------------------------------------------------------------
# 2. SMCH
# --------------------------------------------------------------------------
class SmchItemInline(admin.TabularInline):
    model = SmchItem
    extra = 1

class SmchEventInline(admin.TabularInline):
    model = SmchEvent
    extra = 1

@admin.register(SmchReport)
class SmchReportAdmin(admin.ModelAdmin):
    list_display = ('production_date', 'machine', 'regu', 'waktu_shift', 'operator_name')
    list_filter = ('production_date', 'regu', 'waktu_shift', 'machine')
    inlines = [SmchItemInline, SmchEventInline]


# --------------------------------------------------------------------------
# 3. FINISHING
# --------------------------------------------------------------------------
class StenterItemInline(admin.TabularInline):
    model = StenterItem
    extra = 1
    readonly_fields = ('jam_mulai', 'jam_selesai', 'durasi_menit', 'counter_m')
    fields = ('line_number', 'no_wo_kain', 'kain_artikel', 'dsgn_batch', 'cw_cft', 'jml_pcs', 'counter_yard', 'counter_m', 'temp_celsius', 'speed_m_min', 'jam_mulai', 'jam_selesai', 'durasi_menit', 'keterangan_dokumen')

class StenterEventInline(admin.TabularInline):
    model = StenterEvent
    extra = 1

@admin.register(FinishingReport)
class FinishingReportAdmin(admin.ModelAdmin):
    list_display = ('tanggal', 'machine', 'regu', 'waktu_shift', 'total_pcs', 'get_auto_total_pcs', 'total_counter_yard', 'get_auto_total_counter_yard', 'get_auto_total_counter')
    list_filter = ('tanggal', 'regu', 'waktu_shift', 'machine')
    readonly_fields = ('get_auto_total_pcs', 'get_auto_total_counter_yard', 'get_auto_total_counter')
    inlines = [StenterItemInline, StenterEventInline]

    @admin.display(description='Auto Total Pcs')
    def get_auto_total_pcs(self, obj):
        return obj.auto_total_pcs

    @admin.display(description='Auto Total Yard')
    def get_auto_total_counter_yard(self, obj):
        return obj.auto_total_counter_yard

    @admin.display(description='Auto Total Meter')
    def get_auto_total_counter(self, obj):
        return obj.auto_total_counter
