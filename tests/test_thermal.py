import unittest

from syschime.config import ThermalConfig
from syschime.core.models import RaiseAlert, ResolveAlert
from syschime.plugins.thermal import ThermalStateMachine


class ThermalStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.machine = ThermalStateMachine(ThermalConfig())

    def test_warning_requires_duration(self):
        self.assertEqual(self.machine.evaluate("cpu", 91, "CPU Package", 0), [])
        self.assertEqual(self.machine.evaluate("cpu", 91, "CPU Package", 19), [])
        actions = self.machine.evaluate("cpu", 91, "CPU Package", 20)
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], RaiseAlert)
        self.assertEqual(actions[0].key, "thermal:cpu:warning")

    def test_short_spike_does_not_alert(self):
        self.machine.evaluate("cpu", 92, "CPU Package", 0)
        self.machine.evaluate("cpu", 70, "CPU Package", 10)
        self.assertEqual(self.machine.evaluate("cpu", 92, "CPU Package", 20), [])

    def test_critical_requires_critical_duration(self):
        self.assertEqual(self.machine.evaluate("cpu", 98, "CPU Package", 0), [])
        actions = self.machine.evaluate("cpu", 98, "CPU Package", 5)
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].key, "thermal:cpu:critical")

    def test_warning_escalates_to_critical(self):
        self.machine.evaluate("cpu", 91, "CPU Package", 0)
        self.machine.evaluate("cpu", 91, "CPU Package", 20)
        self.machine.evaluate("cpu", 98, "CPU Package", 21)
        actions = self.machine.evaluate("cpu", 98, "CPU Package", 26)
        self.assertEqual([type(a) for a in actions], [ResolveAlert, RaiseAlert])
        self.assertEqual(actions[0].key, "thermal:cpu:warning")
        self.assertEqual(actions[1].key, "thermal:cpu:critical")

    def test_recovery_resolves_active_alert(self):
        self.machine.evaluate("gpu", 86, "GPU", 0)
        self.machine.evaluate("gpu", 86, "GPU", 20)
        actions = self.machine.evaluate("gpu", 74, "GPU", 21)
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], ResolveAlert)
        self.assertEqual(actions[0].key, "thermal:gpu:warning")

    def test_unknown_category_ignored(self):
        self.assertEqual(self.machine.evaluate("other", 200, "Mystery", 100), [])


if __name__ == "__main__":
    unittest.main()
