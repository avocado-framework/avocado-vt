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
# Copyright 2013-2026 Intranet AG and contributors
# Author: Plamen Dimitrov <plamen.dimitrov@intra2net.com>

r"""
Utility to manage all needed virtual machines.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
This utility can be used by any host control to manage one or more virtual machines.
It in turn uses some other host utilities.

Use the tag argument to add more details to generated test variant name in
case you are running any of the manual step functions here more than once.

**IMPORTANT**: If you don't want to perform the given setup with all virtual machines,
defined by your parameters then just overwrite the parameter `vms` as a space
separated list of the selected virtual machine names. The setup then is going to be
performed only on those machines and not on all. Example is 'vms = vm1 vm2 vm3\n'
to create only vm1 and vm3 add to the overwrite string 'vms = vm1 vm3\n' in order
to overwrite the vms parameter. Of course you can do this with any parameter
to manage other aspects of the virtual environment setup process.

INTERFACE
------------------------------------------------------

"""

import sys
import os
import re
from typing import Generator
from typing import Any, Callable
import logging as log

import contextlib
import importlib
import asyncio
from collections import namedtuple

from avocado.core import job
from avocado.core import data_dir
from avocado.core.suite import TestSuite
from avocado.core.settings import settings
from avocado.core.output import LOG_UI
from virttest.utils_params import Params

from . import params_parser as param
from .cartgraph import TestGraph, TestNode
from .plugins.runner import TestRunner

logging = log.getLogger("avocado.job." + __name__)


#: list of all available manual steps or simply semi-automation tools
__all__ = [
    "noop",
    "unittest",
    "update",
    "run",
    "list",
    "start",
    "stop",
    "boot",
    "download",
    "control",
    "upload",
    "shutdown",
    "check",
    "pop",
    "push",
    "get",
    "set",
    "unset",
    "collect",
    "create",
    "clean",
]


def load_addons_tools() -> None:
    """Load all custom manual steps defined in the test suite tools folder."""
    suite_path = settings.as_dict().get("vt.common.suite_path")
    tools_path = os.path.join(suite_path, "tools")
    sys.path.append(tools_path)
    # we have no other choice to avoid loading at intertest import
    global __all__
    for tool in os.listdir(tools_path):
        if tool.endswith(".py") and not tool.endswith("_unittest.py"):
            module_name = tool.replace(".py", "")
            logging.debug("Loading tools in %s", module_name)
            try:
                module = importlib.import_module(module_name)
            except Exception as error:
                logging.error("Could not load tool %s: %s", module_name, error)
                continue

            if "__all__" not in module.__dict__:
                logging.warning(
                    "Detected tool module doesn't contain publicly defined tools"
                )
                continue

            names = module.__dict__["__all__"]
            globals().update({k: getattr(module, k) for k in names})
            __all__ += module.__all__

            logging.info("Loaded custom tools: %s", ", ".join(module.__all__))


@contextlib.contextmanager
def new_job(config: dict[str, Any]) -> Generator[Params, None, None]:
    """
    Produce a new job object and thus a job.

    :param config: command line arguments
    """
    suite = TestSuite("suite", {}, tests=[], job_config=config)
    with job.Job(config, [suite]) as job_instance:

        loader, runner = config["graph"].l, config["graph"].r
        loader.logdir = job_instance.logdir
        runner.job = job_instance

        yield job_instance


def with_cartesian_graph(fn: Callable[[Any], Any]) -> Callable[[Any], Any]:
    """
    Run a given function with a job-enabled loader-runner hybrid graph.

    :param fn: function to run with a job
    :returns: same function with job resource included
    """

    def wrapper(config: dict[str, Any], tag: str = "") -> int:
        loader = TestGraph
        runner = TestRunner()
        CartesianGraph = namedtuple("CartesianGraph", "l r")
        config["graph"] = CartesianGraph(l=loader, r=runner)

        with new_job(config) as job:
            fn(config, tag=tag)

            config["graph"] = None
            return 0 if runner.all_results_ok() else 1

    return wrapper


############################################################
# Main manual user steps
############################################################


