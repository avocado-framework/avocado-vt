"""
The tmux command related utility functions
"""

import logging

from virttest import utils_misc
from virttest import utils_package


def run_tmux_cmd(cmd, session=None, ignore_status=False):
    """
    Execute shell-commands in tmux on localhost or remote

    :param cmd: The command line to run
    :param session: The session object to the host
    :param ignore_status: Whether to raise an exception when command fails
    :return: command status and output
    """
    if not utils_package.package_install("tmux", session):
        logging.error("Failed to install required package - tmux!")
    tmux_cmd = 'tmux -c "{}"'.format(cmd)

    return utils_misc.cmd_status_output(tmux_cmd, shell=True, verbose=True,
                                        ignore_status=ignore_status,
                                        session=session)
