import requests
import logging
import time
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.models import Machine, MachineStatusSnapshot
from monitoring.utils.manual_status import apply_manual_status_change, SOURCE_SYNC_COMMAND
from django.db import transaction

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = "Sync manual machine status from Google Apps Script"

    # URL Google Apps Script
    GOOGLE_SCRIPT_URL = (
        "https://script.googleusercontent.com/macros/echo?"
        "user_content_key=AehSKLitR9Yk3WiB1Lc59aKz1OPeaL6oFITedbjE2IVbmT30jqKhBd-U3oa-K6NG22hTEhZ7eXqOhHpAd1AZ0jjxciPq8Avo1GbceJWUUXOpf614Z4_UIBDU18ne5d2Pen70qOw3ZjrkBGnGLXd0KrLM8-8GwfyVYbwl8U3wD-4-TVtM4Kd4lrUxCttxrvPOdAbzECF2iliLUg9jSmPJEHMvTSxCu22Nwsh8vgxbAJAi6xg9dbhKGLnsio5WFymUQVDv_2hHai2_deSO3ucnkJHSZ9jz1BUccUQIqzhJZx8m&lib=MhaFiomj2SEjKxGGKt4GlbM8ui7aP0xHH"
    )

    # MAPPING: JSON Key -> Database Machine.code
    MACHINE_CODE_MAPPING = {
        # === JET RELAX (JR) ===
        "JR_1": "JR_01", "JR_2": "JR_02", "JR_3": "JR_03", "JR_4": "JR_04",
        "JR_5": "JR_05", "JR_6": "JR_06", "JR_7": "JR_07", "JR_8": "JR_08",
        "JR_9": "JR_09", "JR_10": "JR_10", "JR_11": "JR_11", "JR_12": "JR_12", "JR_13": "JR_13",
        
        # === JET DYEING (JD) ===
        "JD_1": "JD_01", "JD_3": "JD_03", "JD_4": "JD_04", "JD_5": "JD_05",
        "JD_6": "JD_06", "JD_7": "JD_07", "JD_8": "JD_08", "JD_9": "JD_09",
        "JD_10": "JD_10", "JD_11": "JD_11", "JD_12": "JD_12", "JD_13": "JD_13",
        "JD_14": "JD_14", "JD_15": "JD_15", "JD_16": "JD_16", "JD_18": "JD_18", "JD_19": "JD_19",
        
        # === JET DYEING PRINTING ===
        "JD_3_Printing": "ZET_03", "JD_4_Printing": "ZET_04", "JD_5_Printing": "ZET_05",
        "JD_6_Printing": "ZET_06", "JD_7_Printing": "ZET_07", "JD_10_Printing": "ZET_10",
        "JD_11_Printing": "ZET_11",
        
        # === ZETTEX (ZET) ===
        "ZET_1": "ZET_01", "ZET_2": "ZET_02", "ZET_8": "ZET_08", "ZET_9": "ZET_09", "ZET_12": "ZET_12",
        
        # === WATER SETTING ===
        "Water_Setting_1_PRC": "WETSET_PRC_01", "Water_Setting_2_PRC": "WETSET_PRC_02",
        "Water_Setting_1_Printing": "WETSET_01", "Water_Setting_2_Printing": "WETSET_02",
        
        # === CDR SAMIL ===
        "CDR_SAMIL_Reaction_Chamber": "CDR_SAMIL",
        "CDR_SAMIL_Washing_Chamber": "CDR_SAMIL_WASHING",
        "CDR_SAMIL_Drying_Cylinder": "CDR_SAMIL_DRYING",
        
        # === SSD CYLINDER DRYER ===
        "SSD_1_Cylinder_Dryer": "SSD_01", "SSD_2_Cylinder_Dryer": "SSD_02",
        
        # === CDR ===
        "CDR_Reaction_Chamber": "CDR_PRT",
        "CDR_Washing_Chamber": "CDR_WASHING",
        "CDR_Cylinder_Dryer": "CDR_Cylinder_Dryer",
        
        # === DRYER ===
        "Dryer_Uap_1_Samurai": "DRYERUAP_01",
        
        # === WASHING & OTHERS ===
        "Washing_Printing": "WASHING_PRT",
        "SMCH": "SMCH",
        "Babcock": "BABCOCK",
    }

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Simulate sync tanpa mengubah data di database',
        )
        parser.add_argument(
            '--loop',
            action='store_true',
            help='Jalankan terus menerus setiap interval waktu (mode daemon)',
        )
        parser.add_argument(
            '--interval',
            type=int,
            default=60,
            help='Interval dalam detik untuk mode loop (default: 60)',
        )

    def handle(self, *args, **options):
        dry_run = options.get('dry_run', False)
        loop_mode = options.get('loop', False)
        interval = options.get('interval', 60)
        
        if dry_run:
            self.stdout.write(self.style.WARNING("[DRY RUN] Tidak ada data yang akan diubah"))

        if loop_mode:
            self.stdout.write(self.style.SUCCESS(f"Starting sync in LOOP mode (Interval: {interval}s)..."))
            self.stdout.write("Press CTRL+C to stop.")
            try:
                while True:
                    self.sync_process(dry_run)
                    self.stdout.write(f"[WAIT] Sleeping for {interval} seconds...\n" + "-"*40)
                    time.sleep(interval)
            except KeyboardInterrupt:
                self.stdout.write(self.style.WARNING("\n[STOP] Loop dihentikan oleh user."))
        else:
            self.sync_process(dry_run)

    def sync_process(self, dry_run):
        try:
            current_timestamp = timezone.now().strftime('%Y-%m-%d %H:%M:%S')
            self.stdout.write(f"[{current_timestamp}] Fetching data from Google Apps Script...")
            
            response = requests.get(self.GOOGLE_SCRIPT_URL, timeout=10)
            response.raise_for_status()
            
            data = response.json()
            machine_status_data = self._extract_machine_status(data)

            if not machine_status_data:
                # Ubah jadi debug atau info agar tidak spamming log warning jika memang kosong
                self.stdout.write("[INFO] Tidak ada data status mesin yang valid untuk diupdate.")
                return

            updated_count, skipped_count = self._sync_to_database(machine_status_data, dry_run=dry_run)

            if not dry_run:
                self._create_snapshot()

            self.stdout.write(self.style.SUCCESS(
                f"[DONE] Updated: {updated_count}, Skipped: {skipped_count}"
            ))

        except requests.RequestException as e:
            self.stdout.write(self.style.ERROR(f"[ERROR] Connection error: {e}"))
            logger.error(f"Error fetching Google Script data: {e}")
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[ERROR] Unexpected error: {e}"))
            logger.exception("Unexpected error in sync_manual_machines")

    def _extract_machine_status(self, data):
        """
        Extract status dari JSON.
        Mendukung:
        - Boolean String: "true" -> True, "false" -> False
        - Custom Status (Dryer dll): "Pemanasan", "Produksi" -> True
        - Custom Status Lain: "Standby", "Off", dll -> False
        """
        machine_status = {}
        
        # Daftar status yang dianggap mesin sedang berjalan (Running = True)
        # Gunakan huruf kecil semua untuk pencocokan case-insensitive
        running_keywords = ["true", "pemanasan", "produksi"]
        
        # Daftar status yang dianggap mesin berhenti (Stop = False)
        # Sebenarnya semua yang tidak masuk running akan dianggap false, 
        # tapi kita filter agar data sampah tidak masuk.
        stop_keywords = ["false", "standby", "off", "stop", "mati"]

        for key, value in data.items():
            if not isinstance(value, str):
                continue
            
            val_lower = value.strip().lower()
            
            if val_lower in running_keywords:
                machine_status[key] = True
            elif val_lower in stop_keywords:
                machine_status[key] = False
                
        return machine_status

    def _sync_to_database(self, machine_status_data, dry_run=False):
        updated_count = 0
        skipped_count = 0
        current_time = timezone.now()

        for json_key, is_running in machine_status_data.items():
            db_machine_code = self.MACHINE_CODE_MAPPING.get(json_key)
            
            if not db_machine_code:
                skipped_count += 1
                continue
            
            try:
                machine = Machine.objects.get(
                    code=db_machine_code,
                    operation_mode="MANUAL",
                    is_active=True
                )
            except Machine.DoesNotExist:
                skipped_count += 1
                continue

            # Konversi boolean ke String status untuk Database
            new_manual_status = "Running" if is_running else "Stop"
            new_last_status = "Running" if is_running else "Stop"

            status_changed = (
                machine.manual_status != new_manual_status or
                machine.last_status != new_last_status
            )

            if dry_run:
                if status_changed:
                    self.stdout.write(f"   [CHANGE] {db_machine_code}: {machine.manual_status} -> {new_manual_status}")
                    updated_count += 1
                else:
                    skipped_count += 1
            else:
                if status_changed:
                    with transaction.atomic():
                        apply_manual_status_change(
                            machine,
                            new_manual_status,
                            SOURCE_SYNC_COMMAND,
                            user=None,
                        )
                    
                    self.stdout.write(f"   [UPDATED] {db_machine_code}: {new_manual_status}")
                    updated_count += 1
                else:
                    skipped_count += 1

        return updated_count, skipped_count

    def _create_snapshot(self):
        try:
            current_time = timezone.now()
            snapshot_time = current_time.replace(second=0, microsecond=0)
            
            machines = Machine.objects.filter(is_active=True).only(
                'code', 'operation_mode', 'manual_status', 'last_status', 'last_thermal_status'
            )
            
            snapshot_data = {}
            for machine in machines:
                if machine.operation_mode == "MANUAL":
                    status = machine.manual_status or "Stop"
                    detail = machine.manual_status or "Stop"
                else:
                    status = machine.last_status or "Offline"
                    detail = machine.last_thermal_status or "OFFLINE"
                
                snapshot_data[machine.code] = {
                    "status": status,
                    "detail": detail,
                    "mode": machine.operation_mode
                }
            
            MachineStatusSnapshot.objects.update_or_create(
                timestamp=snapshot_time,
                defaults={"snapshot_data": snapshot_data}
            )
            
        except Exception as e:
            self.stdout.write(self.style.ERROR(f"[ERROR] Snapshot failed: {e}"))