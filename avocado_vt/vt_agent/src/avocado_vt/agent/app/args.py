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

import argparse
import ipaddress
import os
import re
import sys


def validate_host(host):
    """
    Validate the host argument.

    :param host: The host address to validate
    :type host: str
    :return: The validated host address
    :rtype: str
    :raises argparse.ArgumentTypeError: If host is invalid
    """
    if not host:
        raise argparse.ArgumentTypeError("Host cannot be empty")

    try:
        ipaddress.ip_address(host)
        return host
    except ValueError:
        hostname_pattern = (
            r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])"
            r"?(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
        )
        if re.match(hostname_pattern, host) and len(host) <= 253:
            return host
        else:
            raise argparse.ArgumentTypeError(f"Invalid host address: {host}") from None


def validate_port(port):
    """
    Validate the port argument.

    :param port: The port number to validate
    :type port: str
    :return: The validated port number
    :rtype: int
    :raises argparse.ArgumentTypeError: If port is invalid
    """
    try:
        port_int = int(port)
        if port_int < 1 or port_int > 65535:
            raise argparse.ArgumentTypeError(
                f"Port must be between 1 and 65535, got: {port_int}"
            )
        if port_int < 1024:
            print(
                f"Warning: Using privileged port {port_int} may require root privileges",
                file=sys.stderr,
            )
        return port_int
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"Port must be a number, got: {port}"
        ) from None


def validate_pid_file(pid_file):
    """
    Validate the PID file argument.

    :param pid_file: The PID file path to validate
    :type pid_file: str
    :return: The validated PID file path
    :rtype: str
    :raises argparse.ArgumentTypeError: If PID file path is invalid
    """
    if not pid_file:
        raise argparse.ArgumentTypeError("PID file path cannot be empty")

    abs_path = os.path.abspath(pid_file)
    pid_dir = os.path.dirname(abs_path)
    if not os.path.exists(pid_dir):
        raise argparse.ArgumentTypeError(
            f"PID file directory does not exist: {pid_dir}"
        )

    if not os.access(pid_dir, os.W_OK):
        raise argparse.ArgumentTypeError(
            f"PID file directory is not writable: {pid_dir}"
        )

    if os.path.exists(abs_path):
        print(
            f"Warning: PID file already exists and will be overwritten: {abs_path}",
            file=sys.stderr,
        )

    return abs_path


def init_arguments():
    """
    Initialize and validate arguments from the command line.

    :return: The populated and validated namespace of arguments.
    :rtype: argparse.Namespace
    :raises SystemExit: If argument validation fails
    """
    parser = argparse.ArgumentParser(
        prog="avocado_vt.agent",
        description="Avocado VT Agent - XML-RPC server for remote test execution",
        epilog="For security, the agent defaults to localhost binding. "
        "Use --host 0.0.0.0 to allow external connections.",
    )

    parser.add_argument(
        "--host",
        type=validate_host,
        default="127.0.0.1",
        metavar="ADDRESS",
        help="Host address to bind to [default: 127.0.0.1 (localhost only)]",
    )

    parser.add_argument(
        "--port",
        type=validate_port,
        default=9999,
        metavar="PORT",
        help="Port number to listen on [default: 9999]",
    )

    parser.add_argument(
        "--pid-file",
        type=validate_pid_file,
        required=True,
        metavar="PATH",
        help="Path to write the process ID file (required)",
    )

    parser.add_argument(
        "--version", action="version", version="Avocado VT Agent v0.1.0"
    )

    try:
        args = parser.parse_args()

        if args.host == "0.0.0.0":
            print(
                "Warning: Binding to 0.0.0.0 exposes the agent to external networks. "
                "Ensure proper firewall protection.",
                file=sys.stderr,
            )

        return args

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
