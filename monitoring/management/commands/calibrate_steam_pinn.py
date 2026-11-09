import argparse
import json
from django.core.management.base import BaseCommand
from monitoring.services.steam_calibration_runner import SteamCalibrationRunner
from monitoring.models import MachinePhysicsProfile, Machine

class Command(BaseCommand):
    help = 'Kalibrasi PINN Steam Predictor (ODE physics parameters & NN weights)'

    def add_arguments(self, parser):
        parser.add_argument('--machine', type=str, required=True, help='Machine code')
        parser.add_argument('--group', type=str, default='DEFAULT', help='Machine group')
        parser.add_argument('--actuals', type=str, help='JSON dict of batch_num: actual_kg')
        
        # Seeding options
        parser.add_argument('--seed-only', action='store_true', help='Hanya seed profile tanpa kalibrasi/train')
        parser.add_argument('--meq', type=float, help='Meq parameter for seed')
        parser.add_argument('--uloss', type=float, help='Uloss parameter for seed')
        parser.add_argument('--p-set', type=float, help='P_set parameter for seed')
        parser.add_argument('--k-drop', type=float, help='k_drop parameter for seed')
        parser.add_argument('--n-exp', type=float, help='n_exp parameter for seed')
        parser.add_argument('--mae', type=float, help='Calibration MAE %%')
        parser.add_argument('--mark-best', action='store_true', help='Tandai sebagai best of group')

        # Execution options
        parser.add_argument('--train-weights', action='store_true', help='Train and save weights after calibration')
        parser.add_argument('--predict-historical', action='store_true', help='Run 3-layer predict for all historical batches')

    def handle(self, *args, **options):
        runner = SteamCalibrationRunner()
        machine_code = options['machine']
        group = options['group']
        
        try:
            machine = Machine.objects.get(code=machine_code)
        except Machine.DoesNotExist:
            self.stdout.write(self.style.ERROR(f"Machine {machine_code} not found"))
            return

        # 1. Seeding mode
        if options['seed_only']:
            if None in [options['meq'], options['uloss'], options['p_set'], options['k_drop'], options['n_exp']]:
                self.stdout.write(self.style.ERROR("Seed mode requires --meq, --uloss, --p-set, --k-drop, --n-exp"))
                return
            
            physics = {
                'meq': options['meq'], 'uloss': options['uloss'],
                'p_set': options['p_set'], 'k_drop': options['k_drop'], 'n_exp': options['n_exp']
            }
            
            profile = runner.seed_profile(
                machine_code, physics, group, 
                is_best=options['mark_best'], 
                mae_pct=options['mae']
            )
            self.stdout.write(self.style.SUCCESS(f"Seeded profile for {machine_code} (group={group}, best={options['mark_best']})"))
            
        # 2. Calibration mode
        elif options['actuals']:
            actuals = json.loads(options['actuals'])
            self.stdout.write(f"Calibrating {machine_code} with batches: {list(actuals.keys())}...")
            
            res = runner.run_for_machine(machine_code, actuals, machine_group=group)
            self.stdout.write(self.style.SUCCESS(f"Calibration done! MAE: {res['mae_pct']:.2f}%"))
            
            if options['train_weights']:
                self.stdout.write(f"Training weights...")
                path = runner.train_and_save_weights(machine_code, actuals)
                self.stdout.write(self.style.SUCCESS(f"Weights saved to {path}"))
                
        else:
            self.stdout.write(self.style.ERROR("Provide either --seed-only args or --actuals for calibration"))
            return
            
        # 3. Predict Historical
        if options['predict_historical']:
            self.stdout.write("Predicting historical batches...")
            count = runner.predict_all_historical(machine_code)
            self.stdout.write(self.style.SUCCESS(f"Predicted {count} batches for {machine_code}"))

