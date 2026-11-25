# SPDX-License-Identifier: GPL-3.0-or-later
"""Regression tests for the bounded QEMU Monitor Protocol stream reader."""

from __future__ import annotations

import socket
import threading
import unittest

from scripts.ci_cxl_qemu_feasibility import ProbeError, QMPClient


class QMPClientTests(unittest.TestCase):
    def make_pair(self) -> tuple[socket.socket, socket.socket, QMPClient]:
        local, peer = socket.socketpair()
        self.addCleanup(local.close)
        self.addCleanup(peer.close)
        return local, peer, QMPClient(local)

    def test_preserves_multiple_json_frames_received_in_one_packet(self) -> None:
        _local, peer, client = self.make_pair()
        peer.sendall(
            b'{"QMP":{"version":{}}}\r\n'
            b'{"event":"RESET"}\r\n'
            b'{"return":{"ok":true}}\r\n'
        )

        self.assertEqual(client.read_line(), {"QMP": {"version": {}}})
        self.assertEqual(client.read_line(), {"event": "RESET"})
        self.assertEqual(client.read_line(), {"return": {"ok": True}})

    def test_reassembles_a_json_frame_split_across_socket_reads(self) -> None:
        _local, peer, client = self.make_pair()
        payload = b'{"return":{"device":"cxl-vmem0"}}\r\n'
        first = payload[:11]
        second = payload[11:23]
        third = payload[23:]

        def send_fragments() -> None:
            peer.sendall(first)
            peer.sendall(second)
            peer.sendall(third)

        sender = threading.Thread(target=send_fragments)
        sender.start()
        try:
            self.assertEqual(
                client.read_line(timeout_seconds=2),
                {"return": {"device": "cxl-vmem0"}},
            )
        finally:
            sender.join(timeout=2)
        self.assertFalse(sender.is_alive())

    def test_execute_skips_event_and_preserves_coalesced_reply(self) -> None:
        local, peer, client = self.make_pair()
        peer.settimeout(2)

        def emulate_qmp() -> None:
            request = bytearray()
            while b"\n" not in request:
                chunk = peer.recv(4096)
                if not chunk:
                    return
                request.extend(chunk)
            peer.sendall(
                b'{"event":"RESET","data":{}}\r\n'
                b'{"return":{"enabled":true}}\r\n'
            )

        server = threading.Thread(target=emulate_qmp)
        server.start()
        try:
            self.assertEqual(client.execute("qmp_capabilities"), {"enabled": True})
        finally:
            server.join(timeout=2)
        self.assertFalse(server.is_alive())

    def test_rejects_invalid_json_frame(self) -> None:
        _local, peer, client = self.make_pair()
        peer.sendall(b'{"return":}\r\n')
        with self.assertRaises(ProbeError):
            client.read_line()

    def test_rejects_json_frame_over_one_mib(self) -> None:
        _local, peer, client = self.make_pair()
        peer.sendall(b"x" * (QMPClient.MAX_LINE_BYTES + 1))
        with self.assertRaises(ProbeError):
            client.read_line()

    def test_rejects_non_object_json_frame(self) -> None:
        _local, peer, client = self.make_pair()
        peer.sendall(b'[]\r\n')
        with self.assertRaises(ProbeError):
            client.read_line()


if __name__ == "__main__":
    unittest.main()