def noop(config: dict[str, Any], tag: str = "") -> None:
    """
    Empty setup step to invoke plugin without performing anything.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    LOG_UI.info("NOOP")


def unittest(config: dict[str, Any], tag: str = "") -> None:
    """
    Perform self testing for sanity and test result validation.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    import unittest

    util_unittests = unittest.TestSuite()
    util_testrunner = unittest.TextTestRunner(stream=sys.stdout, verbosity=2)

    root_path = settings.as_dict().get("vt.common.suite_path")
    subtests_filter = config["tests_params"].get("ut_filter", "*_unittest.py")

    subtests_path = os.path.join(root_path, "utils")
    subtests_suite = unittest.defaultTestLoader.discover(
        subtests_path, pattern=subtests_filter, top_level_dir=subtests_path
    )
    util_unittests.addTest(subtests_suite)

    subtests_path = os.path.join(root_path, "tools")
    subtests_suite = unittest.defaultTestLoader.discover(
        subtests_path, pattern=subtests_filter, top_level_dir=subtests_path
    )
    util_unittests.addTest(subtests_suite)

    util_testrunner.run(util_unittests)


@with_cartesian_graph
def update(config: dict[str, Any], tag: str = "") -> None:
    """
    Update all states.

    Run all tests from the state defined as ``from_state=<state>``
    to the state defined as ``to_state=<state>``.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    The state can be achieved all the way from the test object creation. The
    performed setup depends entirely on the state's dependencies which can
    be completely different than the regular create->install->deploy path.
    Thus, a change in a state can be reflected in all the dependent states.

    Only singleton test setup is supported within the update setup path since
    we cannot guarantee other setup involved vms exist.

    ..note:: Both the ``from_state`` and ``to_state`` are included in the
        updated path with default behavior also updating the install state,
        i.e. fully recreating the vm.
    """
    l, r = config["graph"].l, config["graph"].r
    selected_vms = sorted(config["vm_strs"].keys())
    LOG_UI.info(
        "Update state cache for %s (%s)",
        ", ".join(selected_vms),
        os.path.basename(r.job.logdir),
    )

    graph = TestGraph()
    graph.new_workers(l.parse_workers(config["param_dict"]))
    for vm_name in selected_vms:
        new_vms = TestGraph.parse_composite_objects(
            vm_name, "vms", config["vm_strs"][vm_name]
        )
        graph.new_objects(new_vms)
        for new_vm in new_vms:
            graph.new_objects(TestGraph.parse_components_for_object(new_vm, "vms"))

    # parse individual net only for the current vm
    for i, worker in enumerate(graph.workers.values()):
        setup_dict = config["param_dict"].copy()
        setup_dict["nets"] = worker.id
        # NOTE: this makes sure that any present states are overwritten and no recreated
        # states are removed, aborting in any other case
        setup_dict.update({"get_mode": "ra", "set_mode": "ff", "unset_mode": "fi"})
        setup_str = config["tests_str"]

        try:
            clean_graph = l.parse_object_trees(
                worker=worker,
                restriction=setup_str,
                prefix=f"{tag}m{i + 1}",
                object_restrs=config["available_vms"],
                params=setup_dict,
                verbose=False,
                with_shared_root=False,
            )
        except param.EmptyCartesianProduct as error:
            logging.warning(error)
            continue
        # flagging children will require connected graphs while flagging intersection can also handle disconnected ones
        clean_graph.flag_intersection(
            clean_graph, flag_type="run", flag=lambda self, slot: False
        )
        clean_graph.flag_intersection(
            clean_graph, flag_type="clean", flag=lambda self, slot: False
        )

        for i, vm_name in enumerate(selected_vms):
            setup_dict["main_vm"] = vm_name
            setup_dict["vms"] = vm_name
            vm_params = config["vms_params"].object_params(vm_name)
            from_state = vm_params.get("from_state", "install")
            to_state = vm_params.get("to_state", "customize")
            logging.info("Updating state '%s' of %s", to_state, vm_name)

            logging.info(
                f"Flagging for removing by {worker.id} all old {vm_name} states "
                f"depending on the updated '{to_state}'"
            )
            flag_state = "" if to_state == "install" else to_state
            vm_objects = [
                o for o in clean_graph.get_objects(param_val=vm_name) if o.key == "vms"
            ]
            for vm_object in vm_objects:
                try:
                    clean_graph.flag_children(
                        flag_state,
                        vm_name,
                        vm_object.component_form + r".*" + worker.id,
                        flag_type="clean",
                        flag=lambda self, slot: len(self.cloned_nodes) == 0,
                        skip_parents=True,
                    )
                except AssertionError as error:
                    logging.error(error)
                    raise ValueError(
                        f"Could not identify a test node from {vm_name}'s to_state='{flag_state}', "
                        f"is it compatible with the default or specified remove set restriction?"
                    )

            logging.info(
                f"Flagging for updating by {worker.id} all {vm_name} states "
                f"between and including '{from_state}' and '{to_state}'"
            )
            if to_state == "install":
                run_graph = l.parse_object_trees(
                    worker=worker,
                    restriction=param.re_str("all..customize"),
                    prefix=tag,
                    object_restrs={vm_name: config["vm_strs"][vm_name]},
                    params=setup_dict,
                    verbose=False,
                )
                install_nodes = run_graph.get_nodes_by_name("all.original")
                # produce a terminal node only run graph
                run_graph = TestGraph()
                run_graph.new_objects(clean_graph.objects)
                run_graph.new_nodes(install_nodes)
            else:
                run_graph = l.parse_object_trees(
                    worker=worker,
                    restriction=param.re_str("all.." + to_state),
                    prefix=tag,
                    object_restrs={vm_name: config["vm_strs"][vm_name]},
                    params=setup_dict,
                    verbose=False,
                )
            clean_graph.flag_intersection(
                run_graph,
                flag_type="run",
                flag=lambda self, slot: not self.is_finished(slot)
                or self.should_rerun(slot),
                skip_shared_root=True,
            )

            if from_state != "install":
                logging.info(
                    f"Flagging for preserving by {worker.id} all {vm_name} states "
                    f"before the updated '{from_state}'"
                )
                skip_graph = l.parse_object_trees(
                    worker=worker,
                    restriction=param.re_str("all.." + from_state),
                    prefix=tag,
                    object_restrs={vm_name: config["vm_strs"][vm_name]},
                    params=setup_dict,
                    verbose=False,
                )
                clean_graph.flag_intersection(
                    skip_graph, flag_type="run", flag=lambda self, slot: False
                )
                for vm_object in vm_objects:
                    try:
                        clean_graph.flag_children(
                            from_state,
                            vm_name,
                            vm_object.component_form + r".*" + worker.id,
                            flag_type="run",
                            flag=lambda self, slot: not self.is_finished(slot)
                            or self.should_rerun(slot),
                            skip_children=True,
                        )
                    except AssertionError as error:
                        logging.error(error)
                        raise ValueError(
                            f"Could not identify a test node from {vm_name}'s from_state='{from_state}', "
                            f"is it compatible with the default or specified remove set restriction?"
                        )

        graph.new_objects([o for o in clean_graph.objects if o.key == "nets"])
        graph.new_nodes(clean_graph.nodes)

    logging.info(f"Bridging worker subgraphs across workers")
    for node1 in graph.nodes:
        for node2 in graph.nodes:
            if node1 == node2:
                continue
            if node1.bridged_form == node2.bridged_form:
                if node1.id == node2.id:
                    raise ValueError
                node1.bridge_with_node(node2)

    graph.parse_shared_root_from_object_roots(config["param_dict"])
    r.run_workers(graph, config["param_dict"])
    LOG_UI.info("Finished updating cache")


