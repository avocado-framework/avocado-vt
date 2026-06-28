# Copyright 2013-2020 Intranet AG and contributors
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
Utility for the main test suite substructures like test nodes.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

from __future__ import annotations

import os
import re
from functools import cmp_to_key
from typing import Generator
from typing import Any
import logging as log

from aexpect.exceptions import ShellCmdError
from aexpect import remote_door as door
from avocado.core.test_id import TestID
from avocado.core.nrunner.runnable import Runnable
from virttest.utils_params import Params

from . import TestSwarm, TestWorker, TestObject, NetObject
from .. import params_parser as param

logging = log.getLogger("avocado.job." + __name__)


door.DUMP_CONTROL_DIR = "/tmp"


class PrefixTreeNode(object):
    """A node of a prefix tree."""

    def __init__(self, variant: str = None, parent: str = None) -> None:
        """Construct a prefix tree node."""
        self.variant = variant
        self.parent = parent
        self.end_test_node = None
        self.children = {}

    def check_child(self, variant: str) -> bool:
        """Check child prefix tree node."""
        return variant in self.children

    def get_child(self, variant: str) -> str:
        """Get child prefix tree node."""
        return self.children[variant]

    def set_child(self, variant: str, child: str) -> None:
        """Set child prefix tree node."""
        self.children[variant] = child

    def unset_child(self, variant: str) -> None:
        """Unset child prefix tree node."""
        del self.children[variant]

    def traverse(self) -> Generator[None, None, None]:
        """Traverse the current node."""
        yield self
        for child in self.children.values():
            yield from child.traverse()


class PrefixTree(object):
    """A trie structure used for faster prefix lookup."""

    def __init__(self) -> None:
        """Construct a prefix tree."""
        self.variant_nodes = {}

    def __contains__(self, name: str) -> bool:
        """Check whether the prefix tree contains a given name."""
        variants = name.split(".")
        if variants[0] not in self.variant_nodes:
            return False
        for current in self.variant_nodes[variants[0]]:
            for variant in variants[1:]:
                if not current.check_child(variant):
                    break
                current = current.get_child(variant)
            else:
                return True
        return False

    def insert(self, test_node: "TestNode") -> None:
        """Insert a test node name in the prefix tree."""
        variants = test_node.params["name"].split(".")
        if variants[0] not in self.variant_nodes.keys():
            self.variant_nodes[variants[0]] = [PrefixTreeNode(variants[0])]
        for current in self.variant_nodes[variants[0]]:
            for variant in variants[1:]:
                if not current.check_child(variant):
                    new_child = PrefixTreeNode(variant)
                    current.set_child(variant, new_child)
                    if variant not in self.variant_nodes:
                        self.variant_nodes[variant] = []
                    self.variant_nodes[variant] += [new_child]
                current = current.get_child(variant)
            current.end_test_node = test_node

    def get(self, name: str) -> list["TestNode"]:
        """Get all the names of the prefix tree."""
        variants = name.split(".")
        if variants[0] not in self.variant_nodes:
            return []
        test_nodes = []
        for current in self.variant_nodes[variants[0]]:
            for variant in variants[1:]:
                if not current.check_child(variant):
                    break
                current = current.get_child(variant)
            else:
                for node in current.traverse():
                    if node.end_test_node is not None:
                        test_nodes.append(node.end_test_node)
        return test_nodes


class EdgeRegister:
    """A register for the Cartesian graph edges allowing counter and worker stats extraction."""

    def __init__(self) -> None:
        """Construct an edge register."""
        self._registry = {}

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        return f"[edge] registry='{self._registry}'"

    def get_workers(self, node: "TestNode" = None) -> set[str]:
        """
        Get all worker visits for the given (possibly bridged) test node are all nodes.

        :param node: possibly registered test node to get visits for
        :returns: all visits by all workers as worker references (allowing repetitions)
        """
        worker_keys = set()
        node_keys = [node.bridged_form] if node else self._registry.keys()
        for node_key in node_keys:
            worker_keys |= {*self._registry.get(node_key, {}).keys()}
        return worker_keys

    def get_counters(self, node: "TestNode" = None, worker: TestWorker = None) -> int:
        """
        Get all workers in the current register.

        :param node: optional test node to get counters for
        :param worker: optional worker to get counters for
        :returns: counter for a given node or worker (typically both)
        """
        counter = 0
        node_keys = [node.bridged_form] if node else self._registry.keys()
        for node_key in node_keys:
            worker_keys = (
                [worker.id] if worker else self._registry.get(node_key, {}).keys()
            )
            for worker_key in worker_keys:
                counter += self._registry.get(node_key, {}).get(worker_key, 0)
        return counter

    def register(self, node: "TestNode", worker: TestWorker) -> None:
        """
        Register a worker visit for the given (possibly bridged) test node.

        :param node: possibly registered test node to register visits for
        :param worker: worker that visited the test node
        """
        if node.bridged_form not in self._registry:
            self._registry[node.bridged_form] = {}
        if worker.id not in self._registry[node.bridged_form]:
            self._registry[node.bridged_form][worker.id] = 0
        self._registry[node.bridged_form][worker.id] += 1


