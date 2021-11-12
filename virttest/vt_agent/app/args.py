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

import argparse


def init_arguments():
    """
    Initialize the arguments from the command line.

    :return: The populated namespace of arguments.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--host",
        action="store",
        default="0.0.0.0",
        nargs="?",
        help='Specify alternate host [default: "0.0.0.0"]',
    )
    parser.add_argument(
        "--port",
        action="store",
        default=8000,
        type=int,
        nargs="?",
        help="Specify alternate port [default: 8000]",
    )
    parser.add_argument("--pid-file", required=True, help="Specify the file of pid.")
    return parser.parse_args()
