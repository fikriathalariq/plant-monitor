import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import sys

new_models = '''
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
'''

with open('monitoring/models.py', 'a', encoding='utf-8') as f:
    f.write(new_models)

print('Models appended.')
