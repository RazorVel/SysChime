import unittest

from syschime.config import BatteryConfig
from syschime.core.models import RaiseAlert, ResolveAlert
from syschime.plugins.battery import BatterySnapshot, BatteryState, BatteryStateMachine


class BatteryStateMachineTests(unittest.TestCase):
    def setUp(self):
        self.machine = BatteryStateMachine(BatteryConfig())

    def test_warning_fires_once(self):
        actions = self.machine.evaluate(BatterySnapshot(20, BatteryState.DISCHARGING))
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], RaiseAlert)
        self.assertEqual(actions[0].key, "battery:warning")
        self.assertEqual(self.machine.evaluate(BatterySnapshot(19, BatteryState.DISCHARGING)), [])

    def test_initial_critical_skips_warning(self):
        actions = self.machine.evaluate(BatterySnapshot(8, BatteryState.DISCHARGING))
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].key, "battery:critical")

    def test_warning_escalates_to_critical(self):
        self.machine.evaluate(BatterySnapshot(20, BatteryState.DISCHARGING))
        actions = self.machine.evaluate(BatterySnapshot(10, BatteryState.DISCHARGING))
        self.assertEqual([type(a) for a in actions], [ResolveAlert, RaiseAlert])
        self.assertEqual(actions[0].key, "battery:warning")
        self.assertEqual(actions[1].key, "battery:critical")

    def test_charging_resolves_and_rearms(self):
        self.machine.evaluate(BatterySnapshot(20, BatteryState.DISCHARGING))
        actions = self.machine.evaluate(BatterySnapshot(19, BatteryState.CHARGING))
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], ResolveAlert)
        self.assertEqual(self.machine.level, None)

        actions = self.machine.evaluate(BatterySnapshot(20, BatteryState.DISCHARGING))
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], RaiseAlert)

    def test_recover_above_reset_resolves(self):
        self.machine.evaluate(BatterySnapshot(20, BatteryState.DISCHARGING))
        actions = self.machine.evaluate(BatterySnapshot(26, BatteryState.DISCHARGING))
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], ResolveAlert)
        self.assertEqual(self.machine.level, None)


if __name__ == "__main__":
    unittest.main()
