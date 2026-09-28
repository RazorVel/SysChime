import tempfile
import unittest
from pathlib import Path

from syschime.platform.hwmon import HwmonThermalProvider, classify_hwmon, parse_nvidia_smi


class HwmonTests(unittest.TestCase):
    def test_classifier(self):
        self.assertEqual(classify_hwmon("coretemp"), "cpu")
        self.assertEqual(classify_hwmon("k10temp"), "cpu")
        self.assertEqual(classify_hwmon("amdgpu"), "gpu")
        self.assertEqual(classify_hwmon("nvme"), "nvme")
        self.assertIsNone(classify_hwmon("acpitz"))

    def test_parse_nvidia_smi(self):
        readings = parse_nvidia_smi("0, 48\n1, 55\n")
        self.assertEqual([r.temperature_c for r in readings], [48.0, 55.0])
        self.assertEqual(readings[1].sensor_id, "nvidia-smi:gpu1")

    def test_reads_supported_sensor(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            hw = root / "hwmon0"
            hw.mkdir()
            (hw / "name").write_text("coretemp\n")
            (hw / "temp1_input").write_text("91500\n")
            (hw / "temp1_label").write_text("Package id 0\n")

            readings = HwmonThermalProvider(root).readings_sync()

        self.assertEqual(len(readings), 1)
        self.assertEqual(readings[0].category, "cpu")
        self.assertAlmostEqual(readings[0].temperature_c, 91.5)
        self.assertIn("Package id 0", readings[0].label)


if __name__ == "__main__":
    unittest.main()
