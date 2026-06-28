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

"""
Specialized test runner for the plugin.

SUMMARY
------------------------------------------------------

Copyright: Intra2net AG

INTERFACE
------------------------------------------------------

"""

from __future__ import annotations

import os
import re
import time
import json
import logging as log

import asyncio

log.getLogger("asyncio").parent = log.getLogger("avocado.job")

from avocado.core.job import Job
from avocado.core.nrunner.task import TASK_DEFAULT_CATEGORY, Task
from avocado.core.messages import MessageHandler
from avocado.core.plugin_interfaces import SuiteRunner as RunnerInterface
from avocado.core.status.repo import StatusRepo
from avocado.core.status.server import StatusServer
from avocado.core.suite import TestSuite
from avocado.core.teststatus import STATUSES_MAPPING
from avocado.core.task.runtime import RuntimeTask, PreRuntimeTask, PostRuntimeTask
from avocado.core.task.statemachine import TaskStateMachine, Worker
from avocado.core.dispatcher import SpawnerDispatcher
from virttest.utils_params import Params
from virttest.cartgraph import TestGraph, TestWorker, TestNode

logging = log.getLogger("avocado.job." + __name__)


class TestRunner(RunnerInterface):
    """Test runner for Cartesian graph traversal."""

    name = "traverser"
    description = "Runs tests through a Cartesian graph traversal"

    def __init__(self) -> None:
        """Construct minimal attributes for the Cartesian runner."""
        self.tasks = {}

        self.status_repo = None
        self.status_server = None
        self.previous_results = []

        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)

    """results functionality"""

    async def _update_status(self) -> None:
        message_handler = MessageHandler()
        while True:
            try:
                _, task_id, _, index = self.status_repo.status_journal_summary_pop()

            except IndexError:
                await asyncio.sleep(0.05)
                continue

            message = self.status_repo.get_task_data(task_id, index)
            task = self.tasks.get(task_id)
            message_handler.process_message(message, task, self.job)

    def all_results_ok(self) -> bool:
        """
        Evaluate if all tests run under this runner have an ok status.

        :returns: whether all tests ended with acceptable status

        ..todo:: There might be repeated tests here that have eventually
            passed so we might need to return an overall "pass" status.
        """
        shared_status = True
        for test in self.job.result.tests:
            shared_status &= any(
                STATUSES_MAPPING[t["status"]]
                for t in self.job.result.tests
                if t["name"].name == test["name"].name
            )
            if not shared_status:
                return False
        return True

    def results_from_previous_jobs(self) -> None:
        """Parse results from previous job to add to all traversed graph nodes."""
        params = self.job.config["param_dict"]
        # TODO: we could really benefit from using an appropriate params object here
        replay_jobs = params.get("replay", "").split(" ")
        for replay_job in replay_jobs:
            if not replay_job:
                continue
            replay_dir = self.job.config.get("datadir.paths.logs_dir", ".")
            replay_results = os.path.join(replay_dir, replay_job, "results.json")
            if not os.path.isfile(replay_results):
                raise RuntimeError(
                    "Cannot find replay job results file %s" % replay_results
                )
            with open(replay_results) as json_file:
                logging.info(f"Parsing previous results to replay {replay_results}")
                data = json.load(json_file)
                if "tests" not in data:
                    raise RuntimeError(
                        f"Cannot find tests to replay against in {replay_results}"
                    )
                for test_details in data["tests"]:
                    logging.info(f"Updating with previous test results {test_details}")
                    self.previous_results += [test_details]

    """running functionality"""

    async def run_test_task(self, node: TestNode) -> None:
        """
        Run a test instance inside a subprocess.

        :param node: test node to run
        """
        host = node.params["nets_host"] or "process"
        gateway = node.params["nets_gateway"] or "localhost"
        spawner = node.params["nets_spawner"]
        logging.debug(
            f"Running {node.id} on {gateway}/{host} using {spawner} isolation"
        )

        if node.started_worker is None:
            raise RuntimeError(f"No worker is running {node}")
        if node.started_worker.spawner is None:
            raise RuntimeError(f"Worker {node.started_worker} cannot spawn tasks")
        if not self.status_repo:
            self.status_repo = StatusRepo(self.job.unique_id)
            self.status_server = StatusServer(
                self.job.config.get("run.status_server_listen"), self.status_repo
            )
            asyncio.ensure_future(self.status_server.serve_forever())
            # TODO: this needs more customization
            asyncio.ensure_future(self._update_status())

        status_server_uri = self.job.config.get("run.status_server_uri")
        node.regenerate_vt_parameters()
        raw_task = Task(
            node,
            node.id_test,
            [status_server_uri],
            category=TASK_DEFAULT_CATEGORY,
            job_id=self.job.unique_id,
        )
        raw_task.runnable.output_dir = os.path.join(
            self.job.test_results_path, raw_task.identifier.str_filesystem
        )
        task = RuntimeTask(raw_task)
        config = (
            self.test_suite.config if hasattr(self, "test_suite") else self.job.config
        )
        pre_tasks = PreRuntimeTask.get_tasks_from_test_task(
            task,
            1,
            self.job.test_results_path,
            None,
            status_server_uri,
            self.job.unique_id,
            config,
        )
        post_tasks = PostRuntimeTask.get_tasks_from_test_task(
            task,
            1,
            self.job.test_results_path,
            None,
            status_server_uri,
            self.job.unique_id,
            config,
        )
        tasks = [*pre_tasks, task, *post_tasks]
        for task in tasks:
            if spawner == "lxc":
                task.spawner_handle = host
            elif spawner == "remote":
                task.spawner_handle = node.started_worker.get_session()
                while True:
                    io_pressure = task.spawner_handle.cmd(
                        "cat /sys/fs/cgroup/io.pressure | grep full"
                    )
                    io_pressure_stat = float(
                        re.search(r"avg60=(\d+.\d+)", io_pressure).group(1)
                    )
                    if io_pressure_stat >= 10.0:
                        logging.warning(
                            f"Waiting 60s due to high IO 60s window pressure: {io_pressure}"
                        )
                        time.sleep(60)
                    else:
                        break

        self.tasks.update(
            {
                str(runtime_task.task.identifier): runtime_task.task
                for runtime_task in tasks
            }
        )

        # TODO: use a single state machine for all test nodes when we are able
        # to at least add requested tasks to it safely (using its locks)
        await Worker(
            state_machine=TaskStateMachine(tasks, self.status_repo),
            spawner=node.started_worker.spawner,
            max_running=1,
            task_timeout=self.job.config.get("task.timeout.running"),
        ).run()

    async def run_test_node(self, node: TestNode, status_timeout: int = 10) -> bool:
        """
        Run a test node with a potential retry prefix modification.

        :param node: test node to run
        :returns: whether the test succeeded as a simple boolean test result status
        :raises: :py:class:`AssertionError` if the ran test node contains no objects
        """
        if node.is_flat():
            raise AssertionError(
                "Cannot run test nodes not using any test objects, here %s" % node
            )

        original_prefix = node.prefix
        # appending a suffix to retries so we can tell them apart
        run_times = len(node.shared_results)
        if run_times > 0:
            node.prefix = original_prefix + f"r{run_times}"
        uid = node.id_test.uid
        name = node.params["name"]

        node_result = {"name": name, "status": "UNKNOWN"}
        node.results += [node_result]
        await self.run_test_task(node)

        for i in range(status_timeout):
            try:
                test_result = next(
                    (
                        x
                        for x in self.job.result.tests
                        if x["name"].name == name and x["name"].uid == uid
                    )
                )
                if len(node.results) > 0:

                    duration = float(test_result["time_elapsed"])
                    max_allowed = max(
                        [
                            float(r["time_elapsed"])
                            for r in node.results
                            if r["status"] == "PASS"
                        ],
                        default=duration,
                    )
                    logging.info(
                        f"Validating test duration {duration} is within usual bounds ({max_allowed})"
                    )
                    if (
                        test_result["status"] == "PASS"
                        and float(duration) > 1.25 * max_allowed
                    ):
                        logging.warning(
                            f"Test result {uid} was obtained but test took much longer ({duration}) than usual"
                        )
                        # TODO: could we replace with WARN before the status is announced to the status server?
                        test_result["status"] = "WARN"
                # job and local results as interpreted by us have only serializable easy to use data
                job_result = {key: value for key, value in test_result.items()}
                job_result["name"] = test_result["name"].name
                node.results += [job_result]
                node.results.remove(node_result)
                test_status = test_result["status"].lower()
                break
            except StopIteration:
                await asyncio.sleep(30)
                logging.warning(
                    f"Test result {uid} wasn't yet found and could not be extracted ({i}/{status_timeout})"
                )
                test_status = "error"
        else:
            logging.error(
                f"Test result {uid} for {name} could not be found and extracted, defaulting to ERROR"
            )
        node.prefix = original_prefix

        logging.info(f"Finished running test with status {test_status.upper()}")
        # no need to log when test was not repeated
        if run_times > 0:
            logging.info(f"Finished running test {run_times + 1} times")

        # FIX: as VT's retval is broken (always True), we fix its handling here
        if test_status in ["error", "fail"]:
            return False
        else:
            return True

    def run_workers(self, test_suite: TestSuite | TestGraph, params: Params) -> None:
        """
        Run all workers in parallel traversing the graph for each.

        :param test_suite: test suite to traverse as graph or a custom test graph to traverse
        :param params: runtime parameters used for extra customization
        :raises: TypeError if the provided test suite is of unknown type
        """
        if isinstance(test_suite, TestSuite):
            graph = TestGraph()
            graph.restrs.update(self.job.config["vm_strs"])
            for node in test_suite.tests:
                assert isinstance(
                    node, TestNode
                ), f"Invalid test type fo test suite to run workers on for {node}"
                # apply default_only or user overwritten restriction
                node.update_restrs(self.job.config["vm_strs"])
            graph.new_nodes(test_suite.tests)
            graph.parse_shared_root_from_object_roots(params)
            graph.new_workers(TestGraph.parse_workers(params))
        elif isinstance(test_suite, TestGraph):
            graph = test_suite
        else:
            raise TypeError(
                f"Unknown test suite type for {type(test_suite)}, must be a Cartesian graph or an Avocado test suite"
            )

        graph.visualize(self.job.logdir)
        self.results_from_previous_jobs()
        graph.runner = self

        for worker in graph.workers.values():
            if not worker.spawner:
                worker.spawner = SpawnerDispatcher(self.job.config, self.job)[
                    worker.params["nets_spawner"]
                ].obj
            if not worker.start():
                raise RuntimeError(f"Failed to start environment {worker.id}")
        slot_workers = sorted([*graph.workers.values()], key=lambda x: x.params["name"])
        to_traverse = [graph.traverse_object_trees(s, params) for s in slot_workers]
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(
                asyncio.wait_for(
                    asyncio.shield(asyncio.gather(*to_traverse)),
                    self.job.timeout or 300000,
                )
            )
        except asyncio.TimeoutError as error:
            logging.error(error)
        except KeyboardInterrupt as error:
            logging.info(error)
            self.job.interrupted_reason = str(error)
            # summary.add("INTERRUPTED")

    def run_suite(self, job: Job, test_suite: TestSuite) -> set[str]:
        """
        Run one or more tests and report with test result.

        :param job: job that includes the test suite
        :param test_suite: test suite with some tests to run
        :returns: a set with types of test failures
        """
        summary = set()

        if not test_suite.enabled:
            job.interrupted_reason = f"Suite {test_suite.name} is disabled."
            return summary

        job.result.tests_total = len(test_suite.tests)

        self.job = job
        self.test_suite = test_suite
        self.tasks = {}

        self.status_repo = StatusRepo(self.job.unique_id)
        self.status_server = StatusServer(
            self.job.config.get("run.status_server_listen"), self.status_repo
        )

        asyncio.set_event_loop(self.loop)
        self.loop.run_until_complete(self.status_server.create_server())
        self.loop.create_task(self.status_server.serve_forever())
        # TODO: this needs more customization
        self.loop.create_task(self._update_status())

        params = self.job.config["param_dict"]
        try:
            self.run_workers(test_suite, params)
            if not self.all_results_ok():
                # the summary is a set so only a single failed test is enough
                summary.add("FAIL")
        except (KeyboardInterrupt, asyncio.TimeoutError) as error:
            logging.info(str(error))
            self.job.interrupted_reason = str(error)
            summary.add("INTERRUPTED")

        # clean up any test node session cache
        for session in TestWorker._session_cache.values():
            session.close()

        # TODO: The avocado implementation needs a workaround here:
        # Wait until all messages may have been processed by the
        # status_updater. This should be replaced by a mechanism
        # that only waits if there are missing status messages to
        # be processed, and, only for a given amount of time.
        # Tests with non received status will always show as SKIP
        # because of result reconciliation.
        time.sleep(0.05)

        self.job.result.end_tests()
        # the status server does not provide a way to verify it is fully initialized
        # so zero test runs need to access an internal attribute before closing
        if self.status_server._server_task:
            self.status_server.close()

        # Update the overall summary with found test statuses, which will
        # determine the Avocado command line exit status
        test_ids = [
            task.identifier for task in self.tasks.values() if task.category == "test"
        ]
        summary.update(
            [
                status.upper()
                for status in self.status_repo.get_result_set_for_tasks(test_ids)
            ]
        )
        return summary