class TestNode(Runnable):
    """
    A wrapper for all test relevant parts.

    These include parameters, parser, used objects and
    dependencies to/from other test nodes (setup/cleanup).
    """

    class ReadOnlyDict(dict[Any, Any]):
        """Custom implementation of a read-only attribute of dictionary type."""

        def _readonly(self, *args: tuple[type, ...], **kwargs: dict[str, type]) -> None:
            raise RuntimeError("Cannot modify read-only dictionary")

        __setitem__ = _readonly
        __delitem__ = _readonly
        pop = _readonly
        popitem = _readonly
        clear = _readonly
        update = _readonly
        setdefault = _readonly

    #: digit: 0 for object root, >0 for everything else
    #: letter: "a" (autosetup), "b" (byproduct), "c" (cleanup), "d" (duplicate)
    prefix_pattern = re.compile(r"^(\d+)([abcd]?)(.+)")

    @property
    def params(self) -> Params:
        """Parameters (cache) property."""
        if self._params_cache is None:
            self.regenerate_params()
        return self._params_cache

    @property
    def shared_started_workers(self) -> set[TestWorker]:
        """Workers that have previously started traversing this node (incl. leaves and others)."""
        workers = set()
        if self.started_worker is not None:
            workers.add(self.started_worker)
        for bridged_node in self.bridged_nodes:
            if bridged_node.started_worker is not None:
                workers.add(bridged_node.started_worker)
        return workers

    @property
    def shared_finished_workers(self) -> set[TestWorker]:
        """Workers that have previously finished traversing this node (incl. leaves and others)."""
        workers = set()
        if self.finished_worker is not None:
            workers.add(self.finished_worker)
        for bridged_node in self.bridged_nodes:
            if bridged_node.finished_worker is not None:
                workers.add(bridged_node.finished_worker)
        return workers

    @property
    def shared_involved_workers(self) -> set[TestWorker]:
        """Workers that picked up the node and possibly have continued to either its setup or cleanup."""
        worker_ids = (
            self._picked_by_setup_nodes.get_workers()
            | self._picked_by_cleanup_nodes.get_workers()
        )
        workers = [
            w
            for s in TestSwarm.run_swarms
            for w in TestSwarm.run_swarms[s].workers
            if w.id in worker_ids
        ]
        return set(workers)

    @property
    def shared_results(self) -> list[dict[str, str]]:
        """Test results shared across all bridged nodes."""
        results = list(self.results)
        for bridged_node in self.bridged_nodes:
            results += bridged_node.results
        return results

    @property
    def shared_filtered_results(self) -> list[dict[str, str]]:
        """Test results shared across all bridged nodes."""
        all_results = self.shared_results
        if (
            self.started_worker
            and "swarm" not in self.params["pool_scope"]
            and self.params.get("nets_spawner") == "lxc"
        ):
            # has separate results for each worker (doesn't matter eager of full)
            scope_filter = self.started_worker.swarm_id + "." + self.started_worker.id
        elif (
            self.started_worker
            and "cluster" not in self.params["pool_scope"]
            and self.params.get("nets_spawner") == "remote"
        ):
            # has results for an entire swarm by at least N of its workers
            scope_filter = self.started_worker.swarm_id
        else:
            # has fully globally shared results
            scope_filter = ""
        results = []
        for result in all_results:
            if scope_filter in result["name"]:
                results += [result]
        return results

    @property
    def shared_result_worker_ids(self) -> set[str]:
        """ID-s of workers that produced the shared results."""
        workers = set()
        for result in self.shared_results:
            if result["status"] != "PASS":
                continue
            worker_ids = [
                w.id for s in TestSwarm.run_swarms.values() for w in s.workers
            ]
            for worker_id in worker_ids:
                if worker_id in result["name"]:
                    workers.add(worker_id)
                    break
        return workers

    @property
    def bridged_nodes(self) -> tuple["TestNode"]:
        """Read-only list of bridged nodes."""
        return tuple(self._bridged_nodes)

    @property
    def cloned_nodes(self) -> tuple["TestNode"]:
        """Read-only list of cloned nodes."""
        return tuple(self._cloned_nodes)

    @property
    def setup_nodes(self) -> dict[TestNode, set[TestObject]]:
        """Read-only dict of setup nodes."""
        return TestNode.ReadOnlyDict(self._setup_nodes)

    @property
    def cleanup_nodes(self) -> dict[TestNode, set[TestObject]]:
        """Read-only dict of cleanup nodes."""
        return TestNode.ReadOnlyDict(self._cleanup_nodes)

    @property
    def setless_form(self) -> Params:
        """Test set invariant form of the test node name."""
        max_restr = ""
        for main_restr in self.params.objects("main_restrictions"):
            if self.params["name"].startswith(main_restr):
                max_restr = (
                    main_restr if len(main_restr) > len(max_restr) else max_restr
                )
        return self.params["name"].replace(max_restr + ".", "", 1)

    @property
    def bridged_form(self) -> Params:
        """Test worker invariant form of the test node name."""
        # TODO: the order of parsing nets and vms has to be improved
        if len(self.objects) == 0:
            return self.setless_form
        # TODO: the long suffix does not contain anything reasonable
        # suffix = self.objects[0].long_suffix
        suffix = self.params["_name_map_file"].get("nets.cfg", "")
        # since this doesn't use the prefix tree a regex could match part of a variant
        return r"\." + self.setless_form.replace(suffix, ".+") + r"$"

    @property
    def long_prefix(self) -> Params:
        """Sufficiently unique prefix to identify a diagram test node."""
        nets = self.params.get("nets", "").replace(" ", ".")
        vms = self.params.get("vms", "").replace(" ", ".")
        return self.prefix + "-" + nets + "." + vms

    @property
    def id(self) -> Params:
        """Use unique ID to identify a test node."""
        return self.prefix + "-" + self.params["name"]

    @property
    def id_test(self) -> Params:
        """Use a unique test ID to identify a test node."""
        return TestID(self.prefix, self.params["name"])

    def __init__(self, prefix: str, recipe: param.Reparsable) -> None:
        """
        Construct a test node (test) for any test objects (vms).

        :param recipe: variant parsing recipe for the test node
        """
        super().__init__("avocado-vt", prefix, {})

        self.prefix = prefix
        self.recipe = recipe
        self._params_cache = None
        self.restrs = {}

        self.should_run = self.default_run_decision
        self.should_clean = self.default_clean_decision

        self.finished_worker = None
        self.started_worker = None

        self._bridged_nodes = []
        self._cloned_nodes = []
        self.incompatible_workers = set()

        self.objects = []
        self.results = []

        # lists of parent and children test nodes
        self._setup_nodes = {}
        self._cleanup_nodes = {}
        self._picked_by_setup_nodes = EdgeRegister()
        self._picked_by_cleanup_nodes = EdgeRegister()
        self._dropped_setup_nodes = EdgeRegister()
        self._dropped_cleanup_nodes = EdgeRegister()

    def __repr__(self) -> str:
        """Provide a representation of the object."""
        shortname = self.params.get("shortname", "<unknown>")
        return f"[node] longprefix='{self.long_prefix}', shortname='{shortname}'"

    def set_objects_from_net(self, net: NetObject) -> None:
        """
        Set all node's objects from a provided test net.

        :param net: test net to use as first and top object
        """
        # flattened list of objects (in composition) involved in the test
        self.objects = [net]
        # TODO: only three nesting levels from a test net are supported
        for test_object in net.components:
            self.objects += [test_object]
            self.objects += test_object.components
            # TODO: dynamically added additional images will not be detected here
            from . import ImageObject
            from .. import params_parser as param

            vm_name = test_object.suffix
            parsed_images = [c.suffix for c in test_object.components]
            for image_name in self.params.object_params(vm_name).objects("images"):
                if image_name not in parsed_images:
                    image_suffix = f"{image_name}_{vm_name}"
                    config = param.Reparsable()
                    config.parse_next_dict(test_object.params.object_params(image_name))
                    config.parse_next_dict(
                        {"object_suffix": image_suffix, "object_type": "images"}
                    )
                    image = ImageObject(image_suffix, config)
                    image.composites.append(test_object)
                    self.objects += [image]

    def is_occupied(self, worker: TestWorker = None) -> bool:
        """
        Check if the test node is sufficiently occupied with respect to a given worker in various scopes.

        :param worker: test worker with respect to which to consider various scopes
        """
        # by default only reentrancy of 1 is allowed independently of previous results
        max_concurrent_tries = self.params.get_numeric(
            "max_concurrent_tries", self.params.get_numeric("max_tries", 1)
        )
        return self.is_started(worker, max(max_concurrent_tries, 1))

    def is_flat(self) -> bool:
        """Check if the test node is flat and does not yet have objects and dependencies to evaluate."""
        return len(self.objects) == 0

    def is_shared_root(self) -> bool:
        """Check if the test node is the root of all test nodes for all test objects."""
        return self.params.get_boolean("shared_root", False)

    def is_object_root(self) -> bool:
        """Check if the test node is the root of all test nodes for some test object."""
        return "object_root" in self.params

    def is_unrolled(self, worker: TestWorker = None) -> bool:
        """
        Check if the test is unrolled as composite node with dependencies.

        :param worker: worker a flat node is unrolled for
        :raises: :py:class:`RuntimeError` if the current node is not flat (cannot be unrolled)
        """
        if self.is_shared_root():
            return True
        elif not self.is_flat():
            raise RuntimeError(f"Only flat nodes can be unrolled, {self} is not flat")
        elif worker and worker.net.long_suffix in self.incompatible_workers:
            return True
        elif worker is None and len(self.incompatible_workers) > 0:
            return True
        for node in self.cleanup_nodes:
            if self.setless_form in node.id:
                if worker and worker.id in node.id:
                    return True
                # whether the node is unrolled for any worker if no worker specified
                elif worker is None:
                    return True
        return False

    def is_setup_ready(self, worker: TestWorker) -> bool:
        """
        Check if all dependencies of the test were run or there were none.

        :param worker: relative setup readiness with respect to a worker ID
        """
        for node in self.setup_nodes:
            if not node.is_flat() and worker.id not in node.params["name"]:
                continue
            if worker.id not in self._dropped_setup_nodes.get_workers(node):
                return False
        return True

    def is_cleanup_ready(self, worker: TestWorker) -> bool:
        """
        Check if all dependent tests were run or there were none.

        :param str worker: relative setup readiness with respect to a worker ID
        """
        for node in self.cleanup_nodes:
            if not node.is_flat() and worker.id not in node.params["name"]:
                continue
            if worker.id not in self._dropped_cleanup_nodes.get_workers(node):
                return False
        return True

    def is_started(self, worker: TestWorker = None, threshold: int = 1) -> bool:
        """
        Check if the test is currently traversed by at least N (-1 for all) workers of all or some scopes.

        :param worker: evaluate with respect to an optional worker ID scope or globally if none given
        :param threshold: how eagerly the node is considered started in terms of number of
                          required workers to use as a threshold (1 for most eagerly, -1 for most fully)
        :returns: whether the test was run by at least N workers of all or some scopes (N=threshold)
        """
        if self.is_flat():
            return False
        if (
            worker
            and "swarm" not in self.params["pool_scope"]
            and self.params.get("nets_spawner") == "lxc"
        ):
            # is started separately by each worker (doesn't matter eager of full)
            return worker in self.shared_started_workers
        elif (
            worker
            and "cluster" not in self.params["pool_scope"]
            and self.params.get("nets_spawner") == "remote"
        ):
            own_cluster = worker.swarm_id
            own_cluster_started_hosts = {
                w for w in self.shared_started_workers if w.swarm_id == own_cluster
            }
            if threshold == -1:
                # is started for an entire swarm by all of its workers that have already picked that node
                own_cluster_all_hosts = self.shared_involved_workers & {
                    *TestSwarm.run_swarms[own_cluster].workers
                }
                return own_cluster_started_hosts == own_cluster_all_hosts
            # is started for an entire swarm by at least N of its workers
            return len(own_cluster_started_hosts) >= threshold
        else:
            if threshold == -1:
                # is started globally by all workers that have already picked that node
                return self.shared_started_workers == self.shared_involved_workers
            # is started globally by at least N workers (down to at least one worker)
            return len(self.shared_started_workers) >= threshold

    def is_finished(self, worker: TestWorker = None, threshold: int = 1) -> bool:
        """
        Check if the test was ever traversed by at least N (-1 for all) workers of all or some scopes.

        :param worker: evaluate with respect to an optional worker ID scope or globally if none given
        :param threshold: how eagerly the node is considered started in terms of number of
                          required workers to use as a threshold (1 for most eagerly, -1 for most fully)
        :returns: whether the test was run by at least one worker of all or some scopes

        Threshold of 1 is the most eager manner so that any already available setup nodes are considered
        finished. If we instead wait for this setup to be cleaned up or synced, this would count most
        of the setup as finished in the very end of the traversal.

        Threshold of -1 is for fully traversed node by all workers unless restricted within some scope
        of setup reuse.
        """
        if self.is_flat():
            return True
        if (
            worker
            and "swarm" not in self.params["pool_scope"]
            and self.params.get("nets_spawner") == "lxc"
        ):
            # is finished separately by each worker (doesn't matter eager of full)
            return worker in self.shared_finished_workers
        elif (
            worker
            and "cluster" not in self.params["pool_scope"]
            and self.params.get("nets_spawner") == "remote"
        ):
            own_cluster = worker.swarm_id
            own_cluster_finished_hosts = {
                w for w in self.shared_finished_workers if w.swarm_id == own_cluster
            }
            if threshold == -1:
                # is finished for an entire swarm by all of its workers that have already picked that node
                own_cluster_all_hosts = self.shared_involved_workers & {
                    *TestSwarm.run_swarms[own_cluster].workers
                }
                return own_cluster_finished_hosts == own_cluster_all_hosts
            # is finished for an entire swarm by at least N of its workers
            return len(own_cluster_finished_hosts) >= threshold
        else:
            if threshold == -1:
                # is finished globally by all workers that have already picked that node
                return self.shared_finished_workers == self.shared_involved_workers
            # is finished globally by at least N workers (down to at least one worker)
            return len(self.shared_finished_workers) >= threshold

    def get_terminal_object(self, key: str = "object_root") -> TestObject | None:
        """
        Determine any object that this node is a root of.

        :param key: parameter key to use to determine the object root
        :returns: object that this node is a root of if any or None otherwise
        """
        object_root = self.params.get(key)
        if not object_root:
            return None
        for test_object in self.objects:
            if test_object.id == object_root:
                return test_object
        return None

    def get_stateful_objects(self, do: str = "set") -> list[TestObject]:
        """
        Check if the test node produces any reusable setup state.

        :param do: state reuse or creation, one of "get" or "set"
        :returns: any test objects that this node produces setup for
        """
        setup_objects = []
        for test_object in self.objects:
            object_params = test_object.object_typed_params(self.params)
            object_state = object_params.get(f"{do}_state")
            if object_state:
                setup_objects += [test_object]
        return setup_objects

    def get_dependency(
        self, restriction: str, test_object: TestObject
    ) -> "TestNode | None":
        """
        Check if the test node has a dependency parsed and available.

        :param restriction: name of the dependency (state or parent test set)
        :param test_object: object used for the dependency
        :returns: whether the dependency was already found among the setup nodes

        ..todo:: Type annotation does not support "|" with string type hint.
        """
        # TODO: use new attribute
        for test_node in self.setup_nodes:
            # TODO: direct object comparison will not work for dynamically
            # (within node) created objects like secondary images
            node_object_suffices = [t.long_suffix for t in test_node.objects]
            if (
                test_object in test_node.objects
                or test_object.long_suffix in node_object_suffices
            ):
                # search is done here to not match repeating restriction for a different object
                if re.search(
                    r"(\.|^)" + restriction + r"(\.|$)", test_node.params.get("name")
                ):
                    return test_node
                setup_object_params = test_object.object_typed_params(test_node.params)
                if restriction == setup_object_params.get("set_state"):
                    return test_node
        return None

    def should_parse(self, worker: TestWorker = None) -> bool:
        """
        Parse if node has been dropped in all its setup nodes by at least one worker.

        :param worker: evaluate with respect to an optional worker ID scope or globally if none given
        :returns: whether the test node should be parsed
        """
        parse_by = f" by {worker}" if worker else ""
        for picked_worker in self.shared_involved_workers:
            if (
                self.is_unrolled(picked_worker)
                and self.is_cleanup_ready(picked_worker)
                and len(picked_worker.restrs) == 0
            ):
                logging.debug(
                    f"Should not parse {self}{parse_by} which is cleanup ready from worker {picked_worker}"
                )
                return False
        logging.debug(
            f"Should parse {self}{parse_by} which is not cleanup ready from any worker"
        )
        return True

    def should_rerun(self, worker: TestWorker = None) -> bool:
        """
        Check if the test node should be rerun based on some retry criteria.

        :param worker: evaluate with respect to an optional worker ID scope or globally if none given
        :returns: whether the test node should be retried

        The retry parameters are `max_tries` and `rerun_status` or `stop_status`. The
        first is the maximum number of tries, and the second two indicate when to continue
        or stop retrying in terms of encountered test status and can be a list of statuses.
        """
        if self.params.get("dry_run", "no") == "yes":
            logging.info(f"Should not rerun via dry test run {self}")
            return False
        elif self.is_flat():
            logging.debug(f"Should not rerun a flat node {self}")
            return False
        elif len(self.cloned_nodes) > 0:
            logging.debug(f"Should not rerun a cloned node {self}")
            return False
        elif worker and worker.id not in self.params["name"]:
            raise RuntimeError(
                f"Worker {worker.id} should not consider rerunning {self}"
            )

        all_statuses = [
            "fail",
            "error",
            "pass",
            "warn",
            "skip",
            "cancel",
            "interrupted",
            "unknown",
        ]
        if self.params.get("replay"):
            rerun_status = self.params.get_list(
                "rerun_status", "fail,error,warn", delimiter=","
            )
        else:
            rerun_status = self.params.get_list("rerun_status", []) or all_statuses
        stop_status = self.params.get_list("stop_status", [])
        for status, status_type in [(rerun_status, "rerun"), (stop_status, "stop")]:
            disallowed_status = {*status} - {*all_statuses}
            if len(disallowed_status) > 0:
                raise ValueError(
                    f"Value of {status_type} status must be a valid test status,"
                    f" found {', '.join(disallowed_status)}"
                )

        # ignore the retry parameters for nodes that cannot be re-run (need to run at least once)
        max_tries = self.params.get_numeric(
            "max_tries", 2 if self.params.get("replay") else 1
        )
        # do not log when the user is not using the retry feature
        if max_tries > 1:
            stop_condition = ", ".join(stop_status) if stop_status else "NONE"
            rerun_condition = ", ".join(rerun_status) if rerun_status else "NONE"
            logging.debug(
                f"Could rerun {self} with stop condition {stop_condition}, a rerun condition "
                f"{rerun_condition}, and a maximum of {max_tries} tries"
            )
        if max_tries < 0:
            raise ValueError("Number of max_tries cannot be less than zero")

        # analyzing rerun and stop status conditions
        if len(self.get_stateful_objects()) == 0:
            test_statuses = [r["status"].lower() for r in self.shared_results]
        else:
            # TODO: the started worker method is implicit and we need a proper function
            old_started_worker = self.started_worker
            self.started_worker = old_started_worker or worker
            # setup tests can be filtered across swarms
            test_statuses = [r["status"].lower() for r in self.shared_filtered_results]
            self.started_worker = old_started_worker
        rerun_statuses_violated = {*test_statuses} - {*rerun_status}
        if len(rerun_statuses_violated) > 0:
            logging.debug(
                f"Stopping test tries due to violated rerun test statuses: {rerun_status}"
            )
            return False
        stop_statuses_found = {*stop_status} & {*test_statuses}
        if len(stop_statuses_found) > 0:
            logging.info(
                f"Stopping test tries due to obtained stop test statuses: {', '.join(stop_statuses_found)}"
            )
            return False

        # the runs total also considers UNKNOWN statuses from currently occupied test nodes minus currently traversed/evaluated case
        total_runs = len(test_statuses)
        # implicitly this means that setting >1 retries will be done on tests actually collecting results (no flat nodes, dry runs, etc.)
        reruns_left = 0 if max_tries == 1 else max_tries - total_runs
        if reruns_left > 0:
            logging.debug(
                f"Still have {reruns_left} allowed reruns left and should rerun {self}"
            )
            return True
        logging.debug(f"Should not rerun {self}")
        return False

    def default_run_decision(self, worker: TestWorker) -> bool:
        """
        Set default decision policy on whether a test node should be run or skipped.

        :param worker: worker which makes the run decision
        :returns: whether the worker should run the test node
        """
        if self.params.get("dry_run", "no") == "yes":
            logging.info(f"Should not run via dry test run {self}")
            return False
        elif self.is_flat():
            logging.debug(f"Should not run a flat node {self}")
            return False
        elif len(self.cloned_nodes) > 0:
            logging.debug(f"Should not run a cloned node {self}")
            return False
        elif worker.id not in self.params["name"]:
            raise RuntimeError(f"Worker {worker.id} should not try to run {self}")

        if len(self.get_stateful_objects()) == 0:
            # most standard stateless behavior is to run each test node once then rerun if needed
            should_run = len(self.shared_results) == 0 or self.should_rerun(worker)

        else:
            should_scan = not self.is_finished(worker, 1)
            should_run_from_scan = self.scan_states() if should_scan else False
            # rerunning of test from previous jobs is never intended
            if len(self.shared_filtered_results) == 0 and not should_run_from_scan:
                self.should_rerun = lambda _: False

            should_run = should_run_from_scan if should_scan else False
            should_run = should_run or self.should_rerun(worker)

        if os.path.exists("/tmp/skip_tests"):
            with open("/tmp/skip_tests", "r") as f:
                skip_variants = f.read().splitlines()
            for skip_variant in skip_variants:
                if skip_variant in self.params["name"].split("."):
                    logging.info(
                        f"Should not run {self} since it is listed in /tmp/skip_tests"
                    )
                    return False

        return should_run

    def default_clean_decision(self, worker: TestWorker) -> bool:
        """
        Set default decision policy on whether a test node should be cleaned or skipped.

        :param worker: worker which makes the clean decision
        :returns: whether the worker should clean the test node
        """
        if self.params.get("dry_run", "no") == "yes":
            logging.info(f"Should not clean via dry test run {self}")
            return False
        elif self.is_flat():
            logging.debug(f"Should not clean a flat node {self}")
            return False
        elif len(self.cloned_nodes) > 0:
            logging.debug(f"Should not clean a cloned node {self}")
            return False
        elif worker.id not in self.params["name"]:
            raise RuntimeError(f"Worker {worker.id} should not try to clean {self}")

        # no support for parallelism within reversible nodes since we might hit a race condition
        # whereby a node will be run for missing setup but its parent will be reversed before it
        # gets any parent-provided states
        for test_object in self.objects:
            object_params = test_object.object_typed_params(self.params)
            is_reversible = (
                object_params.get("unset_mode_images", object_params["unset_mode"])[0]
                == "f"
            )
            is_reversible |= (
                object_params.get("unset_mode_vms", object_params["unset_mode"])[0]
                == "f"
            )
            if is_reversible:
                break
        else:
            is_reversible = False

        if not is_reversible:
            return True
        else:

            # last worker should "close the door" for all workers that opened it and left
            for picked_worker in self.shared_involved_workers:
                # TODO: provide swarm filtering not just here but universally wherever needed
                if (
                    worker.swarm_id != "localhost"
                    and worker.swarm_id not in picked_worker.id
                ):
                    continue
                if self.is_flat() or picked_worker.id in self.params["name"]:
                    picked_node = self
                else:
                    for node in self.bridged_nodes:
                        if picked_worker.id in node.params["name"]:
                            picked_node = node
                            break
                    else:
                        raise ValueError(
                            f"Cannot identify picked node for involved worker {picked_worker} "
                            f"instead of the composite {self} to consider for cleanup"
                        )
                if not picked_node.is_cleanup_ready(picked_worker):
                    logging.debug(f"Node is not cleanup ready for {picked_worker.id}")
                    return False
                # if any worker is still running this test it cannot be reversed
                test_statuses = [r["status"].lower() for r in picked_node.results]
                if "unknown" in test_statuses:
                    logging.debug(
                        f"A worker {picked_worker.id} is still running node which cannot yet be reversed"
                    )
                    return False

            # all involved workers should have also flagged the generalized node as finished
            return self.is_finished(worker, -1)

    @classmethod
    def prefix_priority(cls, prefix1: str, prefix2: str) -> int:
        """
        Class method for secondary prioritization using test prefixes.

        :param prefix1: first prefix to use for the priority comparison
        :param prefix2: second prefix to use for the priority comparison
        :returns: negative integer if prefix1 < prefix2, positive if prefix1 > prefix2,
                  0 otherwise (lower is better in our standard sorting)

        This function also does recursive calls of sub-prefixes.
        """
        if prefix1 == prefix2:
            # identical prefixes detected, nothing we can do but choose a default
            return 0
        match1, match2 = re.match(cls.prefix_pattern, prefix1), re.match(
            cls.prefix_pattern, prefix2
        )
        digit1, alpha1, else1 = (
            (prefix1, "", "") if match1 is None else match1.group(1, 2, 3)
        )
        digit2, alpha2, else2 = (
            (prefix2, "", "") if match2 is None else match2.group(1, 2, 3)
        )

        # compare order of parsing if simple leaf nodes
        if digit1.isdigit() and digit2.isdigit():
            digit1, digit2 = int(digit1), int(digit2)
            if digit1 != digit2:
                return digit1 - digit2
        # we no longer match and are at the end of the prefix
        else:
            if digit1 != digit2:
                return 1 if digit1 > digit2 else -1

        # compare the node type flags next
        if alpha1 is not None and alpha2 is not None and alpha1 != alpha2:
            if alpha1 == "":
                return -1
            if alpha2 == "":
                return 1
            # priority to lower alphas (from a down to e)
            return 1 if alpha1 > alpha2 else -1
        # redo the comparison for the next prefix part
        else:
            if else1 == "":
                raise ValueError(
                    f"could not match test prefix part {prefix1} to choose priority"
                )
            if else2 == "":
                raise ValueError(
                    f"could not match test prefix part {prefix2} to choose priority"
                )
            # priority to the prefix that didn't terminate yet
            if else1.startswith("-"):
                return 1
            elif else2.startswith("-"):
                return -1
            # retry on next step
            return cls.prefix_priority(else1, else2)

    def pick_parent(self, worker: TestWorker) -> "TestNode":
        """
        Pick the next available parent based on some priority.

        :param worker: worker for which the parent is selected
        :returns: the next parent node
        :raises: :py:class:`RuntimeError`

        The current order will prioritize less traversed test paths.
        """
        available_nodes = [
            n for n in self.setup_nodes if worker.id in n.params["name"] or n.is_flat()
        ]
        available_nodes = [
            n
            for n in available_nodes
            if worker.id not in self._dropped_setup_nodes.get_workers(n)
        ]
        if len(available_nodes) == 0:
            raise RuntimeError(
                f"Picked a parent of a node without remaining parents for {self}"
            )
        sorted_nodes = sorted(
            available_nodes,
            key=cmp_to_key(
                lambda x, y: TestNode.prefix_priority(x.long_prefix, y.long_prefix)
            ),
        )
        sorted_nodes = sorted(
            sorted_nodes, key=lambda n: n._picked_by_cleanup_nodes.get_counters()
        )
        sorted_nodes = sorted(sorted_nodes, key=lambda n: int(not n.is_flat()))

        test_node = sorted_nodes[0]
        test_node._picked_by_cleanup_nodes.register(self, worker)
        return test_node

    def pick_child(self, worker: TestWorker) -> "TestNode":
        """
        Pick the next available child based on some priority.

        :param worker: worker for which the child is selected
        :returns: the next child node
        :raises: :py:class:`RuntimeError`

        The current order will prioritize less traversed test paths.
        """
        available_nodes = [
            n
            for n in self.cleanup_nodes
            if worker.id in n.params["name"] or n.is_flat()
        ]
        available_nodes = [
            n
            for n in available_nodes
            if worker.id not in self._dropped_cleanup_nodes.get_workers(n)
        ]
        if len(available_nodes) == 0:
            raise RuntimeError(
                f"Picked a child of a node without remaining children for {self}"
            )
        sorted_nodes = sorted(
            available_nodes,
            key=cmp_to_key(
                lambda x, y: TestNode.prefix_priority(x.long_prefix, y.long_prefix)
            ),
        )
        sorted_nodes = sorted(
            sorted_nodes, key=lambda n: n._picked_by_setup_nodes.get_counters()
        )
        sorted_nodes = sorted(sorted_nodes, key=lambda n: int(not n.is_flat()))

        test_node = sorted_nodes[0]
        test_node._picked_by_setup_nodes.register(self, worker)
        return test_node

    def drop_parent(self, test_node: "TestNode", worker: TestWorker) -> None:
        """
        Add a parent node to the set of visited nodes for this test.

        :param test_node: visited node
        :param worker: worker visiting the node
        :raises: :py:class:`ValueError` if visited node is not directly dependent
        """
        if test_node not in self.setup_nodes:
            raise ValueError(
                f"Invalid parent to drop: {test_node} not a parent of {self}"
            )
        self._dropped_setup_nodes.register(test_node, worker)

    def drop_child(self, test_node: "TestNode", worker: TestWorker) -> None:
        """
        Add a child node to the set of visited nodes for this test.

        :param test_node: visited node
        :param worker: worker visiting the node
        :raises: :py:class:`ValueError` if visited node is not directly dependent
        """
        if test_node not in self.cleanup_nodes:
            raise ValueError(
                f"Invalid child to drop: {test_node} not a child of {self}"
            )
        self._dropped_cleanup_nodes.register(test_node, worker)

    def descend_from_node(self, test_node: "TestNode", test_object: TestObject) -> None:
        """
        Turn the current node into a child of a parent node for a given object.

        :param test_node: parent node the current node is a child of
        :param test_object: test object via which the dependency is determined
        """
        self._setup_nodes[test_node] = self._setup_nodes.get(test_node, set()) | {
            test_object
        }
        test_node._cleanup_nodes[self] = test_node._cleanup_nodes.get(self, set()) | {
            test_object
        }

    def bridge_with_node(self, test_node: "TestNode") -> None:
        """
        Bridge current node with equivalent node for a different worker.

        :param test_node: equivalent node for a different worker
        :raises: :py:class:`ValueError` if bridged node is not equivalent
        """
        if test_node == self:
            return
        # TODO: cannot do simpler comparison due to current limitations in the bridged form
        elif not re.search(test_node.bridged_form, self.params["name"]):
            raise ValueError(f"Cannot bridge {self} with non-equivalent {test_node}")
        if test_node not in self._bridged_nodes:
            logging.info(
                f"Bridging {self.params['shortname']} to {test_node.params['shortname']}"
            )
            self._bridged_nodes.append(test_node)
            test_node._bridged_nodes.append(self)

            self._picked_by_setup_nodes = test_node._picked_by_setup_nodes
            self._dropped_setup_nodes = test_node._dropped_setup_nodes
            self._picked_by_cleanup_nodes = test_node._picked_by_cleanup_nodes
            self._dropped_cleanup_nodes = test_node._dropped_cleanup_nodes

    def clone_as_source(self, test_nodes: list["TestNode"]) -> None:
        """
        Convert the node to a clone source for a list of its clones.

        :param test_nodes: clones to register as a clone source to
        """
        self.prefix = "0" + self.prefix
        self._cloned_nodes = test_nodes

    def pull_locations(self) -> None:
        """Update all setup locations for the current node."""
        if self.is_flat():
            return
        setup_path = self.params.get("swarm_pool", self.params["vms_base_dir"])
        for node in self.setup_nodes:
            setup_locations = [":" + self.params.get("shared_pool", ".")]
            for net_suffix in node.shared_result_worker_ids:
                setup_locations += [net_suffix + ":" + setup_path]

            # update test parameters at runtime with worker parameters of its setup
            for setup_location in setup_locations:
                wid, _ = setup_location.split(":")

                for component in node.cleanup_nodes[self]:
                    # discard parameters if we are not talking about any specific non-net object
                    if component.key == "nets":
                        continue
                    object_suffix = "_" + component.long_suffix
                    if setup_location in self.params.get(
                        f"get_location{object_suffix}", ""
                    ):
                        continue
                    if self.params.get(f"get_location{object_suffix}"):
                        self.params[f"get_location{object_suffix}"] += (
                            " " + setup_location
                        )
                    else:
                        self.params[f"get_location{object_suffix}"] = setup_location

                # no additional parameters needed for shared (local) locations
                if not wid:
                    continue
                # we might have results from previous jobs with non-traversed workers
                workers = [w for s in TestSwarm.run_swarms.values() for w in s.workers]
                for worker in workers:
                    if worker.id == wid:
                        source_suffix = "_" + wid
                        for key in worker.params:
                            # only provide access-related parameters from the worker
                            if not key.startswith("nets_"):
                                continue
                            self.params[f"{key}{source_suffix}"] = worker.params[key]
                        break
                else:
                    raise RuntimeError(
                        f"Could not pull setup location {setup_location} for {self}"
                    )

    def update_restrs(self, object_restrs: dict[str, str]) -> None:
        """
        Update any restrictions with further filters.

        :param object_restrs: multi-line object restrictions to append
        """
        for suffix, restriction in object_restrs.items():
            self.restrs[suffix] = self.restrs.get(suffix, "")
            if restriction != "":
                if restriction.rstrip() not in self.restrs[suffix].splitlines():
                    self.restrs[suffix] += restriction

    def regenerate_params(self, verbose: bool = False) -> None:
        """
        Regenerate all parameters from the current reparsable config.

        :param bool verbose: whether to show generated parameter dictionaries
        """
        self._params_cache = self.recipe.get_params(show_dictionaries=verbose)
        for key, value in list(self._params_cache.items()):
            if key.startswith("only_") or key.startswith("no_"):
                restr_type, suffix = key.split("_", maxsplit=1)
                restr_line = restr_type + " " + value + "\n" if value != "" else ""
                self.update_restrs({suffix: restr_line})
                del self._params_cache[key]
        self.regenerate_vt_parameters()

    def regenerate_vt_parameters(self) -> None:
        """Regenerate the parameters provided to the VT runner."""
        uri = self.params.get("name")
        vt_params = self.params.copy()
        # Flatten the vt_params, discarding the attributes that are not
        # scalars, and will not be used in the context of nrunner
        for key in ("_name_map_file", "_short_name_map_file", "dep"):
            if key in self.params:
                del vt_params[key]
        super().__init__("avocado-vt", uri, **vt_params)

    def scan_states(self) -> bool:
        """
        Scan for present object states to reuse the test from previous runs.

        :returns: whether all required states are available
        """
        should_run = True
        node_params = self.params.copy()

        is_leaf = True
        for test_object in self.objects:
            object_params = test_object.object_typed_params(self.params)
            object_state = object_params.get("set_state")

            # the test leaves an object undefined so it cannot be reused for this object
            if object_state is None or object_state == "":
                continue
            else:
                is_leaf = False

            # the object state has to be defined to reach this stage
            if object_state == "install" and test_object.is_permanent():
                should_run = False
                break

            # ultimate consideration of whether the state is actually present
            object_suffix = f"_{test_object.key}_{test_object.long_suffix}"
            node_params[f"check_state{object_suffix}"] = object_state
            node_params[f"show_location{object_suffix}"] = (
                ":" + object_params["shared_pool"]
            )
            node_params[f"check_mode{object_suffix}"] = object_params.get(
                "check_mode", "rf"
            )
            # TODO: unfortunately we need env object with pre-processed vms in order
            # to provide ad-hoc root vm states so we use the current advantage that
            # all vm state backends can check for states without a vm boot (root)
            if test_object.key == "vms":
                node_params[f"use_env{object_suffix}"] = "no"
            node_params[f"soft_boot{object_suffix}"] = "no"

        if not is_leaf:
            session = self.started_worker.get_session()
            control_path = os.path.join(
                self.params["suite_path"], "controls", "pre_state.control"
            )
            mod_control_path = door.set_subcontrol_parameter(
                control_path, "action", "check"
            )
            mod_control_path = door.set_subcontrol_parameter_dict(
                mod_control_path, "params", node_params
            )
            try:
                door.run_subcontrol(session, mod_control_path)
                should_run = False
            except ShellCmdError as error:
                if "AssertionError" in error.output:
                    should_run = True
                else:
                    raise RuntimeError(
                        "Could not complete state scan due to control file error"
                    )
        logging.info(
            f"Should{' ' if should_run else ' not '}run from scan {self} by {self.started_worker.id}"
        )
        return should_run

    def sync_states(self, params: Params) -> None:
        """Sync or drop present object states to clean or later skip tests from previous runs."""
        node_params = self.params.copy()
        for key in list(node_params.keys()):
            if key.startswith("get_state") or key.startswith("unset_state"):
                del node_params[key]

        # the sync cleanup will be performed if at least one selected object has a cleanable state
        should_clean = False
        for test_object in self.objects:
            object_params = test_object.object_typed_params(self.params)
            object_state = object_params.get("set_state")
            if not object_state:
                continue

            # avoid running any test unless the user really requires cleanup or setup is reusable
            unset_policy = object_params.get("unset_mode", "ri")
            if unset_policy[0] not in ["f", "r"]:
                continue
            # avoid running any test for unselected vms
            if test_object.key == "nets":
                logging.warning("Net state cleanup is not supported")
                continue
            # the object state has to be defined to reach this stage
            if object_state == "install" and test_object.is_permanent():
                should_clean = False
                break
            vm_name = (
                test_object.suffix
                if test_object.key == "vms"
                else test_object.composites[0].suffix
            )
            # TODO: is this needed?
            from .. import params_parser as param

            if vm_name in params.get("vms", param.all_objects("vms")):
                should_clean = True
            else:
                continue

            # TODO: cannot remove ad-hoc root states, is this even needed?
            if test_object.key == "vms":
                vm_params = object_params
                node_params["images_" + vm_name] = vm_params["images"]
                for image_name in vm_params.objects("images"):
                    image_params = vm_params.object_params(image_name)
                    node_params[f"image_name_{image_name}_{vm_name}"] = image_params[
                        "image_name"
                    ]
                    node_params[f"image_format_{image_name}_{vm_name}"] = image_params[
                        "image_format"
                    ]
                    if image_params.get_boolean("create_image", False):
                        node_params[f"remove_image_{image_name}_{vm_name}"] = "yes"
                        node_params["skip_image_processing"] = "no"

            suffixes = f"_{test_object.key}_{test_object.suffix}"
            suffixes += f"_{vm_name}" if test_object.key == "images" else ""
            # spread the state setup for the given test object
            location = ":" + object_params["shared_pool"]
            if unset_policy[0] == "f":
                # reverse the state setup for the given test object
                # NOTE: we are forcing the unset_mode to be the one defined for the test node because
                # the unset manual step behaves differently now (all this extra complexity starts from
                # the fact that it has different default value which is noninvasive
                node_params.update(
                    {
                        f"unset_state{suffixes}": object_state,
                        f"unset_location{suffixes}": location,
                        f"unset_mode{suffixes}": object_params.get("unset_mode", "ri"),
                        f"pool_scope": "own",
                    }
                )
                do = "unset"
                logging.info(f"Need to clean up {self} by {self.started_worker.id}")
            else:
                # spread the state setup for the given test object
                if node_params.get("pool_filter", "reuse") in ["reuse", "block"]:
                    logging.info(
                        f"No need to sync {self} from {self.started_worker.id}"
                    )
                    should_clean = False
                    break
                else:
                    # TODO: actual state copy support is almost fully lacking at present
                    # and the sync operation by itself cannot guarantee equalized setup
                    if node_params.get("pool_filter", "reuse") != "copy":
                        raise ValueError(
                            "Pool filtering can only be one of: reuse, copy, block"
                        )
                    logging.info(
                        f"Need to sync {self} from {location.join(',')} to {self.started_worker.id}"
                    )
                node_params.update(
                    {
                        f"get_state{suffixes}": object_state,
                        f"get_location{suffixes}": location,
                    }
                )
                sync_scopes = set(
                    object_params.get_list("pool_scope", ["swarm", "cluster", "shared"])
                )
                sync_scopes.remove("own")
                node_params[f"pool_scope{suffixes}"] = " ".join(sync_scopes)
                do = "get"
            # TODO: unfortunately we need env object with pre-processed vms in order
            # to provide ad-hoc root vm states so we use the current advantage that
            # all vm state backends can check for states without a vm boot (root)
            if test_object.key == "vms":
                node_params[f"use_env_{test_object.key}_{test_object.suffix}"] = "no"

        if should_clean:
            action = "Cleaning up" if unset_policy[0] == "f" else "Syncing"
            logging.info(f"{action} {self} for {self.started_worker.id}")
            session = self.started_worker.get_session()
            control_path = os.path.join(
                self.params["suite_path"], "controls", "pre_state.control"
            )
            mod_control_path = door.set_subcontrol_parameter(control_path, "action", do)
            mod_control_path = door.set_subcontrol_parameter_dict(
                mod_control_path, "params", node_params
            )
            try:
                door.run_subcontrol(session, mod_control_path)
            except ShellCmdError as error:
                logging.warning(
                    f"{action} {self} for {self.started_worker.id} could not be completed "
                    f"due to control file error: {error}"
                )
        else:
            logging.info(
                f"No need to clean up or sync {self} for {self.started_worker.id}"
            )

    def validate(self) -> None:
        """Validate the test node for sane attribute-parameter correspondence."""
        logging.info(f"Validating {self}")

        if self in self.setup_nodes or self in self.cleanup_nodes:
            raise ValueError("Detected reflexive dependency of %s to itself" % self)

        if self.is_flat():
            return

        param_nets = self.params.objects("nets")
        attr_nets = list(o.suffix for o in self.objects if o.key == "nets")
        if len(attr_nets) > 1 or len(param_nets) > 1:
            raise AssertionError(
                f"Test node {self} can have only one net ({attr_nets}/{param_nets}"
            )
        param_net_name, attr_net_name = attr_nets[0], param_nets[0]
        if self.objects and self.objects[0].suffix != attr_net_name:
            raise AssertionError(
                f"The net {attr_net_name} must be the first node object {self.objects[0]}"
            )
        if param_net_name != attr_net_name:
            raise AssertionError(
                f"Parametric and attribute nets differ {param_net_name} != {attr_net_name}"
            )

        param_vms = set(self.params.objects("vms"))
        attr_vms = set(o.suffix for o in self.objects if o.key == "vms")
        if len(param_vms - attr_vms) > 0:
            raise ValueError(
                "Additional parametric objects %s not in %s" % (param_vms, attr_vms)
            )
        if len(attr_vms - param_vms) > 0:
            raise ValueError(
                "Missing parametric objects %s from %s" % (param_vms, attr_vms)
            )

        # TODO: images can currently be ad-hoc during run and thus cannot be validated

        for node in self.setup_nodes:
            if node.is_flat():
                continue
            object_set = self.setup_nodes[node]
            spurious_objects = object_set - set(self.objects)
            if len(spurious_objects) > 0:
                raise ValueError(
                    f"Detected spurious objects {spurious_objects} for dependency {node}"
                )
            for dependency_object in object_set:
                object_params = dependency_object.object_typed_params(node.params)
                object_state = object_params.get("set_state")
                if not object_state:
                    raise ValueError(
                        f"Detected stateless dependency via {dependency_object} of {self}"
                    )
                object_params = dependency_object.object_typed_params(self.params)
                dependency_state = object_params["get_state"]
                # cloned nodes don't have an explicit get_state parameter for the object
                if dependency_state == "0root":
                    continue
                if object_state != dependency_state:
                    raise ValueError(
                        f"Detected incompatible dependency {object_state}!={dependency_state} via {dependency_object} of {self}"
                    )
