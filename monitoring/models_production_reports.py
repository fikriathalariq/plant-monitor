import re
from decimal import Decimal
from django.db import models
from django.utils import timezone
from .models import Machine

# --------------------------------------------------------------------------
# UTILITY HELPER: CANONICALIZER FOR ORDER AND BATCH
# --------------------------------------------------------------------------
def clean_canonical_order(raw_order: str) -> str:
    """Membersihkan nomor order variatif menjadi format canonical standar (XX-XXX-XX)."""
    if not raw_order:
        return ""
    val = str(raw_order).strip().replace('"', '').replace("'", "")
    
    match = re.search(r"(\d{2})[-/\s]+(\d{3})[-/\s]*(\d{2})?", val)
    if match:
        p1, p2, p3 = match.groups()
        p3 = p3 if p3 else "00"
        return f"{p1}-{p2}-{p3}"
    
    match_short = re.match(r"^(\d{3})$", val)
    if match_short:
        return f"45-{match_short.group(1)}-00"
        
    match_dash = re.search(r"[-/\s]+(\d{3})[-/\s]*(\d{2})?", val)
    if match_dash:
        p2, p3 = match_dash.groups()
        p3 = p3 if p3 else "00"
        return f"45-{p2}-{p3}"
        
    return val


def clean_canonical_batch(raw_batch: str) -> str:
    """Membersihkan nomor batch variatif menjadi nomor batch inti / canonical."""
    if not raw_batch:
        return ""
    val = str(raw_batch).strip()
    
    if "," in val:
        parts = [clean_canonical_batch(p) for p in val.split(",")]
        return ", ".join(parts)
        
    clean = re.sub(r"^(?:[1iIhH0-9])[\s\.\-_/]+", "", val)
    if clean:
        return clean.strip()
    return val.strip()

# --------------------------------------------------------------------------
# 1. ROLL OFF (DEPT. SCOURING)
# --------------------------------------------------------------------------
class RollOffReport(models.Model):
    production_date = models.DateField(default=timezone.now, db_index=True)
    shift = models.CharField(max_length=50)
    operator_name = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Laporan Roll Off"
        verbose_name_plural = "Laporan Roll Off"
        ordering = ["-production_date", "shift"]

    def __str__(self):
        return f"Roll Off {self.production_date} - Shift {self.shift}"

class RollOffItem(models.Model):
    report = models.ForeignKey(RollOffReport, on_delete=models.CASCADE, related_name="items")
    line_number = models.IntegerField(default=1)
    no_order = models.CharField(max_length=50, blank=True)
    grade = models.CharField(max_length=20, blank=True)
    artikel = models.CharField(max_length=100, blank=True)
    no_batch = models.CharField(max_length=50, blank=True)
    standar_lot = models.IntegerField(null=True, blank=True)
    roll_off_pcs = models.IntegerField(default=0)
    jumlah_yard = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    keterangan = models.TextField(blank=True)

    class Meta:
        ordering = ["line_number"]

class RollOffEvent(models.Model):
    report = models.ForeignKey(RollOffReport, on_delete=models.CASCADE, related_name="events")
    jam_mulai = models.TimeField()
    jam_selesai = models.TimeField(null=True, blank=True)
    jenis_event = models.CharField(max_length=100)
    keterangan = models.TextField(blank=True)

    class Meta:
        ordering = ["jam_mulai"]


# --------------------------------------------------------------------------
# 2. BO HANAYAMA - SMCH (DEPT. SCOURING)
# --------------------------------------------------------------------------
class SmchReport(models.Model):
    production_date = models.DateField(default=timezone.now, db_index=True)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True)
    regu = models.CharField(max_length=20, blank=True)
    waktu_shift = models.CharField(max_length=20, blank=True)
    operator_name = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = "Laporan BO Hanayama (SMCH)"
        verbose_name_plural = "Laporan BO Hanayama (SMCH)"
        ordering = ["-production_date", "regu"]

    def __str__(self):
        return f"SMCH {self.production_date} - Regu {self.regu}"

