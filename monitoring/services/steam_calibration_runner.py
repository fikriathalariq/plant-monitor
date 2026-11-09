import os, shutil, logging
import numpy as np
from django.conf import settings
from django.utils import timezone

from monitoring.models import MachinePhysicsProfile, DyeingProcess, Machine
from monitoring.services.pinn_engine import PINNSteamPredictor

logger = logging.getLogger(__name__)

PINN_MODELS_DIR = settings.BASE_DIR / 'pinn_models'

class SteamCalibrationRunner:
    
    def __init__(self):
        self.predictor = PINNSteamPredictor()

    def seed_profile(self, machine_code: str, physics: dict,
                     machine_group: str, is_best: bool = False,
                     calibrated_by: str = 'seed',
                     calibration_batches: list = None,
                     mae_pct: float = None) -> MachinePhysicsProfile:
        """
        Menyimpan parameter yang sudah diketahui tanpa kalibrasi ulang.
        Dipakai untuk 5 mesin yang sudah kita kalibrasi hari ini.
        """
        machine = Machine.objects.get(code=machine_code)
        # Nonaktifkan profil lama
        MachinePhysicsProfile.objects.filter(
            machine=machine, is_active=True).update(is_active=False)
        # Jika is_best, hapus flag best lama di grup yang sama
        if is_best:
            MachinePhysicsProfile.objects.filter(
                machine_group=machine_group,
                is_best_of_group=True).update(is_best_of_group=False)
        
        profile = MachinePhysicsProfile.objects.create(
            machine=machine,
            meq=physics['meq'], uloss=physics['uloss'],
            p_set=physics['p_set'], k_drop=physics['k_drop'],
            n_exp=physics['n_exp'],
            machine_group=machine_group,
            is_best_of_group=is_best,
            calibration_mae_pct=mae_pct,
            calibration_batches=calibration_batches or [],
            calibrated_by=calibrated_by,
            is_active=True
        )
        logger.info(f"Seeded profile for {machine_code} (group={machine_group}, best={is_best})")
        return profile

    def run_for_machine(self, machine_code: str, batch_actuals: dict,
                        machine_group: str = 'DEFAULT',
                        calibrated_by: str = 'system') -> dict:
        """
        Kalibrasi penuh: ambil data → differential_evolution → simpan profil.
        batch_actuals: {batch_number: actual_steam_kg}
        """
        machine = Machine.objects.get(code=machine_code)
        
        # Ambil data menit dari DB
        data_cache = {}
        for b_num in batch_actuals.keys():
            dp = DyeingProcess.objects.get(batch_number=b_num, machine=machine)
            times, temps, pressures, dTdt = self.predictor.get_minute_data(dp)
            if temps is not None:
                data_cache[b_num] = (times, temps, pressures, dTdt)
        
        # Kalibrasi fisika
        physics = self.predictor.calibrate_physics(
            data_cache, batch_actuals, machine_group)
        
        # Simpan profil
        profile = self.seed_profile(
            machine_code, physics, machine_group,
            calibrated_by=calibrated_by,
            calibration_batches=list(batch_actuals.keys()),
            mae_pct=physics['mae_pct']
        )
        
        return {'machine': machine_code, 'profile_id': profile.id,
                'physics': physics, 'mae_pct': physics['mae_pct']}

    def _save_weights(self, machine_code: str, weights: np.ndarray, version: str) -> str:
        """Simpan weights ke disk, return path file."""
        path = PINN_MODELS_DIR / machine_code / f'weights_{version}.npy'
        path.parent.mkdir(parents=True, exist_ok=True)
        np.save(path, weights)
        # Symlink weights_latest.npy → versi ini
        latest = path.parent / 'weights_latest.npy'
        if latest.exists(): latest.unlink()
        try:
            os.link(path, latest)
        except:
            shutil.copy(path, latest)
        return str(path)

    def train_and_save_weights(self, machine_code: str, batch_actuals: dict):
        """
        Train neural net per batch, rata-ratakan bobotnya, lalu simpan ke disk.
        """
        machine = Machine.objects.get(code=machine_code)
        profile = MachinePhysicsProfile.objects.filter(machine=machine, is_active=True).first()
        if not profile:
            raise ValueError(f"No active physics profile for {machine_code}")

        all_weights = []
        for b_num, actual_kg in batch_actuals.items():
            dp = DyeingProcess.objects.get(batch_number=b_num, machine=machine)
            pred, err, w = self.predictor.train_batch(dp, actual_kg, profile.to_physics_dict())
            if w is not None:
                all_weights.append(w)
        
        if not all_weights:
            raise ValueError("Training failed for all batches")

        avg_weights = np.mean(all_weights, axis=0)
        version = timezone.now().strftime("%Y%m%d%H%M%S")
        saved_path = self._save_weights(machine_code, avg_weights, version)
        
        profile.weights_path = saved_path
        profile.save(update_fields=['weights_path'])
        return saved_path


    def predict_single_batch_fallback(self, dyeing_process, fallback_profile) -> bool:
        """
        Prediksi uap untuk mesin tanpa profil sendiri,
        menggunakan parameter fisika dari profil Best of Group sebagai proxy.
        """
        try:
            steam_kg = self.predictor.predict(
                dyeing_process,
                fallback_profile.to_physics_dict(),
                weights=None   # Pure ODE only
            )
            ideal_steam_kg = self.predictor.predict(
                dyeing_process,
                fallback_profile.to_physics_dict(),
                weights=None,
                force_ideal=True
            )
            DyeingProcess.objects.filter(pk=dyeing_process.pk).update(
                predicted_steam_kg=round(steam_kg, 1),
                predicted_steam_best_kg=round(steam_kg, 1),
                predicted_steam_ideal_kg=round(ideal_steam_kg, 1),
                steam_computed_at=timezone.now()
            )
            logger.info(
                f"[FALLBACK] #{dyeing_process.batch_number} "
                f"({dyeing_process.machine.code}) -> "
                f"proxy via {fallback_profile.machine.code}: {steam_kg:.1f} kg"
            )
            return True
        except Exception as e:
            logger.error(f"predict_single_batch_fallback failed: {e}")
            return False

    def predict_single_batch(self, dyeing_process, own_profile,
                             best_profile=None) -> bool:
        """
        Hitung prediksi 3 lapis untuk 1 DyeingProcess dan simpan ke DB.
        """
        try:
            own_weights  = own_profile.get_weights()
            best_weights = best_profile.get_weights() if best_profile else None
            
            result = self.predictor.predict_three_layers(
                dyeing_process, own_profile, best_profile,
                own_weights, best_weights
            )
            
            DyeingProcess.objects.filter(pk=dyeing_process.pk).update(
                predicted_steam_kg=result['predicted_steam_kg'],
                predicted_steam_best_kg=result['predicted_steam_best_kg'],
                predicted_steam_ideal_kg=result['predicted_steam_ideal_kg'],
                steam_computed_at=timezone.now()
            )
            return True
        except Exception as e:
            logger.error(
                f"predict_single_batch failed #{dyeing_process.batch_number}: {e}")
            return False

    def predict_all_historical(self, machine_code: str, queryset=None) -> int:
        """Hitung prediksi 3 lapis untuk semua batch yang belum ada nilainya."""
        machine = Machine.objects.get(code=machine_code)
        own_profile = MachinePhysicsProfile.objects.filter(
            machine=machine, is_active=True).first()
        if not own_profile:
            logger.warning(f"No active profile for {machine_code}")
            return 0
        
        best_profile = MachinePhysicsProfile.get_best_for_group(
            own_profile.machine_group)
        
        if queryset is not None:
            batches = queryset
        else:
            batches = DyeingProcess.objects.filter(
                machine=machine,
                is_complete=True,
                heating_start_time__isnull=False,
                predicted_steam_kg__isnull=True
            )
        
        count = 0
        for dp in batches:
            if self.predict_single_batch(dp, own_profile, best_profile):
                count += 1
        return count
