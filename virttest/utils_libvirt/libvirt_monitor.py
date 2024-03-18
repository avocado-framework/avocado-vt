import copy
import logging
import math

from avocado.core import exceptions

from virttest import libvirt_version, virsh

LOG = logging.getLogger("avocado." + __name__)


def _compare_value(value_type, line, key, tmp_domjobinfo):
    """
    Compare the value of items

    :param value_type: value type, contain 'str_itmes' and 'int_items'
    :param line: one line of domjobinfo output
    :param key: one key of domjobinfo output
    :param tmp_domjobinfo: domain job info
    :return: new domain job info
    """
    if value_type in tmp_domjobinfo and key in tmp_domjobinfo[value_type]:
        tmp_value = tmp_domjobinfo[value_type].get(key)
        if value_type == "str_items":
            value = line.strip().split(":")[1].strip()
        elif value_type == "int_items":
            value = float(line.strip().split(":")[1].strip().split(" ")[0])
            tmp_value = float(tmp_value)
        else:
            raise exceptions.TestFail("Don't support '%s'" % value_type)
        if value != tmp_value:
            raise exceptions.TestFail(
                "'%s' is not matched expect '%s'" % (value, tmp_value)
            )
        else:
            del tmp_domjobinfo[value_type][key]
    return tmp_domjobinfo


def _check_items(value_type, tmp_domjobinfo):
    """
    Check items

    :param value_type: value type, contain 'all_items', 'str_itmes' and 'int_items'
    :param tmp_domjobinfo: domain job info
    :retrun: new domain job info
    """
    if value_type in tmp_domjobinfo:
        if len(tmp_domjobinfo[value_type]) > 0:
            raise exceptions.TestFail(
                "Missing item: %s from %s" % (tmp_domjobinfo[value_type], value_type)
            )
        else:
            del tmp_domjobinfo[value_type]
    return tmp_domjobinfo


def _get_value(expect_key, out):
    """
    Get value from out

    :param expect_key: expect key
    :param out: domain job info
    :retrun: the value of expect key
    """
    for line in out.splitlines():
        key = line.split(":")[0]
        if key == expect_key:
            value, unit = line.strip().split(":")[1].strip().split(" ")
            if unit == "MiB":
                value = round(float(value) / 1024, 3)
            return float(value)
    return None


def _check_sum_items(line, key, tmp_domjobinfo, domjobinfo_out):
    """
    Check the items that need to be summed

    :param line: one line of domjobinfo output
    :param key: one key of domjobinfo output
    :param tmp_domjobinfo: the expected sum items in domjobinfo, for example,
                           {"sum_items": {"Data processed": "Memory processed+File processed"}}
    :param domjobinfo_out: the output of virsh.domjobinfo command
    :return: new domain job info
    """
    if "sum_items" in tmp_domjobinfo and key in tmp_domjobinfo["sum_items"]:
        tmp_value = tmp_domjobinfo["sum_items"].get(key)
        left, right = tmp_value.split("+")
        left_value = _get_value(left, domjobinfo_out)
        right_value = _get_value(right, domjobinfo_out)
        value = _get_value(key, domjobinfo_out)
        sum_value = round((left_value + right_value), 3)
        if not math.isclose(sum_value, value, abs_tol=0.01):
            raise exceptions.TestFail(
                "'%s' is not matched expect '%s'" % (sum_value, value)
            )
        else:
            del tmp_domjobinfo["sum_items"][key]
    return tmp_domjobinfo


def check_domjobinfo_output(
    vm_name,
    expected_domjobinfo={},
    expected_domjobinfo_complete={},
    options="",
    postcopy_options=None,
    remote_ip=None,
):
    """
    Check domjobinfo output

    :param vm_name: VM name
    :param expected_domjobinfo: the expected domjobinfo
    :param expected_domjobinfo_complete: the completed domjobinfo
    :param options: virsh domjobinfo options
    :param postcopy_options: postcopy options
    :param remote_ip: remote host
    """

    def check_domjobinfo_items(expected_domjobinfo):
        """
        Check the items of domjobinfo output

        :param expected_domjobinfo: the expected domjobinfo
        """
        domjobinfo = copy.deepcopy(expected_domjobinfo)
        if "error_msg" in domjobinfo:
            if domjobinfo["error_msg"] not in ret_domjobinfo.stderr:
                raise exceptions.TestFail(
                    "Not found '%s' in '%s'"
                    % (domjobinfo["error_msg"], ret_domjobinfo.stderr)
                )
            return
        for line in ret_domjobinfo.stdout.splitlines():
            key = line.split(":")[0]
            domjobinfo = _check_sum_items(line, key, domjobinfo, ret_domjobinfo.stdout)
            if "all_items" in domjobinfo and len(key) > 0:
                # For postcopy, no "Expected downtime" in domjobinfo from libvirt-9.3.0
                if "Expected downtime" == domjobinfo["all_items"][0]:
                    if postcopy_options and libvirt_version.version_compare(9, 3, 0):
                        del domjobinfo["all_items"][0]
                if key == domjobinfo["all_items"][0]:
                    value = line.strip().split(":")[1].strip().split(" ")[0]
                    if key == "Dirty rate":
                        if float(value) >= 0:
                            del domjobinfo["all_items"][0]
                            continue
                        else:
                            raise exceptions.TestFail("Wrong value for 'Dirty rate'.")

                    if float(value) <= 0:
                        raise exceptions.TestFail("The '%s' should not be 0." % key)
                    else:
                        del domjobinfo["all_items"][0]

            domjobinfo = _compare_value("str_items", line, key, domjobinfo)
            domjobinfo = _compare_value("int_items", line, key, domjobinfo)

        domjobinfo = _check_items("all_items", domjobinfo)
        domjobinfo = _check_items("str_items", domjobinfo)
        domjobinfo = _check_items("int_items", domjobinfo)
        domjobinfo = _check_items("sum_items", domjobinfo)

        if len(domjobinfo) != 0:
            raise exceptions.TestFail("Missing item: {}".format(domjobinfo))

    ret_domjobinfo = None
    LOG.info("Check domjobinfo output.")
    if (
        expected_domjobinfo and "src_items" in expected_domjobinfo
    ) or expected_domjobinfo_complete:
        virsh_args = {"debug": True, "ignore_status": True}
        ret_domjobinfo = virsh.domjobinfo(vm_name, options, **virsh_args)
        if "--completed" in options and expected_domjobinfo_complete:
            check_domjobinfo_items(expected_domjobinfo_complete["src_items"])
        else:
            check_domjobinfo_items(expected_domjobinfo["src_items"])
    if (
        expected_domjobinfo and "dest_items" in expected_domjobinfo
    ) or expected_domjobinfo_complete:
        dest_uri = "qemu+ssh://%s/system" % remote_ip
        virsh_args = {"debug": True, "ignore_status": True, "uri": dest_uri}
        ret_domjobinfo = virsh.domjobinfo(vm_name, options, **virsh_args)
        if "--completed" in options and expected_domjobinfo_complete:
            check_domjobinfo_items(expected_domjobinfo_complete["dest_items"])
        else:
            check_domjobinfo_items(expected_domjobinfo["dest_items"])
