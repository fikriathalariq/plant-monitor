import datetime
from django.core.management.base import BaseCommand
from django.utils import timezone
from monitoring.models import Machine, DyeingProcess
from monitoring.services.steam_calibration_runner import SteamCalibrationRunner

class Command(BaseCommand):
    help = 'Prediksi pemakaian uap per-batch menggunakan model PINN/ODE'

    def add_arguments(self, parser):
        parser.add_argument('--machine', type=str, help='Spesifik satu mesin (kosongkan untuk semua mesin)')
        parser.add_argument('--days', type=int, default=30, help='Jumlah hari ke belakang')
        parser.add_argument('--force', action='store_true', help='Hitung ulang meski sudah ada prediksi')

    def handle(self, *args, **options):
        machine_code = options.get('machine')
        days = options.get('days')
        force = options.get('force')
        
        start_date = timezone.now() - datetime.timedelta(days=days)
        
        machines = []
        if machine_code:
            try:
                machines.append(Machine.objects.get(code=machine_code))
            except Machine.DoesNotExist:
                self.stdout.write(self.style.ERROR(f"Machine {machine_code} not found"))
                return
        else:
            # Ambil semua mesin yang punya profil fisika aktif
            machines = Machine.objects.filter(physics_group__isnull=False).distinct().order_by('code')
            
        runner = SteamCalibrationRunner()
        total_predicted = 0
        
        for machine in machines:
            self.stdout.write(f"Processing {machine.code}...")
            
            qs = DyeingProcess.objects.filter(
                machine=machine,
                is_complete=True,
                heating_start_time__isnull=False,
                start_time__gte=start_date
            )
            
            if not force:
                qs = qs.filter(predicted_steam_kg__isnull=True)
                

            from monitoring.models import MachinePhysicsProfile
            own_profile = MachinePhysicsProfile.objects.filter(machine=machine, is_active=True).first()
            if own_profile:
                count = runner.predict_all_historical(machine.code, queryset=qs)
            else:
                fallback = MachinePhysicsProfile.get_best_for_machine(machine)
                count = 0
                if fallback:
                    self.stdout.write(f"  -> Using fallback profile from {fallback.machine.code}")
                    for dp in qs:
                        if runner.predict_single_batch_fallback(dp, fallback):
                            count += 1
                else:
                    self.stdout.write(self.style.WARNING(f"  -> Skipping {machine.code} (No active profile and no fallback)"))
                    self.stdout.write(self.style.SUCCESS(f"  -> Predicted {count} batches for {machine.code}"))
            total_predicted += count
            
        self.stdout.write(self.style.SUCCESS(f"Total batches predicted: {total_predicted}"))