def run(config: dict[str, Any], tag: str = "") -> int:
    """
    Run a set of tests without any automated setup.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    This is equivalent to but more powerful than the runner plugin.
    """
    # NOTE: each run expects already incremented count in the beginning but this prefix
    # is preferential to setup chains with a single "run" step since this is usually the case
    config["prefix"] = (
        tag + "n" if len(re.findall("run", config["vms_params"]["setup"])) > 1 else ""
    )

    loader = TestGraph
    runner = TestRunner()
    CartesianGraph = namedtuple("CartesianGraph", "l r")
    config["graph"] = CartesianGraph(l=loader, r=runner)

    # essentially we imitate the auto plugin to make the tool plugin a superset
    with new_job(config) as job:

        params, restriction = config["param_dict"], config["tests_str"]
        runnables = TestGraph.parse_flat_nodes(restriction, params)
        job.test_suites[0].tests = runnables

        retcode = job.run()

        config["graph"] = None
        return retcode


def list(config: dict[str, Any], tag: str = "") -> None:
    """
    List a set of tests from the command line.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    This is equivalent to but more powerful than the loader plugin.
    """
    loader = TestGraph
    runner = TestRunner()
    CartesianGraph = namedtuple("CartesianGraph", "l r")
    config["graph"] = CartesianGraph(l=loader, r=runner)

    with new_job(config) as job:

        prefix = (
            tag + "l"
            if len(re.findall("run", config["vms_params"]["setup"])) > 1
            else ""
        )
        # provide the logdir in advance in order to visualize parsed graph there
        TestGraph.logdir = runner.job.logdir
        setup_dict = config["param_dict"].copy()
        # listing can only be done in serial mode
        setup_dict["nets"] = config["param_dict"].get("nets", "net0")
        graph = loader.parse_object_trees(
            restriction=config["tests_str"],
            prefix=prefix,
            object_restrs=config["vm_strs"],
            params=setup_dict,
            verbose=True,
        )
        graph.visualize(job.logdir)


