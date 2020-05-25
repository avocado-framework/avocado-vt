
"""
Virsh domjobinfo command related utility functions
"""

import re
import math
import logging

from avocado.core import exceptions

from virttest import virsh


# pylint: disable=E1121
def check_domjobinfo(vm, params, option="", remote_virsh_dargs=None):
    """
    Check given item in domjobinfo of the guest is as expected

    :param vm: the vm object
    :param params: the parameters used
    :param option: options for domjobinfo
    :param remote_virsh_dargs: the parameters for remote host
    :raise: exceptions.TestFail if the value of given item is unexpected
    """
    def _search_jobinfo(jobinfo, ignore_status=False):
        """
        Find value of given item in domjobinfo

        :param jobinfo: cmdResult object
        :param ignore_status: False to raise Error, True to ignore
        :raise: exceptions.TestFail if not found
        """
        for item in jobinfo.stdout.splitlines():
            if item.count(jobinfo_item):
                groups = re.findall(r'[0-9.]+', item.strip())
                logging.debug("In '%s' search '%s'\n", item, groups[0])
                if (math.fabs(float(groups[0]) - float(compare_to_value)) //
                   float(compare_to_value) > diff_rate):
                    err_msg = ("{} {} has too much difference from "
                               "{}".format(jobinfo_item,
                                           groups[0],
                                           compare_to_value))
                    if ignore_status:
                        logging.error(err_msg)
                    else:
                        raise exceptions.TestFail(err_msg)
                break

    jobinfo_item = params.get("jobinfo_item")
    compare_to_value = params.get("compare_to_value")
    ignore_status = params.get("domjob_ignore_status", False)
    logging.debug("compare_to_value:%s", compare_to_value)
    diff_rate = float(params.get("diff_rate", "0"))
    if not jobinfo_item or not compare_to_value:
        return
    jobinfo = virsh.domjobinfo(vm.name, option, debug=True)
    _search_jobinfo(jobinfo, ignore_status)

    check_domjobinfo_remote = params.get("check_domjobinfo_remote")
    if check_domjobinfo_remote and remote_virsh_dargs:
        remote_virsh_session = virsh.VirshPersistent(**remote_virsh_dargs)
        jobinfo = remote_virsh_session.domjobinfo(vm.name, option, debug=True)
        _search_jobinfo(jobinfo, ignore_status)
        remote_virsh_session.close_session()
