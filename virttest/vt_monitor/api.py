import logging

from virttest import utils_logfile
from virttest.vt_cluster.node import Node
from virttest.vt_vmm.api import vmm

from .rpcpai import ConnectAPI

LOG = logging.getLogger("avocado." + __name__)


class ConnectController(object):  # AKA: MonitorProxy
    def __init__(self, name: str, instance_id: str):
        """
        The controller of the monitor.

        """
        self.instance_id = instance_id
        self._name = name
        self._connect_api = ConnectAPI()
        self._connects = {}
        # Get the default node for instance
        self._node = vmm.get_instance_node(self.instance_id)

    def open_connect(self, protocol, node: Node = None, log_file: str = None) -> str:
        if node is None:
            node = self._node

        LOG.info(
            f"Opening the {protocol} connection {self._name} of "
            f"instance {self.instance_id} on {node.tag}"
        )

        if log_file is None and not node._is_remote_node:
            log_name = "%s-instance-%s.log" % (self._name, self.instance_id)
            log_file = utils_logfile.get_log_filename(log_name)

        connect_id = self._connect_api.open_connect(
            node, self.instance_id, self._name, protocol, log_file
        )
        self._connects[connect_id] = node
        return connect_id

    def is_connected(self, node: Node = None) -> bool:
        if node is None:
            node = self._node

        return self._connect_api.is_connected(node, self.instance_id, self._name)

    def get_connect(self, node: Node = None):
        if node is None:
            node = self._node

        for connect_id, _node in self._connects.items():
            if _node == node:
                return connect_id

    def close_connect(self, connect_id: str):
        node = self._connects.get(connect_id)
        LOG.info(f"closing the connection to {node}")
        self._connect_api.close_connect(node, connect_id)

    def establish_session(self, connect_id: str, establish_cmd: str = None):
        node = self._connects.get(connect_id)
        LOG.info(f"establishing connection session to {node}")
        self._connect_api.establish_session(node, connect_id, establish_cmd)

    def connect(self, protocol, node: Node = None, log_file=None):
        if node is None:
            node = self._node

        return self.open_connect(protocol, node, log_file)
        # self.establish_session(connect_id)

    def disconnect(self, connect_id):
        LOG.info(f"disconnecting the connection {connect_id}")
        node = self._connects.get(connect_id)
        try:
            self._connect_api.close_connect(node, connect_id)
        except Exception as err:
            LOG.error(f"Failed to disconnect from {node}: {err}")

    def send_data(self, connect_id: str, data: bytes, fds: list[int] = None):
        node = self._connects.get(connect_id)
        self._connect_api.send_data(node, connect_id, data, fds)

    def recv_all(self, connect_id: str, bufsize: int = 1024) -> bytes:
        node = self._connects.get(connect_id)
        return self._connect_api.recv_all(node, connect_id, bufsize)

    def is_data_available(self, connect_id: str, timeout: int) -> bool:
        node = self._connects.get(connect_id)
        return self._connect_api.is_data_available(node, connect_id, timeout)

    def is_responsive(self, connect_id: str) -> bool:
        node = self._connects.get(connect_id)
        return self._connect_api.is_responsive(node, connect_id)

    def execute_data(
        self, connect_id: str, data, timeout=None, debug=True, fd=None, data_format=None
    ):
        node = self._connects.get(connect_id)
        return self._connect_api.execute_data(
            node, connect_id, data, timeout, debug, fd, data_format
        )

    def get_events(self, connect_id):
        node = self._connects.get(connect_id)
        return self._connect_api.get_events(node, connect_id)

    def get_event(self, connect_id, name):
        node = self._connects.get(connect_id)
        return self._connect_api.get_event(node, connect_id, name)

    def clear_events(self, connect_id):
        node = self._connects.get(connect_id)
        return self._connect_api.clear_events(node, connect_id)

    def clear_event(self, connect_id, name):
        node = self._connects.get(connect_id)
        return self._connect_api.clear_event(node, connect_id, name)