############################################################
# NET management manual user steps
############################################################


@with_cartesian_graph
def start(config: dict[str, Any], tag: str = "") -> None:
    """
    Start all given workers.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    l, r = config["graph"].l, config["graph"].r
    selected_nets = config["param_dict"]["nets"].split(" ")
    LOG_UI.info(
        "Starting worker nets %s (%s)",
        ", ".join(selected_nets),
        os.path.basename(r.job.logdir),
    )

    workers = l.parse_workers(config["param_dict"])
    for worker in workers:
        worker.start()


@with_cartesian_graph
def stop(config: dict[str, Any], tag: str = "") -> None:
    """
    Stop all given workers.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    l, r = config["graph"].l, config["graph"].r
    selected_nets = config["param_dict"]["nets"].split(" ")
    LOG_UI.info(
        "Stopping worker nets %s (%s)",
        ", ".join(selected_nets),
        os.path.basename(r.job.logdir),
    )

    workers = l.parse_workers(config["param_dict"])
    for worker in workers:
        worker.stop()


############################################################
# VM management manual user steps
############################################################


@with_cartesian_graph
def boot(config: dict[str, Any], tag: str = "") -> None:
    """
    Boot all given vms.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    The boot test always takes care of any other vms so we can do it all in one test
    which is a bit of a hack but is much faster than the standard per-vm handling.
    """
    _parse_one_node_for_all_objects_per_worker(
        config, tag, ("Booting", "start", "boot", "Boot")
    )


@with_cartesian_graph
def download(config: dict[str, Any], tag: str = "") -> None:
    """
    Download a set of files from the given vms.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    The set of files is specified using a "files" parameter.

    The download test always takes care of any other vms so we can do it all in one test
    which is a bit of a hack but is much faster than the standard per-vm handling.
    """
    _parse_one_node_for_all_objects_per_worker(
        config, tag, ("Downloading from", "download", "download", "Download")
    )


@with_cartesian_graph
def control(config: dict[str, Any], tag: str = "") -> None:
    """
    Run a control file on the given vms.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    The control file is specified using a "control_file" parameter.
    """
    _parse_one_node_for_all_objects_per_worker(
        config, tag, ("Running on", "run", "run", "Run")
    )


@with_cartesian_graph
def upload(config: dict[str, Any], tag: str = "") -> None:
    """
    Upload a set of files to the given vms.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    The set of files is specified using a `files` parameter.

    The upload test always takes care of any other vms so we can do it all in one test
    which is a bit of a hack but is much faster than the standard per-vm handling.
    """
    _parse_one_node_for_all_objects_per_worker(
        config, tag, ("Uploading to", "upload", "upload", "Upload")
    )


@with_cartesian_graph
def shutdown(config: dict[str, Any], tag: str = "") -> None:
    """
    Shutdown gracefully or kill living vms.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    The shutdown test always takes care of any other vms so we can do it all in one test
    which is a bit of a hack but is much faster than the standard per-vm handling.
    """
    _parse_one_node_for_all_objects_per_worker(
        config, tag, ("Shutting down", "stop", "shutdown", "Shutdown")
    )


############################################################
# State manipulation manual user steps
############################################################


@with_cartesian_graph
def check(config: dict[str, Any], tag: str = "") -> None:
    """
    Check whether a given state (setup snapshot) exists.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    operation = "check"
    _parse_and_iterate_for_objects_and_workers(
        config,
        tag,
        {
            "vm_action": operation,
            "skip_image_processing": "yes",
        },
        "state " + operation,
    )


@with_cartesian_graph
def pop(config: dict[str, Any], tag: str = "") -> None:
    """
    Get to a state/snapshot disregarding the current changes loosing the it afterwards.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    operation = "pop"
    _parse_and_iterate_for_objects_and_workers(
        config,
        tag,
        {
            "vm_action": operation,
            "skip_image_processing": "yes",
        },
        "state " + operation,
    )


