#!/usr/bin/python

import gc
import logging
import os
import sys
import unittest

from aexpect.exceptions import ShellProcessTerminatedError, ShellStatusError
from avocado import Test, skipUnless

# simple magic for using scripts within a source tree
basedir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.isdir(os.path.join(basedir, "virttest")):
    sys.path.append(basedir)


def virsh_session_is_alive(session_id):
    """Return whether one particular aexpect-backed virsh session is alive."""
    from virttest import virsh

    try:
        session = virsh.VirshSession(a_id=session_id, check_libvirtd=False)
        return session.is_alive()
    except (
        ShellStatusError,
        ShellProcessTerminatedError,
    ):  # The session no longer exists or cannot be attached.
        return False


def virsh_is_available():
    """Check whether the test environment provides a real virsh executable."""
    from virttest import virsh

    return virsh.Virsh()["virsh_exec"] != "/bin/true"


VIRSH_AVAILABLE = virsh_is_available()


class bogusVirshFailureException(unittest.TestCase.failureException):
    def __init__(self, *args, **dargs):
        self.virsh_args = args
        self.virsh_dargs = dargs

    def __str__(self):
        msg = (
            "Codepath under unittest attempted call to un-mocked virsh"
            " method, with args: '%s' and dargs: '%s'"
            % (self.virsh_args, self.virsh_dargs)
        )
        return msg


def FakeVirshFactory(preserve=None):
    """
    Return Virsh() instance with methods to raise bogusVirshFailureException.

    Users of this class should override methods under test on instance.
    :param preserve: List of symbol names NOT to modify, None for all
    """
    from virttest import virsh

    def raise_bogusVirshFailureException(*args, **dargs):
        raise bogusVirshFailureException()

    if preserve is None:
        preserve = []
    fake_virsh = virsh.Virsh(
        virsh_exec="/bin/false", uri="qemu:///system", debug=True, ignore_status=True
    )
    # Make all virsh commands throw an exception by calling it
    for symbol in dir(virsh):
        # Get names of just closure functions by Virsh class
        if symbol in virsh.NOCLOSE + preserve:
            continue
        if isinstance(getattr(fake_virsh, symbol), virsh.VirshClosure):
            # fake_virsh is a propcan, can't use setattr.
            fake_virsh.__super_set__(symbol, raise_bogusVirshFailureException)
    return fake_virsh


class ModuleLoad(Test):
    from virttest import virsh


class ConstantsTest(ModuleLoad):
    def test_ModuleLoad(self):
        self.assertTrue(hasattr(self.virsh, "NOCLOSE"))
        self.assertTrue(hasattr(self.virsh, "SCREENSHOT_ERROR_COUNT"))
        self.assertTrue(hasattr(self.virsh, "VIRSH_COMMAND_CACHE"))
        self.assertTrue(hasattr(self.virsh, "VIRSH_EXEC"))


