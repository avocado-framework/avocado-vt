import os
import logging
import pickle


from virttest import virt_vm


from instance_drivers.qemu import QemuInstanceDriver
from instance_drivers.libvirt import LibvirtInstanceDriver


LOG = logging.getLogger("avocado.service." + __name__)


class VMMigrateProtoUnsupportedError(virt_vm.VMMigrateProtoUnknownError):

    """
    When QEMU tells us it doesn't know about a given migration protocol.

    This usually happens when we're testing older QEMU. It makes sense to
    skip the test in this situation.
    """

    def __init__(self, protocol=None, output=None):
        self.protocol = protocol
        self.output = output

    def __str__(self):
        return (
            "QEMU reports it doesn't know migration protocol '%s'. "
            "QEMU output: %s" % (self.protocol, self.output)
        )


def qemu_proc_term_handler(instance_id, monitor_exit_status, exit_status):
    """Monitors qemu process unexpected exit.

    Callback function to detect QEMU process non-zero exit status and
    push VMExitStatusError to background error bus.

    :param vm: VM object.
    :param monitor_exit_status: True to push VMUnexpectedExitError instance
        with calltrace to global error event bus.
    :param exit_status: QEMU process exit status.
    """
    vmm = VirtualMachinesManager()
    instance_info = vmm.get_instance(instance_id)
    devices = instance_info.get("devices")
    for snapshot in devices.temporary_image_snapshots:
        try:
            os.unlink(snapshot)
        except OSError:
            pass
    devices.temporary_image_snapshots.clear()


def get_instance_driver(instance_id, kind):
    _drivers = {
        "qemu": QemuInstanceDriver,
        "libvirt": LibvirtInstanceDriver,
    }

    if kind not in _drivers:
        raise OSError("Unsupported the %s instance driver" % kind)
    return _drivers.get(kind)(instance_id)


class VMMError(Exception):
    pass


class VirtualMachinesManager(object):
    def __init__(self):
        self._filename = "/var/instances"
        #self._instances = self._load()
        # self._instances = {}

    @property
    def instances(self):
        return self._load()

    def _dump_instances(self, instances):
        with open(self._filename, "wb") as details:
            pickle.dump(instances, details)

    def _load_instances(self):
        # try:
        #     with open(self._filename, "rb") as instances:
        #         return pickle.load(instances)
        # except Exception as e:
        #     LOG.error("Error loading instances: %s", e)
        #     return {}
        if os.path.exists(self._filename):
            with open(self._filename, "rb") as instances:
                return pickle.load(instances)
        return {}

    def _save(self, instances):
        self._dump_instances(instances)

    def _load(self):
        return self._load_instances()

    def register_instance(self, instance_id, info):
        if instance_id in self.instances:
            LOG.error("The instance %s is already registered.", instance_id)
            return False
        instances = self._load()
        instances[instance_id] = info
        self._save(instances)
        return True

    def unregister_instance(self, instance_id):
        instances = self._load()
        if instance_id in instances.copy():
            del instances[instance_id]
            self._save(instances)
            return True
        LOG.error("The instance %s is not registered" % instance_id)
        return False

    def get_instance(self, instance_id):
        return self.instances.get(instance_id)

    def update_instance(self, instance_id, info):
        instances = self._load()
        instances.get(instance_id).update(info)
        self._save(instances)

    @staticmethod
    def build_instance(instance_id, driver_kind, spec, migrate_incoming=None):
        instance_info = dict()
        instance_info["driver_kind"] = driver_kind
        instance_driver = get_instance_driver(instance_id, driver_kind)
        instance_info["driver"] = instance_driver
        instance_driver.create_devices(spec)
        instance_info["devices"] = instance_driver.get_devices()

        if migrate_incoming:
            instance_info["migrate_incoming"] = migrate_incoming
        return instance_info

    def run_instance(self, instance_id):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        migrate_incoming = instance_info.get("migrate_incoming")
        migrate_inc_uri = migrate_incoming.get("uri") if migrate_incoming else None

        instance_driver.make_cmdline(migrate_inc_uri)
        cmdline = instance_driver.get_cmdline()
        instance_info["cmdline"] = cmdline
        instance_driver.start(cmdline)
        self.update_instance(instance_id, {"driver": instance_driver,
                                           "cmdline": cmdline})

    def get_instance_pid(self, instance_id):
        """
        Return the VM's PID.  If the VM is dead return None.

        :note: This works under the assumption that self.process.get_pid()
        :return: the PID of the parent shell process.
        """
        instance_info = self.get_instance(instance_id)
        # process = instance_info.get("process")
        instance_driver = instance_info["driver"]
        return instance_driver.get_pid()

    def is_instance_dead(self, instance_id):
        """
        Return True if the qemu process is dead.
        """
        instance_info = self.get_instance(instance_id)
        _process = instance_info.get("process")
        instance_driver = instance_info["driver"]
        return not _process or not instance_driver.is_proc_alive()

    def stop_instance(self, instance_id, graceful=True, timeout=60,
                      shutdown_cmd=None, username=None, password=None,
                      prompt=None):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        instance_driver.stop(graceful, timeout, shutdown_cmd,
                             username, password, prompt)

    def pause_instance(self, instance_id):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.pause()

    def is_instance_paused(self, instance_id):
        instance_info = self.get_instance(instance_id)
        _process = instance_info.get("process")
        instance_driver = instance_info["driver"]
        return _process and instance_driver.is_proc_alive() and instance_driver.is_paused()

    def continue_instance(self, instance_id):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.cont()

    def is_instance_running(self, instance_id):
        instance_info = self.get_instance(instance_id)
        _process = instance_info.get("process")
        instance_driver = instance_info["driver"]
        return _process and instance_driver.is_proc_alive()

    def get_instance_consoles(self, instance_id, console_type):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        if console_type == "serial":
            return instance_driver.get_serial_consoles()
        elif console_type == "vnc":
            return instance_driver.get_vnc_consoles()
        elif console_type == "spice":
            return instance_driver.get_spice_consoles()
        else:
            raise NotImplementedError

    def get_instance_serials(self, instance_id):
        return

    def get_instance_process_info(self, instance_id, name):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.get_proc_info(name)

    def cleanup_instance(self, instance_id, free_mac_addresses=True):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        instance_driver.cleanup(free_mac_addresses)

    def set_instance_migration_parameter(self, instance_id, connect_id, parameter, value):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        return instance_driver.set_migration_parameter(connect_id, parameter, value)
