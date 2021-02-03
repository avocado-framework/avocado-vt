#!/usr/bin/python

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
# This code was imported from the avocado-vt project,
#
# virttest/rss_client.py
# Original author: Michael Goldish <mgoldish@redhat.com>
#
# Copyright: 2008-2010 Red Hat Inc.
# Authors : Michael Goldish <mgoldish@redhat.com>

"""
Client for file transfer services offered by RSS (Remote Shell Server).
"""

# disable too-many-* as we need them pylint: disable=R0912,R0913,R0914,R0915,C0302
# ..todo:: we could reduce the disabled issues after more significant refactoring

from __future__ import division, print_function
import socket
import struct
import time
import sys
import os
import glob
import argparse

import six


# Globals
CHUNKSIZE = 65536

# Protocol message constants
RSS_MAGIC = 0x525353
RSS_OK = 1
RSS_ERROR = 2
RSS_UPLOAD = 3
RSS_DOWNLOAD = 4
RSS_SET_PATH = 5
RSS_CREATE_FILE = 6
RSS_CREATE_DIR = 7
RSS_LEAVE_DIR = 8
RSS_DONE = 9

# See rss.cpp for protocol details.


class FileTransferError(Exception):
    """Base class for any error related to file transfer."""

    def __init__(self, msg, e=None, filename=None):
        super().__init__(msg, e, filename)
        self.msg = msg
        self.error = e
        self.filename = filename

    def __str__(self):
        errmsg = self.msg
        if self.error and self.filename:
            errmsg += "    (error: %s,    filename: %s)" % (self.error, self.filename)
        elif self.error:
            errmsg += "    (%s)" % self.error
        elif self.filename:
            errmsg += "    (filename: %s)" % self.filename
        return errmsg


class FileTransferConnectError(FileTransferError):
    """Error related to file transfer connection."""


class FileTransferTimeoutError(FileTransferError):
    """Error related to file transfer timeout."""


class FileTransferProtocolError(FileTransferError):
    """Error related to file transfer protocol."""


class FileTransferSocketError(FileTransferError):
    """Error related to file transfer socket."""


class FileTransferServerError(FileTransferError):
    """Error related to file transfer server."""

    def __init__(self, errmsg):
        super().__init__(None, errmsg)

    def __str__(self):
        errmsg = "Server said: %r" % self.error
        if self.filename:
            errmsg += "    (filename: %s)" % self.filename
        return errmsg


class FileTransferNotFoundError(FileTransferError):
    """Error related to file transfer missing files."""


