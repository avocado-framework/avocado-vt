class HostAdapter(object):

    def __init__(self):
        self.name = None
        self.type = None
        self.wwn = None
        self.wwnn = None
        self.wwpn = None
        self.addr = None

    @classmethod
    def adapter_define_by_params(cls, params):
        inst = cls()
        inst.name = params.get("apapter_name")
        inst.type = params.get("adapter_type")
        inst.wwn = params.get("wwn")
        inst.wwpn = params.get("wwpn")
        inst.wwnn = params.get("wwnn")
        parent = params.get("parent")
        if parent:
            parent_params = params.object_params(parent)
            parent_adapter = cls.adapter_define_by_params(parent_params)
            inst.parent = parent_adapter
        return inst


class StorageDevice(object):

    def __init__(self, path):
        self.path = path

    @classmethod
    def device_define_by_params(cls, params):
        return cls(params.get("device_path"))


class StorageHost(object):

    def __init__(self, hostname, port=None):
        self.hostname = hostname
        self.port = port

    @classmethod
    def host_define_by_params(cls, params):
        hostname = params.get("hostname")
        port = params.get("port")
        return cls(hostname, port)
