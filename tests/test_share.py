"""The shared folder: record, checks, and a real server on loopback.

Run:  python -m unittest discover -s tests
"""

from __future__ import annotations

import ftplib
import io
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from qemugui import model, share                    # noqa: E402
from qemugui.model import Machine, Share, Network   # noqa: E402

FIXTURES = HERE / "fixtures"
PASV_RE = re.compile(r"\((\d+),(\d+),(\d+),(\d+),(\d+),(\d+)\)")


def pasv_endpoint(reply: str) -> tuple[str, int]:
    m = PASV_RE.search(reply)
    assert m, reply
    a, b, c, d, p1, p2 = (int(x) for x in m.groups())
    return f"{a}.{b}.{c}.{d}", p1 * 256 + p2


class ShareRecord(unittest.TestCase):

    def test_an_old_record_without_share_loads_with_the_defaults(self):
        m = Machine.load(FIXTURES / "mac-os.json")
        self.assertNotIn("share", json.loads((FIXTURES / "mac-os.json").read_text()))
        self.assertEqual(m.share, Share())
        self.assertEqual(m.share, Share("", "guest", "", "guest-only"))
        self.assertFalse(m.share.enabled)

    def test_share_round_trips(self):
        m = Machine.load(FIXTURES / "mac-os.json")
        m.share = Share("/shared/folder", "mac", "secret", "all-interfaces")
        d = json.loads(m.to_json())
        self.assertEqual(d["share"], {"folder": "/shared/folder", "user": "mac",
                                      "password": "secret", "scope": "all-interfaces"})
        self.assertEqual(Machine.from_json(m.to_json()), m)
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "machine.json"
            m.save(p)
            self.assertEqual(Machine.load(p).share, m.share)

    def test_a_bare_share_block_fills_in_the_defaults(self):
        m = Machine.from_dict({"name": "x", "share": {"folder": "/f"}})
        self.assertEqual(m.share, Share("/f", "guest", "", "guest-only"))
        self.assertTrue(m.share.enabled)
        self.assertEqual(Machine.from_dict({"name": "x", "share": "junk"}).share, Share())


class ShareChecks(unittest.TestCase):

    def machine(self, **kw) -> Machine:
        m = Machine.load(FIXTURES / "mac-os.json")
        m.share = Share(**kw)
        return m

    def validate(self, m: Machine):
        return model.validate(m, None, "darwin", check_files=False)

    def test_no_folder_means_nothing_to_say(self):
        errors, warnings = self.validate(self.machine())
        self.assertEqual(errors, [])
        self.assertFalse(any("shar" in w.lower() for w in warnings), warnings)

    def test_a_folder_that_is_not_there_is_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            errors, _ = self.validate(self.machine(folder=str(Path(td) / "missing")))
            self.assertEqual(errors, ["The shared folder is not a folder that exists."])
            f = Path(td) / "file.txt"
            f.write_text("")
            errors, _ = self.validate(self.machine(folder=str(f)))
            self.assertEqual(errors, ["The shared folder is not a folder that exists."])
            errors, _ = self.validate(self.machine(folder=td))
            self.assertEqual(errors, [])

    def test_all_interfaces_needs_a_password(self):
        with tempfile.TemporaryDirectory() as td:
            errors, _ = self.validate(self.machine(folder=td, scope="all-interfaces"))
            self.assertEqual(errors, ["Sharing on all interfaces needs a password."])
            errors, _ = self.validate(self.machine(folder=td, scope="all-interfaces",
                                                   password="x"))
            self.assertEqual(errors, [])

    def test_an_unknown_scope_is_an_error(self):
        with tempfile.TemporaryDirectory() as td:
            errors, _ = self.validate(self.machine(folder=td, scope="everyone"))
            self.assertTrue(any("sharing setting" in e for e in errors), errors)

    def test_guest_only_warns_unless_the_network_is_slirp(self):
        with tempfile.TemporaryDirectory() as td:
            m = self.machine(folder=td)
            m.network = Network("vmnet-shared", "00:05:02:12:34:56", "")
            errors, warnings = self.validate(m)
            self.assertEqual(errors, [])
            self.assertTrue(any("slirp" in w for w in warnings), warnings)
            m.network = Network("user", "00:05:02:12:34:56", "")
            _, warnings = self.validate(m)
            self.assertFalse(any("slirp" in w for w in warnings), warnings)
            m.network = Network("vmnet-shared", "00:05:02:12:34:56", "")
            m.share = Share(td, "u", "p", "all-interfaces")
            _, warnings = self.validate(m)
            self.assertFalse(any("slirp" in w for w in warnings), warnings)


class GuestUrl(unittest.TestCase):

    def test_slirp_is_always_10_0_2_2(self):
        self.assertEqual(share.share_url(share.guest_side_host("user"), 21), "ftp://10.0.2.2/")
        self.assertEqual(share.share_url(share.guest_side_host("user"), 2121),
                         "ftp://10.0.2.2:2121/")

    def test_other_modes_name_the_host_or_a_placeholder(self):
        self.assertEqual(share.guest_side_host("none"), share.HOST_IP_PLACEHOLDER)
        self.assertEqual(share.guest_side_host("vmnet-bridged", "nosuchif0"),
                         share.HOST_IP_PLACEHOLDER)
        self.assertEqual(share.guest_side_host("vmnet-bridged", ""), share.HOST_IP_PLACEHOLDER)

    def test_loopback_is_an_interface_it_can_read(self):
        if sys.platform == "win32":
            self.skipTest("ifconfig")
        self.assertEqual(share.interface_address("lo0"), "127.0.0.1")


