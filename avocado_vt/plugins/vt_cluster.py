import logging
import sys
import os

from avocado.core import exit_codes
from avocado.core.plugin_interfaces import JobPreTests as Pre
from avocado.core.plugin_interfaces import JobPostTests as Post
from avocado.utils.stacktrace import log_exc_info

from virttest.vt_cluster import cluster
from virttest.vt_cluster import node_metadata


class ClusterCreationError(Exception):
    """
    Represents any error situation when attempting to create a cluster.
    """
    pass


class VTCluster(Pre, Post):

    name = 'vt-cluster'
    description = 'Avocado-VT Cluster Pre/Post'

    def __init__(self, **kwargs):
        self._log = logging.getLogger("avocado.app")

    def pre_tests(self, job):
        if cluster.get_all_nodes():
            try:
                for node in cluster.get_all_nodes():
                    node.start_agent_server()
                node_metadata.load_metadata()

            except Exception as detail:
                msg = "Failure trying to set Avocado-VT job env: %s" % detail
                self._log.error(msg)
                log_exc_info(sys.exc_info(), self._log.name)
                sys.exit(exit_codes.AVOCADO_JOB_FAIL | job.exitcode)

    def post_tests(self, job):
        if cluster.get_all_nodes():
            cluster_dir = os.path.join(job.logdir, "cluster")
            for node in cluster.get_all_nodes():
                try:
                    node_dir = os.path.join(cluster_dir, node.name)
                    os.makedirs(node_dir)
                    node.upload_agent_log(node_dir)
                    node.stop_agent_server()
                except Exception:
                    pass
            node_metadata.unload_metadata()
