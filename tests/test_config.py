import tempfile
import unittest
from pathlib import Path

from syschime.config import BatteryConfig, load_config
from syschime.core.models import SoundMode


class ConfigTests(unittest.TestCase):
    def test_invalid_battery_thresholds_rejected(self):
        with self.assertRaises(ValueError):
            BatteryConfig(warning_threshold=10, critical_threshold=20)

    def test_load_overrides_profile_and_plugin(self):
        text = '''
[plugins.battery]
warning_threshold = 30
reset_threshold = 35

[alerts.profiles.battery_warning]
sound = "warning-soft"
mode = "once"
volume = 0.5
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(text)
            config = load_config(path)

        self.assertEqual(config.battery.warning_threshold, 30)
        profile = config.profiles["battery_warning"]
        self.assertEqual(profile.sound.sound, "warning-soft")
        self.assertEqual(profile.sound.mode, SoundMode.ONCE)
        self.assertEqual(profile.sound.volume, 0.5)

    def test_invalid_sound_name_rejected(self):
        text = '''
[alerts.profiles.vpn_disconnect]
sound = "does-not-exist"
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(text)
            with self.assertRaises(ValueError):
                load_config(path)

    def test_invalid_vpn_watch_type_rejected(self):
        text = '''
[plugins.vpn]
watch = "HTB"
'''
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "config.toml"
            path.write_text(text)
            with self.assertRaises(ValueError):
                load_config(path)


if __name__ == "__main__":
    unittest.main()
