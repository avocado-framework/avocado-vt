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
# Copyright: Red Hat Inc. 2022
# Authors: Yongxue Hong <yhong@redhat.com>

import logging
import pickle
import select
import socketserver
import struct
import threading

from . import ClusterError, cluster

_logger = logging.getLogger("")


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
        super(_LoggerStreamHandler, self).__init__(request, client_address, server)
        self.server = server

    def handle(self):
        """
        Handle multiple requests - each expected to be a 4-byte length,
        followed by the LogRecord in pickle format. Logs the record
        according to whatever policy is configured locally.
        """
        while True:
            chunk = self.connection.recv(4)
            if len(chunk) < 4:
                break
            slen = struct.unpack(">L", chunk)[0]
            chunk = self.connection.recv(slen)
            while len(chunk) < slen:
                chunk = chunk + self.connection.recv(slen - len(chunk))
            obj = self.unpickle(chunk)
            record = logging.makeLogRecord(obj)
            self.handle_logger(record)

    def unpickle(self, data):
        _data = pickle.loads(data)
        self.server.last_output_lines = _data.get("msg")
        return _data

    def handle_logger(self, record):
        client = "Unknown"
        for node in cluster.get_all_nodes():
            if self.client_address[0] == node.address:
                client = node.tag
                break
        format_str = "{client}({address}) {asctime} {module} {levelname} | {msg}"
        _logger.info(
            format_str.format(
                asctime=record.asctime,
                module=record.name,
                levelname=record.levelname,
                msg=record.msg,
                client=client,
                address=self.client_address[0],
            )
        )


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, host, port, handler=_LoggerStreamHandler):
        socketserver.ThreadingTCPServer.__init__(self, (host, port), handler)
        self.abort = False
        self.timeout = 1
        self.last_output_lines = ""

    def run_server_forever(self):
        abort = False
        while not abort:
            rd, wr, ex = select.select([self.socket.fileno()], [], [], self.timeout)
            if rd:
                self.handle_request()
            abort = self.abort


class LoggerServer(object):
    """
    Handler for receiving the log content from the agent node.

    """

    def __init__(self, host, port, logger=None):
        self._host = host
        self._port = port
        self._server = _Server(host, port)
        self._thread = None
        global _logger
        _logger = logger
        _logger.setLevel(logging.DEBUG)

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