class SmchItem(models.Model):
    report = models.ForeignKey(SmchReport, on_delete=models.CASCADE, related_name="items")
    line_number = models.IntegerField(default=1)
    no_order = models.CharField(max_length=50, blank=True)
    artikel = models.CharField(max_length=100, blank=True)
    no_batch = models.CharField(max_length=50, blank=True)
    pcs = models.IntegerField(null=True, blank=True)
    yard = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    temp_celsius = models.FloatField(default=0)
    speed_m_min = models.FloatField(default=0)
    jam_mulai = models.TimeField(null=True, blank=True)
    jam_selesai = models.TimeField(null=True, blank=True)
    keterangan = models.TextField(blank=True)

    class Meta:
        ordering = ["line_number"]

class SmchEvent(models.Model):
    report = models.ForeignKey(SmchReport, on_delete=models.CASCADE, related_name="events")
    jam_mulai = models.TimeField()
    jam_selesai = models.TimeField(null=True, blank=True)
    jenis_event = models.CharField(max_length=100)
    keterangan = models.TextField(blank=True)

    class Meta:
        ordering = ["jam_mulai"]


# --------------------------------------------------------------------------
# 3. REALISASI PRODUKSI FINISHING (MONFONG & EHWA)
# --------------------------------------------------------------------------
class FinishingReport(models.Model):
    tanggal = models.DateField(default=timezone.now, db_index=True)
    machine = models.ForeignKey(Machine, on_delete=models.SET_NULL, null=True, blank=True)
    proses = models.CharField(max_length=100, blank=True)
    regu = models.CharField(max_length=20, blank=True)
    waktu_shift = models.CharField(max_length=20, blank=True)
    operator = models.CharField(max_length=100, blank=True)
    total_pcs = models.IntegerField(default=0)
    total_counter_yard = models.DecimalField(max_digits=12, decimal_places=2, default=0, verbose_name="Total Counter (Yard)")

    @property
    def auto_total_pcs(self):
        total = self.items.aggregate(models.Sum('jml_pcs'))['jml_pcs__sum']
        return total or 0

    @property
    def auto_total_counter(self):
        total = self.items.aggregate(models.Sum('counter_m'))['counter_m__sum']
        return total or Decimal("0.00")

    @property
    def auto_total_counter_yard(self):
        total = self.items.aggregate(models.Sum('counter_yard'))['counter_yard__sum']
        return total or Decimal("0.00")

    def recalculate_timeline(self):
        from datetime import datetime, timedelta, time
        
        # 1. Tentukan Anchor Start Time berdasarkan shift
        shift_upper = (self.waktu_shift or "").upper()
        if "B" in shift_upper or "SIANG" in shift_upper:
            start_hour, start_min = 14, 0
        elif "C" in shift_upper or "MALAM" in shift_upper:
            start_hour, start_min = 22, 0
        else: # Default Pagi / A
            start_hour, start_min = 6, 0
            
        anchor_dt = datetime.combine(self.tanggal, time(start_hour, start_min))
        
        items = list(self.items.all().order_by('line_number'))
        events = list(self.events.all().order_by('jam_mulai'))
        
        if not items and not events:
            return
            
        # Helper konversi jam ke datetime, mengatasi pergantian hari (melewati tengah malam)
        def to_datetime(t, base_dt):
            dt = datetime.combine(base_dt.date(), t)
            # Jika shift mulai malam (misal 22:00) dan waktu saat ini pagi (<12:00), maka tambah 1 hari
            if base_dt.hour >= 18 and dt.hour < 12:
                dt += timedelta(days=1)
            # Jika shift mulai pagi/siang dan waktu malam/besoknya.
            elif base_dt.hour < 12 and dt.hour < base_dt.hour:
                dt += timedelta(days=1)
            return dt

        # Parsing events
        parsed_events = []
        for e in events:
            if not e.jam_mulai: continue
            edt_start = to_datetime(e.jam_mulai, anchor_dt)
            if e.jam_selesai:
                edt_end = to_datetime(e.jam_selesai, anchor_dt)
                if edt_end < edt_start:
                    edt_end += timedelta(days=1)
            else:
                edt_end = edt_start
            
            parsed_events.append({'start': edt_start, 'end': edt_end})
            
        current_dt = anchor_dt
        items_to_update = []
        
        for item in items:
            # 2. Fast-forward waktu JIKA mesin sedang dalam masa Event/downtime antar-kain
            while True:
                active_events = [e for e in parsed_events if e['start'] <= current_dt < e['end']]
                if not active_events:
                    break
                # Loncat ke jam selesainya event yang sedang aktif ini
                current_dt = max([e['end'] for e in active_events])

            dt_start = current_dt.replace(microsecond=0)
            item.jam_mulai = dt_start.time()
            
            if item.speed_m_min and item.speed_m_min > 0 and item.counter_m:
                # 3. Bulatkan durasi murni ke menit terdekat agar tidak ada overlap detik
                remaining_mins = int(round(float(item.counter_m) / float(item.speed_m_min)))
            else:
                remaining_mins = 0
            
            while remaining_mins > 0:
                target_dt = current_dt + timedelta(minutes=remaining_mins)
                
                # Cari event yang overlap dengan rentang [current_dt, target_dt)
                overlapping = [e for e in parsed_events if e['start'] < target_dt and e['end'] > current_dt]
                if not overlapping:
                    current_dt = target_dt
                    remaining_mins = 0
                else:
                    overlapping.sort(key=lambda x: x['start'])
                    first_ev = overlapping[0]
                    
                    if first_ev['start'] <= current_dt:
                        # Sedang berada di dalam event, lompat ke akhir event
                        current_dt = max(current_dt, first_ev['end'])
                    else:
                        # Jalankan mesin sampai event mulai
                        run_dur = int(round((first_ev['start'] - current_dt).total_seconds() / 60.0))
                        remaining_mins -= run_dur
                        current_dt = first_ev['start']
                        
            dt_end = current_dt.replace(microsecond=0)
            item.jam_selesai = dt_end.time()
            item.durasi_menit = int(round((dt_end - dt_start).total_seconds() / 60.0))
            items_to_update.append(item)
            
        if items_to_update:
            # Gunakan bulk_update agar tidak men-trigger signal save lagi (menghindari infinite loop)
            # Impor dilakukan di sini jika diperlukan, tapi kita bisa pakai `item.__class__`
            item.__class__.objects.bulk_update(items_to_update, ['jam_mulai', 'jam_selesai', 'durasi_menit'])

    class Meta:
        verbose_name = "Laporan Finishing"
        verbose_name_plural = "Laporan Finishing"
        ordering = ["-tanggal", "regu"]

    def __str__(self):
        return f"Finishing {self.tanggal} - Regu {self.regu}"

