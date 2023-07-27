class Conductor(object):
    def __init__(self, node, instance_id, instance_config):
        self._instance_server = node.proxy.virt.vmm
        self._instance_id = instance_id
        self._instance_config = instance_config
        self._instance_driver = instance_config["kind"]

    def build_instance(self):
        self._instance_server.build_instance(self._instance_id,
                                             self._instance_driver,
                                             self._instance_config["spec"])

    def run_instance(self):
        self._instance_server.run_instance(self._instance_id)

    def stop_instance(self):
        self._instance_server.stop_instance(self._instance_id)

    def get_instance_status(self):
        self._instance_server.get_instance_status(self._instance_id)

    def get_instance_pid(self):
        self._instance_server.get_instance_pid(self._instance_id)

    def get_consoles(self):
        return self._instance_server.get_consoles(self._instance_id)
