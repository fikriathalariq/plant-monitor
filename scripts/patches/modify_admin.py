import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import re

with open('monitoring/admin.py', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Remove DyeingIdentityInline class
# The inline class starts at 'class DyeingIdentityInline(admin.StackedInline):'
# and ends right before 'class ProcessStatusFilter(admin.SimpleListFilter):'
idx_start = content.find('class DyeingIdentityInline(admin.StackedInline):')
idx_end = content.find('class ProcessStatusFilter(admin.SimpleListFilter):')
if idx_start != -1 and idx_end != -1:
    content = content[:idx_start] + content[idx_end:]

# 2. Add action_isi_identitas to list_display
content = content.replace('"identity_status",\n        "status_display",', '"identity_status",\n        "action_isi_identitas",\n        "status_display",')

# 3. Remove inlines = [DyeingIdentityInline]
content = content.replace('    inlines = [DyeingIdentityInline]\n    ', '')

# 4. Add action_isi_identitas method
action_method = '''    def action_isi_identitas(self, obj):
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
            'machine': obj.machine_id,
            'start_time_snapshot': obj.start_time.strftime("%Y-%m-%d %H:%M:%S") if obj.start_time else "",
        })
        return format_html('<a class="button" href="{}?{}" style=\"background-color:#79aec8;color:white;padding:5px 10px;border-radius:4px;font-weight:bold;\">+ ID</a>', url, params)
    action_isi_identitas.short_description = "Form ID"

'''
content = content.replace('    def identity_status(self, obj):', action_method + '    def identity_status(self, obj):')

# 5. Add DyeingIdentityAdmin class at the end
admin_class = '''
@admin.register(DyeingIdentity)
class DyeingIdentityAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'machine', 'process_start', 'nomor_order', 'batch')
    list_filter = ('machine', 'created_at')
    search_fields = ('nomor_order', 'batch', 'artikel_kain', 'keterangan')
    
    # Sembunyikan relasi asli agar tidak dimanipulasi manual
    exclude = ('dyeing_process',)
    
    fieldsets = (
        ("📝 Identitas Order", {
            "fields": (
                "nomor_order", "artikel_kain", "batch",
                "kode_buyer", "program",
            ),
        }),
        ("🔢 Detail Produksi", {
            "fields": (
                "jumlah_meter", "nomor_warna", "nomor_desain",
                "jumlah_pcs", "handling_quality", "jenis_proses",
                "keterangan",
            ),
        }),
        ("⚓ Anchors (Terisi Otomatis, Jangan Diubah)", {
            "fields": ("machine", "start_time_snapshot"),
            "classes": ("collapse",),
            "description": "Jangkar mesin dan jam mulai digunakan agar data ini selalu menempel di batch yang tepat walau saat proses re-kalkulasi."
        }),
    )
    
    def process_start(self, obj):
        if obj.start_time_snapshot:
            from django.utils import timezone
            local = timezone.localtime(obj.start_time_snapshot)
            return local.strftime("%d %b %Y, %H:%M")
        return "-"
    process_start.short_description = "Start Time"

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        if 'machine' in request.GET:
            initial['machine'] = request.GET['machine']
        if 'start_time_snapshot' in request.GET:
            try:
                from datetime import datetime
                # Parse str to datetime. Since format is '%Y-%m-%d %H:%M:%S', it's naive, timezone.make_aware might be needed.
                naive_dt = datetime.strptime(request.GET['start_time_snapshot'], "%Y-%m-%d %H:%M:%S")
                from django.utils import timezone
                initial['start_time_snapshot'] = timezone.make_aware(naive_dt) if timezone.is_naive(naive_dt) else naive_dt
            except Exception:
                pass
        return initial

    def save_model(self, request, obj, form, change):
        super().save_model(request, obj, form, change)
        
        # Logika Re-link Kustom anti race-condition
        if not obj.dyeing_process and obj.machine and obj.start_time_snapshot:
            from monitoring.models import DyeingProcess
            from datetime import timedelta
            
            match = DyeingProcess.objects.filter(
                machine=obj.machine,
                start_time__range=(
                    obj.start_time_snapshot - timedelta(minutes=15),
                    obj.start_time_snapshot + timedelta(minutes=15)
                )
            ).first()
            if match:
                obj.dyeing_process = match
                obj.save(update_fields=['dyeing_process'])
'''
content += admin_class

with open('monitoring/admin.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done!')