class FileTransferClient(object):

    """
    Connect to a RSS (remote shell server) and transfer files.
    """

    def __init__(self, address, port, log_func=None, timeout=20):
        """
        Connect to a server.

        :param address: The server's address
        :param port: The server's port
        :param log_func: If provided, transfer stats will be passed to this
                function during the transfer
        :param timeout: Time duration to wait for connection to succeed
        :raise FileTransferConnectError: Raised if the connection fails
        """
        family = socket.AF_INET6 if ':' in address else socket.AF_INET
        self._socket = socket.socket(family, socket.SOCK_STREAM)
        self._socket.settimeout(timeout)
        try:
            addrinfo = socket.getaddrinfo(address, port, family,
                                          socket.SOCK_STREAM,
                                          socket.IPPROTO_TCP)
            self._socket.connect(addrinfo[0][4])
        except socket.error as error:
            raise FileTransferConnectError("Cannot connect to server at "
                                           "%s:%s" % (address, port), error) from error
        try:
            if self._receive_msg(timeout) != RSS_MAGIC:
                raise FileTransferConnectError("Received wrong magic number")
        except FileTransferTimeoutError:
            raise FileTransferConnectError("Timeout expired while waiting to "
                                           "receive magic number") from error
        self._send(struct.pack("=i", CHUNKSIZE))
        self._log_func = log_func
        self._last_time = time.time()
        self._last_transferred = 0
        self.transferred = 0

    def __del__(self):
        self.close()

    def close(self):
        """
        Close the connection.
        """
        self._socket.close()

    def _send(self, data, timeout=60):
        try:
            if timeout <= 0:
                raise socket.timeout
            self._socket.settimeout(timeout)
            self._socket.sendall(data)
        except socket.timeout as error:
            raise FileTransferTimeoutError("Timeout expired while sending "
                                           "data to server") from error
        except socket.error as error:
            raise FileTransferSocketError("Could not send data to server", error) from error

    def _receive(self, size, timeout=60):
        strs = []
        end_time = time.time() + timeout
        try:
            while size > 0:
                timeout = end_time - time.time()
                if timeout <= 0:
                    raise socket.timeout
                self._socket.settimeout(timeout)
                data = self._socket.recv(size)
                if not data:
                    raise FileTransferProtocolError("Connection closed "
                                                    "unexpectedly while "
                                                    "receiving data from "
                                                    "server")
                strs.append(data)
                size -= len(data)
        except socket.timeout as error:
            raise FileTransferTimeoutError("Timeout expired while receiving "
                                           "data from server") from error
        except socket.error as error:
            raise FileTransferSocketError("Error receiving data from server",
                                          error) from error
        return b"".join(strs)

    def _report_stats(self, data):
        if self._log_func:
            delta = time.time() - self._last_time
            if delta >= 1:
                transferred = self.transferred / 1048576.
                speed = (self.transferred - self._last_transferred) / delta
                speed /= 1048576.
                self._log_func("%s %.3f MB (%.3f MB/sec)" %
                               (data, transferred, speed))
                self._last_time = time.time()
                self._last_transferred = self.transferred

    def _send_packet(self, data, timeout=60):
        self._send(struct.pack("=I", len(data)))
        self._send(data, timeout)
        self.transferred += len(data) + 4
        self._report_stats("Sent")

    def _receive_packet(self, timeout=60):
        """return bytes"""
        size = struct.unpack("=I", self._receive(4))[0]
        data = self._receive(size, timeout)
        self.transferred += len(data) + 4
        self._report_stats("Received")
        return data

    def _send_file_chunks(self, filename, timeout=60):
        if self._log_func:
            self._log_func("Sending file %s" % filename)
        with open(filename, "rb") as file_handle:
            try:
                end_time = time.time() + timeout
                while True:
                    data = file_handle.read(CHUNKSIZE)
                    self._send_packet(data, end_time - time.time())
                    if len(data) < CHUNKSIZE:
                        break
            except FileTransferError as error:
                error.filename = filename
                raise

    def _receive_file_chunks(self, filename, timeout=60):
        if self._log_func:
            self._log_func("Receiving file %s" % filename)
        with open(filename, "wb") as file_handle:
            try:
                end_time = time.time() + timeout
                while True:
                    data = self._receive_packet(end_time - time.time())
                    file_handle.write(data)
                    if len(data) < CHUNKSIZE:
                        break
            except FileTransferError as error:
                error.filename = filename
                raise

    def _send_msg(self, msg, timeout=60):
        self._send(struct.pack("=I", msg), timeout)

    def _receive_msg(self, timeout=60):
        data = self._receive(4, timeout)
        return struct.unpack("=I", data)[0]

    def _handle_transfer_error(self):
        # Save original exception
        error = sys.exc_info()
        try:
            # See if we can get an error message
            msg = self._receive_msg()
        except FileTransferError:
            # No error message -- re-raise original exception
            six.reraise(*error)
        if msg == RSS_ERROR:
            errmsg = self._receive_packet().decode()
            raise FileTransferServerError(errmsg)
        six.reraise(*error)


