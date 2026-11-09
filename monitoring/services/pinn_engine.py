import os
import numpy as np
from scipy.signal import savgol_filter
from scipy.optimize import differential_evolution, minimize

class PINNSteamPredictor:
    """
    Mesin PINN lengkap: kalibrasi → training → 3-layer inference.
    NN: 4 → [32 ReLU] → [32 ReLU] → 1 Softplus | N_PARAMS=1217
    """
    N_PARAMS = 32*4 + 32 + 32*32 + 32 + 32*1 + 1  # = 1217

    def __init__(self):
        self.ml_model = None
        self.ml_features = None
        self._load_ml_model()

    def _load_ml_model(self):
        import os, pickle
        model_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ml_models', 'meq_xgb.pkl')
        if os.path.exists(model_path):
            try:
                with open(model_path, 'rb') as f:
                    data = pickle.load(f)
                    self.ml_model = data['model']
                    self.ml_features = data['features']
            except Exception as e:
                pass

    BOUNDS_BY_GROUP = {
        'A_2800L': [(5000,15000),(0.3,2.0),(3.5,5.5),(0.01,0.5),(0.8,2.5)],
        'B_4000L': [(8000,15000),(0.2,2.5),(3.0,5.5),(0.01,0.5),(0.8,2.5)],
        'C_2000L': [(4000,10000),(0.5,2.5),(3.5,5.5),(0.05,0.5),(0.8,2.5)],
        'D_5000L': [(10000,20000),(0.3,3.0),(3.0,5.5),(0.01,0.5),(0.8,2.5)],
        'E_1500L': [(3000,8000),(0.3,1.5),(3.5,5.5),(0.01,0.4),(0.8,2.5)],
        'DEFAULT': [(3000,20000),(0.1,3.0),(3.0,5.5),(0.01,0.5),(0.8,2.5)],
    }

    def get_hfg(self, p: float) -> float:
        return 2257 - 37 * max(float(p), 0.0)

    def get_minute_data(self, dyeing_process):
        """
        Mengambil data dari MachineMinuteLog dan Steam_Pr.
        Menggunakan raw_temperature jika tersedia, fallback ke temperature.
        Membaca hingga max(reached_70c_time, cooling_start_time) agar apabila
        terdapat siklus pemanasan ke-2 / Re-Heating setelah cooling_start_time pertama
        (sebelum suhu mencapai <70°C), seluruh siklus pemanasan tetap terbaca.
        Return: (times, temps, pressures, dTdt) — semua np.ndarray
        """
        from monitoring.models import MachineMinuteLog, Machine
        
        try:
            steam_m = Machine.objects.get(code='Steam_Pr')
        except Machine.DoesNotExist:
            return None, None, None, None
            
        start = dyeing_process.heating_start_time or dyeing_process.start_time
        end_candidates = [
            t for t in (dyeing_process.reached_70c_time, dyeing_process.cooling_start_time)
            if t is not None
        ]
        end = max(end_candidates) if end_candidates else dyeing_process.end_time
        if not start or not end:
            return None, None, None, None
        
        logs = list(MachineMinuteLog.objects.filter(
            machine=dyeing_process.machine,
            timestamp__range=(start, end)
        ).order_by('timestamp'))
        
        s_logs = list(MachineMinuteLog.objects.filter(
            machine=steam_m,
            timestamp__range=(start, end)
        ).order_by('timestamp'))
        
        s_dict = {str(l.timestamp)[:16]: (l.temperature or 4.0) for l in s_logs}
        
        times, temps, pressures = [], [], []
        for l in logs:
            ts = str(l.timestamp)[:16]
            t = l.raw_temperature if l.raw_temperature is not None else l.temperature
            if t is None: continue
            times.append(ts[11:])
            temps.append(float(t))
            pressures.append(float(s_dict.get(ts, 4.0)))
        
        if not temps:
            return None, None, None, None
        
        temps = np.array(temps)
        pressures = np.array(pressures)
        w = min(11, len(temps))
        w = w - 1 if w % 2 == 0 else w
        ts_smooth = savgol_filter(temps, w, 3) if (w > 3 and len(temps) >= w) else temps
        dTdt = np.gradient(ts_smooth)
        
        return np.array(times), temps, pressures, dTdt

    def _forward(self, X, params):
        """Forward pass MLP 4→32→32→1."""
        idx = 0
        def unpack(out, inp):
            nonlocal idx
            W = params[idx:idx+out*inp].reshape(out, inp); idx += out*inp
            b = params[idx:idx+out]; idx += out
            return W, b
        W1, b1 = unpack(32, 4)
        W2, b2 = unpack(32, 32)
        W3, b3 = unpack(1,  32)
        h1 = np.maximum(0, X @ W1.T + b1)          # ReLU
        h2 = np.maximum(0, h1 @ W2.T + b2)         # ReLU
        out = np.log1p(np.exp(np.clip(h2 @ W3.T + b3, -50, 50))).squeeze(-1)  # Softplus
        return out

    def calibrate_physics(self, batch_data_cache: dict,
                          batch_actuals: dict,
                          machine_group='DEFAULT') -> dict:
        """
        batch_data_cache: {batch_num: (times, temps, pressures, dTdt)}
        batch_actuals:    {batch_num: actual_steam_kg}
        Return: {'meq','uloss','p_set','k_drop','n_exp','mae_pct'}
        """
        def predict_ode(theta):
            Meq, Uloss, P_set, k, n = theta
            total_err = 0
            for b_num, actual in batch_actuals.items():
                _, temps, press, dTdt = batch_data_cache[b_num]
                m = 0
                cooling_mode = False
                for i in range(len(temps)):
                    if dTdt[i] < -0.4: cooling_mode = True
                    elif dTdt[i] > 0.35: cooling_mode = False
                    
                    if cooling_mode or dTdt[i] < -0.2: continue
                    p = press[i]
                    x = max(0.25, min(1.0, 1.0 - k*((P_set-p)**n) if p < P_set else 1.0))
                    hfg = x * self.get_hfg(p)
                    m += (Meq * max(0, dTdt[i]) + Uloss * max(0, temps[i]-30) * 60) / hfg
                total_err += abs(m - actual)
            return total_err
        
        bounds = self.BOUNDS_BY_GROUP.get(machine_group, self.BOUNDS_BY_GROUP['DEFAULT'])
        res = differential_evolution(predict_ode, bounds,
                                     strategy='best1bin', maxiter=200, popsize=15)
        Meq, Uloss, P_set, k, n = res.x
        
        errors = []
        for b_num, actual in batch_actuals.items():
            _, temps, press, dTdt = batch_data_cache[b_num]
            m = 0
            for i in range(len(temps)):
                if dTdt[i] < -0.2: continue
                p = press[i]
                x = max(0.25, min(1.0, 1.0 - k*((P_set-p)**n) if p < P_set else 1.0))
                hfg = x * self.get_hfg(p)
                m += (Meq * max(0, dTdt[i]) + Uloss * max(0, temps[i]-30) * 60) / hfg
            errors.append(abs(m - actual) / actual * 100)
        
        return {'meq': Meq, 'uloss': Uloss, 'p_set': P_set,
                'k_drop': k, 'n_exp': n, 'mae_pct': np.mean(errors)}

    def _build_inputs(self, temps, pressures, dTdt):
        """Normalisasi input PINN → matrix X (N×4)."""
        N = len(temps)
        T_m, T_s = temps.mean(), temps.std() + 1e-8
        P_m, P_s = pressures.mean(), pressures.std() + 1e-8
        G_m, G_s = dTdt.mean(), dTdt.std() + 1e-8
        return np.stack([
            (temps - T_m) / T_s,
            (pressures - P_m) / P_s,
            (dTdt - G_m) / G_s,
            np.linspace(0, 1, N)
        ], axis=1)

    def train_batch(self, dyeing_process, actual_kg: float,
                    physics: dict) -> tuple:
        """
        Training PINN untuk 1 batch.
        Return: (predicted_kg, error_pct, weights_array[1217])
        """
        _, temps, pressures, dTdt = self.get_minute_data(dyeing_process)
        if temps is None: return None, None, None
        
        Meq = physics['meq']; Uloss = physics['uloss']
        P_set = physics['p_set']; k = physics['k_drop']; n = physics['n_exp']
        
        N = len(temps)
        X       = self._build_inputs(temps, pressures, dTdt)
        active  = (dTdt >= -0.2).astype(float)
        diff    = np.maximum(0, P_set - pressures)
        x_arr   = np.where(pressures < P_set,
                           np.clip(1.0 - k*(diff**n), 0.25, 1.0),
                           1.0)
        hfg_arr = np.array([self.get_hfg(p) for p in pressures])

        def loss(params):
            m_dot = self._forward(X, params) * active
            pred  = np.sum(m_dot)
            L_d   = ((pred - actual_kg) / actual_kg) ** 2
            Q_in  = m_dot * x_arr * hfg_arr
            Q_l   = Meq * np.maximum(dTdt, 0)
            Q_ls  = Uloss * np.maximum(temps - 30, 0) * 60
            heat  = (dTdt > 0.1).astype(float) * active
            L_p   = np.mean(((Q_in - Q_l - Q_ls) * heat) ** 2) / (Meq**2)
            L_s   = np.mean(np.diff(m_dot * active)**2)
            return L_d + 0.5 * L_p + 0.05 * L_s

        np.random.seed(42)
        p0  = np.random.randn(self.N_PARAMS) * 0.05
        res = minimize(loss, p0, method='L-BFGS-B',
                       options={'maxiter': 2500, 'ftol': 1e-14, 'gtol': 1e-10})
        
        m_final = self._forward(X, res.x) * active * x_arr
        pred    = float(np.sum(m_final))
        err_pct = abs(pred - actual_kg) / actual_kg * 100
        return pred, err_pct, res.x

    def predict(self, dyeing_process, physics: dict,
                weights: np.ndarray = None, force_ideal: bool = False,
                single_cycle_only: bool = False) -> float:
        """
        Forward pass. Jika weights tersedia, gunakan PINN.
        Jika weights None, gunakan pure ODE physics calculation.
        - Ketika force_ideal=False (Lapis 1 & Lapis 2), seluruh siklus pemanasan
          (termasuk Re-Heating ke-2, ke-3 dst sebelum <70°C) dihitung sebagai uap aktual.
        - Ketika force_ideal=True (Lapis 3 Ideal) atau single_cycle_only=True,
          hanya siklus pemanasan pertama (1x proses normal) yang dihitung.
        """
        _, temps, pressures, dTdt = self.get_minute_data(dyeing_process)
        if temps is None: return 0.0
        
        Meq = physics['meq']; Uloss = physics['uloss']
        P_set = physics['p_set']; k = physics['k_drop']; n = physics['n_exp']
        active = np.zeros(len(temps))
        cooling_mode = False
        peak_so_far = float(temps[0]) if len(temps) > 0 else 0.0
        has_completed_first_cycle = False

        for i in range(len(temps)):
            if temps[i] > peak_so_far and not has_completed_first_cycle:
                peak_so_far = float(temps[i])

            if dTdt[i] < -0.4:
                cooling_mode = True
            elif dTdt[i] > 0.35:
                cooling_mode = False

            if cooling_mode and peak_so_far >= 75.0 and (peak_so_far - temps[i]) >= 12.0:
                has_completed_first_cycle = True
            
            if cooling_mode:
                active[i] = 0
            elif (force_ideal or single_cycle_only) and has_completed_first_cycle:
                active[i] = 0
            else:
                active[i] = 1 if dTdt[i] >= -0.2 else 0
        
        if not force_ideal:
            # Cegah RuntimeWarning invalid value in power
            diff = np.maximum(0, P_set - pressures)
            x_arr = np.where(pressures < P_set,
                             np.clip(1.0 - k * (diff**n), 0.25, 1.0),
                             1.0)
        else:
            x_arr = np.ones(len(temps))

        if weights is not None:
            X = self._build_inputs(temps, pressures, dTdt)
            m_dot = self._forward(X, weights) * active * x_arr
            return float(np.sum(m_dot))
        else:
            # Pure ODE calculation with Grey Box ML Parameterization
            m_mult = 1.0
            if self.ml_model is not None and hasattr(dyeing_process, 'identity') and dyeing_process.is_complete:
                try:
                    import re
                    import pandas as pd
                    isi = -1
                    prog = 'UNKNOWN'
                    art = 'UNKNOWN'
                    ident = dyeing_process.identity
                    if ident:
                        if ident.isi_per_tube:
                            m = re.search(r'(\d+)', ident.isi_per_tube)
                            if m: isi = float(m.group(1))
                        prog = ident.program or 'UNKNOWN'
                        art = ident.artikel_kain or 'UNKNOWN'
                    
                    input_dict = {'isi': isi, 'startT': dyeing_process.start_temp, 'grad': dyeing_process.heating_avg_gradient}
                    for f in self.ml_features:
                        if f not in input_dict:
                            input_dict[f] = 0
                            
                    if f'prog_{prog}' in input_dict: input_dict[f'prog_{prog}'] = 1
                    if f'art_{art}' in input_dict: input_dict[f'art_{art}'] = 1
                    
                    input_df = pd.DataFrame([input_dict])[self.ml_features]
                    pred = self.ml_model.predict(input_df)[0]
                    m_mult = max(0.75, min(1.25, float(pred)))
                except Exception as e:
                    pass

            hfg_arr = np.array([self.get_hfg(p) for p in pressures])
            # Apply m_mult to Meq
            m_dot_ode = ((Meq * m_mult) * np.maximum(dTdt, 0) + Uloss * np.maximum(temps - 30, 0) * 60) / (x_arr * hfg_arr)
            return float(np.sum(m_dot_ode * active))

    def predict_three_layers(self, dyeing_process,
                             own_profile, best_profile,
                             own_weights, best_weights) -> dict:
        """
        Hitung 3 lapis prediksi sekaligus.
        Return dict siap di-assign ke DyeingProcess fields.
        """
        l1 = self.predict(dyeing_process, own_profile.to_physics_dict(), own_weights)
        
        if best_profile:
            l2 = self.predict(dyeing_process, best_profile.to_physics_dict(), best_weights)
            l3 = self.predict(dyeing_process, best_profile.to_physics_dict(),
                              best_weights, force_ideal=True)
        else:
            l2 = l1   # Jika belum ada best model, gunakan own sebagai fallback
            l3 = l1

        return {
            'predicted_steam_kg':      round(l1, 1),
            'predicted_steam_best_kg': round(l2, 1),
            'predicted_steam_ideal_kg':round(l3, 1),
        }
