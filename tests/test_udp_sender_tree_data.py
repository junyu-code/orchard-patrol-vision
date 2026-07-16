import unittest
from unittest.mock import Mock

from transport.udp_sender import UdpSender


class UdpSenderTreeDataTests(unittest.TestCase):
    def setUp(self):
        self.sender = UdpSender(
            udp_host="127.0.0.1",
            udp_port=9,
            simulate_tree_events=True,
            sock=Mock(),
        )

    def tearDown(self):
        self.sender.close()

    def test_explicit_zero_tree_ids_are_not_replaced_by_simulation(self):
        self.sender._update_tree_indices(
            frame_index=100,
            disease_detected=True,
            explicit_tree_indices=(0, 0),
        )

        self.assertEqual(self.sender.left_tree_index, 0)
        self.assertEqual(self.sender.right_tree_index, 0)

    def test_explicit_tree_ids_are_used_exactly(self):
        self.sender._update_tree_indices(
            frame_index=100,
            disease_detected=False,
            explicit_tree_indices=(1, 256),
        )

        self.assertEqual(self.sender.left_tree_index, 1)
        self.assertEqual(self.sender.right_tree_index, 256)


if __name__ == "__main__":
    unittest.main()
