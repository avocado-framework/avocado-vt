"""

SUMMARY
------------------------------------------------------
Prepare the step file or the unattended file for each vm to synchronize its
installation process with some important Cartesian parameters.

Copyright: Intra2net AG


CONTENTS
------------------------------------------------------
Generally, perform some install-related customization here, since the
original install tests are external to the test suite and therefore not
directly modifiable.


INTERFACE
------------------------------------------------------

"""

import re
import logging

# avocado imports
from avocado.core import exceptions
from virttest import error_context


log = logging.getLogger('avocado.test.log')


###############################################################################
# HELPERS
###############################################################################


def convert_to_key_steps(parameter_string):
    """
    Convert parameter string to steps format keystrokes.

    :param str parameter_string: text to convert
    :returns: a block of lines - one for each keystroke step
    :rtype: str
    """
    keystrokes = []
    for char in parameter_string:
        if char == '.':
            keystrokes.append("key dot\n")
        else:
            keystrokes.append("key " + char + "\n")
    return ''.join(keystrokes)


def string_from_template(filename):
    """
    Obtain a string from a template file.

    :param str filename: template filename
    :returns: template file content
    :rtype: str
    """
    with open(filename + ".template", "r") as f:
        log.info(f"Spawning from {filename}.template")
        template_string = f.read()
    return template_string


def file_from_string(filename, final_string):
    """
    Store a string to a template file.

    :param str filename: template filename
    :param str final_string: template file content
    """
    with open(filename, "w") as f:
        log.info(f"Creating the final {filename}")
        f.write(final_string)


###############################################################################
# MAJOR CONFIGURATION
###############################################################################


@error_context.context_aware
def configure_steps(params):
    """
    Configure the installation of a vm using a steps file.

    :param params: configuration to use
    :type params: {string, string}
    """
    error_context.context("Steps file setup")
    log.info(f"Preparing steps file for {params['main_vm']}")
    steps_string = string_from_template(params["steps"])
    vm_params = params.object_params(params["main_vm"])
    vm_nics = vm_params.objects("nics")
    for i, nic in enumerate(vm_nics):

        nic_params = vm_params.object_params(nic)
        ip = nic_params["ip"]
        mask = nic_params["netmask"]
        log.debug(f"Detected {nic} with ip {ip} and netmask {mask}")
        # uncomment sections responsible for the nic setup
        steps_string = steps_string.replace("# NIC%i: " % (i + 1), "")

        ip_keystrokes = convert_to_key_steps(ip)
        log.debug(f"Replacing # IP_KEYS{i + 1}\n with {ip_keystrokes}")
        steps_string = steps_string.replace("# IP_KEYS%i\n" % (i + 1), ip_keystrokes)
        if ip_keystrokes not in steps_string:
            log.warning(f"Could not insert ip_{nic} in the provided IP_KEYS{i + 1} field")

        mask_keystrokes = convert_to_key_steps(mask)
        log.debug(f"Replacing # NETMASK_KEYS{i + 1}\n with {mask_keystrokes}")
        steps_string = steps_string.replace("# NETMASK_KEYS%i\n" % (i + 1), mask_keystrokes)
        if mask_keystrokes not in steps_string:
            log.warning(f"Could not insert netmask_{nic} in the provided NETMASK_KEYS{i + 1} field")

    current_keystrokes = convert_to_key_steps(params["main_vm"])
    steps_string = steps_string.replace("# NAME_KEYS\n", current_keystrokes)
    current_keystrokes = convert_to_key_steps(params["password"])
    steps_string = steps_string.replace("# PASSWORD_KEYS\n", current_keystrokes)

    file_from_string(params["steps"], steps_string)
    log.info(f"Steps file for {params['main_vm']} ready to use")


@error_context.context_aware
def configure_unattended_kickstart(params):
    """
    Configure the installation of a vm using a kickstart file.

    :param params: configuration to use
    :type params: {string, string}

    .. note:: This approach is currently used for RHEL-based vms.
    """
    error_context.context("Unattended kickstart file setup")
    log.info(f"Preparing unattended file {params['unattended_file']} for {params['main_vm']}")
    ks_string = string_from_template(params["unattended_file"])
    vm_params = params.object_params(params["main_vm"])
    vm_nics = vm_params.objects("nics")

    for nic in vm_nics:
        nic_params = vm_params.object_params(nic)
        network_line = "network --device %s" % nic_params["mac"]
        if nic == params["internet_nic"]:
            network_line = "%s --bootproto=dhcp --activate" % network_line
        else:
            ip = nic_params["ip"]
            netmask = nic_params["netmask"]
            network_line = ("%s --bootproto=static --ip=%s --netmask=%s --bindto=mac "
                            "--activate --nodefroute" % (network_line, ip, netmask))
        log.debug(f"Adding line '{network_line}' to the unattended file")
        first_network_line = "network --hostname #VMNAME#"
        ks_string = re.sub(first_network_line,
                           "%s\n%s" % (first_network_line, network_line),
                           ks_string)

    ks_string = ks_string.replace("#VMNAME#", params["main_vm"])
    ks_string = ks_string.replace("#ROOTPW#", params["password"])

    file_from_string(params["unattended_file"], ks_string)
    log.info(f"Unattended file for {params['main_vm']} ready to use")


