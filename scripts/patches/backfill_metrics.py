import os
import sys
from pathlib import Path

# Bootstrap: ensure project root is on sys.path
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import os
import sys
import django
from datetime import timedelta

# Set up Django
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "plant_monitor.settings")
django.setup()

from django.utils import timezone
from monitoring.models import DailyPlantMetric
from monitoring.api_report import get_daily_summary

def backfill():
    print("Starting backfill for the last 7 days...")
    
    # Calculate the logical "today" date
    # In this plant, "today" starts at 06:00 today and ends at 06:00 tomorrow
    now = timezone.localtime()
    logical_now = now - timedelta(hours=6)
    logical_today = logical_now.date()
    
    # We want to backfill for the 7 days BEFORE today (so today is calculated live later)
    # Wait, the user said "tampilkan 7 hari terakhir total pemakaian uapnya (termasuk hari ini)"
    # So we can backfill up to yesterday, and let today be calculated live.
    # Or we can just calculate up to yesterday. Let's backfill for the last 10 days just to be safe.
    
    for i in range(10, 0, -1):
        target_date = logical_today - timedelta(days=i)
        date_str = target_date.strftime("%Y-%m-%d")
        print(f"Calculating for {date_str}...")
        
        try:
            # get_daily_summary returns a dict
            summary = get_daily_summary(None, date_str)
            
            steam_usage = summary.get("total_steam_usage", 0.0)
            avail_summary = summary.get("availability_summary", {})
            avg_avail = avail_summary.get("average", 0.0)
            
            metric, created = DailyPlantMetric.objects.update_or_create(
                date=target_date,
                defaults={
                    "total_steam_usage": steam_usage,
                    "average_availability": avg_avail,
                    "productivity_goal": 0.0
                }
            )
            print(f"  -> Saved: Steam={steam_usage}kg, Avail={avg_avail}% (Created: {created})")
        except Exception as e:
            print(f"  -> Error calculating for {date_str}: {e}")
            
    print("Backfill completed.")

if __name__ == "__main__":
    backfill()