class FileUploadClient(FileTransferClient):

    """
    Connect to a RSS (remote shell server) and upload files or directory trees.
    """

    def __init__(self, address, port, log_func=None, timeout=20):
        """
        Connect to a server.

        :param address: The server's address
        :param port: The server's port
        :param log_func: If provided, transfer stats will be passed to this
                function during the transfer
        :param timeout: Time duration to wait for connection to succeed
        :raise FileTransferConnectError: Raised if the connection fails
        :raise FileTransferProtocolError: Raised if an incorrect magic number
                is received
        :raise FileTransferSocketError: Raised if the RSS_UPLOAD message cannot
                be sent to the server
        """
        super().__init__(address, port, log_func, timeout)
        self._send_msg(RSS_UPLOAD)

    def _upload_file(self, path, end_time):
        if os.path.isfile(path):
            self._send_msg(RSS_CREATE_FILE)
            self._send_packet(os.path.basename(path).encode())
            self._send_file_chunks(path, end_time - time.time())
        elif os.path.isdir(path):
            self._send_msg(RSS_CREATE_DIR)
            self._send_packet(os.path.basename(path).encode())
            for filename in os.listdir(path):
                self._upload_file(os.path.join(path, filename), end_time)
            self._send_msg(RSS_LEAVE_DIR)

    def upload(self, src_pattern, dst_path, timeout=600):
        """
        Send files or directory trees to the server.

        The semantics of src_pattern and dst_path are similar to those of scp.
        For example, the following are OK:

        ::

            src_pattern='/tmp/foo.txt', dst_path='C:\\'
                (uploads a single file)
            src_pattern='/usr/', dst_path='C:\\Windows\\'
                (uploads a directory tree recursively)
            src_pattern='/usr/*', dst_path='C:\\Windows\\'
                (uploads all files and directory trees under /usr/)

        The following is not OK:

        ::

            src_pattern='/tmp/foo.txt', dst_path='C:\\Windows\\*'
                (wildcards are only allowed in src_pattern)

        :param src_pattern: A path or wildcard pattern specifying the files or
                            directories to send to the server
        :param dst_path: A path in the server's filesystem where the files will
                         be saved
        :param timeout: Time duration in seconds to wait for the transfer to
                        complete
        :raise FileTransferTimeoutError: Raised if timeout expires
        :raise FileTransferServerError: Raised if something goes wrong and the
                                        server sends an informative error
                                        message to the client
        :note: Other exceptions can be raised.
        """
        end_time = time.time() + timeout
        try:
            try:
                self._send_msg(RSS_SET_PATH)
                self._send_packet(dst_path.encode())
                matches = glob.glob(src_pattern)
                for filename in matches:
                    self._upload_file(os.path.abspath(filename), end_time)
                self._send_msg(RSS_DONE)
            except FileTransferTimeoutError:
                raise
            except FileTransferError:
                self._handle_transfer_error()
            else:
                # If nothing was transferred, raise an exception
                if not matches:
                    raise FileTransferNotFoundError("Pattern %s does not "
                                                    "match any files or "
                                                    "directories" %
                                                    src_pattern)
                # Look for RSS_OK or RSS_ERROR
                msg = self._receive_msg(end_time - time.time())
                if msg == RSS_OK:
                    return
                if msg == RSS_ERROR:
                    errmsg = self._receive_packet().decode()
                    raise FileTransferServerError(errmsg)
                # Neither RSS_OK nor RSS_ERROR found
                raise FileTransferProtocolError("Received unexpected msg")
        except Exception:
            # In any case, if the transfer failed, close the connection
            self.close()
            raise