@with_cartesian_graph
def push(config: dict[str, Any], tag: str = "") -> None:
    """
    Use as wrapper for setting state/snapshot, same as :py:func:`set`.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    operation = "push"
    _parse_and_iterate_for_objects_and_workers(
        config,
        tag,
        {
            "vm_action": operation,
            "skip_image_processing": "yes",
        },
        "state " + operation,
    )


@with_cartesian_graph
def get(config: dict[str, Any], tag: str = "") -> None:
    """
    Get to a state/snapshot disregarding the current changes.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    This method could be implemented in identical way to the push/pop
    methods but we use different approach for illustration.
    """
    operation = "get"
    _parse_and_iterate_for_objects_and_workers(
        config,
        tag,
        {
            "vm_action": operation,
            "skip_image_processing": "yes",
        },
        "state " + operation,
    )


@with_cartesian_graph
def set(config: dict[str, Any], tag: str = "") -> None:
    """
    Create a new state/snapshot from the current state/snapshot.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    This method could be implemented in identical way to the push/pop
    methods but we use different approach for illustration.
    """
    operation = "set"
    _parse_and_iterate_for_objects_and_workers(
        config,
        tag,
        {
            "vm_action": operation,
            "skip_image_processing": "yes",
        },
        "state " + operation,
    )


@with_cartesian_graph
def unset(config: dict[str, Any], tag: str = "") -> None:
    """
    Remove a state/snapshot.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    This method could be implemented in identical way to the push/pop
    methods but we use different approach for illustration.
    """
    operation = "unset"
    op_mode = "unset_mode"

    l, r = config["graph"].l, config["graph"].r
    setup_dict = config["param_dict"].copy()
    flat_net = l.parse_net_from_object_restrs("net1", config["vm_strs"])
    for test_object in l.parse_components_for_object(
        flat_net, "nets", params=config["param_dict"], unflatten=True
    ):
        if test_object.key != "vms":
            continue
        vm = test_object

        # since the default unset_mode is passive (ri) we need a better
        # default value for that case but still modifiable by the user
        vm_op_mode = op_mode + "_" + vm.suffix
        state_mode = vm_op_mode if vm_op_mode in setup_dict else op_mode
        if state_mode not in setup_dict:
            setup_dict[vm_op_mode] = "fi"

    setup_dict.update({"vm_action": operation, "skip_image_processing": "yes"})

    _parse_and_iterate_for_objects_and_workers(
        config,
        tag,
        setup_dict,
        "state " + operation,
    )


def collect(config: dict[str, Any], tag: str = "") -> None:
    """
    Get a new test object (vm, root state) from a pool.

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run

    ..todo:: With later refactoring of the root check implicitly getting a
        pool rool state, we can refine the parameters here.
    """
    _reuse_tool_with_param_dict(
        config,
        tag,
        {
            "get_state_images": "root",
            "get_mode_images": "ii",
            # don't touch root states in any way
            "check_mode_images": "rr",
            # this manual tool is compatible only with pool
            "pool_scope": "swarm cluster shared",
        },
        get,
    )


def create(config: dict[str, Any], tag: str = "") -> None:
    """
    Create a new test object (vm, root state).

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    _reuse_tool_with_param_dict(
        config,
        tag,
        {
            "set_state_images": "root",
            "set_mode_images": "af",
            # don't touch root states in any way
            "check_mode_images": "rr",
            # this manual tool is not compatible with pool
            "pool_scope": "own",
        },
        set,
    )


def clean(config: dict[str, Any], tag: str = "") -> None:
    """
    Remove a test object (vm, root state).

    :param config: command line arguments and run configuration
    :param tag: extra name identifier for the test to be run
    """
    _reuse_tool_with_param_dict(
        config,
        tag,
        {
            "unset_state_images": "root",
            "unset_mode_images": "fa",
            # make use of off switch if vm is running
            "check_mode_images": "rf",
            # this manual tool is not compatible with pool
            "pool_scope": "own",
        },
        unset,
    )


############################################################
# Private templates reused by all tools above
############################################################


