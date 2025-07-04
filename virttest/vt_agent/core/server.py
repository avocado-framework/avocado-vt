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
Core XML-RPC server implementation for the vt_agent.

This module provides the RPCServer class that sets up and manages an
XML-RPC server, including custom error handling and dynamic registration
of API functions and external services.
"""

import inspect
import logging
import sys
import traceback
from socketserver import ThreadingMixIn
from xmlrpc.client import Fault, dumps, loads
from xmlrpc.server import SimpleXMLRPCServer

from .. import api

LOG = logging.getLogger("avocado.agent." + __name__)


class _CustomSimpleXMLRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    """
    Custom XML-RPC server that extends SimpleXMLRPCServer with ThreadingMixIn
    for concurrent request handling and overrides _marshaled_dispatch for
    custom error reporting.
    """

    def _marshaled_dispatch(self, data, dispatch_method=None, path=None):
        try:
            params, method = loads(data, use_builtin_types=self.use_builtin_types)

            if dispatch_method is not None:
                response = dispatch_method(method, params)
            else:
                response = self._dispatch(method, params)

            response = (response,)
            response_xml = dumps(
                response,
                methodresponse=True,
                allow_none=self.allow_none,
                encoding=self.encoding,
            )
        except Fault as fault:
            response_xml = dumps(
                fault, allow_none=self.allow_none, encoding=self.encoding
            )
        except Exception:
            exc_type, exc_value, exc_tb = sys.exc_info()
            tb_list = traceback.format_exception(exc_type, exc_value, exc_tb)
            tb_info_str = "".join(tb_list)

            try:
                mod = getattr(exc_type, "__module__", "")
                if mod and mod not in ("__main__", "builtins"):
                    exc_type_str = f"{mod}.{exc_type.__name__}"
                else:
                    exc_type_str = exc_type.__name__

                exc_value_str = str(exc_value)

                fault_string = (
                    f"Server Error: {exc_type_str}: {exc_value_str}\n"
                    f"\nTraceback:\n{tb_info_str}"
                )
                response_xml = dumps(
                    Fault(1, fault_string),
                    encoding=self.encoding,
                    allow_none=self.allow_none,
                )
            except Exception as e_dumps:
                LOG.error(
                    "Error while formatting an exception for RPC response: %s",
                    e_dumps,
                    exc_info=True,
                )
                response_xml = dumps(
                    Fault(
                        1,
                        "Server error: An internal error occurred while processing "
                        "the request and formatting the error response.",
                    ),
                    encoding=self.encoding,
                    allow_none=self.allow_none,
                )

        return response_xml.encode(self.encoding, "xmlcharrefreplace")


class RPCServer(object):
    """
    Manages the vt_agent's XML-RPC server lifecycle.

    This class initializes the XML-RPC server, registers the agent's core API
    functions, provides a mechanism to register external services, and starts
    the server to handle incoming requests.
    """

    def __init__(self, addr=()):
        """
        Initializes the RPCServer.

        :param addr: A tuple (host, port) for the server to bind to.
                     If empty, defaults will be used by SimpleXMLRPCServer.
        :type addr: tuple
        """
        host, port = addr if addr and len(addr) == 2 else ("unknown_host", 0)
        self._server = _CustomSimpleXMLRPCServer(
            addr, allow_none=True, use_builtin_types=False
        )
        self._load_server_api()
        LOG.info("RPCServer initialized on %s:%s.", host, port)

    def _load_server_api(self):
        """
        Registers the agent's internal API functions with the XML-RPC server.
        Functions are sourced from the `virttest.vt_agent.api` module.
        """
        for member_name, member_obj in inspect.getmembers(api):
            if inspect.isfunction(member_obj):
                base_module_name = (
                    api.__name__.split(".", 1)[-1]
                    if "." in api.__name__
                    else api.__name__
                )
                rpc_name = f"{base_module_name}.{member_name}"
                self._server.register_function(member_obj, rpc_name)

    def register_services(self, services):
        """
        Registers functions from external service modules with the XML-RPC server.

        :param services: An iterable of (name, service_module) tuples.
                         'name' is the prefix for the RPC methods from this service.
                         'service_module' is the imported module object.
        :type services: iterable
        """
        service_names_registered = []
        if services:
            for service_name, service_module in services:
                service_names_registered.append(service_name)
                members = inspect.getmembers(service_module)
                for member_name, member_obj in members:
                    if inspect.isfunction(member_obj):
                        rpc_name = f"{service_name}.{member_name}"
                        self._server.register_function(member_obj, rpc_name)

        if service_names_registered:
            LOG.info("Services registered: %s", ", ".join(service_names_registered))

    def serve_forever(self):
        """
        Starts the XML-RPC server and makes it listen for incoming requests indefinitely.
        This method blocks until the server is shut down or an interrupt occurs.
        """
        addr = self._server.server_address
        LOG.info("RPCServer starting to serve forever on %s:%s...", addr[0], addr[1])
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            LOG.info(
                "RPCServer serve_forever() interrupted by KeyboardInterrupt. Shutting down."
            )
        finally:
            LOG.info(
                "RPCServer serve_forever() has exited from %s:%s.", addr[0], addr[1]
            )
