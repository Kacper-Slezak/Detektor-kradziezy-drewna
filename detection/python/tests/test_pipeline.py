"""Run: python -m unittest discover -s tests -v"""
import csv
import json
import subprocess
import tempfile
import unittest
from pathlib import Path

import imageio_ffmpeg

from algorithm.core.detector import Settings, calibrate, classify
from algorithm.core.features import extract
from algorithm.core.io_utils import read_audio, read_sensors
from algorithm.data.demo_data import generate
from algorithm.app.main import _process


class SensorFusionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        generate(cls.root / "data")
        cls.baseline_audio = cls.root / "data/calibration/microphone.wav"
        cls.baseline_sensors = cls.root / "data/calibration/sensors.csv"
        cls.scene_audio = cls.root / "data/scenario/microphone.wav"
        cls.scene_sensors = cls.root / "data/scenario/sensors.csv"

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_wav_reading_and_audio_alone(self):
        sample_rate, data = read_audio(self.scene_audio)
        self.assertEqual(sample_rate, 8000)
        self.assertGreater(len(data), 100000)
        summary = _process("audio", str(self.scene_audio), None, self.root / "out_audio",
                           baseline_audio=str(self.baseline_audio))
        self.assertGreater(summary["engine_windows"], 25)
        self.assertGreater(summary["audio_impact_windows"], 4)
        self.assertEqual(summary["alarm_count"], 0)
        self.assertTrue((self.root / "out_audio/result.png").exists())

    def test_mp3(self):
        target = self.root / "scene.mp3"
        binary = imageio_ffmpeg.get_ffmpeg_exe()
        conversion = subprocess.run([binary, "-y", "-v", "error", "-i", str(self.scene_audio),
                                     "-codec:a", "libmp3lame", "-q:a", "4", str(target)],
                                    capture_output=True)
        self.assertEqual(conversion.returncode, 0, conversion.stderr.decode(errors="replace"))
        sample_rate, decoded = read_audio(target)
        self.assertEqual(sample_rate, 8000)
        self.assertGreater(len(decoded), 8000 * 100)
        summary = _process("audio", str(target), None, self.root / "out_mp3",
                           baseline_audio=str(self.baseline_audio))
        self.assertGreater(summary["engine_windows"], 25)
        self.assertTrue((self.root / "out_mp3/predictions.csv").exists())

    def test_motion_only(self):
        summary = _process("vibration", None, str(self.scene_sensors), self.root / "out_vib",
                           baseline_sensors=str(self.baseline_sensors))
        self.assertGreater(summary["motion_windows"], 5)
        self.assertEqual(summary["alarm_count"], 0)
        self.assertTrue((self.root / "out_vib/result.png").exists())

    def test_fusion(self):
        summary = _process("fusion", str(self.scene_audio), str(self.scene_sensors),
                           self.root / "out_fusion", baseline_audio=str(self.baseline_audio),
                           baseline_sensors=str(self.baseline_sensors))
        self.assertGreaterEqual(summary["alarm_count"], 1)
        self.assertEqual(summary["state_counts"].get("MOTION_ONLY", 0), 0)
        self.assertTrue(all(50 <= t <= 85 for t in summary["alarm_times_s"]))
        self.assertTrue((self.root / "out_fusion/result.png").exists())
        with (self.root / "out_fusion/predictions.csv").open(newline="") as file:
            predictions = list(csv.DictReader(file))
        self.assertEqual(sum(int(r["alarm"]) for r in predictions if 20 <= float(r["time_s"]) < 40), 0)

    def test_vibration_only_column(self):
        src = self.root / "just_vibration.csv"
        with self.scene_sensors.open(newline="") as inp, src.open("w", newline="") as out:
            reader = csv.DictReader(inp)
            writer = csv.DictWriter(out, fieldnames=["time_s", "vibration"])
            writer.writeheader()
            for row in reader:
                writer.writerow({key: row[key] for key in ("time_s", "vibration")})
        summary = _process("vibration", None, str(src), self.root / "out_vib_only")
        self.assertGreater(summary["motion_windows"], 3)
        self.assertTrue((self.root / "out_vib_only/model.json").is_file())

    def test_misaligned_inputs_refused(self):
        audio = read_audio(self.scene_audio)
        sensors = read_sensors(self.scene_sensors, offset_s=300)
        with self.assertRaises(ValueError):
            extract(audio, sensors)


if __name__ == "__main__":
    unittest.main()
