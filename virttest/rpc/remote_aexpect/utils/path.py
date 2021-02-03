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

"""Utils simplifying dir handling"""

import os


class CmdNotFoundError(Exception):

    """
    Indicates that the command was not found in the system after a search.

    :param cmd: String with the command.
    :param paths: List of paths where we looked after.
    """

    def __init__(self, cmd, paths):
        super().__init__()
        self.cmd = cmd
        self.paths = paths

    def __str__(self):
        return ("Command '%s' could not be found in any of the PATH dirs: %s" %
                (self.cmd, self.paths))


def find_command(cmd, default=None):
    """
    Try to find a command in the PATH, paranoid version.

    :param cmd: Command to be found.
    :param default: Command path to use as a fallback if not found
                    in the standard directories.
    :raise: :class:`aexpect.utils.path.CmdNotFoundError` in case the
            command was not found and no default was given.
    """
    try:
        path_paths = os.environ['PATH'].split(":")
    except IndexError:
        path_paths = []

    for common_path in ["/usr/libexec", "/usr/local/sbin", "/usr/local/bin",
                        "/usr/sbin", "/usr/bin", "/sbin", "/bin"]:
        if common_path not in path_paths:
            path_paths.append(common_path)

    for dir_path in path_paths:
        cmd_path = os.path.join(dir_path, cmd)
        if os.path.isfile(cmd_path):
            return os.path.abspath(cmd_path)

    if default is not None:
        return default
    raise CmdNotFoundError(cmd, path_paths)


def init_dir(*args):
    """
    Wrapper around os.path.join that creates dirs based on the final path.

    :param args: List of dir arguments that will be os.path.joined.
    :type directory: list
    :return: directory.
    :rtype: str
    """
    directory = os.path.join(*args)  # pylint: disable=E1120
    if not os.path.isdir(directory):
        os.makedirs(directory)
    return directory