class TestVirshClosure(ModuleLoad):
    @staticmethod
    def somefunc(*args, **dargs):
        return (args, dargs)

    class SomeClass(dict):
        def somemethod(self):
            return "foobar"

    def test_init(self):
        # save some typing
        VC = self.virsh.VirshClosure
        # self is guaranteed to be not dict-like
        self.assertRaises(ValueError, VC, self.somefunc, self)
        self.assertRaises(ValueError, VC, lambda: None, self)

    def test_args(self):
        # save some typing
        VC = self.virsh.VirshClosure
        tcinst = self.SomeClass()
        vcinst = VC(self.somefunc, tcinst)
        args, dargs = vcinst("foo")
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0], "foo")
        self.assertEqual(len(dargs), 0)

    def test_fake_virsh(self):
        fake_virsh = FakeVirshFactory()
        for symb in dir(self.virsh):
            if symb in self.virsh.NOCLOSE:
                continue
            value = fake_virsh.__super_get__(symb)
            self.assertRaises(unittest.TestCase.failureException, value)

    def test_dargs(self):
        # save some typing
        VC = self.virsh.VirshClosure
        tcinst = self.SomeClass(foo="bar")
        vcinst = VC(self.somefunc, tcinst)
        args, dargs = vcinst()
        self.assertEqual(len(args), 0)
        self.assertEqual(len(dargs), 1)
        self.assertEqual(list(dargs.keys()), ["foo"])
        self.assertEqual(list(dargs.values()), ["bar"])

    def test_args_and_dargs(self):
        # save some typing
        VC = self.virsh.VirshClosure
        tcinst = self.SomeClass(foo="bar")
        vcinst = VC(self.somefunc, tcinst)
        args, dargs = vcinst("foo")
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0], "foo")
        self.assertEqual(len(dargs), 1)
        self.assertEqual(list(dargs.keys()), ["foo"])
        self.assertEqual(list(dargs.values()), ["bar"])

    def test_args_dargs_subclass(self):
        # save some typing
        VC = self.virsh.VirshClosure
        tcinst = self.SomeClass(foo="bar")
        vcinst = VC(self.somefunc, tcinst)
        args, dargs = vcinst("foo")
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0], "foo")
        self.assertEqual(len(dargs), 1)
        self.assertEqual(list(dargs.keys()), ["foo"])
        self.assertEqual(list(dargs.values()), ["bar"])

    def test_update_args_dargs_subclass(self):
        # save some typing
        VC = self.virsh.VirshClosure
        tcinst = self.SomeClass(foo="bar")
        vcinst = VC(self.somefunc, tcinst)
        args, dargs = vcinst("foo")
        self.assertEqual(len(args), 1)
        self.assertEqual(args[0], "foo")
        self.assertEqual(len(dargs), 1)
        self.assertEqual(list(dargs.keys()), ["foo"])
        self.assertEqual(list(dargs.values()), ["bar"])
        # Update dictionary
        tcinst["sna"] = "fu"
        # Is everything really the same?
        args, dargs = vcinst("foo", "baz")
        self.assertEqual(len(args), 2)
        self.assertEqual(args[0], "foo")
        self.assertEqual(args[1], "baz")
        self.assertEqual(len(dargs), 2)
        self.assertEqual(dargs["foo"], "bar")
        self.assertEqual(dargs["sna"], "fu")

    def test_multi_inst(self):
        # save some typing
        VC1 = self.virsh.VirshClosure
        VC2 = self.virsh.VirshClosure
        tcinst1 = self.SomeClass(darg1=1)
        tcinst2 = self.SomeClass(darg1=2)
        vcinst1 = VC1(self.somefunc, tcinst1)
        vcinst2 = VC2(self.somefunc, tcinst2)
        args1, dargs1 = vcinst1(1)
        args2, dargs2 = vcinst2(2)
        self.assertEqual(len(args1), 1)
        self.assertEqual(len(args2), 1)
        self.assertEqual(args1[0], 1)
        self.assertEqual(args2[0], 2)
        self.assertEqual(len(dargs1), 1)
        self.assertEqual(len(dargs2), 1)
        self.assertEqual(dargs1["darg1"], 1)
        self.assertEqual(dargs2["darg1"], 2)


class ConstructorsTest(ModuleLoad):
    def test_VirshBase(self):
        vb = self.virsh.VirshBase()
        del vb  # keep pylint happy

    def test_Virsh(self):
        v = self.virsh.Virsh()
        del v  # keep pylint happy

    def test_VirshPersistent(self):
        test_virsh = self.virsh.Virsh()
        if test_virsh["virsh_exec"] == "/bin/true":
            return
        else:
            logging.disable(logging.INFO)
            vp = self.virsh.VirshPersistent()
            vp.close_session()  # Make sure session gets cleaned up

    def TestVirshClosure(self):
        class MyDict(dict):
            pass

        vc = self.virsh.VirshClosure(None, MyDict())
        del vc  # keep pylint happy


# Ensure the following tests ONLY run if a valid virsh command exists #####
class ModuleLoadCheckVirsh(Test):
    from virttest import virsh


@skipUnless(VIRSH_AVAILABLE, "no virsh executable was found")
@unittest.skipUnless(VIRSH_AVAILABLE, "no virsh executable was found")
class SessionManagerTest(ModuleLoadCheckVirsh):
    def test_del_VirshPersistent(self):
        """
        Unittest for __del__ of VirshPersistent.

        This test makes sure the __del__ method of VirshPersistent works
        well in `del vp_instance`.
        """
        vp = self.virsh.VirshPersistent()
        session_id = vp.session_id
        self.assertTrue(virsh_session_is_alive(session_id))
        del vp
        gc.collect()
        self.assertFalse(virsh_session_is_alive(session_id))

    def test_VirshSession(self):
        """
        Unittest for VirshSession.

        This test use VirshSession over VirshPersistent with auto_close=True.
        """
        virsh_exec = self.virsh.Virsh()["virsh_exec"]
        # Build a VirshSession object.
        session_1 = self.virsh.VirshSession(virsh_exec, auto_close=True)
        session_id = session_1.get_id()
        self.assertTrue(session_1.is_alive())
        del session_1
        gc.collect()
        self.assertFalse(virsh_session_is_alive(session_id))

    def test_VirshPersistent(self):
        """
        Unittest for session manager of VirshPersistent.
        """
        vp_1 = self.virsh.VirshPersistent()
        session_id = vp_1.session_id
        self.assertTrue(virsh_session_is_alive(session_id))
        # Init the vp_2 with same params of vp_1.
        vp_2 = self.virsh.VirshPersistent(**vp_1)
        # Make sure vp_1 and vp_2 are refer to the same session.
        self.assertEqual(vp_1.session_id, vp_2.session_id)

        del vp_1
        # Make sure the session is not closed when vp_2 still refer to it.
        self.assertTrue(virsh_session_is_alive(session_id))
        del vp_2
        gc.collect()
        # Session was closed since no other VirshPersistent refer to it.
        self.assertFalse(virsh_session_is_alive(session_id))