@error_context.context_aware
def configure_unattended_preseed(params):
    """
    Configure the installation of a vm using a preseed file.

    :param params: configuration to use
    :type params: {string, string}

    .. note:: This approach is currently used for Debian-based vms.
    """
    error_context.context("Unattended preseed file setup")
    log.info(f"Preparing unattended file {params['unattended_file']} for {params['main_vm']}")
    ps_string = string_from_template(params["unattended_file"])
    vm_params = params.object_params(params["main_vm"])
    vm_nics = vm_params.objects("nics")

    for i, nic in reversed(list(enumerate(vm_nics))):
        network_line = "network --device eth%i" % i
        if nic != params["internet_nic"]:
            ps_string = ps_string.replace("#NETIP#", vm_params.object_params(nic)["ip"])
            ps_string = ps_string.replace("#NETMASK#", vm_params.object_params(nic)["netmask"])
            ps_string = ps_string.replace("#GATEWAY#", vm_params.object_params(nic)["ip_provider"])

    ps_string = ps_string.replace("#VMNAME#", params["main_vm"])
    ps_string = ps_string.replace("#ROOTPW#", params["password"])

    file_from_string(params["unattended_file"], ps_string)
    log.info(f"Unattended file for {params['main_vm']} ready to use")


@error_context.context_aware
def configure_unattended_sif(params):
    """
    Configure the installation of a vm using a sif file.

    :param params: configuration to use
    :type params: {str, str}

    .. note:: This approach is currently used for Windows XP vms.
    """
    error_context.context("Unattended sif file setup")
    log.info(f"Preparing unattended file {params['unattended_file']} for {params['main_vm']}")
    sif_string = string_from_template(params["unattended_file"])
    vm_params = params.object_params(params["main_vm"])
    vm_nics = vm_params.objects("nics")

    for i, nic in reversed(list(enumerate(vm_nics))):
        nic_params = vm_params.object_params(nic)
        ip = nic_params["ip"]
        netmask = nic_params["netmask"]
        mac = nic_params["mac"]

        sif_string = re.sub(r"\[NetAdapters\]\n", "[NetAdapters]\n"
                            r"Adapter%02d = params.Adapter%02d\n" % (i, i),
                            sif_string)
        sif_string = re.sub(";nic names and macs here\n", ";nic names and macs here\n"
                            "[params.Adapter%02d]\nConnectionName=\"%s\"\n"
                            "netcardaddress = 0x%s\n" % (i, nic, mac.replace(":", "")),
                            sif_string)
        if re.search(r"\[params.MS_TCPIP\]", sif_string) is None:
            sif_string = re.sub("MS_TCPIP = params.MS_TCPIP\n",
                                "MS_TCPIP = params.MS_TCPIP\n[params.MS_TCPIP]\n"
                                "AdapterSections = params.MS_TCPIP.Adapter%02d\n" % i,
                                sif_string)
        else:
            sif_string = re.sub("AdapterSections = ",
                                "AdapterSections = params.MS_TCPIP.Adapter%02d," % i,
                                sif_string)

        if nic == params["internet_nic"]:
            sif_string = re.sub(";nic ip configurations here\n", ";nic ip configurations here\n"
                                "[params.MS_TCPIP.Adapter%02d]\nDHCP = Yes\n"
                                "SpecificTo = Adapter%02d\n" % (i, i),
                                sif_string)
        else:
            sif_string = re.sub(";nic ip configurations here\n", ";nic ip configurations here\n"
                                "[params.MS_TCPIP.Adapter%02d]\nDHCP = No\nIPAddress = %s\n"
                                "SpecificTo = Adapter%02d\nSubnetMask = %s\n" % (i, ip, i, netmask),
                                sif_string)

    sif_string = sif_string.replace("#VMNAME#", params["main_vm"])
    sif_string = sif_string.replace("#ROOTPW#", params["password"])

    file_from_string(params["unattended_file"], sif_string)
    log.info(f"Unattended file for {params['main_vm']} ready to use")


