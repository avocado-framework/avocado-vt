# This module provides VT Node interfaces
import socket


from virttest import vt_proxy


class NodeError(Exception):
    pass


class Node(object):
    def __init__(self, params, name):
        self.params = params
        self._name = name
        _address = self.hostname if self.hostname else self.address
        _uri = "http://%s:%s/" % (_address, self.proxy_port)
        _hostname = socket.gethostname()
        self._uri = None if self.hostname == _hostname else _uri

    @property
    def name(self):
        return self._name

    @property
    def proxy(self):
        return vt_proxy.get_server_proxy(self._uri)

    @property
    def hostname(self):
        node_hostname = self.params.get("node_hostname")
        if node_hostname:
            return node_hostname
        return self.address

    @property
    def address(self):
        node_address = self.params.get("node_address")
        if node_address:
            return node_address
        return self.hostname

    @property
    def proxy_port(self):
        return self.params.get("node_proxy_port", "8000")

    @property
    def username(self):
        return self.params.get("node_username", "root")

    @property
    def password(self):
        return self.params.get("node_password")

    @property
    def shell_port(self):
        return self.params.get("node_shell_port", "22")

    @property
    def shell_prompt(self):
        return self.params.get("node_shell_prompt", "#")
