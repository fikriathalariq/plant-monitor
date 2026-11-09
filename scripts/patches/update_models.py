import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

with open('monitoring/models.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_content = content.replace('''    kalman_grad_x = models.FloatField(null=True, blank=True, help_text="Kalman gradient estimate")

    class Meta:
        ordering = ['-timestamp']
        unique_together = [['machine', 'timestamp']]
        indexes = [
            models.Index(fields=['machine', 'timestamp']),
            models.Index(fields=['thermal_state']),
        ]''', '''    kalman_grad_x = models.FloatField(null=True, blank=True, help_text="Kalman gradient estimate")

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
            models.Index(fields=['machine', 'timestamp']),
            models.Index(fields=['thermal_state']),
            models.Index(fields=['machine', '-timestamp'], name='idx_log_machine_ts_desc'),
            models.Index(fields=['machine', 'timestamp', 'data_quality'], name='idx_log_machine_ts_dq'),
        ]''')

with open('monitoring/models.py', 'w', encoding='utf-8') as f:
    f.write(new_content)