class ServerOnLoopback(unittest.TestCase):

    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.folder = Path(self.td.name).resolve()
        self.port = share.free_port()
        self.servers: list[share.ShareServer] = []

    def tearDown(self):
        for s in self.servers:
            s.stop()
        self.td.cleanup()

    def start(self, m: Machine) -> share.ShareServer:
        s = share.start_share(m, ports=(self.port,))
        self.servers.append(s)
        return s

    def machine(self, **kw) -> Machine:
        m = Machine(name="Share test", system="macos_8_to_9")
        m.share = Share(folder=str(self.folder), **kw)
        return m

    def client(self, user: str = "", password: str = "") -> ftplib.FTP:
        f = ftplib.FTP()
        f.connect("127.0.0.1", self.port, timeout=10)
        try:
            f.login(user, password)
        except ftplib.error_perm:
            f.close()
            raise
        return f

    def test_anonymous_guest_only_can_list_upload_download_and_delete(self):
        s = self.start(self.machine())
        self.assertEqual(s.address, ("127.0.0.1", self.port))
        self.assertEqual(s.url_for("user"), f"ftp://10.0.2.2:{self.port}/")
        (self.folder / "already.txt").write_bytes(b"there")
        f = self.client()
        self.assertEqual(f.nlst(), ["already.txt"])
        f.storbinary("STOR up.bin", io.BytesIO(b"\x00\x01binary\xff"))
        self.assertEqual((self.folder / "up.bin").read_bytes(), b"\x00\x01binary\xff")
        got = bytearray()
        f.retrbinary("RETR already.txt", got.extend)
        self.assertEqual(bytes(got), b"there")
        f.delete("up.bin")
        self.assertFalse((self.folder / "up.bin").exists())
        self.assertEqual(sorted(f.nlst()), ["already.txt"])
        f.quit()

    def test_pasv_advertises_the_slirp_host_address(self):
        self.start(self.machine())
        f = self.client()
        host, port = pasv_endpoint(f.sendcmd("PASV"))
        self.assertEqual(host, share.GUEST_HOST_ADDR)
        self.assertIn(port, share.PASSIVE_PORTS)
        f.close()

    def test_a_user_and_password_are_required_when_set(self):
        self.start(self.machine(user="mac", password="secret"))
        with self.assertRaises(ftplib.error_perm):
            self.client()
        with self.assertRaises(ftplib.error_perm):
            self.client("mac", "wrong")
        f = self.client("mac", "secret")
        f.storbinary("STOR ok.txt", io.BytesIO(b"ok"))
        self.assertEqual(f.nlst(), ["ok.txt"])
        f.quit()

    def test_all_interfaces_without_a_password_refuses_to_start(self):
        with self.assertRaises(share.ShareError) as cm:
            share.start_share(self.machine(scope="all-interfaces"), ports=(self.port,))
        self.assertEqual(str(cm.exception), "Sharing on all interfaces needs a password.")
        with self.assertRaises(OSError):
            ftplib.FTP().connect("127.0.0.1", self.port, timeout=2)

    def test_all_interfaces_with_a_password_binds_everywhere(self):
        s = self.start(self.machine(scope="all-interfaces", password="p"))
        self.assertEqual(s.bind_host, "0.0.0.0")
        self.client("guest", "p").quit()

    def test_a_missing_folder_refuses_to_start(self):
        m = self.machine()
        m.share.folder = str(self.folder / "gone")
        with self.assertRaises(share.ShareError):
            share.start_share(m, ports=(self.port,))

    def test_the_second_port_is_taken_when_the_first_is_busy(self):
        first = self.start(self.machine())
        second_port = share.free_port()
        m = self.machine()
        s = share.start_share(m, ports=(self.port, second_port))
        self.servers.append(s)
        self.assertEqual(first.port, self.port)
        self.assertEqual(s.port, second_port)
        self.assertEqual(s.url_for("user"), f"ftp://10.0.2.2:{second_port}/")
        with self.assertRaises(share.ShareError):
            share.start_share(self.machine(), ports=(self.port,))

    def test_classic_machines_speak_mac_roman(self):
        s = self.start(self.machine())
        self.assertEqual(s.encoding, "mac_roman")
        f = self.client()
        f.encoding = "mac_roman"
        f.storbinary("STOR café.txt", io.BytesIO(b"x"))
        self.assertTrue((self.folder / "café.txt").is_file())
        self.assertEqual(f.nlst(), ["café.txt"])
        f.quit()
        m = Machine(name="X", system="macosx_10_0_to_10_2")
        m.share = Share(folder=str(self.folder))
        s2 = share.start_share(m, ports=(share.free_port(),))
        self.servers.append(s2)
        self.assertEqual(s2.encoding, "utf8")

    def test_stop_frees_the_port(self):
        s = self.start(self.machine())
        s.stop()
        self.servers.remove(s)
        with self.assertRaises(OSError):
            ftplib.FTP().connect("127.0.0.1", self.port, timeout=2)
        again = self.start(self.machine())
        self.assertEqual(again.port, self.port)


if __name__ == "__main__":
    unittest.main()
