import os
import re
import logging
from tempfile import mktemp

from avocado.core import exceptions
from avocado.utils import process

from virttest import virsh
from virttest import utils_misc
from virttest.utils_test import libvirt
from virttest.libvirt_xml.nodedev_xml import NodedevXML
from virttest.libvirt_xml.devices import hostdev


_FC_HOST_PATH = "/sys/class/fc_host"
_TIMEOUT = 5


def check_nodedev(dev_name, dev_parent=None):
    """
    Check node device relevant values

    :params dev_name: name of the device
    :params dev_parent: parent name of the device, None is default
    :return: True if nodedev is normal.
    """
    host = dev_name.split("_")[1]
    fc_host_path = os.path.join(_FC_HOST_PATH, host)

    # Check if the /sys/class/fc_host/host$NUM exists
    if not os.access(fc_host_path, os.R_OK):
        logging.error("Can't access %s", fc_host_path)
        return False

    dev_xml = NodedevXML.new_from_dumpxml(dev_name)
    if not dev_xml:
        logging.error("Can't dumpxml %s XML", dev_name)
        return False

    # Check device parent name
    if dev_parent != dev_xml.parent:
        logging.error("The parent name is different: %s is not %s",
                      dev_parent, dev_xml.parent)
        return False

    wwnn_from_xml = dev_xml.wwnn
    wwpn_from_xml = dev_xml.wwpn
    fabric_wwn_from_xml = dev_xml.fabric_wwn

    fc_dict = {}
    name_list = ["node_name", "port_name", "fabric_name"]
    for name in name_list:
        fc_file = os.path.join(fc_host_path, name)
        with open(fc_file, "r") as fc_content:
            fc_dict[name] = fc_content.read().strip().split("0x")[1]

    # Check wwnn, wwpn and fabric_wwn
    if len(wwnn_from_xml) != 16:
        logging.error("The wwnn is not valid: %s", wwnn_from_xml)
        return False
    if len(wwpn_from_xml) != 16:
        logging.error("The wwpn is not valid: %s", wwpn_from_xml)
        return False
    if fc_dict["node_name"] != wwnn_from_xml:
        logging.error("The node name is differnet: %s is not %s",
                      fc_dict["node_name"], wwnn_from_xml)
        return False
    if fc_dict["port_name"] != wwpn_from_xml:
        logging.error("The port name is different: %s is not %s",
                      fc_dict["port_name"], wwpn_from_xml)
        return False
    if fc_dict["fabric_name"] != fabric_wwn_from_xml:
        logging.error("The fabric wwpn is differnt: %s is not %s",
                      fc_dict["fabric_name"], fabric_wwn_from_xml)
        return False

    fc_type_from_xml = dev_xml.fc_type
    cap_type_from_xml = dev_xml.cap_type

    # Check capability type
    if (cap_type_from_xml != "scsi_host") or (fc_type_from_xml != "fc_host"):
        logging.error("The capability type isn't 'scsi_host' or 'fc_host'")
        return False

    return True


def find_hbas(hba_type="hba", status="online"):
    """
    Find online hba/vhba cards.

    :params hba_type: "vhba" or "hba"
    :params status: "online" or "offline"
    :return: A list contains the online/offline vhba/hba list
    """
    # TODO: add status=offline/online judgement, we don't test offline vhba now
    # so leave it here as a placeholder.
    result = virsh.nodedev_list(cap="scsi_host")
    if result.exit_status:
        raise exceptions.TestFail(result.stderr_text)
    scsi_hosts = result.stdout_text.strip().splitlines()
    online_hbas_list = []
    online_vhbas_list = []
    # go through all scsi hosts, and split hbas/vhbas into lists
    for scsi_host in scsi_hosts:
        result = virsh.nodedev_dumpxml(scsi_host)
        stdout = result.stdout_text.strip()
        if result.exit_status:
            raise exceptions.TestFail(result.stderr_text)
        if (re.search('vport_ops', stdout)
                and not re.search('<fabric_wwn>ffffffffffffffff</fabric_wwn>', stdout)
                and not re.search('<fabric_wwn>0</fabric_wwn>', stdout)):
            online_hbas_list.append(scsi_host)
        if re.search('fc_host', stdout) and not re.search('vport_ops', stdout):
            online_vhbas_list.append(scsi_host)
    if hba_type == "hba":
        return online_hbas_list
    if hba_type == "vhba":
        return online_vhbas_list


