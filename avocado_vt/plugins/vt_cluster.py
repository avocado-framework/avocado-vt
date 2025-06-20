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

"""
This module provides an Avocado-VT plugin for managing a test cluster.

The `VTCluster` plugin hooks into the job lifecycle to perform setup before
tests run and cleanup after they complete. It is responsible for starting and
stopping agent servers on cluster nodes, handling metadata, and collecting
logs. This ensures that the test environment is properly configured and torn
down for cluster-based tests.
"""
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed

from virttest.vt_cluster import cluster, node_properties
from virttest.vt_imgr import vt_imgr
from virttest.vt_resmgr import resmgr

from avocado.core import exit_codes
from avocado.core.plugin_interfaces import JobPostTests as Post
from avocado.core.plugin_interfaces import JobPreTests as Pre
from avocado.utils.stacktrace import log_exc_info


class ClusterSetupError(Exception):
    """
    Represents any error situation when attempting to create a cluster.
    """

    pass


class ClusterManagerSetupError(ClusterSetupError):
    """
    Represents an error during the setup of the cluster manager.
    """

    pass


class ClusterCleanupError(Exception):
    """
    Represents an error during the cleanup of the cluster.
    """

    pass


class ClusterManagerCleanupError(ClusterCleanupError):
    """
    Represents an error during the cleanup of the cluster manager.
    """

    pass


class VTCluster(Pre, Post):
    """
    An Avocado-VT plugin to set up and tear down a multi-node cluster.

    This plugin manages the lifecycle of a test cluster by implementing the
    `pre_tests` and `post_tests` hooks. It ensures that cluster nodes are
    initialized with agent servers before tests begin and are properly shut
    down and cleaned up after the job finishes.
    """

    name = "vt-cluster"
    description = "Avocado-VT Cluster Pre/Post"

    def __init__(self, **kwargs):
        """
        Initializes the VTCluster plugin.
        """
        self._log = logging.getLogger("avocado.app")

    @staticmethod
    def _setup_nodes():
        """
        Starts agent servers on all cluster nodes and loads metadata.

        Raises:
            ClusterSetupError: If starting an agent or loading metadata fails.
        """
        # try:
        #     for node in cluster.get_all_nodes():
        #         node.start_agent_server()
        # except Exception as err:
        #     raise ClusterSetupError(err)
        nodes = cluster.get_all_nodes()
        if not nodes:
            return

        def start_node_agent(node):
            """Helper function to start agent on a single node."""
            try:
                node.start_agent_server()
                return node, None
            except Exception as err:
                return node, err

        try:
            with ThreadPoolExecutor(max_workers=len(nodes)) as executor:
                future_to_node = {executor.submit(start_node_agent, node): node
                                  for node in nodes}

                for future in as_completed(future_to_node):
                    node, error = future.result()
                    if error:
                        raise ClusterSetupError(
                            f"Failed to start agent on node '{node.name}': {error}")
        except Exception as err:
            if isinstance(err, ClusterSetupError):
                raise
            raise ClusterSetupError(err)

    @staticmethod
    def _setup_mgr():
        """
        Performs pre-setup for the cluster manager.

        Raises:
            ClusterManagerSetupError: If the manager setup fails.
        """
        try:
            # Pre-setup the cluster manager
            # e.g:
            resmgr.startup()
            vt_imgr.startup()
        except Exception as err:
            raise ClusterManagerSetupError(err)

    @staticmethod
    def _cleanup_mgr():
        """
        Performs post-cleanup for the cluster manager.

        Raises:
            ClusterManagerCleanupError: If the manager cleanup fails.
        """
        try:
            # Post-cleanup the cluster manager
            # e.g:
            vt_imgr.teardown()
            resmgr.teardown()
        except Exception as err:
            raise ClusterManagerCleanupError(err)

    def _cleanup_nodes(self, job):
        """

        Finalizes node cleanup by collecting logs and stopping agents.

        This method is responsible for creating directories for each node's
        logs, uploading the agent logs, and ensuring that agent servers are
        stopped. It also unloads the node metadata.

        :param job: The Avocado job object.
        :type job: avocado.core.job.Job
        """
        # cluster_dir = os.path.join(job.logdir, "cluster")
        # for node in cluster.get_all_nodes():
        #     node_dir = os.path.join(cluster_dir, node.name)
        #     os.makedirs(node_dir, exist_ok=True)
        #     try:
        #         remote_path = node.proxy.api.get_agent_log_filename()
        #         if remote_path:
        #             node.copy_files_from(node_dir, remote_path)
        #     except Exception as err:
        #         self._log.warning(err)
        #     finally:
        #         try:
        #             node.stop_agent_server()
        #         except Exception as detail:
        #             err = ClusterCleanupError(detail)
        #             msg = (
        #                 f"Failed to stop the agent "
        #                 f"server on node '{node.name}': {err}"
        #             )
        #             self._log.warning(msg)

        cluster_dir = os.path.join(job.logdir, "cluster")
        nodes = cluster.get_all_nodes()

        if not nodes:
            return

        def cleanup_single_node(node):
            """Helper function to cleanup a single node."""
            node_dir = os.path.join(cluster_dir, node.name)
            os.makedirs(node_dir, exist_ok=True)

            upload_error = None
            stop_error = None

            try:
                # remote_path = node.proxy.api.get_agent_log_filename()
                remote_path = node.proxy.core.get_agent_log_filename()
                if remote_path:
                    node.copy_files_from(node_dir, remote_path)
            except Exception as err:
                upload_error = err

            finally:
                try:
                    node.stop_agent_server()
                except Exception as stop_err:
                    stop_error = ClusterCleanupError(stop_err)

                return node, upload_error, stop_error

        with ThreadPoolExecutor(max_workers=len(nodes)) as executor:
            future_to_node = {executor.submit(cleanup_single_node, node): node
                              for node in nodes}

            for future in as_completed(future_to_node):
                node, upload_error, stop_error = future.result()

                if upload_error:
                    self._log.warning(upload_error)

                if stop_error:
                    msg = (
                        f"Failed to stop the agent "
                        f"server on node '{node.name}': {stop_error}"
                    )
                    self._log.warning(msg)

    def pre_tests(self, job):
        """
        Hook executed before tests run to set up the cluster environment.

        If cluster nodes are defined, this method orchestrates the setup of
        both the nodes and the cluster manager. If any setup step fails, it
        logs the error and terminates the job.

        :param job: The Avocado job object.
        :type job: avocado.core.job.Job
        """
        if cluster.get_all_nodes():
            try:
                self._setup_nodes()
                self._setup_mgr()
                node_properties.save_properties()
            except Exception as detail:
                msg = f"Failure trying to set Avocado-VT job env: {detail}"
                self._log.error(msg)
                log_exc_info(sys.exc_info(), self._log.name)
                sys.exit(exit_codes.AVOCADO_JOB_FAIL | job.exitcode)

    def post_tests(self, job):
        """
        Hook executed after tests complete to clean up the cluster environment.

        This method ensures that both the cluster manager and the individual
        nodes are cleaned up. It is designed to be robust, attempting all
        cleanup steps even if some fail.

        :param job: The Avocado job object.
        :type job: avocado.core.job.Job
        """
        if cluster.get_all_nodes():
            try:
                self._cleanup_mgr()
            except Exception as err:
                self._log.warning(f"Manager cleanup failed: {err}")
            finally:
                node_properties.remove_properties()
                self._cleanup_nodes(job)
