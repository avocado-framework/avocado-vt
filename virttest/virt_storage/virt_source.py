from virttest.virt_storage.virt_auth import StorageAuthation
from virttest.virt_storage.virt_device import HostAdapter
from virttest.virt_storage.virt_device import StorageDevice
from virttest.virt_storage.virt_device import StorageHost


class PoolSource(object):

    def __init__(self):
        self.name = None
        self.auth = None
        self.hosts = []
        self.devices = []
        self.format = None
        self.vendor = None
        self.adapter = None
        self.product = None
        self.protocol = None
        self.dir_path = None
        self.initiator = None

    def hosts_define_by_params(self, params):
        for item in params.objects("storage_hosts"):
            _params = params.object_params(item)
            host = StorageHost.host_define_by_params(_params)
            self.hosts.append(host)

    def devices_define_by_params(self, params):
        for item in params.objects("devices"):
            _params = params.object_params(item)
            device = StorageDevice.device_define_by_params(_params)
            self.devices.append(device)

    def auth_define_by_params(self, params):
        if params.get("authorization_method", "off") != "off":
            self.auth = StorageAuthation.auth_define_by_params(params)

    def adapter_define_by_params(self, params):
        self.adapter = HostAdapter.adapter_define_by_params(params)

    @classmethod
    def source_define_by_params(cls, name, params):
        instance = cls()
        instance.name = name
        instance.initiator = params.get("initiator")
        instance.vendor = params.get("vendor")
        instance.protocol = params.get("protocol")
        instance.product = params.get("product")
        instance.dir_path = params.get("source_dir")
        instance.format = params.get("source_format")
        instance.hosts_define_by_params(params)
        instance.devices_define_by_params(params)
        instance.auth_define_by_params(params)
        instance.adapter_define_by_params(params)
        return instance

    def __str__(self):
        return "%s: %s" % (self.__class__.__name__, self.name)
