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
import json
import logging
import socket
import sys
import traceback
from socketserver import ThreadingMixIn
from xmlrpc.client import Fault, dumps, loads
from xmlrpc.server import SimpleXMLRPCServer

# pylint: disable=E0611
from avocado_vt.agent.core.logger import DEFAULT_LOG_NAME
from avocado_vt.agent.services import core

LOG = logging.getLogger(f"{DEFAULT_LOG_NAME}." + __name__)


class _CustomSimpleXMLRPCServer(ThreadingMixIn, SimpleXMLRPCServer):
    """
    Custom XML-RPC server that extends SimpleXMLRPCServer with ThreadingMixIn
    for concurrent request handling and overrides _marshaled_dispatch for
    custom error reporting.
    """

    daemon_threads = True

    def __init__(self, addr, **kwargs):
        """Initialize the custom XML-RPC server with enhanced error handling."""
        try:
            super().__init__(addr, **kwargs)
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        except OSError as e:
            if "Address already in use" in str(e):
                raise OSError(
                    f"Cannot bind to {addr[0]}:{addr[1]} - address already in use. "
                    "Another agent instance may be running."
                ) from e
            raise

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
                error_string = (
                    f"Server Error: {exc_type_str}: {exc_value_str}\n"
                    f"\nTraceback:\n{tb_info_str}"
                )
                exe_info = {
                    "exc_type": exc_type_str,
                    "exc_value": exc_value_str,
                    "tb_info": tb_info_str,
                }
                fault_string = json.dumps(exe_info)
                response_xml = dumps(
                    Fault(1, fault_string),
                    encoding=self.encoding,
                    allow_none=self.allow_none,
                )
                LOG.error(error_string)
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
        try:
            host, port = addr if addr and len(addr) == 2 else ("localhost", 0)
        except (TypeError, ValueError) as e:
            LOG.warning(
                "Invalid addr parameter '%s': %s. Using default (localhost, 0)", addr, e
            )
            host, port = "localhost", 0

        self._server = _CustomSimpleXMLRPCServer(
            (host, port), allow_none=True, use_builtin_types=False
        )
        self._register_core_server()

    def _register_core_server(self):
        """
        Registers the agent's core API functions with the XML-RPC server.
        Functions are sourced from the `avocado_vt.agent.services.core` module.
        """
        for member_name, member_obj in inspect.getmembers(core):
            if inspect.isfunction(member_obj) and not member_name.startswith("_"):
                if not callable(member_obj):
                    LOG.warning("Skipping non-callable API member: %s", member_name)
                    continue

                base_module_name = (
                    core.__name__.split(".", 1)[-1]
                    if "." in core.__name__
                    else core.__name__
                )
                rpc_name = f"{base_module_name}.{member_name}"

                try:
                    self._server.register_function(member_obj, rpc_name)
                except Exception as e:
                    LOG.error("Failed to register API function %s: %s", rpc_name, e)

    def register_services(self, services):
        """
        Registers functions from non-core service modules with the XML-RPC server.

        :param services: An iterable of (name, service_module) tuples.
                         'name' is the prefix for the RPC methods from this service.
                         'service_module' is the imported module object.
        :type services: iterable
        """
        if not services:
            return

        for service_name, service_module in services:
            if not service_name or not service_module:
                LOG.warning(
                    "Skipping invalid service registration: name=%s, module=%s",
                    service_name,
                    service_module,
                )
                continue

            members = inspect.getmembers(service_module)

            for member_name, member_obj in members:
                # TODO: Add an allowlist(whitelist) of permitted service functions
                #  to enhance security. This would prevent registration of potentially
                #  dangerous functions by explicitly defining which functions are
                #  safe to expose via RPC.
                if inspect.isfunction(member_obj) and not member_name.startswith("_"):
                    if not callable(member_obj):
                        LOG.warning(
                            "Skipping non-callable service member: %s.%s",
                            service_name,
                            member_name,
                        )
                        continue

                    rpc_name = f"{service_name}.{member_name}"

                    try:
                        self._server.register_function(member_obj, rpc_name)
                    except Exception as e:
                        LOG.error(
                            "Failed to register service function %s: %s", rpc_name, e
                        )

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
                "RPCServer interrupted by KeyboardInterrupt. Shutting down gracefully."
            )
        except Exception as e:
            LOG.error("Unexpected error in server main loop: %s", e, exc_info=True)
            raise
        finally:
            try:
                self._server.shutdown()
                self._server.server_close()
            except Exception as e:
                LOG.warning("Error during server cleanup: %s", e)
