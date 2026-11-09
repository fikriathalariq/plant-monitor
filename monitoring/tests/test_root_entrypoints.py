import os
from pathlib import Path
from django.test import SimpleTestCase
from django.conf import settings


class RootEntrypointsAndHygieneTest(SimpleTestCase):
    """
    Unit test to safeguard root entrypoints, DevOps deployment scripts,
    worker supervision paths, and root cleanliness.
    """

    def setUp(self):
        self.root_dir = Path(settings.BASE_DIR)

    def test_core_entrypoints_and_devops_scripts_exist(self):
        """Verify that essential production entrypoints and DevOps scripts exist in root."""
        essential_files = [
            "manage.py",
            "run_server.py",
            "deploy.ps1",
            "rollback.ps1",
            "watchdog_heal.ps1",
            "Dockerfile",
            "docker-compose.yml",
            "requirements.txt",
            ".gitignore",
            ".dockerignore",
            ".env.example",
            ".coveragerc",
            "README.md",
            "LICENSE",
        ]
        for filename in essential_files:
            file_path = self.root_dir / filename
            self.assertTrue(
                file_path.exists(),
                f"Core file '{filename}' must exist in root project directory: {file_path}",
            )

    def test_background_worker_supervisor_targets(self):
        """Verify scripts/start_background_workers.ps1 exists and targets valid scripts."""
        supervisor_file = self.root_dir / "scripts" / "start_background_workers.ps1"
        self.assertTrue(
            supervisor_file.exists(),
            "Supervisor script 'scripts/start_background_workers.ps1' must exist",
        )

        content = supervisor_file.read_text(encoding="utf-8")
        # Ensure it references the ops path for loop_anomalies
        self.assertIn("scripts\\ops\\loop_anomalies.bat", content)

        # Ensure the targeted loop anomalies script actually exists
        target_ops_script = self.root_dir / "scripts" / "ops" / "loop_anomalies.bat"
        self.assertTrue(
            target_ops_script.exists(),
            f"Target script '{target_ops_script}' referenced by supervisor must exist",
        )

    def test_root_python_hygiene(self):
        """Verify that no ad-hoc Python scripts linger in the root directory."""
        py_files_in_root = [
            p.name for p in self.root_dir.glob("*.py") if p.is_file()
        ]
        # Only manage.py and run_server.py are allowed in root
        allowed_root_py = {"manage.py", "run_server.py"}
        extra_py = set(py_files_in_root) - allowed_root_py
        self.assertEqual(
            extra_py,
            set(),
            f"Found unauthorized ad-hoc Python scripts in root: {extra_py}",
        )

    def test_analytics_perf_log_destination(self):
        """Verify that analytics profiler logs to logs/ directory instead of project root."""
        from monitoring import api_analytics
        perf_log_path = Path(api_analytics._perf_log_path)
        self.assertEqual(perf_log_path.parent.name, "logs")
        self.assertEqual(perf_log_path.name, "analytics_perf.log")

    def test_frontend_hygiene_no_bak_or_cjs(self):
        """Verify that frontend/src has no stray .bak files and frontend root has no ad-hoc .cjs scripts."""
        fe_src = self.root_dir / "frontend" / "src"
        bak_files = list(fe_src.rglob("*.bak"))
        self.assertEqual(
            bak_files,
            [],
            f"Found stray .bak files in frontend/src: {bak_files}",
        )

        fe_root = self.root_dir / "frontend"
        cjs_in_fe_root = list(fe_root.glob("*.cjs"))
        self.assertEqual(
            cjs_in_fe_root,
            [],
            f"Found stray .cjs scripts in frontend root (should be in archive/): {cjs_in_fe_root}",
        )