class FileDownloadClient(FileTransferClient):

    """
    Connect to a RSS (remote shell server) and download files or directory trees.
    """

    def __init__(self, address, port, log_func=None, timeout=20):
        """
        Connect to a server.

        :param address: The server's address
        :param port: The server's port
        :param log_func: If provided, transfer stats will be passed to this
                function during the transfer
        :param timeout: Time duration to wait for connection to succeed
        :raise FileTransferConnectError: Raised if the connection fails
        :raise FileTransferProtocolError: Raised if an incorrect magic number
                is received
        :raise FileTransferSendError: Raised if the RSS_UPLOAD message cannot
                be sent to the server
        """
        super().__init__(address, port, log_func, timeout)
        self._send_msg(RSS_DOWNLOAD)

    def download(self, src_pattern, dst_path, timeout=600):
        """
        Receive files or directory trees from the server.
        The semantics of src_pattern and dst_path are similar to those of scp.

        For example, the following are OK:

        ::

            src_pattern='C:\\foo.txt', dst_path='/tmp'
                (downloads a single file)
            src_pattern='C:\\Windows', dst_path='/tmp'
                (downloads a directory tree recursively)
            src_pattern='C:\\Windows\\*', dst_path='/tmp'
                (downloads all files and directory trees under C:\\Windows)

        The following is not OK:

        ::

            src_pattern='C:\\Windows', dst_path='/tmp/*'
                (wildcards are only allowed in src_pattern)

        :param src_pattern: A path or wildcard pattern specifying the files or
                            directories, in the server's filesystem, that will
                            be sent to the client
        :param dst_path: A path in the local filesystem where the files will
                         be saved
        :param timeout: Time duration in seconds to wait for the transfer to
                        complete
        :raise FileTransferTimeoutError: Raised if timeout expires
        :raise FileTransferServerError: Raised if something goes wrong and the
                                        server sends an informative error
                                        message to the client
        :note: Other exceptions can be raised.
        """
        dst_path = os.path.abspath(dst_path)
        end_time = time.time() + timeout
        file_count = 0
        dir_count = 0
        try:
            try:
                self._send_msg(RSS_SET_PATH)
                self._send_packet(src_pattern.encode())
            except FileTransferError:
                self._handle_transfer_error()
            while True:
                msg = self._receive_msg()
                if msg == RSS_CREATE_FILE:
                    # Receive filename and file contents
                    filename = self._receive_packet().decode()
                    if os.path.isdir(dst_path):
                        dst_path = os.path.join(dst_path, filename)
                    self._receive_file_chunks(dst_path, end_time - time.time())
                    dst_path = os.path.dirname(dst_path)
                    file_count += 1
                elif msg == RSS_CREATE_DIR:
                    # Receive dirname and create the directory
                    dirname = self._receive_packet().decode()
                    if os.path.isdir(dst_path):
                        dst_path = os.path.join(dst_path, dirname)
                    if not os.path.isdir(dst_path):
                        os.mkdir(dst_path)
                    dir_count += 1
                elif msg == RSS_LEAVE_DIR:
                    # Return to parent dir
                    dst_path = os.path.dirname(dst_path)
                elif msg == RSS_DONE:
                    # Transfer complete
                    if not file_count and not dir_count:
                        raise FileTransferNotFoundError("Pattern %s does not "
                                                        "match any files or "
                                                        "directories that "
                                                        "could be downloaded" %
                                                        src_pattern)
                    break
                elif msg == RSS_ERROR:
                    # Receive error message and abort
                    errmsg = self._receive_packet().decode()
                    raise FileTransferServerError(errmsg)
                else:
                    # Unexpected msg
                    raise FileTransferProtocolError("Received unexpected msg")
        except Exception:
            # In any case, if the transfer failed, close the connection
            self.close()
            raise


def upload(address, port, src_pattern, dst_path, log_func=None, timeout=60,
           connect_timeout=20):
    """
    Connect to server and upload files.

    :see:: FileUploadClient
    """
    client = FileUploadClient(address, port, log_func, connect_timeout)
    client.upload(src_pattern, dst_path, timeout)
    client.close()


def download(address, port, src_pattern, dst_path, log_func=None, timeout=60,
             connect_timeout=20):
    """
    Connect to server and upload files.

    :see:: FileDownloadClient
    """
    client = FileDownloadClient(address, port, log_func, connect_timeout)
    client.download(src_pattern, dst_path, timeout)
    client.close()


def main():
    """Main entry if this code is ran as a script."""
    usage = "usage: %prog [args] address port src_pattern dst_path"
    parser = argparse.ArgumentParser(description=usage)
    parser.add_argument("address")
    parser.add_argument("port")
    parser.add_argument("src_pattern")
    parser.add_argument("dst_path")
    parser.add_argument("-d", "--download",
                        action="store_true", dest="download",
                        help="download files from server")
    parser.add_argument("-u", "--upload",
                        action="store_true", dest="upload",
                        help="upload files to server")
    parser.add_argument("-v", "--verbose",
                        action="store_true", dest="verbose",
                        help="be verbose")
    parser.add_argument("-t", "--timeout",
                        type=int, dest="timeout", default=3600,
                        help="transfer timeout")
    args = parser.parse_args()
    if args.download == args.upload:
        parser.error("you must specify either -d or -u")
    address, port = args.address, args.port
    src_pattern, dst_path = args.src_pattern, args.dst_path
    port = int(port)

    logger = None
    if args.verbose:
        def log_print(message):
            """Print logger."""
            print(message)
        logger = log_print

    if args.download:
        download(address, port, src_pattern, dst_path, logger, args.timeout)
    elif args.upload:
        upload(address, port, src_pattern, dst_path, logger, args.timeout)


if __name__ == "__main__":
    main()
