"""

SUMMARY
------------------------------------------------------
Tool to use for GUI and non-GUI test development on virtual machines.

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
This tool can be used for rapid development of tests whereby the developer
could save and revert to vm states multiple times during development, all
by using a GUI with a few buttons.


INTERFACE
------------------------------------------------------

"""

import os
import contextlib
import asyncio
from collections import namedtuple

from avocado.core.output import LOG_UI, LOG_JOB as logging

from avocado_i2n.cartgraph import TestGraph
from avocado_i2n.intertest_setup import with_cartesian_graph


#: list of all available manual steps or simply semi-automation tools
__all__ = ["develop"]


############################################################
# Custom manual user steps
############################################################


@with_cartesian_graph
def develop(config, tag=""):
    """
    Run manual tests specialized at development speedup.

    :param config: command line arguments and run configuration
    :type config: {str, str}
    :param str tag: extra name identifier for the test to be run

    Current modes that can be supplied from the command line
    can be found in the "develop" test set.

    As with all manual tests, providing setup and making sure
    that all the vms exist is a user's responsibility.
    """
    l, r = config["graph"].l, config["graph"].r
    selected_vms = list(config["vm_strs"].keys())
    LOG_UI.info("Developing on virtual machines %s (%s)",
                ", ".join(selected_vms), os.path.basename(r.job.logdir))

    graph = TestGraph()
    graph.new_workers(l.parse_workers(config["param_dict"]))
    for vm_name in selected_vms:
        graph.new_objects(TestGraph.parse_composite_objects(vm_name, "vms", config["vm_strs"][vm_name]))

    vms = " ".join(selected_vms)
    setup_dict = config["param_dict"].copy()
    setup_dict.update({"vms": vms, "main_vm": selected_vms[0]})
    for test_worker in graph.workers.values():
        test_worker.net.update_restrs(config["vm_strs"])
        mode = config["tests_params"].get("devmode", "generator")
        nodes = graph.parse_composite_nodes("all..manual..develop.%s" % mode, test_worker.net,
                                            tag, params=setup_dict)
        if len(nodes) == 0:
            logging.warning(f"Skipped incompatible worker {test_worker.id}")
            continue
        elif len(nodes) > 1:
            raise RuntimeError(f"There must be exactly one {mode} develop test variant "
                               f"for {test_worker.id} from {nodes}")
        graph.new_nodes(nodes[0])

    graph.parse_shared_root_from_object_roots(config["param_dict"])
    graph.flag_children(
        flag_type="run",
        flag=lambda self, slot: not self.is_shared_root() and slot not in self.shared_finished_workers,
    )
    r.run_workers(graph, config["param_dict"])
    LOG_UI.info("Development complete")
