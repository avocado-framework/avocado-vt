import logging
import os
import sys

from avocado.core import exit_codes
from avocado.core.plugin_interfaces import JobPostTests as Post
from avocado.core.plugin_interfaces import JobPreTests as Pre
from avocado.utils.stacktrace import log_exc_info

from virttest.vt_cluster import cluster, node_metadata
from virttest.vt_imgr import imgr
from virttest.vt_resmgr import resmgr


class ClusterSetupError(Exception):
    """
    Represents any error situation when attempting to create a cluster.
    """

    pass


class ClusterManagerSetupError(ClusterSetupError):
    pass


class ClusterCleanupError(Exception):
    pass


class ClusterManagerCleanupError(ClusterCleanupError):
    pass


class VTCluster(Pre, Post):

    name = "vt-cluster"
    description = "Avocado-VT Cluster Pre/Post"

    def __init__(self, **kwargs):
        self._log = logging.getLogger("avocado.app")

    @staticmethod
    def _pre_node_setup():
        try:
            for node in cluster.get_all_nodes():
                node.start_agent_server()
            node_metadata.load_metadata()
        except Exception as err:
            raise ClusterSetupError(err)

    @staticmethod
    def _pre_mgr_setup():
        try:
            # Pre-setup the cluster manager
            resmgr.startup()
            imgr.startup()
        except Exception as err:
            raise ClusterManagerSetupError(err)

    @staticmethod
    def _post_mgr_cleanup():
        try:
            # Post-cleanup the cluster manager
            imgr.teardown()
            resmgr.teardown()
        except Exception as err:
            raise ClusterManagerCleanupError(err)

    def _post_node_setup(self, job):
        cluster_dir = os.path.join(job.logdir, "cluster")
        for node in cluster.get_all_nodes():
            node_dir = os.path.join(cluster_dir, node.name)
            os.makedirs(node_dir)
            try:
                node.upload_agent_log(node_dir)
            except Exception as err:
                self._log.warning(err)
            finally:
                try:
                    node.stop_agent_server()
                except Exception as detail:
                    err = ClusterCleanupError(detail)
                    msg = (
                        f"Failed to stop the agent "
                        f"server on node '{node.name}': {err}"
                    )
                    self._log.warning(msg)
        node_metadata.unload_metadata()

    def pre_tests(self, job):
        if cluster.get_all_nodes():
            try:
                self._pre_node_setup()
                self._pre_mgr_setup()
            except Exception as detail:
                msg = "Failure trying to set Avocado-VT job env: %s" % detail
                self._log.error(msg)
                log_exc_info(sys.exc_info(), self._log.name)
                sys.exit(exit_codes.AVOCADO_JOB_FAIL | job.exitcode)

    def post_tests(self, job):
        if cluster.get_all_nodes():
            try:
                self._post_mgr_cleanup()
            except ClusterManagerCleanupError as err:
                self._log.warning(err)
            finally:
                self._post_node_setup(job)
