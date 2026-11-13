#!/usr/bin/env python
"""
Regression tests for the ARP fallback in libvirt_vm.VM._get_address.

These are isolated unit tests: no guest is started, no libvirt connection is
opened and no command is run on the host. A ``libvirt_vm.VM`` object with an
``ip_sniffing.AddrCache`` is built, and the ``virt_vm.BaseVM._get_address`` and
``utils_net.verify_ip_address_ownership`` code paths run unmodified on top of
fake ``/proc/net/arp`` content, read either locally or through a fake remote
ShellSession. Any attempt to run a host command fails the test.
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

import aexpect

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)

from virttest import ip_sniffing, libvirt_vm, utils_net, utils_params, virt_vm

# Dummy values: locally administered MAC and a TEST-NET-1 (RFC 5737) address.
MAC = "52:54:00:12:34:56"
IP = "192.0.2.10"
ARP_HEADER = (
    "IP address       HW type     Flags       HW address            Mask     Device\n"
)
ARP_WITH_MAC = ARP_HEADER + "%s    0x1         0x2         %s     *        virbr0\n" % (
    IP,
    MAC,
)
ARP_WITHOUT_MAC = ARP_HEADER


class FakeSession(object):
    """
    Remote ShellSession stand-in.

    ``arp_outputs`` is consumed one item per ``cat /proc/net/arp``; the last
    item is repeated. An item that is an Exception instance is raised.
    Any other command returns an empty string.
    """

    def __init__(self, arp_outputs):
        self.arp_outputs = list(arp_outputs)
        self.calls = []

    def cmd_output(self, cmd, timeout=None, **kwargs):
        self.calls.append((cmd, timeout, kwargs))
        if "cat /proc/net/arp" not in cmd:
            return ""
        item = (
            self.arp_outputs.pop(0)
            if len(self.arp_outputs) > 1
            else self.arp_outputs[0]
        )
        if isinstance(item, Exception):
            raise item
        return item

    def arp_calls(self):
        return [c for c in self.calls if "cat /proc/net/arp" in c[0]]


class LibvirtVMGetAddressTest(unittest.TestCase):
    PARAMS = {
        "vm_type": "libvirt",
        "driver_type": "libvirt",
        "nics": "nic1",
        "nettype": "bridge",
        "netdst": "virbr0",
        "mac_nic1": MAC,
        # Make a failed ownership check raise VMAddressVerificationError.
        "pci_assignable_nic1": "no",
    }

    def setUp(self):
        # Patch the objects the code under test really uses instead of
        # resolving dotted names, which depends on what other tests imported.
        for obj, name, value in (
            (libvirt_vm.virsh, "driver", "qemu"),
            (libvirt_vm, "normalize_connect_uri", "qemu:///system"),
            # The ownership check looks for the arping binary on the host even
            # when it runs through a remote session; do not require it here.
            (utils_net.utils_path, "find_command", "arping"),
        ):
            patcher = mock.patch.object(obj, name, return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)
        # Isolation guard: nothing may run a command on the host.
        for func in ("getoutput", "run", "system_output"):
            patcher = mock.patch.object(
                utils_net.process,
                func,
                side_effect=AssertionError("host command run by %s()" % func),
            )
            patcher.start()
            self.addCleanup(patcher.stop)
        self.vm = libvirt_vm.VM(
            "vm1",
            utils_params.Params(dict(self.PARAMS)),
            tempfile.gettempdir(),
            ip_sniffing.AddrCache(),
        )

    def _timeout_error(self):
        return aexpect.ShellTimeoutError("cat /proc/net/arp", "")

    def test_cache_hit_does_not_read_arp(self):
        self.vm.address_cache[MAC] = IP
        session = FakeSession([ARP_WITH_MAC])
        self.assertEqual(self.vm._get_address(session=session, timeout=5), IP)
        # Only the base ownership check read the table, no fallback.
        self.assertEqual(len(session.arp_calls()), 1)

    def test_remote_cache_miss_forwards_session_and_timeout(self):
        session = FakeSession([ARP_WITH_MAC])
        self.assertEqual(self.vm._get_address(session=session, timeout=7.0), IP)
        self.assertEqual(self.vm.address_cache[MAC], IP)
        arp_calls = session.arp_calls()
        # one read for the fallback, one for the base ownership verification
        self.assertEqual(len(arp_calls), 2)
        for _, timeout, kwargs in arp_calls:
            self.assertEqual(timeout, 7.0)
            self.assertTrue(kwargs.get("safe"))

    def test_local_cache_miss_found_in_arp(self):
        arp = mock.mock_open(read_data=ARP_WITH_MAC)
        with mock.patch("virttest.utils_net.open", arp, create=True):
            self.assertEqual(self.vm._get_address(), IP)
        self.assertEqual(self.vm.address_cache[MAC], IP)
        arp.assert_called_with("/proc/net/arp", "r")

    def test_mac_not_in_arp_keeps_missing_error(self):
        session = FakeSession([ARP_WITHOUT_MAC])
        with self.assertRaises(virt_vm.VMIPAddressMissingError):
            self.vm._get_address(session=session, timeout=5)
        self.assertIsNone(self.vm.address_cache[MAC])

    def test_ipv6_exception_preserved(self):
        session = FakeSession([ARP_WITH_MAC])
        with self.assertRaises(virt_vm.VMIPAddressMissingError) as ctx:
            self.vm._get_address(ip_version="ipv6", session=session, timeout=5)
        self.assertEqual(ctx.exception.ip_version, "ipv6")
        self.assertEqual(ctx.exception.mac, MAC)
        # ARP is IPv4 only: the fallback must not run nor touch the cache.
        self.assertEqual(session.arp_calls(), [])
        self.assertIsNone(self.vm.address_cache[MAC])

    def test_verification_failure_drops_cache_entry(self):
        # The entry is visible for the fallback but gone when the base class
        # verifies the address (e.g. unstable ARP entry early in guest boot).
        session = FakeSession([ARP_WITH_MAC, ARP_WITHOUT_MAC])
        with self.assertRaises(virt_vm.VMAddressVerificationError):
            self.vm._get_address(session=session, timeout=0.5)
        self.assertIsNone(self.vm.address_cache[MAC])

    def test_stale_entry_is_not_reused_by_next_lookup(self):
        session = FakeSession([ARP_WITH_MAC, ARP_WITHOUT_MAC])
        with self.assertRaises(virt_vm.VMAddressVerificationError):
            self.vm._get_address(session=session, timeout=0.5)
        # Entry was dropped: the next attempt falls back to ARP again instead
        # of failing verification on a cached, unverified address.
        with self.assertRaises(virt_vm.VMIPAddressMissingError):
            self.vm._get_address(session=session, timeout=0.5)

    def test_remote_arp_timeout_becomes_missing_error(self):
        session = FakeSession([self._timeout_error()])
        with self.assertRaises(virt_vm.VMIPAddressMissingError):
            self.vm._get_address(session=session, timeout=5)
        self.assertIsNone(self.vm.address_cache[MAC])

    def test_remote_arp_timeout_is_retried(self):
        session = FakeSession([self._timeout_error(), ARP_WITH_MAC])

        def get_address(index=0, ip_version="ipv4"):
            return self.vm._get_address(index, ip_version, session=session, timeout=5)

        with mock.patch.object(self.vm, "get_address", side_effect=get_address):
            ipaddr = self.vm.wait_for_get_address(0, timeout=10, interval=0.1)
        self.assertEqual(ipaddr, IP)
        # first read timed out; the retry read the table and verified it
        self.assertGreaterEqual(len(session.arp_calls()), 2)


if __name__ == "__main__":
    unittest.main()
