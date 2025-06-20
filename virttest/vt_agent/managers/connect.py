import logging

from vt_agent.drivers.connect_client import qemu

LOG = logging.getLogger("avocado.service." + __name__)


class ConnectManager(object):
    """
    Manager the connection to the monitor
    """

    def __init__(self):
        self._connects = {}

    @staticmethod
    def create_connect(
        instance_id, instance_pid, instance_type, name, protocol, params, log_file=None
    ):

        LOG.info(
            f"<Instance: {instance_id}(pid: {instance_pid})> Create a {protocol} connection {name}"
        )
        if instance_type == "qemu":
            connect = qemu.create_connect_client(
                instance_id, instance_pid, name, protocol, params, log_file=log_file
            )
            return connect
        elif instance_type == "libvirt":
            raise NotImplementedError("Not implemented")
        else:
            raise NotImplementedError(f"Unsupported connect type {instance_type}")

    def register_connect(self, con_id, connect):
        if con_id in self._connects:
            raise ValueError
        self._connects[con_id] = connect

    def unregister_connect(self, con_id):
        del self._connects[con_id]

    def get_connect(self, con_id=None):
        return self._connects.get(con_id)

    def get_connects_by_instance(self, instance_id):
        connects = []
        for connect in self._connects.values():
            if connect.instance_id == instance_id:
                connects.append(connect)

        return connects
