from __future__ import annotations

import json
import socket
import unittest
from unittest.mock import patch

from pc.communication import network_scanner
from pi import pisend_receive


class _FakeSocket:
    def __init__(self, responses):
        self._responses = list(responses)
        self.sent_packets = []

    def setsockopt(self, *_args, **_kwargs):
        return None

    def settimeout(self, *_args, **_kwargs):
        return None

    def sendto(self, data, addr):
        self.sent_packets.append((data, addr))

    def recvfrom(self, _size):
        if self._responses:
            return self._responses.pop(0)
        raise socket.timeout()

    def close(self):
        return None


class ProtocolPortTests(unittest.TestCase):
    def test_get_ws_port_reads_config_and_falls_back(self) -> None:
        with patch.object(pisend_receive, "get_pi_config", return_value="9012"):
            self.assertEqual(pisend_receive._get_ws_port(), 9012)
        with patch.object(pisend_receive, "get_pi_config", return_value="70000"):
            self.assertEqual(pisend_receive._get_ws_port(), 8001)
        with patch.object(pisend_receive, "get_pi_config", side_effect=ValueError("bad")):
            self.assertEqual(pisend_receive._get_ws_port(), 8001)

    def test_scan_multi_nodes_uses_reported_ws_port(self) -> None:
        payload = json.dumps({
            "type": "raspberry_pi_response",
            "ip": "192.168.10.20",
            "ws_port": 9012,
        }).encode("utf-8")
        fake_socket = _FakeSocket([(payload, ("192.168.10.20", 50000))])

        with patch("pc.communication.network_scanner.socket.socket", return_value=fake_socket), \
             patch("pc.communication.network_scanner.console_info", lambda *_args, **_kwargs: None):
            result = network_scanner.scan_multi_nodes(expected_count=1, timeout=0.01)

        self.assertEqual(result, {"1": "192.168.10.20:9012"})
        self.assertEqual(fake_socket.sent_packets[0][1], ("<broadcast>", 50000))


if __name__ == "__main__":
    unittest.main()
