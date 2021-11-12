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
# Copyright: Red Hat Inc. 2024
# Authors: Yongxue Hong <yhong@redhat.com>

import logging.handlers
import os
import sys

from .. import core

LOG = logging.getLogger("avocado.agent." + __name__)


def run(host, port, pid_file):
    """
    Run the agent server.

    :param host: The host of agent server.
    :type host: str
    :param port: The port of agent server to be listened.
    :type port: int
    :param pid_file: The PID file.
    :type pid_file: str
    """
    try:
        LOG.info("Serving VT agent on %s:%s", host, port)
        pid = str(os.getpid())
        LOG.info("Running the agent daemon with PID %s", pid)
        services = core.service.load_services()
        server = core.server.RPCServer((host, port))
        server.register_services(services)
        LOG.info("Waiting for connecting.")

        with open(pid_file, "w+") as f:
            f.write(pid + "\n")
        server.serve_forever()
    except KeyboardInterrupt:
        LOG.warn("Keyboard interrupt received, exiting.")
        sys.exit(0)
    except Exception as e:
        LOG.error(e, exc_info=True)
        sys.exit(-1)
    finally:
        try:
            os.remove(pid_file)
        except OSError:
            pass