def is_vhbas_added(old_vhbas):
    """
    Check if a vhba is added

    :param old_vhbas: Pre-existing vhbas
    :return: True/False based on addition
    """
    new_vhbas = find_hbas("vhba")
    new_vhbas.sort()
    old_vhbas.sort()
    if len(new_vhbas) - len(old_vhbas) >= 1:
        return True
    return False


def is_vhbas_removed(old_vhbas):
    """
    Check if a vhba is removed

    :param old_vhbas: Pre-existing vhbas
    :return: True/False based on removal
    """
    new_vhbas = find_hbas("vhba")
    new_vhbas.sort()
    old_vhbas.sort()
    if len(new_vhbas) - len(old_vhbas) < 0:
        return True
    return False


def nodedev_create_from_xml(params):
    """
    Create a node device with a xml object.

    :param params: Including nodedev_parent, scsi_wwnn, scsi_wwpn set in xml
    :return: The scsi device name just created
    """
    nodedev_parent = params.get("nodedev_parent")
    scsi_wwnn = params.get("scsi_wwnn")
    scsi_wwpn = params.get("scsi_wwpn")
    status_error = "yes" == params.get("status_error", "no")
    vhba_xml = NodedevXML()
    vhba_xml.cap_type = 'scsi_host'
    vhba_xml.fc_type = 'fc_host'
    vhba_xml.parent = nodedev_parent
    vhba_xml.wwnn = scsi_wwnn
    vhba_xml.wwpn = scsi_wwpn
    logging.debug("Prepare the nodedev XML: %s", vhba_xml)
    vhba_file = mktemp()
    with open(vhba_file, 'w') as xml_object:
        xml_object.write(str(vhba_xml))

    result = virsh.nodedev_create(vhba_file,
                                  debug=True,
                                  )
    # Remove temprorary file
    os.unlink(vhba_file)
    libvirt.check_exit_status(result, status_error)
    output = result.stdout_text
    logging.info(output)
    for scsi in output.split():
        if scsi.startswith('scsi_host'):
            # Check node device
            utils_misc.wait_for(
                lambda: check_nodedev(scsi, nodedev_parent),
                timeout=_TIMEOUT)
            if check_nodedev(scsi, nodedev_parent):
                return scsi
            else:
                raise exceptions.TestFail(
                    "XML of vHBA card '%s' is not correct,"
                    "Please refer to log err for detailed info" % scsi)


def nodedev_destroy(scsi_host, params={}):
    """
    Destroy a nodedev of scsi_host#.
    :param scsi_host: The scsi to destroy
    :param params: Contain status_error
    """
    status_error = "yes" == params.get("status_error", "no")
    result = virsh.nodedev_destroy(scsi_host)
    logging.info("destroying scsi:%s", scsi_host)
    # Check status_error
    libvirt.check_exit_status(result, status_error)
    # Check nodedev value
    if not check_nodedev(scsi_host):
        logging.info(result.stdout_text)
    else:
        raise exceptions.TestFail("The relevant directory still exists"
                                  " or mismatch with result")


def check_nodedev_exist(scsi_host):
    """
    Check if scsi_host# exist.
    :param scsi_host: The scsi host to be checked
    :return: True if scsi_host exist, False if not
    """
    host = scsi_host.split("_")[1]
    fc_host_path = os.path.join(_FC_HOST_PATH, host)
    if os.path.exists(fc_host_path):
        return True
    return False


def vhbas_cleanup(vhba_list):
    """
    Clean up vhbas.
    """
    for scsi_host in vhba_list:
        nodedev_destroy(scsi_host)
    left_vhbas = find_hbas("vhba")
    if left_vhbas:
        logging.error("old vhbas are: %s", left_vhbas)
    else:
        logging.debug("scsi_hosts destroyed: %s", vhba_list)


def create_hostdev_xml(adapter_name="", **kwargs):
    """
    Create vhba hostdev xml.

    :param adapter_name: The name of the scsi adapter
    :param kwargs: Could contain addr_bus, addr_target,
     addr_unit, mode, and managed
    :return: a xml object set by kwargs
    """
    addr_bus = kwargs.get('addr_bus', 0)
    addr_target = kwargs.get('addr_target', 0)
    addr_unit = kwargs.get('addr_unit', 0)
    mode = kwargs.get('mode', 'subsystem')
    managed = kwargs.get('managed', 'no')

    hostdev_xml = hostdev.Hostdev()
    hostdev_xml.type = "scsi"
    hostdev_xml.managed = managed
    hostdev_xml.mode = mode

    source_args = {}
    source_args['adapter_name'] = adapter_name
    source_args['bus'] = addr_bus
    source_args['target'] = addr_target
    source_args['unit'] = addr_unit
    hostdev_xml.source = hostdev_xml.new_source(**source_args)
    logging.info(hostdev_xml)
    return hostdev_xml