@error_context.context_aware
def configure_unattended_xml(params):
    """
    Configure the installation of a vm using an xml file.

    :param params: configuration to use
    :type params: {string, string}

    .. note:: This approach is currently used for Windows 7 vms.
    """
    error_context.context("Unattended xml file setup")
    log.info(f"Preparing unattended file {params['unattended_file']} for {params['main_vm']}")
    xml_string = string_from_template(params["unattended_file"])
    vm_params = params.object_params(params["main_vm"])
    vm_nics = vm_params.objects("nics")

    for i, nic in reversed(list(enumerate(vm_nics))):
        if nic == params["internet_nic"]:
            log.info(f"Only static IP configuration is included in the unattended xml "
                     f"file so the internet nic of {params['main_vm']} (DHCP) will be skipped")
        else:
            nic_params = vm_params.object_params(nic)
            ip = nic_params["ip"]
            netmask = nic_params["netmask"]
            # a bit artificial but we don't need more advanced functionality for now
            netmask_bits = {"255.0.0.0": "8",
                            "255.255.0.0": "16",
                            "255.255.255.0": "24",
                            "255.255.255.255": "32"}
            netmask_bit = netmask_bits[netmask]
            mac = nic_params["mac"]
            nic_str = ("                <Interface wcm:action=\"add\">\n"
                       "                    <Identifier>%s</Identifier>\n"
                       "                    <Ipv4Settings>\n"
                       "                        <DhcpEnabled>false</DhcpEnabled>\n"
                       "                        <Metric>10</Metric>\n"
                       "                        <RouterDiscoveryEnabled>false</RouterDiscoveryEnabled>\n"
                       "                    </Ipv4Settings>\n"
                       "                    <UnicastIpAddresses>\n"
                       "                        <IpAddress wcm:action=\"add\" wcm:keyValue=\"1\">%s/%s</IpAddress>\n"
                       "                    </UnicastIpAddresses>\n"
                       "                </Interface>\n" % (mac.replace(":", "-"), ip, netmask_bit))
            # this is for more flexible network configuration so should rather be used later on
            #if nic_params.get("ip_provider", None) is not None:
            #    gateway_str = ("                    <Routes>\n"
            #                   "                        <Route wcm:action=\"add\">\n"
            #                   "                            <Identifier>1</Identifier>\n"
            #                   "                            <Prefix>0.0.0.0/0</Prefix>\n"
            #                   "                            <Metric>10</Metric>\n"
            #                   "                            <NextHopAddress>%s</NextHopAddress>\n"
            #                   "                        </Route>\n"
            #                   "                    </Routes>\n" % nic_params["ip_provider"])
            #    nic_str = re.sub("</UnicastIpAddresses>\n", "</UnicastIpAddresses>\n%s" % gateway_str, nic_str)
            xml_string = re.sub("<Interfaces>\n", "<Interfaces>\n%s" % nic_str, xml_string)

    xml_string = xml_string.replace("#VMNAME#", params["main_vm"])
    xml_string = xml_string.replace("#ROOTPW#", params["password"])

    file_from_string(params["unattended_file"], xml_string)
    log.info(f"Unattended file for {params['main_vm']} ready to use")


###############################################################################
# TEST MAIN
###############################################################################


@error_context.context_aware
def run(test, params, env):
    """
    Main test run.

    :param test: test object
    :type test: :py:class:`avocado_vt.test.VirtTest`
    :param params: extended dictionary of parameters
    :type params: :py:class:`virttest.utils_params.Params`
    :param env: environment object
    :type env: :py:class:`virttest.utils_env.Env`
    """
    if params["configure_install"] == "steps":
        configure_steps(params)
    elif params["configure_install"] == "unattended_install":
        if params["unattended_file"].endswith(".ks"):
            configure_unattended_kickstart(params)
        elif params["unattended_file"].endswith(".preseed"):
            configure_unattended_preseed(params)
        elif params["unattended_file"].endswith(".sif"):
            configure_unattended_sif(params)
        elif params["unattended_file"].endswith(".xml"):
            configure_unattended_xml(params)
        else:
            raise exceptions.TestError("Unsupported unattended file format for %s" % params["unattended_file"])
    elif params["configure_install"] == "shared_gui_install":
        log.warning("A GUI installation does not need any preconfiguration.")
    elif params["configure_install"] == "stepmaker":
        log.warning("A stepmaker installation process cannot be preconfigured - you are supposed "
                    "to use it only to produce step files where no preconfiguration is necessary.")
    elif params["configure_install"] == "shared_multigui_generator":
        log.warning("A GUI installation development process cannot be preconfigured - you are supposed "
                    "to use it only to produce GUI tests where no preconfiguration is necessary.")
    else:
        raise exceptions.TestError("Unsupported installation method '%s' - must be one of "
                                   "'steps', 'stepmaker', 'unattended_install'" % params["configure_install"])