class StenterItem(models.Model):
    report = models.ForeignKey(FinishingReport, on_delete=models.CASCADE, related_name="items")
    line_number = models.IntegerField(default=1)
    no_wo_kain = models.CharField(max_length=100, blank=True)
    kain_artikel = models.CharField(max_length=100, blank=True)
    dsgn_batch = models.CharField(max_length=100, blank=True)
    cw_cft = models.CharField(max_length=100, blank=True)
    jml_pcs = models.IntegerField(null=True, blank=True)
    counter_yard = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    counter_m = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    temp_celsius = models.FloatField(default=0)
    speed_m_min = models.FloatField(default=0)
    jam_mulai = models.TimeField(null=True, blank=True)
    jam_selesai = models.TimeField(null=True, blank=True)
    durasi_menit = models.IntegerField(default=0)
    keterangan_dokumen = models.TextField(blank=True)

    def save(self, *args, **kwargs):
        if self.counter_yard is not None:
            self.counter_m = round(Decimal(str(self.counter_yard)) * Decimal('0.9144'), 2)
        super().save(*args, **kwargs)

    class Meta:
        ordering = ["line_number"]

class StenterEvent(models.Model):
    report = models.ForeignKey(FinishingReport, on_delete=models.CASCADE, related_name="events")
    jam_mulai = models.TimeField()
    jam_selesai = models.TimeField(null=True, blank=True)
    jenis_event = models.CharField(max_length=100)
    keterangan = models.TextField(blank=True)

    class Meta:
        ordering = ["jam_mulai"]

from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver

@receiver(post_save, sender=StenterItem)
@receiver(post_delete, sender=StenterItem)
def stenter_item_changed(sender, instance, **kwargs):
    if hasattr(instance, 'report') and instance.report:
        instance.report.recalculate_timeline()

@receiver(post_save, sender=StenterEvent)
@receiver(post_delete, sender=StenterEvent)
def stenter_event_changed(sender, instance, **kwargs):
    if hasattr(instance, 'report') and instance.report:
        instance.report.recalculate_timeline()
