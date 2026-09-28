import unittest

from syschime.config import VpnConfig
from syschime.core.models import RaiseAlert, ResolveAlert
from syschime.plugins.vpn import VpnStateMachine


class VpnStateMachineTests(unittest.TestCase):
    def test_no_alert_for_disconnected_startup(self):
        machine = VpnStateMachine(VpnConfig(watch=("HTB",)))
        self.assertEqual(machine.evaluate(set()), [])
        self.assertEqual(machine.evaluate(set()), [])

    def test_disconnect_after_connection_alerts_once(self):
        machine = VpnStateMachine(VpnConfig(watch=("HTB",)))
        machine.evaluate(set())
        actions = machine.evaluate({"HTB"})
        self.assertEqual(actions, [])

        actions = machine.evaluate(set())
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], RaiseAlert)
        self.assertEqual(actions[0].key, "vpn:HTB:disconnect")
        self.assertEqual(machine.evaluate(set()), [])

    def test_reconnect_resolves_disconnect_alert(self):
        machine = VpnStateMachine(VpnConfig(watch=("HTB",)))
        machine.evaluate({"HTB"})
        machine.evaluate(set())
        actions = machine.evaluate({"HTB"})
        self.assertEqual(len(actions), 1)
        self.assertIsInstance(actions[0], ResolveAlert)

    def test_dynamic_mode_tracks_only_observed_vpns(self):
        machine = VpnStateMachine(VpnConfig())
        self.assertEqual(machine.evaluate(set()), [])
        self.assertEqual(machine.evaluate({"work"}), [])
        actions = machine.evaluate(set())
        self.assertEqual(len(actions), 1)
        self.assertEqual(actions[0].key, "vpn:work:disconnect")


if __name__ == "__main__":
    unittest.main()
