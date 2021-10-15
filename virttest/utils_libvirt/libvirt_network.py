
"""
Virsh net* command related utility functions
"""
import re
import logging
import ast

from avocado.core import exceptions
from avocado.utils import process

from virttest import virsh
from virttest import remote

from virttest.libvirt_xml import NetworkXML
from virttest.utils_test import libvirt

LOG = logging.getLogger('avocado.' + __name__)


def create_or_del_network(net_dict, is_del=False, remote_args=None):
    """
    Create or delete network on local or remote

    :param net_dict: Dictionary with the network parameters
    :param is_del: Whether the networks should be deleted
    :param remote_args: The parameters for remote
    """

    remote_virsh_session = None
    if remote_args:
        remote_virsh_session = virsh.VirshPersistent(**remote_args)

    if not is_del:
        net_dev = libvirt.create_net_xml(net_dict.get("net_name"), net_dict)

        if not remote_virsh_session:
            if net_dev.get_active():
                net_dev.undefine()
            net_dev.define()
            net_dev.start()
        else:
            remote_ip = remote_args.get("remote_ip")
            remote_user = remote_args.get("remote_user")
            remote_pwd = remote_args.get("remote_pwd")
            if not all([remote_ip, remote_user, remote_pwd]):
                raise exceptions.TestError("remote_[ip|user|pwd] are necessary!")
            remote.scp_to_remote(remote_ip, '22', remote_user, remote_pwd,
                                 net_dev.xml, net_dev.xml, limit="",
                                 log_filename=None, timeout=600,
                                 interface=None)
            remote_virsh_session.net_define(net_dev.xml, debug=True)
            remote_virsh_session.net_start(net_dict.get("net_name"),
                                           debug=True)
            remote.run_remote_cmd("rm -rf %s" % net_dev.xml, remote_args)
    else:
        virsh_session = virsh
        if remote_virsh_session:
            virsh_session = remote_virsh_session
        if net_dict.get("net_name") in virsh_session.net_state_dict():
            virsh_session.net_destroy(net_dict.get("net_name"),
                                      debug=True, ignore_status=True)
            virsh_session.net_undefine(net_dict.get("net_name"),
                                       debug=True, ignore_status=True)
    if remote_virsh_session:
        remote_virsh_session.close_session()


def check_established(params):
    """
    Parses netstat output for established connection
    on remote or local

    :param params: the parameters used
    :return: str, the port used
    :raises: exceptions.TestFail if no match
    """
    port_to_check = params.get("port_to_check", "4915")
    check_local = 'yes' == params.get("check_local_port", "no")
    ipv6_config = "yes" == params.get("ipv6_config", "no")
    if ipv6_config:
        server_ip = params.get("ipv6_addr_des", "")[:17]
    else:
        server_ip = params.get("server_ip", params.get("remote_ip"))

    cmd = "netstat -tunap|grep %s" % port_to_check
    if check_local:
        cmdRes = process.run(cmd, shell=True)
    else:
        cmdRes = remote.run_remote_cmd(cmd, params)

    if port_to_check != '4915':
        pat_str = r'.*%s:%s.*ESTABLISHED.*qemu-kvm.*' % (server_ip,
                                                         port_to_check)
        search = re.search(pat_str, cmdRes.stdout_text.strip())
        if not search:
            raise exceptions.TestFail("Pattern '%s' is not matched in "
                                      "'%s'" % (pat_str,
                                                cmdRes.stdout_text.strip()))
        else:
            return port_to_check
    else:
        pat_str = r'.*%s:(\d*).*ESTABLISHED.*qemu-kvm.*' % server_ip
        search = re.search(pat_str, cmdRes.stdout_text.strip())
        if search:
            LOG.debug("Get the port used:%s", search.group(1))
            return search.group(1)
        else:
            raise exceptions.TestFail("Pattern '%s' is not matched in "
                                      "'%s'" % (pat_str,
                                                cmdRes.stdout_text.strip()))


