"""

SUMMARY
------------------------------------------------------
Tool to semi-automate the creation of a selection of permanent vms.

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
This tool contains manual steps to use to create permanent vms.

Currently supported vms are based on: Ubuntu.


INTERFACE
------------------------------------------------------

"""

import os

from avocado.core.output import LOG_UI, LOG_JOB as logging
from virttest import params_parser as param
from virttest.cartgraph import TestGraph
from virttest.intertest_setup import with_cartesian_graph, update


#: list of all available manual steps or simply semi-automation tools
__all__ = ["permubuntu"]


############################################################
# Custom manual user steps
############################################################


@with_cartesian_graph
def permubuntu(config, tag=""):
    """
    Perform all extra setup needed for the ubuntu permanent vms.

    :param config: command line arguments and run configuration
    :type config: {str, str}
    :param str tag: extra name identifier for the test to be run
    """
    l, r = config["graph"].l, config["graph"].r
    selected_vms = sorted(config["vm_strs"].keys())
    LOG_UI.info("Starting permanent vm setup for %s (%s)",
                ", ".join(selected_vms), os.path.basename(r.job.logdir))

    # configure the update tool for remove test set independent behavior
    for vm_name in selected_vms:
        config["param_dict"]["vms"] = vm_name
        config["param_dict"]["main_vm"] = vm_name
        # in case of permanent vms, support creation and other otherwise dangerous operations
        config["param_dict"]["create_permanent_vm"] = "yes"
        config["tests_str"] = "only all..customize"
        update(config, tag=tag)

    graph = TestGraph()
    graph.new_workers(l.parse_workers(config["param_dict"]))
    for vm_name in selected_vms:
        graph.new_objects(TestGraph.parse_composite_objects(vm_name, "vms", config["vm_strs"][vm_name]))

    for test_worker in graph.workers.values():
        test_worker.net.update_restrs(config["vm_strs"])
        for test_object in [o for o in graph.objects if o.key == "vms"]:
            setup_dict = config["param_dict"].copy()
            setup_dict["vms"] = test_object.suffix
            setup_dict.update({"set_state_vms": "ready"})

            # consider this as a special kind of state converting test which concerns
            # permanent objects (i.e. instead of transition from customize to on
            # root, it is a transition from supposedly "permanentized" vm to the root)
            logging.info("Booting %s for the first permanent on state", test_object.suffix)
            nodes = graph.parse_composite_nodes("all..internal..manage.start", test_worker.net,
                                                tag, params=setup_dict)
            if len(nodes) == 0:
                logging.warning(f"Skipped incompatible worker {test_worker.id}")
                continue
            graph.new_nodes(nodes)

            # TODO: traversal relies explicitly on object_suffix which only indicates
            # where a parent node was parsed from, i.e. which test object of the child node
            for node in nodes:
                node.params["object_suffix"] = test_object.long_suffix

    graph.parse_shared_root_from_object_roots(config["param_dict"])
    r.run_workers(graph, config["param_dict"])
    LOG_UI.info("Finished permanent vm setup")
