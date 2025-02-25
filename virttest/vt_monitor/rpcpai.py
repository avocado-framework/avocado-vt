from threading import RLock


class ConnectAPI(object):
    def __init__(self):
        self._lock = RLock()

    @staticmethod
    def _get_server(node):
        return node.proxy.virt.connect

    def open_connect(self, node, instance_id, connect_name, protocol, log_file=None):
        client = self._get_server(node)
        connect_id = client.open_connect(instance_id, connect_name, protocol, log_file)
        return connect_id

    def is_connected(self, node, instance_id, connect_name):
        client = self._get_server(node)
        return client.is_connected(instance_id, connect_name)

    def establish_session(self, node, connect_id, establish_cmd=None):
        client = self._get_server(node)
        client.establish_connect_session(connect_id, establish_cmd)

    def close_connect(self, node, connect_id):
        client = self._get_server(node)
        client.close_connect(connect_id)

    def get_monitor_log_files(self, node, monitor_id):
        client = self._get_server(node)
        return client.get_monitor_log_files(monitor_id)

    def send_data(self, node, connect_id, data, fds):
        client = self._get_server(node)
        client.send_data(connect_id, data, fds)

    def recv_all(self, node, connect_id, bufszie):
        client = self._get_server(node)
        return client.recv_all(connect_id, bufszie)

    def is_data_available(self, node, connect_id, timeout):
        client = self._get_server(node)
        return client.is_data_available(connect_id, timeout)

    def is_responsive(self, node, connect_id):
        client = self._get_server(node)
        return client.is_responsive(connect_id)

    def get_log_files(self, node, connect_id):
        client = self._get_server(node)
        return client.get_log_files(connect_id)

    def execute_data(
        self,
        node,
        connect_id,
        data,
        timeout=None,
        debug=True,
        fd=None,
        data_format=None,
    ):
        client = self._get_server(node)
        return client.execute_connect_data(
            connect_id, data, timeout, debug, fd, data_format
        )

    def get_events(self, node, connect_id):
        client = self._get_server(node)
        return client.get_connect_events(connect_id)

    def get_event(self, node, connect_id, name):
        client = self._get_server(node)
        return client.get_connect_event(connect_id, name)

    def clear_events(self, node, connect_id):
        client = self._get_server(node)
        return client.clear_connect_events(connect_id)

    def clear_event(self, node, connect_id, name):
        client = self._get_server(node)
        return client.clear_connect_event(connect_id, name)
