import numpy as np
from unittest.mock import MagicMock
from django.test import SimpleTestCase
from monitoring.services.pinn_engine import PINNSteamPredictor


class PINNSteamPredictorTests(SimpleTestCase):
    def setUp(self):
        self.predictor = PINNSteamPredictor()

    def test_get_hfg_enthalpy_formula(self):
        # Base enthalpy at 0 bar: 2257 kJ/kg
        self.assertEqual(self.predictor.get_hfg(0.0), 2257.0)
        # Negative pressure clipped to 0.0
        self.assertEqual(self.predictor.get_hfg(-5.0), 2257.0)
        # Enthalpy at 4 bar: 2257 - (37 * 4) = 2109 kJ/kg
        self.assertAlmostEqual(self.predictor.get_hfg(4.0), 2109.0)

    def test_mlp_forward_pass_shape_and_softplus_activation(self):
        # 10 minute points
        temps = np.linspace(35.0, 120.0, 10)
        pressures = np.full(10, 4.0)
        dTdt = np.gradient(temps)

        X = self.predictor._build_inputs(temps, pressures, dTdt)
        self.assertEqual(X.shape, (10, 4))

        # Forward pass using zero weights
        weights = np.zeros(self.predictor.N_PARAMS)
        out = self.predictor._forward(X, weights)

        self.assertEqual(out.shape, (10,))
        # Softplus activation output must be strictly positive (> 0)
        self.assertTrue(np.all(out > 0))

    def test_predict_three_layers_preserves_passed_weights(self):
        """Regression test: verify that passed weights are not overwritten with None."""
        mock_process = MagicMock()
        mock_own_profile = MagicMock()
        mock_own_profile.to_physics_dict.return_value = {
            'meq': 5000, 'uloss': 1.0, 'p_set': 4.0, 'k_drop': 0.1, 'n_exp': 1.0
        }
        mock_best_profile = MagicMock()
        mock_best_profile.to_physics_dict.return_value = {
            'meq': 4800, 'uloss': 0.9, 'p_set': 4.0, 'k_drop': 0.1, 'n_exp': 1.0
        }

        # Mock predict method to record what weights are passed
        passed_weights = []
        def fake_predict(process, physics, weights=None, force_ideal=False, single_cycle_only=False):
            passed_weights.append(weights)
            return 123.4

        self.predictor.predict = fake_predict

        dummy_own_w = np.ones(self.predictor.N_PARAMS)
        dummy_best_w = np.ones(self.predictor.N_PARAMS) * 2

        res = self.predictor.predict_three_layers(
            mock_process,
            mock_own_profile,
            mock_best_profile,
            dummy_own_w,
            dummy_best_w
        )

        self.assertEqual(res['predicted_steam_kg'], 123.4)
        self.assertEqual(len(passed_weights), 3)
        # Ensure dummy_own_w was passed to layer 1
        self.assertIs(passed_weights[0], dummy_own_w)
        # Ensure dummy_best_w was passed to layer 2 and layer 3
        self.assertIs(passed_weights[1], dummy_best_w)
        self.assertIs(passed_weights[2], dummy_best_w)
