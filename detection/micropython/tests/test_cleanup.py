"""Smoke checks for the v4.6-only cleaned source package."""
import tempfile, unittest
from unittest.mock import patch
from pathlib import Path
from algorithm.app import v4_6_stage_lopy

ROOT = Path(__file__).resolve().parents[1]

class TestCleanV46(unittest.TestCase):
    def test_no_v47_or_old_model_runtime(self):
        self.assertNotIn('tg_v42_device', (ROOT/'firmware/main.py').read_text())
        self.assertNotIn('tg_v45_device', (ROOT/'firmware/main.py').read_text())
        self.assertNotIn('tg_v47_device', (ROOT/'firmware/main.py').read_text())
        self.assertIn("MODEL_FLAVOR = 'v4_6'", (ROOT/'firmware/config.py').read_text())
        self.assertNotIn('pulse_alarm', (ROOT/'firmware/lib/tg_hardware.py').read_text())

    def test_selected_analog_mic_and_no_physical_alarm(self):
        cfg=(ROOT/'firmware/config.py').read_text()
        self.assertIn('SparkFun BOB-12758', cfg)
        self.assertIn('ENABLE_PHYSICAL_ALARM = False',cfg)
        self.assertIn('ALARM_OUTPUT_PIN = None',cfg)
        self.assertIn('AUDIO_RATE_HZ = 4000',cfg)

    def test_staging_requires_trained_model(self):
        with tempfile.TemporaryDirectory() as temp:
            missing=Path(temp)/'missing.py'
            output=Path(temp)/'stage'
            with patch('sys.argv', ['stage', '--model', str(missing), '--output', str(output)]):
                with self.assertRaises(FileNotFoundError):
                    v4_6_stage_lopy.main()
            self.assertFalse(output.exists())

    def test_staging_copies_only_v46_files(self):
        with tempfile.TemporaryDirectory() as temp:
            model=Path(temp)/'tg_model_v46.py'
            model.write_text('MODEL_TYPE = "tiny_cnn_wide_v46"\nRATE = 4000\n',encoding='utf8')
            output=Path(temp)/'stage'
            with patch('sys.argv', ['stage', '--model', str(model), '--output', str(output)]):
                # Stage uses relative firmware path; run from project root.
                cwd=Path.cwd()
                import os
                try:
                    os.chdir(ROOT)
                    v4_6_stage_lopy.main()
                finally:
                    os.chdir(cwd)
            staged={p.relative_to(output).as_posix() for p in output.rglob('*') if p.is_file()}
            self.assertEqual(staged, {
                'main.py','config.py','lopy_v46_memory_probe.py',
                'lib/tg_model_v46.py','lib/tg_v46_device.py','lib/tg_temporal_v46.py',
                'lib/tg_cnn_v46.py','lib/tg_presence_v46.py',
                'lib/tg_sampling_v46.py','lib/tg_hardware.py'})

if __name__=='__main__':unittest.main()