def find_scsi_luns(scsi_host):
    """
    Find available luns of specified scsi_host.

    :param scsi_host: The scsi host name in format of "scsi_host#"
    :return: A dictionary contains all available fc luns
    """
    lun_dicts = []
    tmp_list = []
    scsi_number = scsi_host.replace("scsi_host", "")
    cmd = "multipath -ll | grep '\- %s:' | grep 'ready running' |\
           awk '{FS=\" \"}{for (f=1; f<=NF; f+=1) {if ($f ~ /%s:/)\
           {print $f}}}'" % (scsi_number, scsi_number)
    try:
        result = process.run(cmd, shell=True)
    except Exception as e:
        raise exceptions.TestError("run 'multipath' failed: %s" % str(e))
    tmp_list = result.stdout_text.strip().splitlines()
    for lun in tmp_list:
        lun = lun.split(":")
        lun_dicts_item = {}
        lun_dicts_item["scsi"] = lun[0]
        lun_dicts_item["bus"] = lun[1]
        lun_dicts_item["target"] = lun[2]
        lun_dicts_item["unit"] = lun[3]
        lun_dicts.append(lun_dicts_item)
    return lun_dicts


def find_mpath_devs():
    """
    Find all mpath devices in /dev/mapper which is start with "mpath"
    and not ending with a digit (which means it's a partition)
    """
    mpath_devs = []
    cmd = "ls -l /dev/mapper/ | grep mpath | awk -F ' ' '{print $9}' \
           | grep -Ev [0-9]$ |sort -d"
    cmd_result = process.run(cmd, shell=True)
    mpath_devs = cmd_result.stdout_text.split("\n")
    return mpath_devs


def is_mpath_devs_added(old_mpath_devs):
    """
    Check if a mpath device is added
    :param old_mpaths: Pre-existing mpaths
    :return: True/False based on addition
    """
    new_mpath_devs = find_mpath_devs()
    new_mpath_devs.sort()
    old_mpath_devs.sort()
    if len(new_mpath_devs) - len(old_mpath_devs) >= 1:
        return True
    return False


def restart_multipathd(mpath_dev="", expect_exist=False):
    """
    Restart the multipath deamon, and check if mpath_dev still exists
    after deamon restarted, as expected.
    """
    cmd_status = process.system('service multipathd restart', verbose=True)
    if cmd_status:
        raise exceptions.TestFail("Restart multipathd failed.")
    if not os.path.exists(mpath_dev):
        if not expect_exist:
            return True
    else:
        if expect_exist:
            return True
    return False


def prepare_multipath_conf(conf_path="/etc/multipath.conf", conf_content="",
                           replace_existing=False, restart_multipath=True):
    """
    Prepare multipath conf file.

    :param conf_path: Path to the conf file.
    :param conf_content: Content of the conf file.
    :param replace_existing: True means to replace exsiting conf file.
    :param restart_multipathd: True means to restart multipathd.
    :return: The content of original conf, can be used to recover env.
    """
    default_conf_content = ("defaults {\n\tuser_friendly_names yes"
                            "\n\tfind_multipaths yes\n}")
    old_conf_content = ""
    new_conf_content = conf_content if conf_content else default_conf_content
    if os.path.exists(conf_path):
        with open(conf_path, 'r+') as conf_file:
            old_conf_content = conf_file.read()
            logging.info("Old multipath conf is: %s" % old_conf_content)
            if replace_existing:
                conf_file.seek(0)
                conf_file.truncate()
                conf_file.write(new_conf_content)
                logging.info("Replace multipath conf to: %s" % new_conf_content)
            else:
                logging.info("Multipath conf exsits, skip preparation.")
    else:
        with open(conf_path, 'w') as conf_file:
            conf_file.write(new_conf_content)
            logging.info("Create multipath conf: %s" % new_conf_content)
    if restart_multipath:
        restart_multipathd()
    return old_conf_content
