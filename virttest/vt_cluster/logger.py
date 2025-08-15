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

import json
import logging
import select
import socket
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
        # Initialize attributes before the superclass __init__ is called,
        # as it will trigger self.handle() which uses these attributes.
        self._node_cache = {}
        # The `self.server` attribute is set by the superclass constructor.
        super().__init__(request, client_address, server)

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """
        self.connection.settimeout(60)
        while True:
            try:
                chunk = self.connection.recv(4)
                if len(chunk) < 4:
                    break
            except socket.timeout:
                self.server.logger.warning("Logger server connection timeout")
                break
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
        _data = json.loads(data)
        self.server.last_output_lines = _data.get("msg")
        return _data

    def _get_client_tag(self, address):
        """
        Get client tag by address, with cache.
        """
        if address in self._node_cache:
            return self._node_cache[address]
        for node in cluster.get_all_nodes():
            if address == node.address:
                self._node_cache[address] = node.tag
                return node.tag
        return "Unknown"

    def _handle_logger(self, record):
        client = self._get_client_tag(self.client_address[0])
        self.server.logger.info(
            f"{client}({self.client_address[0]}) {record.asctime} "
            f"{record.name} {record.levelname} | {record.msg}"
        )


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, host, port, handler, logger):
        super().__init__((host, port), handler)
        self.abort = False
        self.timeout = 1
        self.last_output_lines = ""
        self.logger = logger

    def run_server_forever(self):
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

    def __init__(self, host, port, logger=None):
        self._host = host
        self._port = port
        if logger is None:
            logger = logging.getLogger(self.__class__.__name__)
        self._server = _Server(host, port, _LoggerStreamHandler, logger)
        self._thread = None
        self.logger = logger
        self.logger.setLevel(logging.DEBUG)

    @property
    def host(self):
        return self._host

    @property
    def port(self):
        return self._port

    def start(self):
        """Start the logger server"""
        self._thread = threading.Thread(
            target=self._server.run_server_forever, name="logger_server", args=()
        )
        self._thread.daemon = True
        self._thread.start()

    def stop(self):
        """Stop the logger server"""
        self._server.abort = True

    @property
    def last_output_lines(self):
        return self._server.last_output_lines
