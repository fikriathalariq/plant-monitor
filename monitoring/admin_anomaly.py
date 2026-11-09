from django.contrib import admin
from django import forms
from django.utils.safestring import mark_safe

from monitoring.models import (
    AnomalyThresholdMaster,
    AnomalyThresholdProposal,
    AnomalyRuleConfig,
    AnomalySeverityLevel,
)

# ═══════════════════════════════════════════════════════════════════════════════
# ANOMALY DETECTION V2 ADMIN
# ═══════════════════════════════════════════════════════════════════════════════

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
