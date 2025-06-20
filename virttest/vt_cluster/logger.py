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

"""Cluster logging server for distributed virtualization testing.

This module provides a centralized logging server that collects and processes
log messages from remote nodes in a cluster environment. It implements a
socketserver-based architecture for handling multiple concurrent logging
connections from distributed test nodes.

The module consists of:
- LoggerServer: Main server class for managing the logging infrastructure
- _LoggerStreamHandler: Handler for processing incoming log streams
- _Server: Custom TCP server with timeout and abort capabilities
- LoggerServerError: Exception class for logger-specific errors
"""

import json
import logging
import select
import socketserver
import struct
import threading

from . import ClusterError, cluster


class LoggerServerError(ClusterError):
    """Generic LoggerServerError."""

    pass


class _LoggerStreamHandler(socketserver.StreamRequestHandler):
    """
    Handler for a streaming logging request.

    This basically logs the record using whatever logging policy is
    configured locally.
    """

    def __init__(self, request, client_address, server):
        """
        Initialize the stream handler for a logging connection.

        :param request: The socket request object.
        :type request: socket.socket
        :param client_address: The client's network address (host, port).
        :type client_address: tuple[str, int]
        :param server: The server instance handling this request.
        :type server: _Server
        """
        self._node_cache = {}
        super().__init__(request, client_address, server)

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """
        # self.connection.settimeout(60)
        while True:
            try:
                chunk = self.connection.recv(4)
                if len(chunk) < 4:
                    break
            # except socket.timeout:
            #     self.server.logger.warning("Logger server connection timeout")
            #     break
            except (ConnectionResetError, BrokenPipeError) as e:
                self.server.logger.warning(f"Logger server connection error: {e}")
                break
            slen = struct.unpack(">L", chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = self._unserialize(chunk)
            record = logging.makeLogRecord(obj)
            self._handle_logger(record)

    def _unserialize(self, data):
        """
        Deserialize log data from JSON format.

        :param data: The serialized log data in JSON format.
        :type data: bytes
        :return: The deserialized log record data.
        :rtype: dict
        """
        _data = json.loads(data)
        # self.server.last_output_lines = _data.get("msg")
        return _data

    def _get_client_tag(self, address):
        """
        Get the client tag (node identifier) by address, with caching.

        This method looks up the node tag associated with a given address
        by searching through all registered cluster nodes. Results are cached
        to improve performance for subsequent lookups.

        :param address: The address of the client node.
        :type address: str
        :return: The node tag if found, otherwise "Unknown".
        :rtype: str
        """
        if address in self._node_cache:
            return self._node_cache[address]
        for node in cluster.get_all_nodes():
            if address == node.host:
                self._node_cache[address] = node.tag
                return node.tag
        return "Unknown"

    def _handle_logger(self, record):
        """
        Process and log a received log record.

        Formats the log record with client identification information and
        forwards it to the server's logger.

        :param record: The log record to process.
        :type record: logging.LogRecord
        """
        client = self._get_client_tag(self.client_address[0])
        self.server.logger.info(
            f"{client}({self.client_address[0]}) {record.asctime} "
            f"{record.name} {record.levelname} | {record.msg}"
        )


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, address, handler, logger):
        """
        Initialize the custom TCP server.

        :param address: The server address (host, port) to bind to.
        :type address: tuple[str, int]
        :param handler: The request handler class.
        :type handler: type[socketserver.BaseRequestHandler]
        :param logger: The logger instance for server messages.
        :type logger: logging.Logger
        """
        super().__init__(address, handler)
        self.abort = False
        self.timeout = 1
        # self.last_output_lines = ""
        self.logger = logger

    def run_server_forever(self):
        """
        Run the server in a loop until abort is requested.

        This method uses select() to handle incoming requests with a timeout,
        allowing for graceful shutdown when the abort flag is set.
        """
        abort = False
        while not abort:
            rd, wr, ex = select.select([self.socket.fileno()], [], [], self.timeout)
            if rd:
                self.handle_request()
            abort = self.abort


class LoggerServer(object):
    """
    The logger server that logs messages from the client side.
    """

    def __init__(self, address, logger=None):
        """
        Initialize the logger server.

        :param address: The server address (host, port) to bind to.
        :type address: tuple[str, int]
        :param logger: Optional logger instance. If None, a default logger
                      will be created using the class name.
        :type logger: logging.Logger | None
        """
        self._address = address
        if logger is None:
            logger = logging.getLogger(self.__class__.__name__)
        self._server = _Server(address, _LoggerStreamHandler, logger)
        self._thread = None
        self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    @property
    def address(self):
        """
        Get the server address.

        :return: The server address as (host, port).
        :rtype: tuple[str, int]
        """
        return self._address

    def start(self):
        """
        Start the logger server in a separate daemon thread.

        The server will begin accepting connections from remote nodes
        and processing their log messages.
        """
        self._thread = threading.Thread(
            target=self._server.run_server_forever, name="logger_server", args=()
        )
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """
        Stop the logger server gracefully.

        Sets the abort flag to signal the server thread to stop accepting
        new connections and exit its main loop.
        """
        self._server.abort = True