@skipUnless(VIRSH_AVAILABLE, "no virsh executable was found")
@unittest.skipUnless(VIRSH_AVAILABLE, "no virsh executable was found")
class VirshHasHelpCommandTest(ModuleLoadCheckVirsh):
    def setUp(self):
        # subclasses override self.virsh
        self.VIRSH_COMMAND_CACHE = self.virsh.VIRSH_COMMAND_CACHE

    def test_false_command(self):
        self.assertFalse(self.virsh.has_help_command("print"))
        self.assertFalse(self.virsh.has_help_command("Commands:"))
        self.assertFalse(self.virsh.has_help_command("dom"))
        self.assertFalse(self.virsh.has_help_command("pool"))

    def test_true_command(self):
        self.assertTrue(self.virsh.has_help_command("uri"))
        self.assertTrue(self.virsh.has_help_command("help"))
        self.assertTrue(self.virsh.has_help_command("list"))

    def test_no_cache(self):
        self.VIRSH_COMMAND_CACHE = None
        self.assertTrue(self.virsh.has_help_command("uri"))
        self.VIRSH_COMMAND_CACHE = []
        self.assertTrue(self.virsh.has_help_command("uri"))

    def test_subcommand_help(self):
        regex = r"--command"
        self.assertTrue(self.virsh.has_command_help_match("help", regex))
        self.assertFalse(self.virsh.has_command_help_match("uri", regex))

    def test_groups_in_commands(self):
        # groups will be empty in older libvirt, but test will still work
        groups = self.virsh.help_command_group(cache=True)
        groups_set = set(groups)
        commands = self.virsh.help_command_only(cache=True)
        commands_set = set(commands)
        grp_cmd = self.virsh.help_command(cache=True)
        grp_cmd_set = set(grp_cmd)
        # No duplicates check
        self.assertEqual(len(commands_set), len(commands))
        self.assertEqual(len(groups_set), len(groups))
        self.assertEqual(len(grp_cmd_set), len(grp_cmd))
        # No groups in commands or commands in groups
        self.assertEqual(len(groups_set & commands_set), 0)
        # Groups and Commands in help_command
        self.assertTrue(len(grp_cmd_set), len(commands_set) + len(groups_set))


@skipUnless(VIRSH_AVAILABLE, "no virsh executable was found")
@unittest.skipUnless(VIRSH_AVAILABLE, "no virsh executable was found")
class VirshHelpCommandTest(ModuleLoadCheckVirsh):
    def test_cache_command(self):
        l1 = self.virsh.help_command(cache=True)
        l2 = self.virsh.help_command()
        l3 = self.virsh.help_command()
        self.assertEqual(l1, l2)
        self.assertEqual(l2, l3)
        self.assertEqual(l3, l1)


class VirshClassHasHelpCommandTest(VirshHasHelpCommandTest):
    def setUp(self):
        logging.disable(logging.INFO)
        super(VirshClassHasHelpCommandTest, self).setUp()
        self.virsh = self.virsh.Virsh(debug=False)


@skipUnless(VIRSH_AVAILABLE, "no virsh executable was found")
@unittest.skipUnless(VIRSH_AVAILABLE, "no virsh executable was found")
class VirshPersistentClassHasHelpCommandTest(VirshHasHelpCommandTest):
    def setUp(self):
        logging.disable(logging.INFO)
        super(VirshPersistentClassHasHelpCommandTest, self).setUp()
        self.VirshPersistent = self.virsh.VirshPersistent
        self.virsh = self.VirshPersistent(debug=False)
        self.assertTrue(virsh_session_is_alive(self.virsh.session_id))

    def test_recycle_session(self):
        # virsh can be used as a dict of it's properties
        another = self.VirshPersistent(**self.virsh)
        self.assertEqual(self.virsh.session_id, another.session_id)

    def tearDown(self):
        try:
            if hasattr(self.virsh, "session_id"):
                session_id = self.virsh.session_id
                self.assertTrue(virsh_session_is_alive(session_id))
                self.virsh.close_session()
                self.assertFalse(virsh_session_is_alive(session_id))
        finally:
            super(VirshPersistentClassHasHelpCommandTest, self).tearDown()


if __name__ == "__main__":
    unittest.main()
