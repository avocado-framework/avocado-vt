# Copyright 2013-2023 Intranet AG and contributors
#
# avocado-i2n is free software: you can redistribute it and/or modify
# it under the terms of the GNU Lesser General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# avocado-i2n is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with avocado-i2n.  If not, see <http://www.gnu.org/licenses/>.

"""
Utility for the main test suite substructures like test objects.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

from __future__ import annotations

import logging as log

import aexpect
from aexpect.exceptions import ShellTimeoutError
from aexpect import remote
from aexpect.client import RemoteSession
from virttest.utils_params import Params

from . import NetObject

logging = log.getLogger("avocado.job." + __name__)


class TestEnvironment(object):
    """Generic environment isolating a given test."""

    def __init__(self, id: str) -> None:
        """
        Construct a test environment for any test nodes (tests).

        :param id: ID of the test environment
        """
        self.id = id


class TestSwarm(TestEnvironment):
    """A wrapper for a test swarm of workers traversing the graph."""

    run_swarms = {}

    def __init__(self, id: str, workers: list[TestWorker] = None) -> None:
        """
        Construct a test swarm (of sub-environments for execution) for any test nodes (tests).

        The rest of the arguments are inherited from the base class.
        """
        super().__init__(id)
        self.workers = workers or []

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        dump = f"[swarm] id='{self.id}', workers='{len(self.workers)}'"
        for worker in self.workers:
            dump = f"{dump}\n\t{worker}"
        return dump


class TestWorker(TestEnvironment):
    """A wrapper for a test worker traversing the graph."""

    _session_cache = {}

    @property
    def params(self) -> Params:
        """Parameters (cache) property."""
        return self.net.params

    @property
    def restrs(self) -> dict[str, str]:
        """Restrictions property."""
        return self.net.restrs

    def __init__(self, id_net: NetObject) -> None:
        """
        Construct a test worker (execution environment) for any test nodes (tests).

        :param id_net: flat test net object to get configuration from

        The rest of the arguments are inherited from the base class.
        """
        super().__init__(id_net.params["shortname"])
        self.net = id_net
        _, self.swarm_id, _ = self.params["name"].split(".")
        self.spawner = None

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        return f"[worker] id='{self.id}', spawner='{self.params['nets_spawner']}'"

    def overwrite_with_slot(self, slot: str) -> None:
        """
        Overwrite worker parameters with configuration extrapolated from a slot string.

        :param slot: slot string in the format "gateway/host"
        """
        env_tuple = tuple(slot.split("/"))
        if len(env_tuple) == 1:
            env_net = ""
            env_name = "c" + env_tuple[0] if env_tuple[0] else ""
            if env_name != "":
                prefix = self.params["nets_ip_prefix"]
                ip = f"{prefix}.{env_name[1:]}"
            else:
                ip = "localhost"
            port = self.params["nets_shell_port"]
            # NOTE: at present handle empty environment id (lack of slots) as an indicator
            # of using non-isolated serial runs via the old process environment spawner
            env_type = "lxc" if env_name else "process"
        elif len(env_tuple) == 2:
            env_net = env_tuple[0]
            env_name = env_tuple[1]
            if not env_name.isdigit():
                raise RuntimeError(
                    f"Invalid remote host '{env_name}', "
                    f"only numbers (as forwarded ports) accepted"
                )
            env_type = "remote"
            port = f"22{env_name}"
            ip = env_net
        else:
            raise ValueError(f"Slot string {slot} could not be parsed")

        self.params["nets_gateway"] = env_net
        self.params["nets_host"] = env_name
        self.params["nets_spawner"] = env_type
        self.params["nets_shell_host"] = ip
        self.params["nets_shell_port"] = port

    def start(self) -> bool:
        """
        Start the environment for executing a test node.

        :returns: whether the environment is available after current or previous start
        :raises: :py:class:`ValueError` when environment ID could not be parsed
        """
        logging.info(f"Starting worker {self.id} environment")
        isolation_type = self.params["nets_spawner"]
        if isolation_type == "process":
            logging.debug("Serial runs do not have any startable environment")
            return True
        elif isolation_type == "lxc":
            import lxc

            cid = self.params["nets_host"]
            container = lxc.Container(cid)
            if not container.running:
                logging.info(f"Starting container environment {cid}")
                return container.start()
            return container.running
        elif isolation_type == "remote":
            # TODO: send wake-on-lan package to start remote host (assuming routable)
            logging.warning("Assuming the remote host is running for now")
            return True
        else:
            raise RuntimeError(f"Unsupported isolation type {isolation_type}")

    def stop(self) -> bool:
        """
        Stop the environment for executing a test node.

        :returns: whether the environment stopping succeded
        :raises: :py:class:`ValueError` when environment ID could not be parsed
        """
        logging.info(f"Stopping worker {self.id} environment")
        isolation_type = self.params["nets_spawner"]
        if isolation_type == "process":
            logging.debug("Serial runs do not have any stoppable environment")
            return True
        elif isolation_type == "lxc":
            import lxc

            cid = self.params["nets_host"]
            container = lxc.Container(cid)
            if container.running:
                logging.info(f"Stopping container environment {cid}")
                return container.stop()
            return container.running
        elif isolation_type == "remote":
            # TODO: send shutdown via session to stop remote host (assuming routable)
            logging.warning("Assuming the remote host is not running for now")
            return True
        else:
            raise RuntimeError(f"Unsupported isolation type {isolation_type}")

    def get_session(self) -> RemoteSession:
        """
        Get a remote session to the current slot for the given test node.

        :returns: remote session to the slot determined from current node environment
        """
        log.getLogger("aexpect").parent = log.getLogger("avocado.job")

        address = self.params["nets_shell_host"] + ":" + self.params["nets_shell_port"]
        cache = type(self)._session_cache
        session = cache.get(address)
        if session:
            # check for corrupted sessions
            try:
                logging.debug(
                    "Remote session health check: " + session.cmd_output("date")
                )
            except ShellTimeoutError as error:
                logging.warning(f"Bad remote session health for {address}!")
                session = None
        if not session:
            session = remote.wait_for_login(
                self.params["nets_shell_client"],
                self.params["nets_shell_host"],
                self.params["nets_shell_port"],
                self.params["nets_username"],
                self.params["nets_password"],
                self.params["nets_shell_prompt"],
            )
            cache[address] = session

        return session