def modify_network_xml(net_dict, testnet_xml):
    """
    modify the network's xml

    :param net_dict: The dict restore need updated items like mac, bandwidth, forward
    :param testnet_xml: the network xml object to be modified
    :return: the updated network xml
    """
    del_nat = net_dict.get('del_nat_attrs')
    del_ip = net_dict.get('del_ip')
    dns_txt = net_dict.get('dns_txt')
    domain = net_dict.get('domain')
    bridge = net_dict.get('bridge')
    forward = net_dict.get('forward')
    # get the params about forward interface
    interface_dev = net_dict.get('interface_dev')
    virtualport = net_dict.get('virtualport')
    # bandwidth to be set if any
    net_bandwidth_outbound = net_dict.get('net_bandwidth_outbound')
    net_bandwidth_inbound = net_dict.get('net_bandwidth_inbound')
    mac = net_dict.get("mac")

    # delete the <bridge/> and <mac/> elements as they can be
    # generated automatically if needed
    testnet_xml.del_bridge()
    testnet_xml.del_mac()
    if del_nat is True:
        testnet_xml.del_nat_attrs()
    if del_ip:
        testnet_xml.del_ip()
    if dns_txt:
        dns_dict = {"txt": ast.literal_eval(dns_txt)}
        dns_obj = testnet_xml.new_dns(**dns_dict)
        testnet_xml.dns = dns_obj
    if mac:
        testnet_xml.mac = mac
    if domain:
        testnet_xml.domain_name = domain
    if bridge:
        testnet_xml.del_bridge()
        testnet_xml.bridge = {"name": bridge}
    if forward:
        testnet_xml.del_forward()
        testnet_xml.forward = eval(forward)
        LOG.debug("current mode is %s" % testnet_xml.forward)
    if interface_dev:
        testnet_xml.forward_interface = [{'dev': interface_dev}]
    if virtualport:
        testnet_xml.virtualport_type = net_dict.get('virtualport_type', 'openvswitch')
    if net_bandwidth_inbound:
        net_inbound = ast.literal_eval(net_bandwidth_inbound)
        testnet_xml.bandwidth_inbound = net_inbound
    if net_bandwidth_outbound:
        net_outbound = ast.literal_eval(net_bandwidth_outbound)
        testnet_xml.bandwidth_outbound = net_outbound
    return testnet_xml


def ensure_default_network():
    """
    Ensure the default network exists on the host and in active status
    :return: None
    """
    net_state = virsh.net_state_dict()
    if 'default' not in net_state:
        # define and start the default network
        virsh.net_define("/usr/share/libvirt/networks/default.xml",
                         debug=True, ignore_status=False)
    if not net_state["default"].get("active"):
        virsh.net_start("default", debug=True, ignore_status=False)
        virsh.net_autostart("default", debug=True, ignore_status=False)


def check_tap_connected(tap_name, estate, br_name):
    """
    Check if the tap device is connected to a bridge
    :param tap_name: the tap device name on the host
    :param estate: True or False, True for expected connected.
    :param br_name: the bridge which the tap device attach or detach
    :return: True or False. If get expected result, return True, or return False
    """
    cmd = "bridge link | grep master | grep %s" % br_name
    outputs = process.run(cmd, shell=True, ignore_status=True).stdout_text
    LOG.debug("The interface attached to the bridge is:\n%s", outputs)
    if tap_name in outputs:
        if estate:
            LOG.debug("The tap is attached to bridge as expected!")
        else:
            LOG.error("The tap isn't detached from bridge!")
            return False
    else:
        if estate:
            LOG.error("The tap is not attached to bridge!")
            return False
        else:
            LOG.debug("The tap isn't attached to bridge as expected!")
    return True


def check_network_connection(net_name, expected_conn=0):
    """
    Check network connections in network xml

    :param net_name: The network to be checked
    :param expected_conn: The expected value
    :raise: exceptions.TestFail when no match
    """
    netxml = NetworkXML(network_name=net_name).new_from_net_dumpxml(net_name)
    net_conn = int(netxml.xmltreefile.getroot().get('connections', '0'))
    LOG.debug("Network connection is %d.", net_conn)
    if expected_conn != net_conn:
        raise exceptions.TestFail("Unable to get the expected connection "
                                  "number. Expected: %d, Actual: %d."
                                  % (expected_conn, net_conn))
