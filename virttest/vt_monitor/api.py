import logging
from typing import Optional

from virttest.vt_vmm.api import vmm

LOG = logging.getLogger("avocado." + __name__)


class ConnectController(object):
    """
    Controller for managing virtual machine monitor connections.
    
    This class acts as a proxy for monitor connections, managing the lifecycle
    of connections to VM instances across different nodes in a distributed setup.
    """
    
    def __init__(self, name: str, instance_id: str):
        """
        Initialize the connection controller.

        :param name: Name identifier for the connection
        :type name: str
        :param instance_id: Unique identifier for the VM instance
        :type instance_id: str
        """
        self.instance_id = instance_id
        self._name = name
        self._connects = {}
        self._node = vmm.get_instance_node(self.instance_id)

    @staticmethod
    def _get_service(node):
        """
        Get the connection service from a node.
        
        :param node: Node object containing the proxy service
        :returns: Connection service interface
        """
        return node.proxy.virt.connect

    def create_connect(self, protocol: str, node: Optional[object] = None, log_file: Optional[str] = None) -> str:
        """
        Create a new connection to the VM instance.
        
        :param protocol: Protocol to use for the connection (e.g., 'qmp', 'human')
        :type protocol: str
        :param node: Target node for the connection. Uses default node if None
        :type node: object or None
        :param log_file: Path to log file for connection logging
        :type log_file: str or None
        :returns: Unique connection ID for the created connection
        :rtype: str
        """
        if node is None:
            node = self._node

        LOG.info(
            f"Opening the {protocol} connection {self._name} of "
            f"instance {self.instance_id} on {node.tag}"
        )

        service = self._get_service(node)
        connect_id = service.create_connect(self.instance_id, self._name, protocol, log_file)
        self._connects[connect_id] = node
        return connect_id

    def close_connect(self, connect_id: str):
        """
        Close an existing connection.
        
        :param connect_id: Unique identifier of the connection to close
        :type connect_id: str
        """
        node = self._connects.get(connect_id)
        service = self._get_service(node)
        service.close_connect(connect_id)

    def execute_data(
        self, connect_id: str, data, timeout=None, debug=True, fd=None, data_format=None
    ):
        """
        Execute data through a connection.
        
        :param connect_id: Unique identifier of the connection
        :type connect_id: str
        :param data: Data to execute through the connection
        :param timeout: Timeout in seconds for the operation
        :type timeout: int or None
        :param debug: Enable debug mode. Defaults to True
        :type debug: bool
        :param fd: File descriptor for the operation
        :param data_format: Format of the data
        :type data_format: str or None
        :returns: Result of the data execution
        """
        node = self._connects.get(connect_id)
        service = self._get_service(node)
        return service.execute_connect_data(
            connect_id, data, timeout, debug, fd, data_format
        )

    def get_events(self, connect_id):
        """
        Get all events from a connection.
        
        :param connect_id: Unique identifier of the connection
        :type connect_id: str
        :returns: All events from the connection
        """
        node = self._connects.get(connect_id)
        service = self._get_service(node)
        return service.get_connect_events(connect_id)

    def get_event(self, connect_id, name):
        """
        Get a specific event by name from a connection.
        
        :param connect_id: Unique identifier of the connection
        :type connect_id: str
        :param name: Name of the event to retrieve
        :type name: str
        :returns: The specified event from the connection
        """
        node = self._connects.get(connect_id)
        service = self._get_service(node)
        return service.get_connect_event(connect_id, name)

    def clear_events(self, connect_id):
        """
        Clear all events from a connection.
        
        :param connect_id: Unique identifier of the connection
        :type connect_id: str
        :returns: Result of clearing all events
        """
        node = self._connects.get(connect_id)
        service = self._get_service(node)
        return service.clear_connect_events(connect_id)

    def clear_event(self, connect_id, name):
        """
        Clear a specific event by name from a connection.
        
        :param connect_id: Unique identifier of the connection
        :type connect_id: str
        :param name: Name of the event to clear
        :type name: str
        :returns: Result of clearing the specified event
        """
        node = self._connects.get(connect_id)
        service = self._get_service(node)
        return service.clear_connect_event(connect_id, name)
