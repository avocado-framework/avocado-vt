import json
import logging

from .. import instance_drivers

LOG = logging.getLogger("avocado.agent." + __name__)


class VMMError(Exception):
    pass


class VirtualMachinesManager(object):
    def __init__(self):
        self._filename = "/var/instances"
        self._instances = self._load()

    @property
    def instances(self):
        return self._load()

    def _dump_instances(self):
        with open(self._filename, "w") as details:
            json.dump(self._instances, details)

    def _load_instances(self):
        try:
            with open(self._filename, 'r') as instances:
                return json.load(instances)
        except Exception:
            return {}

    def _save(self):
        self._dump_instances()

    def _load(self):
        return self._load_instances()

    def register_instance(self, name, info):
        if name in self._instances:
            LOG.error("The instance %s is already registered.", name)
            return False
        self._instances[name] = info
        self._save()
        return True

    def unregister_instance(self, name):
        if name in self._instances:
            del self._instances[name]
            self._save()
            return True
        LOG.error("The instance %s is not registered" % name)
        return False

    def get_instance(self, name):
        return self._instances.get(name)

    def update_instance(self, name, info):
        self._instances.get(name).update(info)
        self._save()

    @staticmethod
    def build_instance(driver_kind, spec):
        instance_info = {}
        instance_driver = instance_drivers.get_instance_driver(driver_kind, spec)
        instance_info["devices"] = instance_driver.create_devices()
        instance_info["driver"] = instance_driver
        return instance_info

    def run_instance(self, instance_id):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        cmdline = instance_driver.make_cmdline()
        instance_info["cmdline"] = cmdline
        process = instance_driver.run_cmdline(cmdline)
        instance_info["process"] = process

    def stop_instance(self, instance_id):
        instance_info = self.get_instance(instance_id)
        instance_driver = instance_info["driver"]
        if instance_driver.is_alive():
            pass

    def get_instance_status(self, instance_id):
        pass

    def get_instance_pid(self, instance_id):
        pass
