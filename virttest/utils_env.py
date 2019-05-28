import os
import logging
import threading
import functools
try:
    from collections import UserDict as IterableUserDict
except ImportError:
    from UserDict import IterableUserDict
try:
    import pickle as cPickle
except ImportError:
    import cPickle

from aexpect import remote

from avocado.core import exceptions

from virttest import virt_vm
from virttest import ip_sniffing

ENV_VERSION = 1


def get_env_version():
    return ENV_VERSION


class EnvSaveError(Exception):
    pass


def lock_safe(function):
    """
    Get the environment safe lock, run the function, then release the lock.

    Unfortunately, it only works if the 1st argument of the function is an
    Env instance. This is mostly to save up code.

    :param function: Function to wrap.
    """
    @functools.wraps(function)
    def wrapper(env, *args, **kwargs):
        with env.save_lock:
            return function(env, *args, **kwargs)
    return wrapper


class Env(IterableUserDict):

    """
    A dict-like object containing global objects used by tests.
    """

    def __init__(self, filename=None, version=0):
        """
        Create an empty Env object or load an existing one from a file.

        If the version recorded in the file is lower than version, or if some
        error occurs during unpickling, or if filename is not supplied,
        create an empty Env object.

        :param filename: Path to an env file.
        :param version: Required env version (int).
        """
        IterableUserDict.__init__(self)
        empty = {"version": version}
        self._filename = filename
        self._sniffer = None
        self.save_lock = threading.RLock()
        if filename:
            try:
                if os.path.isfile(filename):
                    with open(filename, "rb") as f:
                        env = cPickle.load(f)
                    if env.get("version", 0) >= version:
                        self.data = env
                    else:
                        logging.warn(
                            "Incompatible env file found. Not using it.")
                        self.data = empty
                else:
                    # No previous env file found, proceed...
                    logging.warn("Creating new, empty env file")
                    self.data = empty
            # Almost any exception can be raised during unpickling, so let's
            # catch them all
            except Exception as e:
                logging.warn("Exception thrown while loading env")
                logging.warn(e)
                logging.warn("Creating new, empty env file")
                self.data = empty
        else:
            logging.warn("Creating new, empty env file")
            self.data = empty

    def save(self, filename=None):
        """
        Pickle the contents of the Env object into a file.

        :param filename: Filename to pickle the dict into.  If not supplied,
                use the filename from which the dict was loaded.
        """
        filename = filename or self._filename
        if filename is None:
            raise EnvSaveError("No filename specified for this env file")
        with self.save_lock, open(filename, "wb") as f:
            cPickle.dump(self.data, f, protocol=0)

    def get_all_vms(self):
        """
        Return a list of all VM objects in this Env object.
        """
        return [v for k, v in self.data.items() if k and k.startswith("vm__")]

    def clean_objects(self):
        """
        Destroy all objects registered in this Env object.
        """
        self.stop_ip_sniffing()
        for key in self.data:
            try:
                if key.startswith("vm__"):
                    self.data[key].destroy(gracefully=False)
            except Exception:
                pass
        self.data = {}

    def destroy(self):
        """
        Destroy all objects stored in Env and remove the backing file.
        """
        self.clean_objects()
        if self._filename is not None:
            if os.path.isfile(self._filename):
                os.unlink(self._filename)

    def get_vm(self, name):
        """
        Return a VM object by its name.

        :param name: VM name.
        """
        return self.data.get("vm__%s" % name)

    def create_vm(self, vm_type, target, name, params, bindir):
        """
        Create and register a VM in this Env object
        """
        vm_class = virt_vm.BaseVM.lookup_vm_class(vm_type, target)
        if vm_class is not None:
            vm = vm_class(name, params, bindir, self.get("address_cache"))
            self.register_vm(name, vm)
            return vm

    @lock_safe
    def register_vm(self, name, vm):
        """
        Register a VM in this Env object.

        :param name: VM name.
        :param vm: VM object.
        """
        self.data["vm__%s" % name] = vm

    @lock_safe
    def unregister_vm(self, name):
        """
        Remove a given VM.

        :param name: VM name.
        """
        del self.data["vm__%s" % name]

    @lock_safe
    def register_syncserver(self, port, server):
        """
        Register a Sync Server in this Env object.

        :param port: Sync Server port.
        :param server: Sync Server object.
        """
        self.data["sync__%s" % port] = server

    @lock_safe
    def unregister_syncserver(self, port):
        """
        Remove a given Sync Server.

        :param port: Sync Server port.
        """
        del self.data["sync__%s" % port]

    def get_syncserver(self, port):
        """
        Return a Sync Server object by its port.

        :param port: Sync Server port.
        """
        return self.data.get("sync__%s" % port)

    @lock_safe
    def register_lvmdev(self, name, lvmdev):
        """
        Register lvm device object into env;

        :param name: name of register lvmdev object
        :param lvmdev: lvmdev object;
        """
        self.data["lvmdev__%s" % name] = lvmdev

    @lock_safe
    def unregister_lvmdev(self, name):
        """
        Remove lvm device object from env;

        :param name: name of lvm device object;
        """
        del self.data["lvmdev__%s" % name]

    def get_lvmdev(self, name):
        """
        Get lvm device object by name from env;

        :param name: lvm device object name;
        :return: lvmdev object
        """
        return self.data.get("lvmdev__%s" % name)

    def start_ip_sniffing(self, params):
        """
        Start ip sniffing.

        :param params: Params object.
        """
        self.data.setdefault("address_cache", ip_sniffing.AddrCache())
        sniffers = ip_sniffing.Sniffers

        if not self._sniffer:
            remote_pp = params.get("remote_preprocess") == "yes"
            remote_opts = None
            session = None
            if remote_pp:
                client = params.get('remote_shell_client', 'ssh')
                remote_opts = (params['remote_node_address'],
                               params.get('remote_shell_port', '22'),
                               params['remote_node_user'],
                               params['remote_node_password'],
                               params.get('remote_shell_prompt', '#'))
                session = remote.remote_login(client, *remote_opts)
            for s_cls in sniffers:
                if s_cls.is_supported(session):
                    self._sniffer = s_cls(self.data["address_cache"],
                                          "ip-sniffer.log",
                                          remote_opts)
                    break
            if session:
                session.close()

        if not self._sniffer:
            raise exceptions.TestError("Can't find any supported ip sniffer! "
                                       "%s" % [s.command for s in sniffers])

        self._sniffer.start()

    def stop_ip_sniffing(self):
        """Stop ip sniffing."""
        if self._sniffer:
            self._sniffer.stop()
