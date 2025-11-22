# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
# Copyright: Red Hat Inc. 2025
# Authors: Yongxue Hong <yhong@redhat.com>

"""
Proxy interfaces for virtual test cluster communication.

This module provides interfaces for communicating with remote agent nodes
in a virtualization test cluster. It handles XML-RPC communication and
provides error handling for distributed test operations.

Key components:
- ServerProxyError: Exception class for proxy operation errors
- _ClientProxy: Client-side proxy for communicating with remote agents
- get_server_proxy: Factory function to create proxy instances
"""

import importlib
import importlib.util
import json
import logging
from xmlrpc import client

from . import ClusterError

LOG = logging.getLogger("avocado." + __name__)


class ServerProxyError(ClusterError):
    """
    Exception raised for errors occurring during server proxy operations.

    This typically wraps errors from XML-RPC communication or when
    re-raising exceptions from the remote agent.

    :param code: The error code, often from an XML-RPC fault.
    :param message: A descriptive message for the error.
    """

    def __init__(self, code, message):
        self.code = code
        self.message = message
        super().__init__(f"ServerProxyError (Code: {code}): {message}")

    def __str__(self):
        return f"\n{self.message}"


class _ClientMethod:
    """
    Internal helper class to represent a method callable via `_ClientProxy`.

    This allows for dynamic method calls on the XML-RPC server, like
    `proxy.service.method(*args)`. It also handles reconstruction of
    remote exceptions.
    """

    def __init__(self, send, name):
        self.__send = send
        self.__name = name

    def __getattr__(self, name):
        return _ClientMethod(self.__send, "%s.%s" % (self.__name, name))

    def __call__(self, *args):
        try:
            return self.__send(self.__name, args)
        except client.Fault as e:
            fault_code = e.faultCode
            fault_string = json.loads(e.faultString)
            LOG.error(
                "ClientProxy: Fault occurred calling method '%s': Code=%s, String=%s",
                self.__name,
                fault_code,
                fault_string,
            )
            if "." in fault_string.get("exc_type"):
                root_mod_name = ".".join(fault_string.get("exc_type").split(".")[:-1])
                exc_type_name = fault_string.get("exc_type").split(".")[-1]
            else:
                root_mod_name = None
                exc_type_name = fault_string.get("exc_type")

            kargs = fault_string.get("exc_value")

            # FIXME: For backward compatibility with the current framework interfaces,
            #        this code reconstructs the remote exception locally. A better
            #        approach would be to use a structured error code mechanism
            #        instead of dynamically importing and reconstructing exceptions.
            try:
                if root_mod_name:
                    actual_root_mod = importlib.import_module(root_mod_name)
                    specific_exception_class = getattr(actual_root_mod, exc_type_name)
                else:
                    specific_exception_class = getattr(
                        importlib.import_module("builtins"), exc_type_name, None
                    )
                    if specific_exception_class is None:
                        specific_exception_class = eval(exc_type_name)

                if isinstance(kargs, dict):
                    raise specific_exception_class(**kargs)
                elif isinstance(kargs, str):
                    raise specific_exception_class(kargs)
                else:
                    raise specific_exception_class()
            except Exception:
                raise ServerProxyError(fault_code, fault_string.get("tb_info")) from e


class _ClientProxy(client.ServerProxy):
    """
    An XML-RPC client proxy for communicating with a remote agent server.

    It extends `xmlrpc.client.ServerProxy` to use `_ClientMethod` for
    method calls, enabling more detailed logging and custom error handling,
    including attempting to reconstruct remote exceptions.

    :param uri: The URI of the remote XML-RPC server (agent server).
    :type uri: str
    """

    def __init__(self, uri):
        super(_ClientProxy, self).__init__(uri, allow_none=True, use_builtin_types=True)
        self._uri = uri

    def __getattr__(self, name):
        return _ClientMethod(self._ServerProxy__request, name)

    def __getstate__(self):
        """
        Custom pickle serialization to avoid connection attempts.

        Only serialize the URI, not the transport or other connection objects.
        """
        return {"uri": self._uri}

    def __setstate__(self, state):
        """
        Custom pickle de-serialized to reconstruct the proxy.

        Reinitialize the proxy with the stored URI.
        """
        self.__init__(state["uri"])


def get_server_proxy(uri):
    """
    Get the server proxy.

    :param uri: The URI of the server proxy. e.g: http://$host:$proxy_port/
    :type uri: str
    :return: The proxy obj.
    :rtype: _ClientProxy
    """
    return _ClientProxy(uri)
