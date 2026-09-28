import unittest

from syschime.core.models import SoundPolicy


class ModelValidationTests(unittest.TestCase):
    def test_volume_range(self):
        with self.assertRaises(ValueError):
            SoundPolicy(volume=1.1)
        with self.assertRaises(ValueError):
            SoundPolicy(volume=-0.1)

    def test_repeat_count(self):
        with self.assertRaises(ValueError):
            SoundPolicy(repeat_count=0)


if __name__ == "__main__":
    unittest.main()