def _parse_one_node_for_all_objects_per_worker(
    config: dict[str, Any], tag: str, verb: tuple[str, str, str, str]
) -> None:
    """
    Parse a single node for all test objects and a given worker.

    :param verb: verb forms in a tuple (gerund form, variant, test name, present)

    The rest of the arguments match the public functions.

    ..todo:: Currently only vm objects are supported.
    """
    l, r = config["graph"].l, config["graph"].r
    selected_vms = sorted(config["vm_strs"].keys())
    LOG_UI.info(
        "%s virtual machines %s (%s)",
        verb[0],
        ", ".join(selected_vms),
        os.path.basename(r.job.logdir),
    )

    graph = TestGraph()
    graph.new_workers(l.parse_workers(config["param_dict"]))
    for vm_name in selected_vms:
        graph.new_objects(
            TestGraph.parse_composite_objects(
                vm_name, "vms", config["vm_strs"][vm_name]
            )
        )

    vms = " ".join(selected_vms)
    setup_dict = config["param_dict"].copy()
    setup_dict.update({"vms": vms, "main_vm": selected_vms[0]})
    for test_worker in graph.workers.values():
        test_worker.net.update_restrs(config["vm_strs"])
        nodes = graph.parse_composite_nodes(
            "all..internal.stateless.manage.%s" % verb[1],
            test_worker.net,
            tag,
            params=setup_dict,
        )
        if len(nodes) == 0:
            logging.warning(f"Skipped incompatible worker {test_worker.id}")
            continue
        elif len(nodes) > 1:
            raise RuntimeError(
                f"There must be exactly one {verb[2]} test variant "
                f"for {test_worker.id} from {nodes}"
            )
        graph.new_nodes(nodes[0])

    graph.parse_shared_root_from_object_roots(config["param_dict"])
    graph.flag_children(
        flag_type="run",
        flag=lambda self, slot: not self.is_shared_root()
        and slot not in self.shared_finished_workers,
    )
    r.run_workers(graph, config["param_dict"])
    LOG_UI.info("%s complete", verb[3])


def _parse_and_iterate_for_objects_and_workers(
    config: dict[str, Any], tag: str, param_dict: dict[str, str], operation: str
) -> None:
    """
    Parse a single node for each test object and test worker.

    :param param_dict: additional parameters to overwrite the previous dictionary with
    :param operation: operation description to use when logging

    The rest of the arguments match the public functions.

    ..todo:: Currently only vm objects are supported.
    """
    l, r = config["graph"].l, config["graph"].r
    selected_vms = sorted(config["vm_strs"].keys())
    LOG_UI.info(
        "Starting %s for %s with job %s and params:\n%s",
        operation,
        ", ".join(selected_vms),
        os.path.basename(r.job.logdir),
        param.ParsedDict(config["param_dict"]).reportable_form().rstrip("\n"),
    )

    graph = TestGraph()
    graph.new_workers(l.parse_workers(config["param_dict"]))
    for vm_name in selected_vms:
        graph.new_objects(
            TestGraph.parse_composite_objects(
                vm_name, "vms", config["vm_strs"][vm_name]
            )
        )

    for test_worker in graph.workers.values():
        test_worker.net.update_restrs(config["vm_strs"])
        for test_object in [o for o in graph.objects if o.key == "vms"]:
            setup_dict = config["param_dict"].copy()
            setup_dict.update(param_dict)
            setup_dict["vms"] = test_object.suffix

            nodes = graph.parse_composite_nodes(
                f"all..internal.stateful.{operation}",
                test_worker.net,
                tag,
                params=setup_dict,
            )
            if len(nodes) == 0:
                logging.warning(f"Skipped incompatible worker {test_worker.id}")
                continue
            graph.new_nodes(nodes)

            # TODO: traversal relies explicitly on object_suffix which only indicates
            # where a parent node was parsed from, i.e. which test object of the child node
            for node in nodes:
                node.params["object_suffix"] = test_object.long_suffix

    graph.parse_shared_root_from_object_roots(config["param_dict"])
    # as each worker's traversal will be restricted only to its nodes the run policy is also simpler
    graph.flag_children(
        flag_type="run",
        flag=lambda self, slot: not self.is_shared_root()
        and slot not in self.shared_finished_workers,
    )
    r.run_workers(graph, config["param_dict"])
    LOG_UI.info("Finished %s", operation)


def _reuse_tool_with_param_dict(
    config: dict[str, Any],
    tag: str,
    param_dict: dict[str, str],
    tool: Callable[[Any], Any],
) -> None:
    """
    Reuse a previously defined tool with temporary updated parameter dictionary.

    :param param_dict: additional parameters to overwrite the previous dictionary with
    :param tool: tool to reuse

    The rest of the arguments match the public functions.
    """
    setup_dict = config["param_dict"].copy()
    config["param_dict"].update(param_dict)
    tool(config, tag=tag)
    config["param_dict"] = setup_dict
